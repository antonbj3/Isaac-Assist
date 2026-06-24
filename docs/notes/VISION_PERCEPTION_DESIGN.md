# Camera / Computer-Vision Perception Direction (cont.319 2026-06-24, Anton-steered)

Goal: grasp from CAMERA data (sim-to-real fidelity), not sim ground-truth USD poses.

## Pipeline (LLM + SAM2 + depth -> pose -> grasp)
1. **Isaac camera** (overhead or eye-in-hand) -> RGB + DEPTH + intrinsics/extrinsics.
2. **Target ID** (LLM layer, optional): Gemini sees RGB -> points at the target (pixel).
   Decouple from CV: prove SAM2+depth->pose accuracy FIRST, add LLM-ID on top.
3. **SAM2** (INSTALLED: vision_models/sam2.1_hiera_small.pt + HF sam2.1-hiera-large) promptable
   point -> precise object mask.
4. **Pose from mask+depth**: unproject masked pixels (K + extrinsics) -> 3D point cloud ->
   centroid (position) + PCA (orientation) -> 6DOF grasp pose.
5. **Grasp** with the camera-derived pose (NOT the USD bbox).
6. **Verify**: (a) camera-pose vs sim ground-truth (perception accuracy, < few mm), (b) scene_eyes pick.

## Feasibility (confirmed)
- SAM2 + checkpoints present; Isaac camera tooling (sensors.py add_sensor camera, vpu viewport); GPU 7.5GB free.

## ★ KEY CONSTRAINT FOUND (3 PoC iterations, scripts/qa/vision_pose_poc.py)
The shared RPC Kit (:8001, the one scene_eyes drives) can capture RGB via the VIEWPORT
(`vpu.capture_viewport_to_file`, proven) but **Replicator DEPTH annotators do NOT populate**:
- `rep.orchestrator.step()` -> "can only be performed in a standalone workflow, not from within Kit".
- offscreen Camera-sensor render product -> empty data (rgb/depth shape (0,)).
- viewport render-product + annotator attach -> still empty get_data().
So RTX render-DEPTH (what a real RGB-D camera gives) needs a render path the RPC Kit doesn't tick.

## DECISION POINT (path forward)
- **(A) Standalone vision-Kit**: a separate Isaac process (SimulationApp standalone) where
  rep.orchestrator.step + annotators WORK -> real RTX RGB+depth -> SAM2 -> pose. Clean, but a
  2nd Kit process (the shared :8001 is reserved for scene_eyes manipulation).
- **(B) In-Kit raycast-depth**: cast rays through the camera pixel grid into the scene (no RTX
  render) -> geometric depth. Works in RPC Kit, but it's SIM-GEOMETRY depth (less sim-to-real
  honest than RTX render-depth; ~equivalent to using ground-truth for the masked region).
- **(C) Viewport depth-AOV**: investigate capturing the viewport's depth AOV directly (the
  viewport renders; if its depth AOV is capturable like RGB, depth without orchestrator).

Recommendation: (A) standalone vision-Kit for honest RTX RGB-D, OR (C) if the viewport depth-AOV
is capturable. (B) raycast is a quick stand-in to prove the SAM2->mask->pose->grasp WIRING while
deferring true-depth fidelity. The LLM-ID layer (Gemini-vision on the RGB) is independent + works now.

## ★ RESULT (2026-06-24): LLM-VISION-pick PROVEN 3/3 (the (a) multimodal-vision sense)
Gemini-2.5-flash via Vertex SEES the rendered scene + identifies the target object VISUALLY.
- Feasibility: gemini_vision_test.py -> Gemini reads a 3-colour test image correctly (image POST via
  the GeminiProvider Vertex base_url + ADC bearer works; provider doesn't parse images so POST raw).
- End-to-end (llm_vision_pick.py): build 3 cubes with NEUTRAL prim names (Cube_A/B/C) + display colours,
  capture the viewport RGB (vpu.capture_viewport_to_file — the proven in-Kit RGB path), POST image+prim-list
  to Gemini "based ONLY on the image, which prim is the RED cube?". 3/3 CORRECT: red->Cube_A, green->Cube_B,
  blue->Cube_C. Names neutral -> Gemini MUST read colour from the image (true visual identification).
- ★ RENDER-FIDELITY findings (diagnostik-först, Gemini self-reported the failures honestly):
  (1) default USD camera focal -> ~23deg FOV too narrow; set focal ~16 for ~65deg.
  (2) a cube DIRECTLY BELOW an overhead camera SPECULAR-BLOWS-OUT to white (Gemini saw the middle cube as
      "white / a light source", not green) -> ANGLE the camera (translate -y + RotateX ~20deg) so no object
      is directly under it -> all colours render crisply.
  (3) pure display colours (1,0,0)/(0,1,0)/(0,0,1) + a DomeLight (even fill) + moderate DistantLight.
  -> with these, 3/3. The LLM-vision capability is solid; render quality is the lever, and Gemini HONESTLY
     reports when it can't see a colour (a good built-in false-success guard).
NEXT for a scene_eyes-verified GOLD: wire vision-selection -> source_paths -> Franka pick -> scene_eyes
(the pick half is the proven LLM-pick pipeline). DEPTH/SAM2 path (sense b) still pending the (A/B/C) decision.

## ★ SAM2 segmentation PROVEN (2026-06-24, scripts/qa/sam2_segment_poc.py)
SAM2.1-hiera-small (vision_models/) segments a cube from a COARSE point seed on our captured
render: a colour-centroid seed (= what a VLM 'point at the X cube' gives) -> SAM2 precise mask.
3/3: red/green/blue masks each ~0.7% of image, score 0.92-0.94, coherent + cube-sized. Mask
centroids ((469,402),(639,402),(810,402)) = the cube image-centres -> these feed depth-unproject.
⇒ the SEGMENTATION half of the CV-grasp pipeline works (point -> precise mask).

## CV PIPELINE STATUS (perception -> grasp)
- [x] RGB capture (viewport, in-Kit) — works
- [x] LLM-vision identification (Gemini-2.5-flash Vertex sees render, IDs target) — 3/3
- [x] SAM2 segmentation (coarse point -> precise mask) — 3/3, score ~0.93
- [ ] mask + DEPTH -> 3D pose : depth path = (A) standalone RTX-Kit / (B) in-Kit RAYCAST / (C) viewport-AOV
- [ ] grasp from camera-derived pose -> scene_eyes verify
NEXT: (B) raycast-depth (no 2nd process) — unproject the SAM2 mask centroid to a camera ray,
physx-raycast into the scene -> 3D hit point, compare to ground-truth (perception accuracy), then grasp.
