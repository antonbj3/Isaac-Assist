# CP-70 FJ-free suction grip — GUI session plan (for Anton + Claude, 2026-06-02)

## One-line problem
UR10 reach is solved and a manual PhysX raycast from the suction cone HITS Cube_1 (3 mm), but the
IsaacSurfaceGripper **never forms the attachment** (`grippedObjects` stays empty, cube never lifts).
6 autonomous interventions tested, none bind. The SG's grip *logic runs* (status responds to pose), so the
failure is the runtime D6 attachment (articulation-link cone ↔ free cube) not forming. Needs live comparison.

## What is already ruled out (don't re-test)
- Reach (16 mm), ray geometry (hits Cube_1), forwardAxis=Z, clearanceOffset=0.008, attachmentPoints wired,
  excludeFromArticulation=True on the AP — all correct/verified live.
- maxGripDistance {0.05, 0.02, 0.015}; cone collider; free-body cone (detaches); driving cone USD pose (status
  flips Closed→Closing = SG reads USD, but still no latch); `/physics/updateToUsd`+`useFabricSceneDelegate=False`.

## GUI protocol (fastest path)
1. **Confirm the reference binds in OUR Kit build.** Load NVIDIA's gantry example:
   `isaacsim.examples.interactive` → "Surface Gripper" → Load → Close. Watch the "Gripped Objects" field populate.
   (Asset: `/mnt/shared_data/isaac-sim/exts/isaacsim.robot.surface_gripper/data/SurfaceGripper_gantry.usda`.)
   If it binds here → the SG engine works in our Kit; the difference is our setup. If it does NOT bind here →
   it's a Kit/Fabric/headless-config issue, not our setup.
2. **Build CP-70 in the same GUI session** (`execute_template_canonical` via the assist panel or a script), play,
   let the arm reach the cube, and **manually Close** the SG. Watch `isaac:grippedObjects` on
   `/World/UR10/ee_link/SurfaceGripper` (Property panel) + look for a new joint prim appearing under it.
3. **Diff gantry vs CP-70 at the grip moment** — the decisive comparisons:
   - Is the gantry's `Gripper_Cones` actually a folded articulation link, or a maximal-coord free body? (Select it,
     check Physics → whether PhysX shows it as an articulation link.) **This is the prime suspect**: if the gantry
     cone is NOT in the articulation (free body, USD-live pose) while ours IS (folded, USD-stale), that's the root.
   - When the gantry grips, does its AttachmentPoint D6 `body1` re-point to the box, or does a new joint appear?
     Replicate exactly whatever it does for CP-70.
   - Gantry SG prim is top-level `/World/SurfaceGripper` + joints in `/World/Surface_Gripper_Joints`; ours is nested
     under `ee_link`. (Likely not the cause — component logic runs — but cheap to rule out by moving it.)
4. **If gantry cone is a free body:** the fix is to make CP-70's cone a free (non-articulation) rigid body whose pose
   is driven to follow the wrist by something OTHER than a maximal-coord FixedJoint (which doesn't transmit) — e.g.,
   a per-physics-step kinematic target via `omni.physics.tensors RigidBodyView.set_kinematic_targets` driven from
   cuRobo FK, **plus** ensuring its USD pose is written live (so the SG raycast origin is correct). Then the cone is
   USD-live like the gantry and the SG should bind.

## Files
- Diagnosis: `docs/notes/function_gate_ledger.md` (entries 2026-06-01 23:55 / 2026-06-02 00:40).
- Probes: `~/.isaac_qa/run/grip_{axis_test,geom,traj,maxd,freecone,drive,collider,usdwb}.py`.
- Authoring under test: `service/.../handlers/robot.py:6242-6334` (gated suction-only; 37 baseline untouched).
- This blocks the UR10 vacuum cluster (~15 templates: CP-69/70/71/72/73/74/78–86).

---
## UPDATE 2026-06-02 03:00 — sharpened after ~20 Kit cycles (read THIS first)
**PROVEN: the SurfaceGripper works headless.** `~/.isaac_qa/run/minimal_sg.py` (a bare scene: free cone held to a
kinematic anchor ~10mm above a free cube, gantry-faithful SG/attachment) **grips and LIFTS the cube** (cube z 0.5→0.617
when the cone is raised). So the engine is fine headless; the old "engine-blocked" verdict is dead.

**The CP-70 scene does NOT grip, regardless of SG/cone setup.** Tested in the full scene: folded / free / kinematic /
free+kinematic-follower cone; build-time & mid-session SG; under-ee & top-level SG; collider on/off; both frame conventions;
maxGrip 0.011–0.05; physics-step driving; hold-when-stationary; updateToUsd; fabric-delegate off. In ALL, the cone tracks
the cube perfectly (sits at the cube for the full dwell) but the SG stays "Closing" and the cube never lifts.

**So the blocker is SCENE-LEVEL.** Two prime suspects to settle in GUI (cheap):
1. **cuRobo controller prestep interference** — it shares the physics step with the SG's grip-detection. TEST: in GUI, load
   CP-70, let the arm reach the cube, then PAUSE/disable the controller and manually Close the SG with the cone at the cube
   — does it grip then? If yes → the controller's per-step work (joint-target writes / world updates) is disrupting the SG
   settling; fix = sequence the SG close in a sub-step the controller doesn't stomp, or pause controller world-writes during grip.
2. **SG nested under the articulated ee_link** vs minimal's top-level SG. The ONE config not yet tried: BUILD-TIME +
   TOP-LEVEL SG in the CP-70 scene (cp70_verify was build-time but under-ee; cp70_toplevel was top-level but mid-session/
   unregistered). TEST: author `/World/UR10_SurfaceGripper` (top-level) at build time + the free-cone+follower recipe.

**The verified working recipe to port once the scene blocker is cleared** (from minimal_sg + cp70_follower):
- cone = FREE dynamic rigid body (RigidBodyAPI + CollisionAPI + disableGravity), identity-oriented, size ~0.02.
- a KINEMATIC follower (top-level) driven to the FK ee pose +(0,0,0.04) each PHYSICS step; cone held to it by a FixedJoint
  (excludeFromArticulation=True, breakForce max) — the only FJ, a structural tool mount.
- SG (build-time authored, manager-registered) + attachment D6: body0=cone, body1=follower, forwardAxis Z, localRot0=180X
  (ray world-down), clearanceOffset 0.008, maxGrip 0.05, transZ[0,0.01], gantry drives/limits, excludeFromArticulation.
- the follower-driving belongs in pick_place.py's UR10-suction prestep (the controller already computes FK).
- GRIP SIGNAL = cube-follows-cone (z rises); `isaac:grippedObjects` is UNRELIABLE (empty even during a real grip).
The robot.py implementation of this recipe is saved at `~/.isaac_qa/robot.py.bak_*follower*` (reverted from main; re-apply
once the scene blocker is fixed). Probes: `~/.isaac_qa/run/{minimal_sg,cp70_verify,cp70_follower,cp70_prestep}.py`.
