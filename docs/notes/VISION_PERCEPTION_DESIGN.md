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
