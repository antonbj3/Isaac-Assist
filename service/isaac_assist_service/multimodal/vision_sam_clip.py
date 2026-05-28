"""Local SAM2 + CLIP vision provider — Gemini-quota-free fallback.

Mirrors the async surface of ``service.isaac_assist_service.chat.vision_gemini.GeminiVisionProvider``
so it can be slotted into the same call-sites (``_handle_add_vision_classifier_gate``,
``vision_detect_objects``, ``vision_bounding_boxes``, ``vision_analyze_scene``) without
changing the caller.

Algorithm
=========
1. ``SAM2AutomaticMaskGenerator`` proposes per-image segmentation masks.
2. Each mask's tight bbox → image crop.
3. CLIP zero-shot scores ``"a photo of {label}"`` for every requested label
   against each crop. Best label per mask is the assigned class.
4. Top-N crops by CLIP confidence are returned in the Gemini-shaped schema:
   ``[{"point": [y, x], "box_2d": [ymin, xmin, ymax, xmax], "label": ...,
   "confidence": ...}, ...]`` with coordinates normalised to 0-1000 (matches
   the Gemini contract — see ``chat/vision_gemini.py`` for the reference shape).

Wiring
======
- Lazily loads SAM2 + CLIP on first call so importing the module is free.
- Lazy load lets quota-free deployments avoid the ~1.5 s SAM2 init when no
  template hits the vision gate.
- Selected through ``_shared._get_vision_provider`` (provider-selection
  policy). See module docstring there.

Caveats
=======
- Requires ``torch``, ``sam2``, ``open_clip_torch``. All present in repo
  env (``vision_pilot.py`` exercises the same pair).
- ``vision_models/sam2.1_hiera_small.pt`` (184 MB) must be on disk; falls
  back to ``"no_detection"`` if missing.
- ``plan_trajectory`` is NOT implementable locally — it requires VLM
  reasoning. Falls through to a graceful-degradation string.
- The mask-generator is the heaviest path (~1-2 s/image on RTX 5070).
  Acceptable for vision-gate templates which fire once per scene.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paths + configuration
# ---------------------------------------------------------------------------

# Repo root inferred from this file: …/service/isaac_assist_service/multimodal/
_REPO_ROOT = Path(__file__).resolve().parents[3]
SAM_CHECKPOINT = _REPO_ROOT / "vision_models" / "sam2.1_hiera_small.pt"
SAM_CONFIG = "configs/sam2.1/sam2.1_hiera_s.yaml"  # bundled with sam2 pkg

# CLIP defaults — small + fast, runs comfortably on RTX 5070.
CLIP_MODEL = "ViT-B-32"
CLIP_PRETRAINED = "laion2b_s34b_b79k"


# ---------------------------------------------------------------------------
# Module-level singletons (lazy-loaded on first detect call)
# ---------------------------------------------------------------------------

_sam_predictor = None  # SAM2ImagePredictor
_sam_mask_generator = None  # SAM2AutomaticMaskGenerator
_clip_model = None
_clip_preprocess = None
_clip_tokenizer = None
_device = None
_load_lock = asyncio.Lock()


async def _ensure_loaded() -> Tuple[bool, Optional[str]]:
    """Idempotently load SAM2 + CLIP. Returns (ok, error_or_None)."""
    global _sam_predictor, _sam_mask_generator, _clip_model
    global _clip_preprocess, _clip_tokenizer, _device

    if _sam_predictor is not None and _clip_model is not None:
        return True, None

    async with _load_lock:
        # Re-check inside the lock — another coroutine may have loaded
        # while we were waiting.
        if _sam_predictor is not None and _clip_model is not None:
            return True, None

        if not SAM_CHECKPOINT.exists():
            return False, f"SAM2 checkpoint missing: {SAM_CHECKPOINT}"

        try:
            import torch  # noqa: F401
        except ImportError:
            return False, "torch not installed"

        try:
            from sam2.build_sam import build_sam2
            from sam2.sam2_image_predictor import SAM2ImagePredictor
            from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
        except ImportError as exc:
            return False, f"sam2 not installed: {exc}"

        try:
            import open_clip
        except ImportError as exc:
            return False, f"open_clip not installed: {exc}"

        import torch
        _device = "cuda" if torch.cuda.is_available() else "cpu"
        try:
            sam_model = build_sam2(SAM_CONFIG, str(SAM_CHECKPOINT), device=_device)
            _sam_predictor = SAM2ImagePredictor(sam_model)
            # Conservative automatic-mask settings — keep mask count
            # reasonable so CLIP scoring stays in the ~1 s budget.
            _sam_mask_generator = SAM2AutomaticMaskGenerator(
                model=sam_model,
                points_per_side=16,
                pred_iou_thresh=0.7,
                stability_score_thresh=0.85,
                min_mask_region_area=200,
            )
        except Exception as exc:  # noqa: BLE001
            return False, f"SAM2 init failed: {type(exc).__name__}: {exc}"

        try:
            clip_model, _, clip_preprocess = open_clip.create_model_and_transforms(
                CLIP_MODEL, pretrained=CLIP_PRETRAINED
            )
            clip_model = clip_model.to(_device).eval()
            _clip_model = clip_model
            _clip_preprocess = clip_preprocess
            _clip_tokenizer = open_clip.get_tokenizer(CLIP_MODEL)
        except Exception as exc:  # noqa: BLE001
            return False, f"CLIP init failed: {type(exc).__name__}: {exc}"

        logger.info(
            "SAM+CLIP vision provider loaded on %s (SAM2=%s, CLIP=%s/%s)",
            _device, SAM_CHECKPOINT.name, CLIP_MODEL, CLIP_PRETRAINED,
        )
        return True, None


# ---------------------------------------------------------------------------
# Image / coordinate helpers
# ---------------------------------------------------------------------------

def _decode_image(image_bytes: bytes):
    """Decode raw image bytes to a numpy HxWx3 uint8 RGB array."""
    import numpy as np
    from PIL import Image
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return np.array(img)


def _mask_to_bbox(mask):
    """Return tight ``[x1, y1, x2, y2]`` pixel bbox of a binary mask, or None if empty."""
    import numpy as np
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def _mask_centroid(mask) -> Optional[Tuple[float, float]]:
    """Return pixel-space centroid ``(x_mean, y_mean)`` of binary mask, or None."""
    import numpy as np
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    return (float(xs.mean()), float(ys.mean()))


def _pixel_to_normalized_yx(px_x: float, px_y: float, w: int, h: int) -> List[int]:
    """Convert pixel (x, y) to Gemini-shaped ``[y, x]`` normalised to 0-1000."""
    nx = int(round(px_x / max(1, w) * 1000))
    ny = int(round(px_y / max(1, h) * 1000))
    return [max(0, min(1000, ny)), max(0, min(1000, nx))]


def _pixel_box_to_normalized(box: List[float], w: int, h: int) -> List[int]:
    """Convert pixel ``[x1, y1, x2, y2]`` to Gemini-shaped ``[ymin, xmin, ymax, xmax]`` 0-1000."""
    x1, y1, x2, y2 = box
    return [
        max(0, min(1000, int(round(y1 / max(1, h) * 1000)))),
        max(0, min(1000, int(round(x1 / max(1, w) * 1000)))),
        max(0, min(1000, int(round(y2 / max(1, h) * 1000)))),
        max(0, min(1000, int(round(x2 / max(1, w) * 1000)))),
    ]


def _score_crop(crop, labels: List[str]) -> List[float]:
    """Return CLIP softmax probabilities of ``crop`` against each label.

    Crops smaller than 8×8 px return uniform probabilities (signal is noise).
    """
    import numpy as np
    import torch
    from PIL import Image

    if crop.size == 0 or crop.shape[0] < 8 or crop.shape[1] < 8:
        n = len(labels)
        return [1.0 / max(1, n)] * n

    pil = Image.fromarray(crop)
    img_t = _clip_preprocess(pil).unsqueeze(0).to(_device)
    prompts = [f"a photo of {lbl}" for lbl in labels]
    text_t = _clip_tokenizer(prompts).to(_device)

    with torch.no_grad():
        img_f = _clip_model.encode_image(img_t)
        text_f = _clip_model.encode_text(text_t)
        img_f = img_f / img_f.norm(dim=-1, keepdim=True)
        text_f = text_f / text_f.norm(dim=-1, keepdim=True)
        sim = (img_f @ text_f.T).softmax(dim=-1)[0]
    return [float(s) for s in sim.cpu().numpy()]


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class SamClipVisionProvider:
    """Local SAM2 + CLIP vision provider matching the Gemini async surface.

    Methods mirror ``chat.vision_gemini.GeminiVisionProvider``:
    ``detect_objects``, ``detect_bounding_boxes``, ``analyze_scene``,
    ``plan_trajectory``. ``plan_trajectory`` is a graceful-degradation
    stub — local stack can't replace VLM trajectory reasoning.
    """

    model = "sam2-hiera-s+clip-vit-b32-local"

    def __init__(self) -> None:
        """No-op constructor; expensive setup is deferred to ``_ensure_loaded``."""
        pass

    # ── Gemini-shaped methods ──────────────────────────────────────────────

    async def detect_objects(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        labels: Optional[List[str]] = None,
        max_objects: int = 10,
    ) -> List[Dict[str, Any]]:
        """Return ``[{"point": [y, x], "label": str, "confidence": float, "box_2d": [...]}, ...]``.

        ``point`` and ``box_2d`` are normalised to 0-1000 per the Gemini contract.
        """
        ok, err = await _ensure_loaded()
        if not ok:
            logger.warning("SAM+CLIP unavailable: %s", err)
            return []
        if not labels:
            # Without a label set CLIP has nothing to score against.
            # Skip rather than guess — caller may have intended detect-only.
            logger.info("SAM+CLIP detect_objects: no labels given, returning empty")
            return []

        try:
            img = _decode_image(image_bytes)
        except Exception as exc:  # noqa: BLE001
            logger.error("SAM+CLIP image decode failed: %s", exc)
            return []

        H, W = img.shape[:2]
        masks = await asyncio.to_thread(_sam_mask_generator.generate, img)
        if not masks:
            return []

        # Score every mask region with CLIP, pick top-N by best-label-conf.
        scored: List[Tuple[float, int, str, List[int]]] = []
        # (confidence, mask_idx, label, bbox_pixel)
        for i, m in enumerate(masks):
            seg = m.get("segmentation")
            if seg is None:
                continue
            bbox_px = _mask_to_bbox(seg)
            if bbox_px is None:
                continue
            x1, y1, x2, y2 = bbox_px
            if x2 - x1 < 4 or y2 - y1 < 4:
                continue
            crop = img[y1:y2 + 1, x1:x2 + 1]
            probs = _score_crop(crop, labels)
            best_j = max(range(len(labels)), key=lambda j: probs[j])
            scored.append((probs[best_j], i, labels[best_j], bbox_px))

        scored.sort(key=lambda t: t[0], reverse=True)
        top = scored[: max(1, max_objects)]

        out: List[Dict[str, Any]] = []
        for conf, mi, label, bbox_px in top:
            seg = masks[mi].get("segmentation")
            cent = _mask_centroid(seg) if seg is not None else None
            if cent is None:
                cent = ((bbox_px[0] + bbox_px[2]) / 2.0, (bbox_px[1] + bbox_px[3]) / 2.0)
            out.append({
                "point": _pixel_to_normalized_yx(cent[0], cent[1], W, H),
                "label": label,
                "confidence": round(conf, 3),
                "box_2d": _pixel_box_to_normalized(bbox_px, W, H),
            })
        return out

    async def detect_bounding_boxes(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        max_objects: int = 25,
    ) -> List[Dict[str, Any]]:
        """Return ``[{"box_2d": [ymin, xmin, ymax, xmax], "label": str}, ...]``.

        Without external labels we tag each mask "object_N" — caller can
        post-filter. Matches the Gemini contract field-names.
        """
        ok, err = await _ensure_loaded()
        if not ok:
            logger.warning("SAM+CLIP unavailable: %s", err)
            return []

        try:
            img = _decode_image(image_bytes)
        except Exception as exc:  # noqa: BLE001
            logger.error("SAM+CLIP image decode failed: %s", exc)
            return []

        H, W = img.shape[:2]
        masks = await asyncio.to_thread(_sam_mask_generator.generate, img)
        # Sort by mask area desc (largest first), cap by max_objects.
        masks.sort(key=lambda m: m.get("area", 0), reverse=True)
        out: List[Dict[str, Any]] = []
        for i, m in enumerate(masks[: max(1, max_objects)]):
            seg = m.get("segmentation")
            if seg is None:
                continue
            bbox_px = _mask_to_bbox(seg)
            if bbox_px is None:
                continue
            out.append({
                "box_2d": _pixel_box_to_normalized(bbox_px, W, H),
                "label": f"object_{i}",
            })
        return out

    async def analyze_scene(
        self,
        image_bytes: bytes,
        question: str,
        mime_type: str = "image/png",
    ) -> str:
        """Return a short SAM-counts-based text summary (no VLM reasoning).

        Local stack cannot match Gemini free-form spatial reasoning.
        This emits a deterministic count-based summary as the honest fallback.
        """
        ok, err = await _ensure_loaded()
        if not ok:
            return f"Local SAM+CLIP analyze_scene unavailable: {err}"
        try:
            img = _decode_image(image_bytes)
        except Exception as exc:  # noqa: BLE001
            return f"Local SAM+CLIP image decode failed: {exc}"
        masks = await asyncio.to_thread(_sam_mask_generator.generate, img)
        H, W = img.shape[:2]
        return (
            f"SAM2 found {len(masks)} distinct segments in a {W}x{H} image. "
            f"Local provider lacks scene-reasoning capacity; for free-form "
            f"narrative re-run with Gemini provider (set IA_VISION_PROVIDER=gemini)."
        )

    async def plan_trajectory(
        self,
        image_bytes: bytes,
        instruction: str,
        num_points: int = 15,
        mime_type: str = "image/png",
    ) -> List[Dict[str, Any]]:
        """Local stack cannot replace VLM trajectory reasoning — returns ``[]``.

        Caller should treat empty-list as "no_detection" and fall through.
        """
        logger.info(
            "SAM+CLIP plan_trajectory: not implementable locally "
            "(instruction=%r); returning empty",
            instruction[:80],
        )
        return []
