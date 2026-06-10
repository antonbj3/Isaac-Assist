# E2E trace — `packer-suction-sheet` (T2, UR10, suction-place)

**Scenario id:** `packer-suction-sheet`
**Tier:** T2
**Robot:** UR10
**Task:** suction-place
**Persona:** packaging operator
**One-sentence request:** "UR10 vacuum-picks flat label sheets and places each within 2mm on a workpiece"

This document traces the COMPLETE sequence of actions the user (packaging operator) and the LLM acting
on their behalf take to reach the target scene, plus the OUTCOME. Every step is tagged
`[USER]`/`[LLM]`/`[SYSTEM]` and `[CHEAP-static]`/`[EXPENSIVE-physics]`. All tool/template/handler claims
are grounded in real files with `file:line` citations. Honest notes on drafts/missing-tools/unverified
capability are inline and summarized at the end.

---

## 0. Template match (what the LLM retrieves)

The request has three hard signals: **vacuum/suction**, **flat label sheets**, **±2mm placement on a
workpiece**, on a **UR10**. Grepping the real library
(`/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/`):

- `CP-NEW-vacuum-gripper-sheet-pick.json` — the ONLY canonical that picks *thin flat sheets*
  (0.30×0.22×0.003 m) with `surface_gripper`. **Robot = Franka** (`role_defaults.primary_robot.class
  = "franka"`, line ~171), destination is a 3-slot tray with **loose** `xy_tolerance: 0.3`
  (`simulate_args`, line 85). It does NOT enforce ±2mm.
- `CP-NEW-label-applicator-pose.json` — the ONLY canonical with the **±2mm / ±2° tight-tolerance**
  pose-critical placement onto a workpiece-as-fixture (`tolerance_position_m: 0.002`,
  `tolerance_orientation_deg: 2.0`, lines 110-111 / 326-327). But the workpiece is a **single thin
  label** (0.05×0.03×0.002 m), and **Robot = Franka** (`class: "franka"`, line ~246).
- `CP-NEW-yrkesroll-gripper-vacuum-pick.json` — vacuum + conveyor + mixed sheets, also **Franka**.

**No single template matches the request as stated.** The closest match is a *fusion* of
`CP-NEW-label-applicator-pose` (the ±2mm pose spec, the `get_world_transform` verification, the
`drop_targets`+`gripper_rotation` mechanism) and `CP-NEW-vacuum-gripper-sheet-pick` (the *sheet* feeder
geometry), **re-targeted from Franka to UR10**. There IS a real UR10 + `surface_gripper` cluster in the
library (CP-69/70/71/73/75/79/80/81/82/83/84/85/86, all `class: "ur10e"`/`"ur10"`), so a UR10 suction
arm is a supported instantiation — but every one of those UR10 suction templates picks **cubes**, never
thin sheets, and none carries a 2mm pose-tolerance verify. So the LLM here is doing **template
adaptation across two donors + a robot swap**, not a clean instantiation. Mark this honestly: the
resulting scene is a **derived draft**, not a verified canonical.

---

## 1. Numbered narrative

### Phase A — User states the goal

**Step 1.** `[USER]` `[CHEAP-static]` — The packaging operator types the request into the Isaac Assist
chat: *"UR10 vacuum-picks flat label sheets and places each within 2mm on a workpiece."* No file
touched yet; this is pure NL intake.

**Step 2.** `[LLM]` `[CHEAP-static]` — The LLM parses intent into a structural shape: `pattern_hint =
pick_place`, `gripper_type = surface_gripper` (vacuum), `destination_kind = fixture` (workpiece, not a
bin), `has_pose_critical_placement = true`, `tolerance_position_m = 0.002`, robot family `ur10`. This
mirrors the `intent.structural_features` block that the two donor templates carry
(`CP-NEW-label-applicator-pose.json:165-179`).

**Step 3.** `[LLM]` `[CHEAP-static]` — The LLM retrieves the nearest canonicals (the three above) and
selects `CP-NEW-label-applicator-pose` as the *tolerance/verification skeleton* and
`CP-NEW-vacuum-gripper-sheet-pick` as the *sheet-geometry source*. It notes the **robot mismatch**
(both donors are Franka) and commits to a UR10 swap using the proven UR10-suction cluster as the
robot-spawn reference (e.g. `CP-70.json`, `class: "ur10e"`).

