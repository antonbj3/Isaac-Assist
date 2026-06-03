"""Vision-pilot: SAM2 + CLIP analysis on canonical templates.

Two modes:

  (default — single-frame) For each template:
    1. observe_one() — build + run sim to completion (existing scene_observer)
    2. Capture viewport PNG once
    3. For each prim with vision_input bbox: SAM2 mask + CLIP zero-shot label
    4. Output per-prim IoU(bbox_proj, bbox_sam), CLIP label, flags

  (--video-track) For each template:
    1. Build scene via execute_template_canonical (NO scene_observer run)
    2. Start sim timeline.play()
    3. Loop n_frames @ hz Hz:
         step ~1/hz seconds of sim
         capture viewport PNG (saved as JPG to frames/<name>/000000.jpg ...)
         read USD per-cube positions + camera view/projection matrices
    4. Stop sim
    5. Run SAM2VideoPredictor on frame sequence:
         init_state on frame 0 (saved JPG dir)
         add_new_points_or_box per cube using bbox from USD-projected position
         propagate_in_video → per-frame masks
    6. Per cube + frame: SAM-centroid (pixel) vs USD-projected-centroid (pixel)
    7. PNG overlay: red=USD trajectory, green=SAM trajectory, blue=frame markers
    8. JSON metrics: mean/max pixel-distance, tracking-success-ratio

Usage:
    python scripts/review/vision_pilot.py CP-77 CP-09 CP-13 CP-14
    python scripts/review/vision_pilot.py --video-track CP-09 --n-frames 60 --hz 10
"""
import argparse, asyncio, base64, json, os, shutil, sys, time, urllib.request
from pathlib import Path

REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/"scripts"))

KIT_CAPTURE_URL = "http://127.0.0.1:8001/capture"
OUT_DIR = REPO/"workspace/qa_runs/vision_pilot"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FRAMES_ROOT = OUT_DIR/"_frames"
FRAMES_ROOT.mkdir(parents=True, exist_ok=True)

SAM_CHECKPOINT = REPO/"vision_models/sam2.1_hiera_small.pt"
SAM_CONFIG = "configs/sam2.1/sam2.1_hiera_s.yaml"

CLIP_LABELS = ["a cube", "a flat plate", "a cylinder", "something else"]
# 2026-05-21: tightened from 8 labels to 4 — previous set gave uniform softmax
# (all ~0.125 conf) since labels were too varied. 4-set should distinguish
# wrong_object_type cases (cube vs plate) with stronger signal.


# -----------------------------------------------------------------------------
# COMMON helpers
# -----------------------------------------------------------------------------

def capture_viewport_png(out_path: Path, max_dim: int = 1280) -> bool:
    """Capture Kit viewport via HTTP /capture endpoint. Returns True on success."""
    try:
        url = f"{KIT_CAPTURE_URL}?max_dim={max_dim}"
        with urllib.request.urlopen(url, timeout=30) as r:
            if r.status != 200: return False
            d = json.loads(r.read())
        b64 = d.get("image_b64")
        if not b64: return False
        out_path.write_bytes(base64.b64decode(b64))
        return True
    except Exception as e:
        print(f"  capture failed: {e}")
        return False


def iou_xyxy(a, b):
    """IoU of two [x1,y1,x2,y2] boxes."""
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
    x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
    if x2 <= x1 or y2 <= y1: return 0.0
    inter = (x2-x1)*(y2-y1)
    ua = (a[2]-a[0])*(a[3]-a[1]); ub = (b[2]-b[0])*(b[3]-b[1])
    return inter / max(1e-9, ua + ub - inter)


def mask_to_bbox(mask) -> list:
    """Tight bbox of a binary mask. Returns [x1,y1,x2,y2] or None if empty."""
    import numpy as np
    ys, xs = np.where(mask)
    if len(xs) == 0: return None
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def mask_centroid(mask):
    """Pixel-space centroid (x_mean, y_mean) of binary mask. None if empty."""
    import numpy as np
    ys, xs = np.where(mask)
    if len(xs) == 0: return None
    return (float(xs.mean()), float(ys.mean()))


# -----------------------------------------------------------------------------
# SINGLE-FRAME mode (preserved for backward-compat)
# -----------------------------------------------------------------------------

