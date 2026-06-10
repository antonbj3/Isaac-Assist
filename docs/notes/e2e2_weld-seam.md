# E2E Trace — weld-seam / continuous-seam-track (UR10)

**Scenario id:** `e2e2_weld-seam`
**Domain:** welding · **Robot:** ur10 · **Task:** continuous-seam-track
**Request (verbatim):** *"follow a weld seam continuously along a workpiece edge"*
**Date:** 2026-06-09
**Closest real template:** `workspace/templates/CP-NEW-welder-seam-track.json` (near-exact match)
**Sibling templates:** `CP-NEW-yrkesroll-welder-mig-tack.json` (DISCRETE tack variant), `CP-NEW-yrkesroll-paint-sprayer-trajectory.json` (coverage-raster sibling), `CP-NEW-weld-seam-vision-ndt.json` (inspection variant)

---

## TL;DR — the verdict

This request maps **1:1** onto an existing template (`CP-NEW-welder-seam-track`), the tools are all **registered**, and a parallel Python spec
(`multimodal/sub_phase_99_pick_hold_weld_scenario.py` + `arena_benchmark_spec.py::linear_seam_500mm`) even encodes the *physics* of seam welding
(weave amplitude/frequency, constant travel speed, lateral-deviation < 1 mm). **Yet nothing in the chain executes.** The whole task terminates as a
**dry-run plan emission** — every compliance call raises `NotImplementedError` in live mode, the vision-correction loop produces 2-D image points that
are never lifted to 3-D, and the function-gate has no concept of "seam deviation" so it measures *nothing*.

The **already-inventoried** gap (P10: compliance dry-run, absent ros2_control bridge — `TOOL_GAP_INVENTORY_V2.md:54`) is the *shallow* blocker. The
**NEW class-level gap** this trace reveals sits one layer beneath that: **there is no continuous-path-tracking controller CLASS and no path-tracking
gate CLASS in the entire system.** Even with a perfect torque bridge, Isaac Assist could not *measure* or *drive* "stay within ε of a parametric
curve at constant travel-speed." That is the same shape as the humanoid-cabinet finding (pick-place breaks on articulated doors → needs a revolute-pull
controller): **the entire surface-process family** — seam welding, spray-paint raster, deburring, polishing, sealant bead, glue dispensing, plasma/laser
cut, sanding — needs a **`surface_process` controller class + a `path_tracking` gate class** that no pick-place / sort / insert primitive can stand in for.

---

## The target scene (what "done" looks like)

From `CP-NEW-welder-seam-track.json` `code`:

- `/World/DomeLight`, `/World/Ground` (collision cube)
- `/World/WeldTable` — Cube at `[0.6, 0, 0.4]`, scale `[1.2, 0.8, 0.4]`
- `/World/Workpiece` — steel-plate Cube at `[0.6, 0, 0.815]`, scale `[0.5, 0.3, 0.015]`, semantic `steel_plate`
- `/World/SeamMarker` — thin strip Cube at `[0.6, 0, 0.832]`, scale `[0.48, 0.005, 0.002]`, semantic `seam_target` (the parametric centreline the torch must track)
- `/World/UR10` — `robot_wizard` spawn at origin, `solverPositionIterationCount=16`
- **Success criterion (per `verify_args.note`):** torch tool-tip (`/World/UR10/tool0`) traverses the 0.5 m seam start→end with **path deviation < 2 mm** from the SeamMarker centreline, maintaining ~5 N contact via soft-Z impedance.

Physically faithful spec (the *real* requirement, encoded but unwired) lives in `multimodal/sub_phase_99_pick_hold_weld_scenario.py:73` `WeldSeamSpec`:
`speed_mm_per_s=5.0`, `weave_amplitude_mm=1.5`, `weave_frequency_hz=2.0` — i.e. a sinusoidal weave overlaid on the seam axis at constant travel speed,
with `success_force_window_N=(5.0, 50.0)`. `arena_benchmark_spec.py:253` `linear_seam_500mm` (difficulty L3) demands *"seam length ≥ 490 mm,
lateral deviation < 1 mm"*; `weld_02 complex_corner_joint` (L5) adds *"re-entry overlap 5-10 mm, no burn-through"*.

---

## Full action sequence (every step, marked)

Legend: `[USER]` / `[LLM]` / `[SYSTEM]` · `[CHEAP-static]` (no physics step, kinematics/USD/VLM only) · `[EXPENSIVE-physics]` (would step PhysX / drive torque).