### Phase B — LLM authors the scene (CHEAP, no physics yet)

Each of the following is the LLM emitting a tool call. All the tools below are **real and registered**
(handler file cited). Nothing here steps PhysX, so all of Phase B is `[CHEAP-static]` scene authoring.

**Step 4.** `[LLM]` `[CHEAP-static]` — `create_prim` ×N for the scene skeleton: DomeLight, Ground,
Cell, Table. Handler: `scene_authoring.py` (`create_prim` registered there; `get_world_transform` lives
in the same file). Followed by `apply_api_schema(PhysicsCollisionAPI)` on Ground/Table.

**Step 5.** `[LLM]` `[CHEAP-static]` — `set_physics_scene_config(config={"enable_gpu_dynamics": False,
"broadphase_type": "MBP"})`. CPU dynamics for deterministic thin-body contacts — the exact setting both
donors use (`CP-NEW-vacuum-gripper-sheet-pick.json` code block; rationale in `thoughts` item 7). This
*configures* physics but does not step it → still CHEAP.

**Step 6.** `[LLM]` `[CHEAP-static]` — `robot_wizard(robot_name="ur10e", dest_path="/World/UR10",
position=[0,0,0.75], orientation=[1,0,0,0])`. Handler: `resolve.py` (`robot_wizard`). The UR10 registry
entry exists in `robot.py:197-201` (`"ur10": {rmp_config, desc, urdf, ee_frame: "ee_link"}`). **Honest
note:** MEMORY records that a raw `add_reference(ur10.usd)` starts the arm *wound* (wrist_2 ≈ −298°);
the working UR10 suction templates spawn via `robot_wizard`/`robot_wizard(home_joints)` to avoid this.
The LLM must use `robot_wizard`, not a raw reference, or the arm starts in a bad configuration.

**Step 7.** `[LLM]` `[CHEAP-static]` — `surface_gripper(robot_path="/World/UR10",
ee_link="/World/UR10/ee_link", grip_threshold=0.003, force_limit=20.0, torque_limit=10.0,
graph_path="/World/UR10/SuctionGraph")`. Handler: `robot.py` — the suction branch builds an
**OgnSurfaceGripper** OmniGraph node (`robot.py:1477-1514`, node
`isaacsim.robot.surface_gripper.OgnSurfaceGripper` at line 1497). **Robot-swap caveat:** the donor
templates pass `ee_link=".../panda_hand"` (Franka). For UR10 the ee frame is `ee_link` (`robot.py:201`,
`"ee_frame": "ee_link"`), and the real UR10 suction path uses a `suction_cup` sub-prim as the
cup-position source (`pick_place.py:5686`, `_SG_CUP_PATH = .../suction_cup`). The LLM must emit the UR10
ee frame, not the Franka one.

**Step 8.** `[LLM]` `[CHEAP-static]` — Feeder + workpiece + sheet authoring:
- `create_bin(prim_path="/World/SheetFeeder", ...)` for the flat-sheet source tray. Handler:
  `resolve.py`/`robot.py` (`create_bin` registered).
- `create_prim(... "/World/Workpiece" ..., Cube)` + `apply_api_schema(PhysicsCollisionAPI)` — the
  static fixture (the thing the sheet is placed on), per
  `CP-NEW-label-applicator-pose.json` (`/World/Workpiece`, static, lines 272-285).
- `create_prim(... "/World/Sheet_1" ..., Cube, scale=[0.15,0.11,0.0015])` for each flat sheet, then
  `apply_api_schema` ×4 (RigidBody/Collision/Mass/PhysxRigidBody) and
  `bulk_set_attribute(... enableCCD=True ...)`. **CCD on thin sheets is mandatory** (donor failure mode:
  "CCD tunnelling on thin sheets", `CP-NEW-vacuum-gripper-sheet-pick.json:103`). Handler:
  `scene_authoring.py` (`bulk_set_attribute`), `physics.py`/`resolve.py` (`apply_physics_material`).