def analyze_one(name, observed_rec, sam_predictor, clip_model, clip_tokenizer, device):
    """Analyze one template's PNG + vision_input against SAM2 + CLIP."""
    import numpy as np
    from PIL import Image
    import torch

    png_path = OUT_DIR/f"{name}.png"
    if not capture_viewport_png(png_path):
        return {"error": "capture_failed"}

    vi = (observed_rec.get('engine_data') or {}).get('vision_input') or {}
    vp = vi.get('__viewport__') or {}
    if not vi or 'error' in vi.get('__error__', ''):
        return {"error": f"vision_input missing or errored: {vi.get('__error__')}"}

    # Load image
    img = np.array(Image.open(png_path).convert("RGB"))
    H, W = img.shape[:2]
    # Note: viewport returned via /capture may have been resized vs Kit's
    # reported resolution. Scale bbox coords by ratio if mismatch.
    rw = W / max(1, vp.get('width', W))
    rh = H / max(1, vp.get('height', H))

    sam_predictor.set_image(img)
    results = {}
    for prim_path, info in vi.items():
        if prim_path.startswith('__'): continue  # __viewport__, __error__
        bbox = info.get('bbox_2d')
        if not bbox: continue
        # Scale to actual PNG size
        bbox_s = [bbox[0]*rw, bbox[1]*rh, bbox[2]*rw, bbox[3]*rh]
        # Skip degenerate boxes
        if bbox_s[2]-bbox_s[0] < 5 or bbox_s[3]-bbox_s[1] < 5:
            results[prim_path] = {"flag": "bbox_too_small", "bbox_proj": bbox_s}
            continue
        try:
            masks, scores, _ = sam_predictor.predict(
                box=np.array(bbox_s, dtype=np.float32),
                multimask_output=True,
            )
            # Pick best-scoring mask
            best_i = int(np.argmax(scores))
            mask = masks[best_i]
            mask_bbox = mask_to_bbox(mask)
            if mask_bbox is None:
                results[prim_path] = {"iou": 0.0, "flag": "sam_returned_empty"}
                continue
            iou = iou_xyxy(bbox_s, mask_bbox)
            mask_area = int(mask.sum())
            # CLIP zero-shot on mask region
            x1, y1, x2, y2 = mask_bbox
            crop = img[y1:y2+1, x1:x2+1]
            clip_label = None; clip_conf = None
            if crop.size > 0 and crop.shape[0] >= 8 and crop.shape[1] >= 8:
                pil_crop = Image.fromarray(crop)
                with torch.no_grad():
                    # open_clip uses its own preprocess
                    img_t = clip_model.preprocess(pil_crop).unsqueeze(0).to(device)
                    text_t = clip_tokenizer(CLIP_LABELS).to(device)
                    img_f = clip_model.encode_image(img_t)
                    text_f = clip_model.encode_text(text_t)
                    img_f /= img_f.norm(dim=-1, keepdim=True)
                    text_f /= text_f.norm(dim=-1, keepdim=True)
                    sim = (img_f @ text_f.T).softmax(dim=-1)[0]
                    best = int(sim.argmax())
                    clip_label = CLIP_LABELS[best]
                    clip_conf = float(sim[best])
            r = {
                "bbox_proj": [round(x, 1) for x in bbox_s],
                "bbox_sam": mask_bbox,
                "iou": round(iou, 3),
                "mask_area": mask_area,
                "sam_score": round(float(scores[best_i]), 3),
                "clip_label": clip_label,
                "clip_conf": round(clip_conf, 3) if clip_conf else None,
                "expected_kind": info.get('expected_kind'),
            }
            # Flag suspicious cases
            flags = []
            if iou < 0.1: flags.append("render_decoupled")
            if (info.get('expected_kind') == 'cube' and clip_label
                and 'cube' not in clip_label.lower() and clip_conf and clip_conf > 0.5):
                flags.append("wrong_object_type_visible")
            if flags: r['flags'] = flags
            results[prim_path] = r
        except Exception as e:
            results[prim_path] = {"error": str(e)[:200]}
    return {"per_prim": results, "image_size": [W, H]}


# -----------------------------------------------------------------------------
# VIDEO-TRACK mode
# -----------------------------------------------------------------------------

# Kit-side: start sim (timeline.play). Returns viewport+camera info.
START_SIM_CODE = r"""
import omni.usd, omni.timeline, omni.kit.app
from pxr import Sdf, UsdGeom
import json
stage = omni.usd.get_context().get_stage()
tl = omni.timeline.get_timeline_interface()
tl.set_current_time(0.0)
tl.set_end_time(max(tl.get_end_time(), 600.0))
tl.play()
# Make sure first physics tick happens
app = omni.kit.app.get_app()
for _ in range(3): app.update()
print("SIM_STARTED")
"""

# Kit-side: stop sim
STOP_SIM_CODE = r"""
import omni.timeline
omni.timeline.get_timeline_interface().stop()
print("SIM_STOPPED")
"""