| # | Actor | Step | Cost | Lands? | Evidence |
|---|-------|------|------|--------|----------|
| 1 | `[USER]` | "follow a weld seam continuously along a workpiece edge" | — | — | request |
| 2 | `[SYSTEM]` | Retrieval → nearest canonical `CP-NEW-welder-seam-track` (`structural_tags: isaac:topology.seam_tracking`, `isaac:compliance.impedance`, `isaac:motion.compliant_follow`, `isaac:assembly.weld_seam`) | `[CHEAP-static]` | ✅ | template `intent.structural_tags` |
| 3 | `[LLM]` | Plan two-phase motion: rigid transit (cuRobo/Lula) → compliant follow (impedance) + vision correction | `[CHEAP-static]` | ✅ | template `thoughts[0]` |
| 4 | `[LLM]` | Build scene: `create_prim`×5, `apply_api_schema`, `set_attribute` (semantic labels), `set_physics_scene_config` | `[CHEAP-static]` | ✅ live | scene_authoring.py handlers, all `queue_exec_patch` |
| 5 | `[LLM]` | `robot_wizard(robot_name="ur10", dest_path="/World/UR10", position=[0,0,0])` | `[CHEAP-static]` | ✅ live | robot.py robot_wizard — known-good UR10 spawn (avoids wound-start, see MEMORY) |
| 6 | `[LLM]` | `bulk_set_attribute(... solverPositionIterationCount=16)` | `[CHEAP-static]` | ✅ live | scene_authoring |
| 7 | `[LLM]` | `check_singularity(art="/World/UR10", target=[0.35,0,0.90], ori=[0,.707,0,.707])` | `[CHEAP-static]` | ✅ **live** | diagnostics.py:~790 — real Jacobian SVD condition number via cuRobo FK, `queue_exec_patch`. **Only genuinely-live diagnostic in the chain.** |
| 8 | `[LLM]` | `plan_trajectory(art="/World/UR10", waypoints=[approach, descend], planner="rmpflow", robot_type="ur10")` | `[CHEAP-static]` | ⚠️ plans-only | robot.py:2402 `_gen_plan_trajectory` — real `LulaTaskSpaceTrajectoryGenerator`, returns a joint trajectory but **does not execute it** (PLAN, no step). No timed traversal, no contact. |
| 9 | `[LLM]` | `setup_impedance_controller(robot="/World/UR10", target_frame="tool0", Kx=[600,600,200], torque_mode=True, dry_run=True)` | `[CHEAP-static]` | ⚠️ **dry-run** | compliance.py:343 — writes an in-memory config dict to `_INSTALLED_COMPLIANCE`. **`dry_run=False` → `raise NotImplementedError` (compliance.py:399)**, "requires Kit RPC + ros2_control bridge + torque-mode robot." |
| 10 | `[LLM]` | Loop `for seg in range(3): vision_plan_trajectory(instruction="follow the weld seam left→right", num_points=10)` | `[CHEAP-static]` | ⚠️ **2-D dead-end** | vision.py:1363 — captures viewport, asks VLM for waypoints, returns **image-space 2-D points**. *No `pixel_to_world` in the loop*; output is **never consumed** by anything 3-D (verified: no caller wires it to the controller). Template's own `failure_modes[2]` admits this. |
| 11 | `[LLM]` | `set_compliance_params(robot="/World/UR10", stiffness_xyz=[400,400,150], dry_run=True)` | `[CHEAP-static]` | ⚠️ **dry-run** | compliance.py:505 — mutates in-memory dict. `dry_run=False` → `NotImplementedError` (compliance.py:537). |
| 12 | `[LLM]` | `follow_trajectory_with_compliance(trajectory=[4 seam poses], robot="/World/UR10", compliance_handoff_at=0.05, compliance_controller="cartesian_impedance", timeout_s=60, velocity_scaling=0.3, dry_run=True)` | `[EXPENSIVE-physics]` *intended* | ❌ **never runs** | compliance.py:838. Validates args, checks `_INSTALLED_COMPLIANCE` membership, splits handoff → returns a **plan dict only**. `dry_run=False` → **`raise NotImplementedError` (compliance.py:1014)**: "requires Kit RPC + ros2_control bridge (CRM-A1) to drive the rigid prefix and hand off to the compliance controller." **This is the actual seam-follow. It does not execute.** |
| 13 | `[LLM]` | `get_kinematic_state(prim="/World/UR10/tool0")` | `[CHEAP-static]` | ✅ live | diagnostics — reads tool0 pose. But because step 12 never moved the arm, this returns the **plan/approach pose, not a traversed path.** |
| 14 | `[LLM]` | `release_compliance(robot="/World/UR10", dry_run=True)` | `[CHEAP-static]` | ⚠️ dry-run | compliance.py:645 — pops in-memory entry. `dry_run=False` → `NotImplementedError` (compliance.py:678). |
| 15 | `[SYSTEM]` | **Gate / verify.** `verify_args.stages = []`, `simulate_args = null` → the cube-delivery function-gate (`scripts/qa/gate_one.py`) has **nothing to simulate** and **no deviation metric**. `score_scenario` (sub_phase_99:255) would award `seam_complete` only if `seam_progress_pct >= 100` — but nothing ever calls `update_seam_progress`. | `[CHEAP-static]` | ❌ **un-gradeable** | gate_one.py is `cube_path`/`target_path`-centric; no seam/path-deviation verifier exists. |