**Step 9.** `[LLM]` `[CHEAP-static]` — `define_grasp_pose(robot_path="/World/UR10",
object_path="/World/Sheet_1", gripper_offset=[0,0,0.001], approach_direction=[0,0,-1])`. Handler:
`robot.py` (`define_grasp_pose`). Top-down vacuum contact on the sheet's top-face centre. (Per donor
`CP-NEW-label-applicator-pose.json` code: `define_grasp_pose ... approach_direction=[0,0,-1]`.)

**Step 10.** `[LLM]` `[CHEAP-static]` — `add_proximity_sensor(sensor_path="/World/PlaceArrivalSensor",
position=<target pose>, size=[0.06,0.04,0.01])`. Handler: `sensors.py` (`add_proximity_sensor`). Tight
detection volume over the target so only a settled sheet trips it. (`overlap_sphere`, also in
`sensors.py`, would be the stack-presence query if a multi-sheet stack source were used as in the
sheet-pick donor.)

**Step 11.** `[LLM]` `[CHEAP-static]` — `setup_pick_place_controller(robot_path="/World/UR10",
target_source="curobo", source_paths=["/World/Sheet_1", ...], destination_path="/World/Workpiece",
drop_targets={"/World/Sheet_1": [x,y, workpiece_top_z + half_sheet]},
gripper_rotation={"/World/Sheet_1": 0.0}, approach_height=0.05, planning_obstacles=["/World/Table",
"/World/SheetFeeder", "/World/Workpiece"], sensor_path="/World/PlaceArrivalSensor")`. This is the one
tool that wires the whole pick-place behaviour. Handler: `pick_place.py` (the giant controller —
`setup_pick_place_controller` is the registered entry; the `_quat_delta`/USD→physics sync is internal,
not a tolerance check, `pick_place.py:2580`). The `drop_targets` + `gripper_rotation` are the mechanism
the request's "within 2mm" leans on (donor rationale `CP-NEW-label-applicator-pose.json:thoughts` item
5). **Still CHEAP** — this *installs* the controller's OmniGraph/callback; it does not run the sim.

**Step 12.** `[LLM]` `[CHEAP-static]` — `get_world_transform(prim_path="/World/Sheet_1")` and
`get_world_transform(prim_path="/World/Workpiece")`. Handler: `scene_authoring.py`. These snapshot poses
so a downstream pose-delta check *could* compare against the ±2mm spec. **Critical honesty flag:**
`get_world_transform` only READS a pose. The actual ±2mm/±2° comparison is described in the donor's
`thoughts`/`diagnose_args` as a downstream "diagnose pipeline" step — **there is no registered tool that
performs that comparison** (see §3, Tool gaps).

### Phase C — Static pre-filter (CHEAP "virtual eyes", catches problems before the expensive gate)

Before paying for a full physics gate, the static validators read the **post-build, post-settle**
geometry (one short settle play, but no full pick-place run). These are the cheap eyes.

**Step 13.** `[SYSTEM]` `[CHEAP-static]` — `scene_validate.py` builds + settles the scene and checks
three classes that recur in LLM-authored scenes (`scripts/qa/scene_validate.py:7-14`):
- **REACH** — is each sheet within the UR10 reachable shell? Uses `ROBOT_REACH["ur10"] = 1.30`
  (`scene_validate.py:32`), mirroring the controller's own reach gate. **This is where a UR10 placement
  error is caught cheaply:** if the LLM, swapping from Franka (reach 0.855) to UR10, leaves the feeder
  or workpiece at a Franka-tuned offset that lands in a UR10 dead-zone (the UR10 cup-down reach floor is
  non-monotonic in y — see `reach_validate.py:21-24`), the static check flags `UNREACHABLE` here, with
  **zero** physics cost, instead of burning a 90-120 s gate run.
- **INTERPENETRATION** — are the stacked sheets clumped into one point? (the dispenser-clump class).
- **SUPPORT** — does each sheet rest on the feeder surface (not floating, not buried)? A 3 mm sheet
  authored with the wrong z (Franka feeder_top 0.80 vs a UR10 table at a different height) shows up here
  as floating/buried.