# Kit-side: step sim by N updates (~0.1s for 60Hz target if N=6) + dump per-cube
# world positions and camera matrices. Returns JSON between markers.
STEP_AND_SAMPLE_CODE_TPL = r"""
import omni.usd, omni.kit.app, omni.timeline
from pxr import Sdf, UsdGeom, Gf
import json, time
stage = omni.usd.get_context().get_stage()
app = omni.kit.app.get_app()
N_UPDATES = {n_updates}
CUBE_PATHS = {cube_paths!r}

# Step sim
for _ in range(N_UPDATES):
    app.update()
t = float(omni.timeline.get_timeline_interface().get_current_time())

# Read cube positions
out = {{"t": t, "cubes": {{}}, "camera": {{}}, "viewport": {{}}}}
for cp in CUBE_PATHS:
    try:
        pr = stage.GetPrimAtPath(Sdf.Path(cp))
        if not (pr and pr.IsValid()):
            out["cubes"][cp] = None
            continue
        m = UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(0)
        tr = m.ExtractTranslation()
        bb = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_]).ComputeWorldBound(pr).ComputeAlignedRange()
        out["cubes"][cp] = {{
            "pos": [float(tr[0]), float(tr[1]), float(tr[2])],
            "bbox_world_min": [float(bb.GetMin()[0]), float(bb.GetMin()[1]), float(bb.GetMin()[2])],
            "bbox_world_max": [float(bb.GetMax()[0]), float(bb.GetMax()[1]), float(bb.GetMax()[2])],
        }}
    except Exception as e:
        out["cubes"][cp] = {{"error": str(e)[:120]}}

# Camera matrices (4x4 view + 4x4 projection) and viewport size
try:
    import omni.kit.viewport.utility as _vp_util
    _vp = _vp_util.get_active_viewport()
    if _vp:
        _cam_path = str(_vp.camera_path)
        _cam_prim = stage.GetPrimAtPath(Sdf.Path(_cam_path))
        _cam = UsdGeom.Camera(_cam_prim)
        _gf_cam = _cam.GetCamera(0)
        _view = _gf_cam.frustum.ComputeViewMatrix()
        _proj = _gf_cam.frustum.ComputeProjectionMatrix()
        try: _w, _h = _vp.resolution
        except: _w, _h = 1280, 720
        out["camera"] = {{
            "view": [[float(_view[i][j]) for j in range(4)] for i in range(4)],
            "proj": [[float(_proj[i][j]) for j in range(4)] for i in range(4)],
            "camera_path": _cam_path,
        }}
        out["viewport"] = {{"width": int(_w), "height": int(_h)}}
except Exception as e:
    out["camera"] = {{"error": str(e)[:200]}}

print("SAMPLE_BEGIN")
print(json.dumps(out))
print("SAMPLE_END")
"""


def project_world_to_pixel(p_world, view_mat, proj_mat, vp_w, vp_h):
    """Project a 3D world-space point to (px, py) using USD row-vector convention.

    view_mat / proj_mat are 4x4 lists-of-lists. Returns (px, py) or None if behind cam.
    """
    import numpy as np
    V = np.array(view_mat, dtype=np.float64)
    P = np.array(proj_mat, dtype=np.float64)
    v = np.array([p_world[0], p_world[1], p_world[2], 1.0], dtype=np.float64)
    # USD/Gf is row-major; mimic _v * _view * _proj used in scene_observer
    vc = v @ V
    cc = vc @ P
    if cc[3] == 0: return None
    nx = cc[0] / cc[3]; ny = cc[1] / cc[3]; nz = cc[2] / cc[3]
    if nz >= 1.0:  # behind camera / outside frustum far
        return None
    px = (nx + 1) * 0.5 * vp_w
    py = (1 - ny) * 0.5 * vp_h
    return (float(px), float(py))


def project_aabb_to_pixel_bbox(bbox_min, bbox_max, view_mat, proj_mat, vp_w, vp_h):
    """Project 8 corners of an AABB and return tight [x1,y1,x2,y2] pixel bbox, clamped."""
    corners = []
    for i in range(8):
        c = (bbox_min[0] + (i & 1) * (bbox_max[0] - bbox_min[0]),
             bbox_min[1] + ((i >> 1) & 1) * (bbox_max[1] - bbox_min[1]),
             bbox_min[2] + ((i >> 2) & 1) * (bbox_max[2] - bbox_min[2]))
        p = project_world_to_pixel(c, view_mat, proj_mat, vp_w, vp_h)
        if p is not None: corners.append(p)
    if not corners: return None
    xs = [c[0] for c in corners]; ys = [c[1] for c in corners]
    bb = [max(0, min(xs)), max(0, min(ys)),
          min(vp_w, max(xs)), min(vp_h, max(ys))]
    if bb[2] <= bb[0] or bb[3] <= bb[1]: return None
    return bb