**Net:** steps 4-8, 13 land live (scene + spawn + singularity check + a *plan*). The seam follow itself (9-12, 14) is a **dry-run plan emission**. The gate
(15) cannot score it. **No torch ever moves along the seam. No deviation is ever measured.**

---

## OUTCOME

**Form-gate:** ✅ passes (schema valid; `verified_status: form-gate-schema ✓`).
**Function-gate:** ❌ **N/A — there is no path-tracking verifier.** The template is honestly labelled `function-gate ⏳ diagnostic`. `gate_one.py` would
either skip it (empty `stages`) or mis-apply a cube-delivery check that is meaningless here.
**Live physics:** ❌ The seam traversal never executes — `follow_trajectory_with_compliance(dry_run=False)` raises `NotImplementedError`
(compliance.py:1014). With `dry_run=True` the system emits a plan dict and *reports success on the plan*, which is a **silent-success / form-only pass**:
the structural representation exists, the behaviour does not.
**Faithfulness:** the realistic welding requirements (sinusoidal weave at `weave_frequency_hz=2.0`, constant `speed_mm_per_s=5.0`, contact-force window
`(5,50) N`, lateral deviation < 1 mm) are encoded as **inert dataclasses** with zero live producers. This is scaffolding, not capability.

---

## Tool / template / capability gaps found

### Already in the inventory (cited, NOT the headline)
- **P10** compliance/impedance/admittance `dry_run=False` → `NotImplementedError`, blocked on absent **ros2_control torque bridge** (`TOOL_GAP_INVENTORY_V2.md:54,202`; compliance.py:186/399/537/678/1014). This trace *confirms* it but it is not new.

### NEW gaps this trace surfaces

1. **No continuous-path-tracking controller CLASS (the headline — see below).** `plan_trajectory` plans but does not execute a timed traversal;
   `linear_motion` exists only as an internal cuRobo `ToolPoseCriteria` baked into a *single* pick-place lift segment (pick_place.py:5281, axis="z"),
   not an externally-callable parametric-path follower; `follow_trajectory_with_compliance` is the only "follow" verb and it is dry-run-only AND
   compliance-coupled. **There is no rigid-mode "traverse this curve at v m/s" primitive either** — so even a non-compliant seam-follow (e.g. laser cut)
   has no executor.

2. **No path-deviation / path-tracking GATE class.** Every verifier in `scripts/qa/` is delivery-centric (`simulate_traversal_check`, `cube_path`,
   `target_path`, under_target). There is no verifier that records a TCP trajectory, projects it onto a parametric seam axis, and computes cross-track
   error vs a threshold — exactly the metric `verify_args.max_deviation_mm=2.0` and `arena_benchmark_spec` "lateral deviation < 1 mm" demand. The
   `WeldSeamSpec`/`score_scenario` machinery exists but is **unwired** (no live caller of `update_seam_progress`, `weave_amplitude_mm`,
   `weave_frequency_hz`). Effort: **M** (handler + record_trajectory → project-onto-curve + gate wiring).

3. **Vision-correction loop is open (2-D → 3-D break).** `vision_plan_trajectory` returns image-space points; the seam-tracking *premise* is closed-loop
   visual servoing, but there is no `pixel_to_world` lift inside the loop and the VLM output feeds nothing. The "adaptive correction per segment" is
   cosmetic. Effort: **M** (wire `pixel_to_world` + depth lift into the follow loop). A real seam-tracker needs a **dedicated seam-sensing modality**
   (structured-light/laser seam tracker), not a generic scene VLM — that is **research**.

4. **No travel-speed / weave-overlay primitive.** Welding (and sealant/glue/paint) requires a *constant tool-frame travel speed* with an optional
   superimposed oscillation. `velocity_scaling` on a dry-run dict is not this. No tool expresses `(parametric_path, travel_speed, weave(amp,freq))`.

5. **No process-side asset/material.** Kimate's 243 assets contain **zero** weld/torch/seam/F-T-sensor primitives (`find -iname "*weld*|*seam*|*torch*"`
   → only `WELD_CHASSIS_BODY_ASM` mesh names on nova_carter, unrelated). `arena_benchmark_spec` lists `WeldFixture_Linear`, `WeldTool`, `WeldFixture_Corner`
   as `required_assets` that **do not exist on disk.** Effort: **S-M** (author torch-tool proxy + groove-fixture + mountable F/T sensor prim).

---

## THE class-level finding (key deliverable)