**Step 14.** `[SYSTEM]` `[CHEAP-static]` — `reach_validate.py` runs the **UR10 cup-down** reach probe
specifically: it points the cup straight down at the real grasp height (`REPOINT=-90`,
`_reach_probe_z_off=0.193`, `reach_validate.py:8-10`) and returns a per-target REACHABLE/UNREACHABLE
verdict using live cuRobo IK. This is the UR10-specific cheap gate that the Franka donors never needed.
**Honest caveat from the tool's own docstring (`reach_validate.py:12-18`):** REACHABLE means "the grasp
pose has an IK solution from the home seed" — it is **necessary, not sufficient**; a marginal pose can
probe REACHABLE yet still fail the function gate (measured: CP-81 probed REACHABLE but the gate FAILED).
The probe is also stochastic (cuRobo Halton seeds) → use N-of-M. So the static eyes can *reject* a bad
layout cheaply, but a *pass* here does not promise the expensive gate passes.

> **What the static eyes do NOT check:** sheet *flatness*, suction *seal feasibility* on a 3 mm face,
> orientation/yaw alignment, or the ±2mm *placement* tolerance. There is **no** `flatness` / `sheet_fit`
> / `footprint_fit` static tool (`grep` over `scripts/qa/` + `handlers/` returns nothing). Those are
> only observable in physics — and even then not measured by the gate (§2, §3).

### Phase D — Expensive physics gate (the OUTCOME)

**Step 15.** `[SYSTEM]` `[EXPENSIVE-physics]` — `gate_one.py` builds the canonical, settles, and runs
`simulate_traversal_check` with the template's own `simulate_args`
(`scripts/qa/gate_one.py:71-88`). This is the authoritative function gate and it steps PhysX for the
full `duration_s` (the label donor uses 90 s; the sheet donor 120 s). This is the expensive run the
static eyes exist to protect.

**Step 16.** `[SYSTEM]` `[EXPENSIVE-physics]` — **Gate success criterion** (the OUTCOME), from
`handlers/diagnostics.py:4436-4449`:
- single-target: `success = in_xy AND above_floor AND at_rest AND upright_ok`
- multi-target: `success = (any cube delivered) AND upright_ok`
where `in_xy` = the sheet's final xy is inside the target bbox expanded by `xy_tolerance`
(`diagnostics.py:4019, 4436-4438`), `above_floor` = within `floor_tolerance` (default 0.10) of the
target floor, `at_rest` = settled speed below `rest_speed`, and `upright_ok` = the part's local +Z·world
+Z ≥ `upright_tolerance_dot` (default 0.95, `diagnostics.py:4023,4443-4444`).

**Step 17.** `[SYSTEM]` `[CHEAP-static]` — The gate prints the verdict JSON; `success=True` ⇒ gate PASS
(`gate_one.py:87-88`). Reading the verdict is cheap.

---

## 2. The OUTCOME, stated honestly

**Gate success-criterion the scenario is graded on:** sheet delivered into/onto the target's xy bbox
(expanded by `xy_tolerance`), above floor, at rest, and **upright** (dot ≥ 0.95) —
`diagnostics.py:4436-4449`.

**The request asks for "within 2mm." The gate does not, and cannot, measure that.** The gate's position
test is **bbox containment with a tolerance that the template author sets** — the sheet donor uses
`xy_tolerance: 0.3` (300 mm!) and the label donor floors it to `0.10` (100 mm; see the label template's
`_patch_history` `p2_xy_tol_floor_0.10`, lines 338-344). There is no sub-mm position comparison and **no
orientation-degree comparison at all** in `simulate_traversal_check` — only the binary `upright` dot
product. So a sheet that lands 50 mm off and rotated 15° in-plane would still register a gate PASS as
long as it is inside the (loose) bbox and lies flat. **The 2mm/2° spec is effectively unverified by the
production gate.** This is the headline honesty point for this scenario.

**Capability status:** Both donors are explicitly **drafts**:
- `CP-NEW-vacuum-gripper-sheet-pick.json:276` → `"function-gate ⏳"`, `motion_controllers.verified: []`,
  `curobo` only `untested`.
- `CP-NEW-label-applicator-pose.json:337` → `"form-gate-schema ⏳; function-gate ⏳ Kit RPC"`,
  `curobo` `untested`.