async def step_and_sample(kit_tools, cube_paths, n_updates):
    """Step sim ~n_updates frames and return dict {t, cubes, camera, viewport}."""
    code = STEP_AND_SAMPLE_CODE_TPL.format(n_updates=n_updates, cube_paths=cube_paths)
    r = await kit_tools.exec_sync(code, timeout=60)
    out = (r.get("output") or "").strip()
    b = out.find("SAMPLE_BEGIN"); e = out.find("SAMPLE_END")
    if b < 0 or e < 0:
        return {"error": f"sample parse fail: {out[:200]}"}
    payload = out[b + len("SAMPLE_BEGIN"):e].strip()
    try: return json.loads(payload)
    except Exception as ex: return {"error": f"json: {ex}; raw={payload[:200]}"}


async def track_cube_video(template_name, n_frames, hz, kit_tools, device):
    """Capture n_frames @ hz Hz, save JPGs, run SAM2 video tracking, cross-check vs USD.

    Returns dict with per-cube time-series + metrics. Also writes:
      - JPG frames to FRAMES_ROOT/<template>/{000000.jpg, ...}
      - PNG trajectory-overlay to OUT_DIR/<template>_trajectory.png
      - JSON metrics to OUT_DIR/<template>_track_metrics.json
    """
    import numpy as np
    from PIL import Image
    from sam2.build_sam import build_sam2_video_predictor

    # -- Phase 1: build scene
    tpl_path = REPO/f"workspace/templates/{template_name}.json"
    if not tpl_path.exists():
        return {"error": f"template not found: {template_name}"}
    tpl = json.loads(tpl_path.read_text())
    sa = tpl.get("simulate_args") or {}
    cube_paths = sa.get("cube_paths") or ([sa.get("cube_path")] if sa.get("cube_path") else [])
    if not cube_paths:
        return {"error": "no cube_paths in simulate_args"}
    # NOTE: cube_paths from simulate_args is often only the primary cube. After
    # build we discover all cube-named RigidBodyAPI prims so multi-cube templates
    # (e.g. CP-09 with Cube_1..Cube_5 in /World) are tracked in full.

    from service.isaac_assist_service.chat.canonical_instantiator import (
        execute_template_canonical, settle_after_canonical,
    )
    # fresh stage
    await kit_tools.exec_sync(
        "import omni.usd\n"
        "ctx=omni.usd.get_context()\n"
        "ctx.new_stage()\n"
        "stage=ctx.get_stage()\n"
        "from pxr import UsdGeom\n"
        "UsdGeom.Xform.Define(stage,'/World')\n", timeout=20)
    print(f"  build scene...", flush=True)
    try:
        b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
        if not b.get("instantiated"):
            return {"error": f"BUILD_FAIL: {b.get('errors')[:2]}"}
    except Exception as e:
        return {"error": f"BUILD_EXC: {type(e).__name__}: {e}"}
    try: await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
    except: pass

    # -- Phase 1b: discover additional cube prims (e.g. CP-09 has Cube_1..Cube_5)
    DISCOVER_CUBES_CODE = r"""
import omni.usd, json
from pxr import UsdPhysics, Sdf
stage = omni.usd.get_context().get_stage()
out = []
try:
    for prim in stage.Traverse():
        pth = str(prim.GetPath())
        if not pth.startswith('/World/'): continue
        if 'cube' not in pth.lower(): continue
        if not prim.HasAPI(UsdPhysics.RigidBodyAPI): continue
        out.append(pth)
except Exception as _e: pass
print("CUBES_BEGIN")
print(json.dumps(out))
print("CUBES_END")
"""
    try:
        rr = await kit_tools.exec_sync(DISCOVER_CUBES_CODE, timeout=20)
        oo = (rr.get("output") or "").strip()
        b = oo.find("CUBES_BEGIN"); e = oo.find("CUBES_END")
        if b >= 0 and e >= 0:
            discovered = json.loads(oo[b + len("CUBES_BEGIN"):e].strip())
            extra = [c for c in discovered if c not in cube_paths]
            if extra:
                print(f"  discovered {len(extra)} extra cubes: {extra[:5]}{'...' if len(extra)>5 else ''}", flush=True)
                cube_paths = sorted(set(cube_paths + discovered))
    except Exception as _e:
        print(f"  cube discovery failed (using simulate_args only): {_e}", flush=True)

    # -- Phase 2: prepare frame dir
    frame_dir = FRAMES_ROOT/template_name
    if frame_dir.exists(): shutil.rmtree(frame_dir)
    frame_dir.mkdir(parents=True, exist_ok=True)

    # -- Phase 3: start sim & capture frames
    print(f"  start sim, capture {n_frames} frames @ {hz}Hz...", flush=True)
    await kit_tools.exec_sync(START_SIM_CODE, timeout=20)

    # Per-frame USD samples
    usd_samples = []  # list of dicts {t, cubes, camera, viewport}
    # ~60Hz Kit physics, hz=10 Hz capture → ~6 updates per capture
    # Adjust by clock-rate; assume Kit's app.update() ~ 1/60s
    updates_per_capture = max(1, int(round(60.0 / hz)))

    # capture frame 0 with NO prior step (immediate)
    sample0 = await step_and_sample(kit_tools, cube_paths, n_updates=2)
    usd_samples.append(sample0)
    png_path = frame_dir/f"{0:06d}.jpg"
    # SAM2 video predictor wants JPG sequence — capture PNG then convert
    tmp_png = frame_dir/f"_{0:06d}.png"
    if not capture_viewport_png(tmp_png):
        await kit_tools.exec_sync(STOP_SIM_CODE, timeout=10)
        return {"error": "frame 0 capture failed"}
    Image.open(tmp_png).convert("RGB").save(png_path, "JPEG", quality=90)
    tmp_png.unlink(missing_ok=True)

    n_capture_fail = 0
    for fi in range(1, n_frames):
        s = await step_and_sample(kit_tools, cube_paths, n_updates=updates_per_capture)
        usd_samples.append(s)
        tmp_png = frame_dir/f"_{fi:06d}.png"
        png_path = frame_dir/f"{fi:06d}.jpg"
        if not capture_viewport_png(tmp_png):
            n_capture_fail += 1
            # Synthesize a black frame so SAM2 indexing stays aligned
            arr = np.zeros((720, 1280, 3), dtype=np.uint8)
            Image.fromarray(arr).save(png_path, "JPEG", quality=90)
        else:
            Image.open(tmp_png).convert("RGB").save(png_path, "JPEG", quality=90)
            tmp_png.unlink(missing_ok=True)
        if fi % 10 == 0:
            print(f"    captured {fi}/{n_frames} (fail={n_capture_fail})", flush=True)

    await kit_tools.exec_sync(STOP_SIM_CODE, timeout=10)
    print(f"  captured {n_frames} frames, fail={n_capture_fail}", flush=True)

    # -- Phase 4: validate samples + build initial bboxes from frame 0
    s0 = usd_samples[0]
    if "error" in s0: return {"error": f"frame0 sample error: {s0['error']}"}
    cam = s0.get("camera") or {}
    vp = s0.get("viewport") or {}
    if "view" not in cam or "proj" not in cam:
        return {"error": f"no camera matrices: {cam}"}
    view = cam["view"]; proj = cam["proj"]
    vpw = vp.get("width", 1280); vph = vp.get("height", 720)

    cube_init_bboxes = {}  # path -> [x1,y1,x2,y2]
    valid_cube_paths = []
    for cp in cube_paths:
        ci = (s0.get("cubes") or {}).get(cp)
        if not ci or "error" in (ci or {}):
            print(f"    skip {cp}: no USD bbox (error={ci.get('error') if ci else 'missing'})")
            continue
        bb = project_aabb_to_pixel_bbox(ci["bbox_world_min"], ci["bbox_world_max"], view, proj, vpw, vph)
        if bb is None:
            print(f"    skip {cp}: bbox off-screen at frame 0")
            continue
        if bb[2]-bb[0] < 4 or bb[3]-bb[1] < 4:
            print(f"    skip {cp}: bbox degenerate at frame 0: {bb}")
            continue
        cube_init_bboxes[cp] = bb
        valid_cube_paths.append(cp)
    if not valid_cube_paths:
        return {"error": "no cubes had valid bbox in frame 0"}
    print(f"  initial bbox for {len(valid_cube_paths)} cubes", flush=True)

    # Check first JPG's actual size, may be resized vs Kit's reported vp
    img0 = np.array(Image.open(frame_dir/"000000.jpg").convert("RGB"))
    Himg, Wimg = img0.shape[:2]
    rw = Wimg / max(1, vpw); rh = Himg / max(1, vph)
    # Scale initial bboxes to actual image size
    for cp in cube_init_bboxes:
        b = cube_init_bboxes[cp]
        cube_init_bboxes[cp] = [b[0]*rw, b[1]*rh, b[2]*rw, b[3]*rh]

    # -- Phase 5: SAM2 video tracking
    print(f"  load SAM2VideoPredictor on {device}...", flush=True)
    import torch
    sam_video = build_sam2_video_predictor(SAM_CONFIG, str(SAM_CHECKPOINT), device=device)

    with torch.inference_mode(), torch.autocast(device, dtype=torch.bfloat16):
        inference_state = sam_video.init_state(video_path=str(frame_dir))
        # Add bbox prompt for each cube as separate object
        cube_obj_ids = {}  # path -> obj_id
        for i, (cp, bb) in enumerate(cube_init_bboxes.items()):
            obj_id = i + 1
            cube_obj_ids[cp] = obj_id
            sam_video.add_new_points_or_box(
                inference_state=inference_state,
                frame_idx=0,
                obj_id=obj_id,
                box=np.array(bb, dtype=np.float32),
            )
        # propagate forward through video
        per_frame_masks = {}  # frame_idx -> {obj_id: mask (HxW bool)}
        for out_frame_idx, out_obj_ids, out_mask_logits in sam_video.propagate_in_video(inference_state):
            per_frame_masks[out_frame_idx] = {}
            for j, obj_id in enumerate(out_obj_ids):
                mask = (out_mask_logits[j] > 0.0).cpu().numpy()
                if mask.ndim == 3: mask = mask[0]
                per_frame_masks[out_frame_idx][int(obj_id)] = mask
    print(f"  SAM2 tracked {len(per_frame_masks)} frames", flush=True)

    # -- Phase 6: build per-cube time-series + USD-projection cross-check
    id_to_path = {v: k for k, v in cube_obj_ids.items()}
    per_cube_series = {cp: [] for cp in cube_init_bboxes}
    pixel_dists = {cp: [] for cp in cube_init_bboxes}
    occluded_counts = {cp: 0 for cp in cube_init_bboxes}

    for fi in range(len(usd_samples)):
        s = usd_samples[fi]
        if "error" in s: continue
        cam_f = s.get("camera") or {}
        vp_f = s.get("viewport") or {}
        view_f = cam_f.get("view", view)
        proj_f = cam_f.get("proj", proj)
        vpw_f = vp_f.get("width", vpw); vph_f = vp_f.get("height", vph)
        rwf = Wimg / max(1, vpw_f); rhf = Himg / max(1, vph_f)
        t_ms = round(s.get("t", fi/hz) * 1000.0, 1)

        frame_masks = per_frame_masks.get(fi, {})
        for cp in cube_init_bboxes:
            obj_id = cube_obj_ids[cp]
            mask = frame_masks.get(obj_id)
            sam_centroid = None; mask_area = 0; occluded = True
            if mask is not None:
                ma = int(mask.sum())
                if ma > 0:
                    sam_centroid = mask_centroid(mask)
                    mask_area = ma
                    occluded = False
            if occluded:
                occluded_counts[cp] += 1
            # USD-projected centroid
            usd_centroid_px = None
            ci = (s.get("cubes") or {}).get(cp)
            if ci and "pos" in ci:
                p_px = project_world_to_pixel(ci["pos"], view_f, proj_f, vpw_f, vph_f)
                if p_px is not None:
                    usd_centroid_px = (p_px[0]*rwf, p_px[1]*rhf)
            # pixel distance
            dist_px = None
            if sam_centroid is not None and usd_centroid_px is not None:
                dx = sam_centroid[0] - usd_centroid_px[0]
                dy = sam_centroid[1] - usd_centroid_px[1]
                dist_px = float((dx*dx + dy*dy) ** 0.5)
                pixel_dists[cp].append(dist_px)
            entry = {
                "frame_idx": fi,
                "t_ms": t_ms,
                "sam_centroid_px": (round(sam_centroid[0], 1), round(sam_centroid[1], 1)) if sam_centroid else None,
                "usd_centroid_px": (round(usd_centroid_px[0], 1), round(usd_centroid_px[1], 1)) if usd_centroid_px else None,
                "mask_area": mask_area,
                "occluded": occluded,
                "pixel_dist": round(dist_px, 1) if dist_px is not None else None,
            }
            per_cube_series[cp].append(entry)

    # -- Phase 7: metrics + flagged frames
    n_frames_total = len(usd_samples)
    metrics = {
        "template": template_name,
        "n_frames": n_frames_total,
        "hz": hz,
        "duration_s": round(n_frames_total / hz, 2),
        "image_size": [Wimg, Himg],
        "viewport_size": [vpw, vph],
        "n_cubes_tracked": len(cube_init_bboxes),
        "n_capture_fail": n_capture_fail,
        "per_cube": {},
        "global": {},
    }
    all_dists = []
    for cp in cube_init_bboxes:
        dists = pixel_dists[cp]
        flagged = [e["frame_idx"] for e in per_cube_series[cp] if e.get("pixel_dist") is not None and e["pixel_dist"] > 50]
        metrics["per_cube"][cp] = {
            "n_frames_with_match": len(dists),
            "n_frames_occluded": occluded_counts[cp],
            "tracking_success_ratio": round((n_frames_total - occluded_counts[cp]) / max(1, n_frames_total), 3),
            "mean_pixel_dist_usd_vs_sam": round(sum(dists) / max(1, len(dists)), 2) if dists else None,
            "max_pixel_dist_usd_vs_sam": round(max(dists), 2) if dists else None,
            "frames_with_dist_gt_50px": flagged,
            "n_frames_with_dist_gt_50px": len(flagged),
        }
        all_dists.extend(dists)
    if all_dists:
        metrics["global"] = {
            "mean_pixel_dist_usd_vs_sam": round(sum(all_dists) / len(all_dists), 2),
            "max_pixel_dist_usd_vs_sam": round(max(all_dists), 2),
            "n_distance_measurements": len(all_dists),
        }
    # write metrics JSON
    metrics_path = OUT_DIR/f"{template_name}_track_metrics.json"
    metrics_path.write_text(json.dumps({
        "metrics": metrics,
        "per_cube_series": per_cube_series,
    }, indent=2, default=str))

    # -- Phase 8: render PNG overlay (last frame as backdrop, draw trajectories)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        last_img = np.array(Image.open(frame_dir/f"{n_frames_total-1:06d}.jpg").convert("RGB"))
        fig, ax = plt.subplots(figsize=(12, 7))
        ax.imshow(last_img)
        ax.set_title(f"{template_name} — USD (red) vs SAM2 (green), {n_frames_total} frames @ {hz}Hz")
        ax.axis("off")
        # Annotate per-cube label near start of trajectory; legend is global USD vs SAM
        usd_label_added = False; sam_label_added = False
        for ci_idx, cp in enumerate(cube_init_bboxes):
            entries = per_cube_series[cp]
            xs_usd = [e["usd_centroid_px"][0] for e in entries if e["usd_centroid_px"]]
            ys_usd = [e["usd_centroid_px"][1] for e in entries if e["usd_centroid_px"]]
            xs_sam = [e["sam_centroid_px"][0] for e in entries if e["sam_centroid_px"]]
            ys_sam = [e["sam_centroid_px"][1] for e in entries if e["sam_centroid_px"]]
            short_cp = cp.split("/")[-1]
            if xs_usd:
                ax.plot(xs_usd, ys_usd, color="red", linewidth=2.0, alpha=0.85,
                        label="USD-projected" if not usd_label_added else None)
                ax.scatter(xs_usd[::5], ys_usd[::5], c="red", s=18, marker="o", alpha=0.7)
                ax.text(xs_usd[0]+6, ys_usd[0]-6, short_cp, color="white", fontsize=8,
                        bbox=dict(facecolor="red", alpha=0.5, pad=1))
                usd_label_added = True
            if xs_sam:
                ax.plot(xs_sam, ys_sam, color="lime", linewidth=2.0, alpha=0.85,
                        label="SAM2-tracked" if not sam_label_added else None)
                ax.scatter(xs_sam[::5], ys_sam[::5], c="lime", s=18, marker="s", alpha=0.7)
                sam_label_added = True
        if metrics.get("global"):
            g = metrics["global"]
            ax.text(8, 24, f"mean dist USD↔SAM = {g['mean_pixel_dist_usd_vs_sam']}px  max = {g['max_pixel_dist_usd_vs_sam']}px",
                    color="white", fontsize=11, bbox=dict(facecolor="black", alpha=0.6))
        leg = ax.legend(loc="upper right", framealpha=0.7)
        traj_path = OUT_DIR/f"{template_name}_trajectory.png"
        plt.tight_layout()
        plt.savefig(traj_path, dpi=110, bbox_inches="tight")
        plt.close(fig)
        print(f"  trajectory PNG: {traj_path}", flush=True)
    except Exception as e:
        print(f"  PNG overlay failed: {type(e).__name__}: {e}", flush=True)

    print(f"  metrics: {metrics_path}", flush=True)
    return {
        "template": template_name,
        "n_frames": n_frames_total,
        "n_cubes_tracked": len(cube_init_bboxes),
        "metrics_path": str(metrics_path),
        "trajectory_path": str(OUT_DIR/f"{template_name}_trajectory.png"),
        "global_metrics": metrics.get("global", {}),
        "per_cube_summary": {cp: {
            "tracking_success_ratio": metrics["per_cube"][cp]["tracking_success_ratio"],
            "mean_dist": metrics["per_cube"][cp]["mean_pixel_dist_usd_vs_sam"],
            "max_dist": metrics["per_cube"][cp]["max_pixel_dist_usd_vs_sam"],
            "n_high_dist": metrics["per_cube"][cp]["n_frames_with_dist_gt_50px"],
        } for cp in cube_init_bboxes},
    }


