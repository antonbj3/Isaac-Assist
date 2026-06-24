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

## ★ Camera-ray GEOMETRY VALIDATED (2026-06-24, client-side from SAM2 centroids)
Unproject each SAM2 mask-centroid through the camera intrinsics+pose, intersect the table plane:
- X (horizontal): err <=5mm (0.304/0.419/0.535 vs gt 0.30/0.42/0.54) -> intrinsics fx/cx + pose correct.
- Y: consistent systematic offset 14-31mm depending on the assumed plane-z (0.06->31, 0.03->23, 0.0->14mm).
  Most of it is the PLANE-Z ASSUMPTION (centroid maps to the object centre/contact, not its top) + a ~14mm
  residual (tilt/fy). ⇒ the chain (RGB -> SAM2 mask -> camera ray -> 3D) is geometrically SOUND; true
  per-pixel DEPTH (not a plane assumption) removes the Y systematic AND gives z for non-planar objects.
So the only thing between here and a camera-derived grasp pose is the DEPTH source (A/B/C decision).

## CV PIPELINE — UPDATED STATUS
- [x] RGB capture (viewport) | [x] Gemini-vision ID 3/3 | [x] SAM2 segmentation 3/3 | [x] camera-ray geom (X 5mm)
- [ ] TRUE DEPTH -> z + Y-systematic-fix : (A) standalone RTX-Kit RGB-D / (B) in-Kit physx-RAYCAST / (C) viewport-AOV
- [ ] grasp from camera pose -> scene_eyes verify
The HARD perception parts (identify, segment, unproject geometry) are PROVEN. Remaining = the depth-source
engineering + grasp wiring. Recommendation: try (B) physx-raycast first (in-Kit, no 2nd process; feasibility
check needed: does omni.physx scene-query raycast work in the RPC Kit, given the Replicator render did not?).

## ★★ PATH (B) VIABLE — physx-raycast WORKS in the RPC Kit (2026-06-24)
omni.physx scene-query raycast(origin,dir) in the shared :8001 Kit -> EXACT hit: from (0.40,0.15,0.5)
straight down hit /World/Cube at (0.40,0.15,0.075) = the cube top (cube centre 0.05, top 0.075),
distance 0.425, collision='/World/Cube'. (Needs CollisionAPI on the object + a PhysicsScene + a few
timeline.play() updates to cook colliders.) So unlike the Replicator RGB-D annotators (which need a
standalone workflow), RAYCAST works IN-KIT -> true per-pixel depth without a 2nd process.

## ⇒ ENTIRE CV-PERCEPTION PIPELINE PROVEN (every piece), full camera-grasp UNBLOCKED:
  [x] RGB capture (viewport)              [x] Gemini-vision ID 3/3 (Vertex, sees render)
  [x] SAM2 segmentation 3/3 (point->mask) [x] camera-ray geometry (X 5mm)
  [x] physx-raycast in-Kit (EXACT depth)  -> mask-centroid pixel -> camera ray -> raycast -> TRUE 3D pose
The remaining work is pure INTEGRATION (wire perception 3D pose -> controller grasp -> scene_eyes verify),
all blockers cleared. Build order: (1) scene with collision cubes + Franka + bin + angled camera;
(2) capture RGB; (3) SAM2 mask centroid; (4) camera-ray + physx-raycast -> 3D pose (no ground-truth);
(5) grasp at that pose; (6) scene_eyes verifies the right object delivered. = honest sim-to-real camera grasp.

## STATUS: INTEGRATION COMPLETE (cont.319, 2026-06-24)
Full camera-perception-driven grasp VERIFIED end-to-end (`scripts/qa/vision_grasp_e2e.py`),
NO ground-truth used for selection or localisation:
 1. Kit renders 3 colour collision-cubes via an offset-overhead camera -> RGB.
 2. SAM2 segments the TARGET colour -> mask centroid pixel (3/3 colours).
 3. Camera-ray (camera FRUSTUM intrinsics) + physx `raycast_closest` -> HIT PRIM + 3D pose.
 4. CP-VISION-GRASP written with `source_paths=[hit_prim]` (camera-chosen, not GT).
 5. scene_eyes confirms ONLY the perceived cube is delivered to the bin; others untouched.
Results: red->Cube_red delivered (xy-in-bin=yes, gripped, converged, upright); blue->Cube_blue
delivered, red+green untouched. The camera DRIVES which cube is grasped (target swap changes the
delivered object). Pose accuracy X 0.8-2.5mm, Z exact (cube top 0.825).
### KEY CALIBRATION FIX
The Omniverse viewport CONFORMS the camera vertical aperture to the viewport aspect ratio, so the
USD `verticalAperture` attribute is stale -> pixels are SQUARE in the render -> use `fy = fx =
focal*W/horizontalAperture`. Reading the stale vertical-aperture attr made fy too small by H/W
(0.5625), overshooting the y-ray by 1/0.5625=1.78x and MISSING the cube. One-line fix `fy=fx`.

## REAL-OBJECT CV-PERCEPTION — HONEST STATUS (cont.319, 2026-06-24)
`scripts/qa/vision_grasp_real.py` extends the pipeline to REAL YCB meshes (banana/can/brick via
add_reference). The synthetic-cube pipeline does NOT transfer cleanly — concrete measured blockers:
 1. **SAM2-auto segments the TABLE + fragments, not the small objects.** Candidate masks come back
    table-sized (5596-9146px); nearest-to-VLM matching then selects a table region. Area-filtering
    by absolute px is too coarse — the table dominates the scene.
 2. **Thin settled meshes graze to the table on raycast.** Banana/brick lie flat (~3cm), can rolls
    onto its side; a ray to the mask centroid (or 60 samples across a table-dominated mask) hits
    /World/Table at z=0.80, not the object.
 3. **YCB props ROLL/settle** to unpredictable xy (cans especially); needs full settle-to-static
    BEFORE capture, and the live RPC-Kit sim advances between the capture exec and the raycast exec.
 4. Gemini-vision pointing is in the right x-REGION but imprecise (±60-110px) on small varied shapes.
What WORKS (verified, synthetic): Gemini-vision selection + SAM2 + camera-ray + raycast + grasp on
display-coloured cubes (CP-VISION-GRASP, both colour-seed and VLM-driven). The REAL-object arc needs
a different recipe: tighter camera (objects large in frame), depth/instance segmentation instead of
auto-mask+area-filter, thin-mesh raycast handling (sample object-class hits only, reject table by z),
and a settle-to-static gate read back from sim before perceiving. NOT a quick wire — a deliberate arc.