Neither has a passing function gate on record. The UR10 swap is **not** represented by any existing
template (every UR10-suction canonical picks cubes), so the traced `packer-suction-sheet` scene is a
**new, unverified derived draft** — its function-gate outcome is **unknown** until actually run, and
even a PASS would not confirm the ±2mm requirement.

---

## 3. Tools that would be NEEDED but do NOT exist (grep-confirmed)

1. **A pose-tolerance verifier** — a tool that compares a placed part's world pose against a target pose
   and returns pass/fail for a `tolerance_position_m` (2mm) + `tolerance_orientation_deg` (2°) spec.
   The donor templates *describe* this as a "diagnose pipeline" step and stash the numbers in
   `simulate_args`/`diagnose_args` (`CP-NEW-label-applicator-pose.json:110-129`), but **no registered
   handler performs the comparison.** `grep -rE "tolerance_orientation_deg|pose_delta_check|
   verify_pose_delta" handlers/` returns nothing; the only `quat_delta` hits are an internal USD→physics
   body-sync inside `pick_place.py:2580`, not a verifier. `get_world_transform` only reads a pose.
   **This is the single biggest gap for this scenario** — the request's defining requirement (±2mm)
   has no tool to grade it.

2. **A static sheet-flatness / footprint-fit pre-check** — a cheap "does this thin flat part fit the
   slot / lie flat on the workpiece face / will the cup get a seal" check, runnable before the gate.
   `grep -rniE "flatness|sheet_fit|footprint_fit|fits_in_slot"` over `scripts/qa/` and `handlers/`
   returns nothing. `scene_validate.py` covers only REACH / INTERPENETRATION / SUPPORT
   (`scene_validate.py:7-14`).

3. **A suction-seal feasibility model** — the OgnSurfaceGripper uses AABB proximity, not surface
   normals (donor failure mode, `CP-NEW-vacuum-gripper-sheet-pick.json:101`), so nothing validates that
   a 3 mm sheet face actually yields a *physically faithful* seal. MEMORY further records the UR10
   suction grip is currently a near-weld-equivalent rigid mount, not a compliant suction — "faithful
   suction is an open research item" (`project_isaac_assist_cp70_suction_solved`). So even when the gate
   passes, the *grip fidelity* is unverified — there is no tool that asserts it.

4. **A UR10-suction-sheet canonical** — there is no template combining UR10 + surface_gripper +
   thin-sheet workpiece + 2mm pose. The LLM must hand-fuse two Franka donors and swap the robot; no
   tool/template provides this as a verified starting point.

---

## 4. Where the static eyes earn their keep (summary)

For THIS scenario the cheap pre-filter most plausibly catches a **REACH/SUPPORT** error introduced by
the **Franka→UR10 robot swap**: the donor geometry is tuned to Franka's 0.855 m envelope and table
height, while UR10 has a 1.30 m envelope with a *non-monotonic cup-down reach floor*
(`reach_validate.py:21-24`). If the LLM keeps the Franka-tuned feeder/workpiece offsets, `scene_validate
.py` (REACH, `ROBOT_REACH["ur10"]=1.30`) and `reach_validate.py` (live cup-down IK probe) flag
`UNREACHABLE`/floating-part **before** the 90-120 s physics gate runs — saving the expensive run. What
the static eyes can NOT save you from, and the gate can NOT either, is the **±2mm/±2° tolerance** — that
requirement falls through every existing check (gap #1).

---

## 5. Verdict line

`packer-suction-sheet` is reachable as a **derived UR10 draft** fused from `CP-NEW-label-applicator-pose`
(±2mm spec + verification scaffolding) and `CP-NEW-vacuum-gripper-sheet-pick` (sheet geometry), but:
(a) **no template** matches it directly; (b) both donors are **unverified drafts** (`function-gate ⏳`);
(c) the production gate grades only **bbox-containment + upright**, so the headline **±2mm placement
requirement is unverifiable** with current tooling; and (d) the **pose-tolerance verifier**, the
**static flatness/fit check**, and a **faithful suction-seal model** are all **missing**. The static
eyes (`scene_validate.py` + `reach_validate.py`) will cheaply catch a robot-swap reach/support error,
but cannot certify the 2mm spec.
