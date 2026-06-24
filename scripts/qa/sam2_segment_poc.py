"""SAM2 segmentation PoC (cont.319, Anton CV direction): does SAM2 segment a cube from
our captured render, given a coarse point prompt? Loads the last LLM-vision RGB, finds each
colour's centroid (a coarse seed = what a VLM 'point at the red cube' gives), prompts SAM2 ->
precise mask. If each mask is cube-sized + coherent (not the whole frame), SAM2 works in the
pipeline -> next: mask + depth -> 6DOF pose. Run: python scripts/qa/sam2_segment_poc.py"""
import numpy as np
from PIL import Image
from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor

CKPT = "/home/anton/projects/Omniverse_Nemotron_Ext/vision_models/sam2.1_hiera_small.pt"
CFG = "configs/sam2.1/sam2.1_hiera_s.yaml"
PNG = "/tmp/llm_vision_scene.png"

model = build_sam2(CFG, CKPT, device="cuda")
pred = SAM2ImagePredictor(model)
img = np.array(Image.open(PNG).convert("RGB"))
H, W = img.shape[:2]
print("image %dx%d" % (W, H))
pred.set_image(img)
r, g, b = img[..., 0].astype(int), img[..., 1].astype(int), img[..., 2].astype(int)
seeds = {"red": (r > 110) & (g < 90) & (b < 90),
         "green": (g > 110) & (r < 90) & (b < 90),
         "blue": (b > 110) & (r < 90) & (g < 90)}
for name, sm in seeds.items():
    ys, xs = np.where(sm)
    if len(xs) == 0:
        print("%s: no seed pixels found in render" % name); continue
    px, py = int(np.median(xs)), int(np.median(ys))
    masks, scores, _ = pred.predict(point_coords=np.array([[px, py]]),
                                    point_labels=np.array([1]), multimask_output=False)
    m = masks[0].astype(bool)
    pct = 100.0 * m.sum() / m.size
    # mask centroid (image) — would feed depth-unproject for the 3D pose
    mys, mxs = np.where(m)
    cm = (int(mxs.mean()), int(mys.mean())) if m.sum() else (None, None)
    print("%-5s seed=(%d,%d) seed_px=%d -> SAM2 mask area=%d (%.2f%% img) score=%.3f mask_centroid=%s %s" % (
        name, px, py, len(xs), m.sum(), pct, scores[0], cm,
        "OK(cube-sized)" if 0.05 < pct < 15 else "CHECK(too big/small)"))