# -----------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("templates", nargs="*", default=["CP-77", "CP-09", "CP-13", "CP-14"])
    parser.add_argument("--video-track", action="store_true", help="Use multi-frame SAM2VideoPredictor mode")
    parser.add_argument("--n-frames", type=int, default=60, help="Number of frames to capture per template (video-track only)")
    parser.add_argument("--hz", type=float, default=10.0, help="Capture rate Hz (video-track only)")
    args = parser.parse_args()

    templates = args.templates
    mode = "video-track" if args.video_track else "single-frame"
    print(f"Vision pilot ({mode}): {len(templates)} templates", flush=True)

    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # Connect to running Kit (don't launch own)
    from service.isaac_assist_service.chat.tools import kit_tools
    if not await kit_tools.is_kit_rpc_alive():
        print("ERROR: Kit RPC not alive on port 8001. Spec says: share existing Kit, don't launch own.", flush=True)
        sys.exit(2)

    if args.video_track:
        # Video-tracking mode
        results = []
        for i, name in enumerate(templates, 1):
            print(f"\n[{i}/{len(templates)}] {name} (video-track)", flush=True)
            t0 = time.time()
            try:
                r = await track_cube_video(name, args.n_frames, args.hz, kit_tools, device)
            except Exception as e:
                import traceback
                print(f"  EXC: {type(e).__name__}: {e}", flush=True)
                traceback.print_exc()
                r = {"template": name, "error": f"{type(e).__name__}: {e}"}
            elapsed = round(time.time() - t0, 1)
            r["elapsed_s"] = elapsed
            results.append(r)
            print(f"  [{name}] {elapsed}s", flush=True)
        out = OUT_DIR/f"vision_pilot_track_{time.strftime('%Y%m%d_%H%M%S')}.json"
        out.write_text(json.dumps(results, indent=2, default=str))
        print(f"\nDONE. Results: {out}", flush=True)
        return

    # --- single-frame mode (original) ---
    # Load SAM2
    print("Loading SAM2...", flush=True)
    from sam2.build_sam import build_sam2
    from sam2.sam2_image_predictor import SAM2ImagePredictor
    sam_model = build_sam2(SAM_CONFIG, str(SAM_CHECKPOINT), device=device)
    sam_predictor = SAM2ImagePredictor(sam_model)
    print(f"  SAM2 on {device}", flush=True)

    # Load CLIP
    print("Loading CLIP...", flush=True)
    import open_clip
    clip_model, _, clip_preprocess = open_clip.create_model_and_transforms('ViT-B-32', pretrained='laion2b_s34b_b79k')
    clip_model = clip_model.to(device).eval()
    clip_model.preprocess = clip_preprocess
    clip_tokenizer = open_clip.get_tokenizer('ViT-B-32')
    print(f"  CLIP on {device}", flush=True)

    # Sim + analyze each template
    from review.sweep_all_rewritten import observe_one

    results = []
    for i, name in enumerate(templates, 1):
        print(f"\n[{i}/{len(templates)}] {name}", flush=True)
        t0 = time.time()
        # Run sim → get scene_observer rec (with vision_input)
        rec = await observe_one(name)
        rec['template'] = name
        if rec.get('exception'):
            print(f"  sim failed: {rec['exception']}")
            results.append({"template": name, "error": rec['exception']})
            continue
        # Capture viewport + analyze
        analysis = analyze_one(name, rec, sam_predictor, clip_model, clip_tokenizer, device)
        elapsed = round(time.time() - t0, 1)
        results.append({
            "template": name,
            "elapsed_s": elapsed,
            "honest_pass": rec.get('honest_pass'),
            "ve_patterns": [n for n, p in (rec.get('virtual_eyes') or {}).get('patterns', {}).items() if p.get('detected')],
            "ve_narrative": (rec.get('virtual_eyes') or {}).get('narrative'),
            "vision_analysis": analysis,
        })
        # Print short summary
        per_prim = (analysis or {}).get('per_prim') or {}
        for pp, r in per_prim.items():
            if 'error' in r: continue
            tag = ', '.join(r.get('flags', [])) or 'ok'
            print(f"  {pp}: iou={r.get('iou','?')} clip={r.get('clip_label','?')}({r.get('clip_conf','?')}) [{tag}]")
        print(f"  → {elapsed}s")

    out = OUT_DIR/f"vision_pilot_results_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nDONE. Results: {out}")


if __name__ == "__main__":
    asyncio.run(main())