> **Continuous-seam-track exposes that Isaac Assist has no `surface_process` controller class and no `path_tracking` gate class — a missing primitive
> *family*, not a missing template.**

This is structurally identical to the humanoid-cabinet trace (pick-place fundamentally breaks on an articulated door → needs a revolute-pull controller).
There, the gap was a *controller* for a constrained DOF. Here, the gap is an entire **process paradigm**:

- Every shipped controller is a **discrete waypoint/grasp** machine: pick-place, sort, insert, stack — *go to pose A, actuate, go to pose B*. Success is
  **terminal state** (object delivered / inserted).
- Surface processes are **continuous trajectory** machines: *traverse a parametric curve at controlled speed while maintaining tool-frame contact/standoff,
  optionally with superimposed motion (weave/raster/orbit)*. Success is a **path-integral property** (cross-track error, coverage %, constant travel-speed,
  contact-force window) — **never a terminal object state.**

No amount of composing pick-place / move_to_pose / plan_trajectory yields this, because:
(a) there is no executor that drives a **timed traversal** of a planned curve (plan_trajectory stops at the plan);
(b) there is no gate that scores a **path-integral** metric (all gates score terminal delivery);
(c) the one "follow" verb (`follow_trajectory_with_compliance`) is welded to the compliance/ros2_control bridge that does not exist, so it cannot serve
the **rigid** members of the family (laser/plasma cut, dispensing) either.

**A whole family is blocked by the same two missing classes:**
seam welding (this), **spray-paint raster** (`CP-NEW-yrkesroll-paint-sprayer-trajectory` — same `record_trajectory`+coverage pattern, same un-wired gate),
deburring, polishing/buffing, sanding/grinding, **sealant/adhesive bead**, glue dispensing, laser/plasma/water-jet cutting, brushing/coating, plus the
inspection cousins (`CP-NEW-weld-seam-vision-ndt`, NDT scan, leak-test trace). They differ only in *contact mode* (compliant vs rigid vs standoff) and
*coverage geometry* (1-D seam vs 2-D raster vs 3-D orbit) — all four share one controller class and one gate class.

**Minimum viable unblock (the new build target):**
1. `surface_process_follow(path | seam_marker_path, travel_speed_m_s, contact_mode∈{rigid, standoff, compliant}, weave={amp,freq}|None)` — a live
   executor that, for `rigid`/`standoff`, needs **only cuRobo** (already live) — no ros2_control bridge, so it ships *now* for cut/dispense/paint and gives
   the compliant welder a real spine the moment the torque bridge lands.
2. `path_tracking_gate(robot_path, seam_path | coverage_grid, metric∈{cross_track_mm, coverage_pct}, threshold)` — records the TCP trajectory (the live
   `record_trajectory` already exists, robot.py:3779), projects onto the parametric path, scores the path-integral. Wire `score_scenario`
   (sub_phase_99) to it.

Until both exist, *every* continuous-process request degrades to a **plausible dry-run plan that passes the form-gate and silently never moves** — the most
dangerous failure mode (looks like success, is vapour).

---

## File:line citations
- Template: `workspace/templates/CP-NEW-welder-seam-track.json` (whole; `verify_args.note`, `failure_modes[0,2,4]`, `intent.structural_tags`)
- compliance.py:399 (impedance live → NotImplementedError), :537 (set_params), :678 (release), :838 + :1014 (**follow_trajectory_with_compliance live → NotImplementedError**)
- vision.py:1363 (`_handle_vision_plan_trajectory` → 2-D image points, no pixel_to_world consumer)
- diagnostics.py:~790-853 (`check_singularity` — the one genuinely-live step, real Jacobian SVD)
- robot.py:2402 (`_gen_plan_trajectory` — plans, never executes), :3779 (`_gen_record_trajectory` — exists, unused by any seam path)
- pick_place.py:5281 (`linear_motion` is an internal cuRobo lift constraint, NOT a path follower)
- multimodal/sub_phase_99_pick_hold_weld_scenario.py:73 (`WeldSeamSpec` weave/speed — inert), :215 (`update_seam_progress` — no live caller), :255 (`score_scenario` — measures the un-driven `seam_progress_pct`)
- multimodal/arena_benchmark_spec.py:251 (`linear_seam_500mm` L3, "lateral deviation < 1 mm"; required_assets `WeldFixture_Linear`/`WeldTool` absent on disk)
- scripts/qa/gate_one.py (cube-delivery-only; no path-deviation verifier)
- Kimate assets: `find /home/anton/kimate_assets/assets -iname "*weld*|*seam*|*torch*"` → no weld/torch/seam/F-T prims
- Existing inventory overlap: `docs/notes/TOOL_GAP_INVENTORY_V2.md:54,202` (P10 compliance dry-run / ros2_control bridge — confirmed, not the headline)
