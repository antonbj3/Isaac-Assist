# E2E Trace — tool-changer-swap (flexible-cell, UR10)

**Scenario ID:** tool-changer-swap
**Request (verbatim):** *"swap from a parallel-jaw gripper to a suction tool at a tool-changer dock mid-task"*
**Robot:** UR10 · **Domain:** flexible-cell · **Task:** automated end-of-arm-tooling (EOAT) changeover
**Closest real template:** `workspace/templates/CP-NEW-tool-changer-swap.json` (status: `drafted-2026-05-16; form-gate-schema pending; smoke-test pending` — **authored but never run**)
**Sibling that quietly proves the same root:** `workspace/templates/CP-NEW-adaptive-3finger-gripper.json` (the physics fingers were *deleted* from its `code` field — see §6)

---

## 0. One-paragraph outcome (read this first)

The scenario is **buildable as a static USD tableau** but **the actual user request — a *mid-task* swap — is not executable as a temporal sequence, and is not scorable by any gate.** The template models the swap by authoring the *end-state* (which `FixedJoint` is active at t=0) and then teleporting `xformOp:translate` on Cube proxies; it never moves a real arm to a dock, never releases under physics, never engages under physics. The two motion calls (`move_to_pose`, `rmpflow`) are **single-step reactive nudges** (robot.py:2230–2238) that do not drive the wrist to the dock, so the "synchronization barrier" the template relies on (F1) is a no-op. The success criterion the template declares (*which tool is parented to the wrist via FixedJoint at end*) **cannot be measured** — the only function-gate, `simulate_traversal_check`, is a `cube_path → target_path` bbox-delivery checker (diagnostics.py:3920) with zero awareness of joint identity, `stage_kind: release/engage`, `expected_active_joint`, or `uses_tool_changer`. The template smuggles the swap into the gate by setting `cube_path=/World/Tools/VacuumCup`, `target_path=/World/UR10/tool0` — i.e. it asks the delivery gate "did the vacuum cube reach the wrist bbox," which a `set_attribute(xformOp:translate)` teleport trivially satisfies **whether or not any swap physics happened.** This is a textbook silent-success. **The new class-level gap is real and large** (see §7).

---

## Actors / legend
- **[USER]** human operator typing into Isaac Assist chat
- **[LLM]** the planning model emitting tool calls
- **[SYSTEM]** Kit RPC / handlers / gate executing
- **[CHEAP-static]** USD authoring, no `world.play()` — exec_sync only
- **[EXPENSIVE-physics]** requires the timeline to run (`simulate_traversal_check`, real motion)

---

## 1. [USER] The ask
> "swap from a parallel-jaw gripper to a suction tool at a tool-changer dock mid-task"

Implicit requirements a competent operator means by this:
1. The arm is **already mid-task** holding/using a parallel-jaw gripper (there is a *before* state with work in progress).
2. It **drives to a physical dock**, **deposits** the jaw into an empty bay, **latches out**.
3. It **indexes to a second bay**, **latches in** a suction tool, **resumes** the task.
4. The swap is **temporal and physical** — a real motion + a real mechanical coupling change — not a relabel.

None of (1)–(4) survives to execution. See §3–§5.

---

## 2. [LLM] Plan / template match  — `[CHEAP-static]`
The retriever matches `CP-NEW-tool-changer-swap` (the only `isaac:industry.tool_changer` canonical; `intent.structural_tags` line 105–113). `tools_used` (lines 4–15):
`create_prim, set_attribute, apply_api_schema, robot_wizard, create_articulated_joint, move_to_pose, get_world_transform, prim_exists, set_physics_scene_config, list_relationships`.

**Every one of these tools exists and resolves.** That is *why this scenario is dangerous* — it looks fully covered. The gap is not a missing tool name; it is a missing **controller class** and a missing **gate class** (§7).

---

## 3. [SYSTEM] PHASE 0 — build the static scene  — `[CHEAP-static]`
Executes the `code` field (template lines 17). All succeed under `exec_sync`:

| Step | Tool | Handler | Result |
|---|---|---|---|
| dome + ground + table | `create_prim` / `apply_api_schema` | scene_authoring.py | ✅ |
| CPU physics (`enable_gpu_dynamics:False`) | `set_physics_scene_config` | physics.py | ✅ deterministic FixedJoint reattach |
| UR10 spawn at [0,0,0.75] | `robot_wizard` | robot.py | ✅ (wound-start auto-repair applies — MEMORY: ur10 wound_start root) |
| ToolStand + Plate + Dock_1 + Dock_2 | `create_prim`/`apply_api_schema` | ✅ visual/collision Cubes |
| ParallelJaw cube @ **guessed** `[0.50,0.0,1.20]` | `create_prim` + 4 schemas | ✅ |
| VacuumCup cube parked in Dock_2 | `create_prim` + 4 schemas | ✅ |
| `Wrist_to_ParallelJaw` FixedJoint, body0=`/World/UR10/tool0`, body1=ParallelJaw | `create_articulated_joint` | ⚠️ **see §3a** |

### 3a. **BUG (latent, confirmed by reading the handler):** the initial FixedJoint is mis-framed
`create_articulated_joint(joint_type="fixed")` (robot.py:4522–4642) sets **only** `Body0Rel`/`Body1Rel`. It **never authors `localPos0/localPos1/localRot0/localRot1`** (grep confirmed: the only `CreateLocalPos*` calls in robot.py are inside the *surface_gripper* path at 6360–6361 and the `_ur10_cupframe` rework at 6520, **not** in `create_articulated_joint`). A `UsdPhysics.FixedJoint` with no local frames welds the two bodies **at their relative pose when PhysX first parses the joint.** The ParallelJaw cube was authored at a *hand-guessed* `[0.50, 0.0, 1.20]` — the comment in the template literally says *"Approximate wrist world pose … a reasonable Z … cuRobo/RMPflow handle the exact transform at runtime"* (template line note 4). The UR10 `tool0` at home is **not** at `[0.50,0.0,1.20]`. So at t=0 the weld bakes in **whatever offset exists between the real tool0 and the guessed cube position** — typically 10–30 cm. The "mounted" jaw therefore hangs in space at a fixed offset from the flange. This is exactly failure-mode **F3** that the template warns about for the *vacuum* engage — but it is **unmitigated for the initial jaw mount**, because the F3 mitigation (teleport-to-wrist-before-joint) is only applied in PHASE 4, never in PHASE 0.

> **This is a NEW concrete bug, not in TOOL_GAP_INVENTORY_V2:** `create_articulated_joint(fixed)` has no `bake_local_frame` option, so *any* "attach tool X to flange" use welds at the authored offset. The surface_gripper path solves it (localPose baking, robot.py:6334–6361); the generic joint tool does not. Every EOAT-mount template that uses `create_articulated_joint` instead of `surface_gripper` inherits this.

---

## 4. [SYSTEM] PHASE 1–4 — the "swap"  — `[CHEAP-static]` (NOT physics)
This is where the **mid-task** semantics evaporate.

**PHASE 1 — approach Dock_1:**
`move_to_pose(articulation=/World/UR10, target=[0.55,0.10,0.95], planner="rmpflow")`.
Per the handler docstring (robot.py:2230–2238): rmpflow *"calls `get_next_articulation_action` **once** … applied immediately."* **One control tick.** The wrist takes a single joint nudge toward the target; it does **not** arrive at `[0.55,0.10,0.95]`. The follow-up `get_world_transform(/World/UR10/tool0)` is described in the template (F1) as a "synchronization barrier … forces the executor to await PhysX state" — **false.** It is a static read of the authored pose (MEMORY: scene_eyes row0 = authored pose); it neither plays the timeline nor waits for arrival. **The wrist is nowhere near the dock when release fires.**

**PHASE 2 — release jaw:**
- `set_attribute(Wrist_to_ParallelJaw, "physics:jointEnabled", False)` — the `set_attribute` generator (scene_authoring.py:781) infers `Sdf.ValueTypeNames.Bool` and creates the attr (line 856–857). Authored fine. **But this happens at build time, before any `play()`** — so it is not a *runtime* disengage of a moving joint; it is just authoring the end-state "off". Whether PhysX honors a *runtime* toggle on an already-instantiated joint is the open question the template itself flags (failure-mode 6, "Disabled-joint semantics may vary by PhysX version") — and **nothing in the trace ever tests it**, because the timeline never runs with the joint initially enabled then toggled.
- `set_attribute(ParallelJaw, "xformOp:translate", [0.55,0.10,0.86])` — **teleports** the jaw into Dock_1. This is the move that makes the scene *look* right in a screenshot.

**PHASE 3 — index to Dock_2:** another single-tick `move_to_pose` + static `get_world_transform`. Same no-op as PHASE 1.

**PHASE 4 — engage vacuum:**
- `set_attribute(VacuumCup, "xformOp:translate", [0.55,-0.10,0.95])` — teleport cup up to the (still-static, still-home) wrist guess.
- `create_articulated_joint(Wrist_to_VacuumCup, fixed)` — welds cup to flange at the **current** (teleported) relative pose. Inherits the same no-localPose issue (§3a): if the wrist isn't actually at `[0.55,-0.10,0.95]` (it isn't — see PHASE 3), the weld bakes the wrong offset.

**Net:** the entire "swap" is `set_attribute(translate)` × 2 + two FixedJoint authoring calls. **Zero physics. Zero arm travel. Zero mechanical-coupling dynamics.** The "mid-task" framing is gone: there is no *task* in progress, no before/after work, no resume.

---

## 5. [SYSTEM] Verification / gate  — `[EXPENSIVE-physics]` then `[CHEAP-static]`

### 5a. What the template ASKS the gate to check (`verify_args`, lines 43–67)
`stages:[{stage_kind:"release"},{stage_kind:"engage"}]`, `expected_active_joint`, `expected_inactive_joint`, `expected_parked_tool`, `expected_mounted_tool`, `parked_position_tolerance_m`, `mounted_position_tolerance_m`.

**None of these keys are read by any code.** Grep across `service/` + `scripts/qa/` for `stage_kind`, `expected_active_joint`, `expected_mounted_tool`: **zero consumers.** The verifier registry (verifier_registry.py, 512 lines) has checks for `reach / conveyor_active / controller_installed / cube_source_bridged / footprint / color_routing / cube_delivered / upright_at_rest` — **no `joint_identity` / `tool_mounted` / `release_engage` check.** `scripts/canonical_schema.py` validates `pattern_hint='other'` is allowed, but "other" means *"no form-gate structural check runs"* — it is the **opt-out bucket**, not a tool-swap verifier.

### 5b. What the function-gate ACTUALLY runs (`simulate_args`, lines 68–74)
`gate_one.py` reads `simulate_args.cube_path` / `target_path` and calls `simulate_traversal_check` (gate_one.py:78–82). The template set:
```
target_path = "/World/UR10/tool0"      # the wrist flange
cube_path   = "/World/Tools/VacuumCup" # the suction tool proxy
xy_tolerance = 0.05
```
So the **only** thing the EXPENSIVE physics gate measures is: *after `duration_s=60` of play, is the VacuumCup's XY inside the tool0 bbox, above-floor, at-rest?* (diagnostics.py:3920–4025: `in_target_xy ∧ above_floor ∧ at_rest`).

Because PHASE 4 **teleported** VacuumCup to `[0.55,-0.10,0.95]` and **welded** it to tool0, the cube is at/under the flange bbox and rigidly held → `in_target_xy=True, at_rest=True`. **The gate returns `success=True`.** It would return `success=True` **even if the parallel-jaw were never released, even if both joints were live, even if the arm never moved** — because the verdict is "did the orange cube end up near the flange," and a build-time teleport guarantees that. **This is a false-positive by construction** — the same silent-success family flagged in MEMORY (gates lie; confirm with raw scene data).

### 5c. The thing a human means by "swap" is never asserted
No check asserts: (a) jaw *left* the flange, (b) jaw *seated* in Dock_1, (c) exactly *one* tool is mounted at the end (the F2 over-constraint the template fears is **undetectable** — `list_relationships(Wrist_to_VacuumCup)` is called but its output is not graded), (d) the swap happened in *sequence* (F4 race is unobservable), (e) the wrist was *actually at the dock* when release/engage fired (it wasn't — §4).

---

## 6. Corroborating evidence — the 3-finger sibling already conceded the root
`CP-NEW-adaptive-3finger-gripper.json` was authored the same day (2026-05-16) to mount a multi-finger EOAT. Its `code` field (lines 25, and the `code_template` at 367) contains the smoking gun:

> *"authoring rigid-body Cube fingers + force-driven prismatic joints onto panda_hand adds zero grasp value and **corrupts the Franka articulation (PhysX blowup at sim start)**. The physics finger/joint authoring is therefore **intentionally omitted**."*

So the *adaptive gripper* template **gave up** on attaching a custom EOAT to the robot articulation under physics, and fell back to "express the gripper via semantics only." The tool-changer template is the **same problem one level up**: you cannot, with today's primitives, attach/detach a *tool* to a robot *flange* under live physics without either (a) corrupting the articulation, or (b) faking it with teleport+weld. **Both EOAT templates independently route around the same missing capability.** That convergence is the proof this is class-level, not a one-off.

---

## 7. ★ NEW CLASS-LEVEL ARCHITECTURAL GAP ★

> **Missing class: a runtime EOAT-changeover controller + a tool-mount gate.**
> Just as the humanoid-cabinet trace revealed *pick-place fundamentally breaks on articulated doors → needs a revolute-pull controller class*, this trace reveals:
> **the entire tool-changer / EOAT-swap family has no controller that performs a swap as a temporal physics sequence, and no gate that scores "which tool is mounted."** Every swap template degenerates to build-time teleport + weld + a delivery-gate masquerade.

This decomposes into **three coupled missing primitives** (none in TOOL_GAP_INVENTORY_V2 — those gaps are transport/sort/dexterous-grasp; this is mount-seam mechanics):

### GAP-TC1 — `swap_eoat` / `tool_changeover_controller` (missing CONTROLLER class) — Effort **M→L**
A state-machine handler (sibling to `setup_pick_place_controller`) that, **on a running timeline**, drives: `approach_dock_A → verify_arrival(get_world_transform under play) → release(disable+detach jaw, let it settle into bay under gravity) → retract → index_dock_B → approach → engage(attach suction, bake correct localPose) → retract → resume`. Today there is **literally no swap/changeover/eoat handler** (grep for `def _handle.*swap|changeover|eoat` → zero). `surface_gripper` (robot.py:6153) is single-tool and attaches the EE to *workpieces*, not the flange to *tools*; it cannot re-target between two tool prims. The arm-travel-to-dock is unexecutable because `move_to_pose` is single-tick (robot.py:2230) and there is no execution loop that plays the timeline until the wrist *arrives* — this is the same "no replay loop" wall the pick-place controller had to build internally (`_advance`/`_reached` state machine, pick_place.py:703–759). **A swap needs its own equivalent loop.**

### GAP-TC2 — `create_articulated_joint(..., bake_local_frame=True)` / a `mount_tool` verb (missing PRIMITIVE) — Effort **S**
`create_articulated_joint(fixed)` welds at the authored relative pose with **no local-frame baking** (§3a; robot.py:4604–4606 set only Body0/Body1 rels). Outcome: any "mount tool to flange" call freezes whatever offset happened to exist, so tools float. The fix already exists *inside* the surface_gripper path (localPose0/localPose1 baking, robot.py:6360–6361) and the cup-frame rework (6520) — it just needs to be **lifted into the generic joint tool as an option, or exposed as a dedicated `mount_tool(robot, flange_link, tool_path)` verb** that computes the zero-offset rest frame. Cheap; unblocks every EOAT-mount and payload-weld template (shares substrate with inventory M4 attach-payload, but the *local-frame correctness* angle is new).

### GAP-TC3 — `verify_tool_mounted` / a tool-identity gate check (missing GATE class) — Effort **M**
A `register_function_check` (verifier_registry.py pattern) that reads, **after play**: which FixedJoint(s) have body0=flange, asserts **exactly one** active (catches F2 over-constraint), asserts the *expected* tool is the mounted one and the *other* tool is seated in its dock within tolerance (consumes the already-authored `verify_args.expected_active_joint / expected_parked_tool / parked_position_tolerance_m` — **the template wrote the spec; nothing reads it**). Also a sequence check that the parked tool *transited* into the dock under physics, not teleport. Without this, **`pattern_hint='other'` is a measurement black hole**: every "other" template currently passes the function-gate purely on the `cube_path→target_path` delivery proxy, which is trivially gamed by teleport (§5b). This is the **#1 honesty gap for the entire non-delivery (`pattern_hint='other'`) canonical family**, not just tool-changer.

**Why class-level, not scenario-level:** the swap mechanism (`isaac:pattern.fixed_joint_swap`) is shared by every future tool-changer variant the template explicitly anticipates (`extends: industrial-tool-changer-swap-001`, `extension_notes`: pneumatic, multi-dock, etc.), **and** by the broader EOAT-attach family (3-finger, dex hands, payload-weld) that all route around GAP-TC2. Build TC1+TC2+TC3 once → the whole changeover/EOAT-mount cluster becomes real and scorable. Skip them → every such template is a teleport tableau that the delivery-gate rubber-stamps.

---

## 8. Asset reality check (Kimate's 243-appliance drop)
Searched `/home/anton/kimate_assets/assets` for `tool / changer / gripper / atc / quick-change / eoat / flange`: **no industrial tool-changer, ATC plate, dock, or EOAT asset exists.** Hits are household toolboxes, watches, chrome MDLs, scratch textures. Kimate's collection is appliances/kitchens/furniture/datacenter/Worker-actor — **nothing for this scenario.** So the scenario must keep using **Cube proxies** for both tools and docks (as the template does) — which is fine *for mechanism testing*, but means there is also a latent **asset gap** (no real ATC/dock USD) for any fidelity work. The mechanism gaps (§7) are the blocking ones; the asset gap is secondary.

---

## 9. Honest bottom line
- **What works:** static scene authoring; both FixedJoints author cleanly; the gate returns green.
- **What's a lie:** the green. The gate scores a teleported cube reaching the flange bbox — it does **not** score a swap. No arm travels to a dock; no tool releases under physics; no joint-identity is asserted; the `mid-task` requirement is absent entirely.
- **Tool/template/capability missing:** a **swap controller** (TC1), a **local-frame-correct mount primitive** (TC2), and a **tool-mounted gate check** (TC3). The template author already wrote the *spec* for TC3 in `verify_args` — the code to read it was never built.
- **Severity:** this is the same shape as the humanoid-cabinet → revolute-pull discovery: a whole task family (EOAT changeover) sits on a missing controller+gate class, currently masked by a delivery-gate false-positive.

**Files cited:**
- `workspace/templates/CP-NEW-tool-changer-swap.json` (the traced template; verify_args 43–67, simulate_args 68–74, failure_modes 85–92)
- `workspace/templates/CP-NEW-adaptive-3finger-gripper.json:25,367` (physics-EOAT omission concession)
- `service/.../handlers/robot.py:4522` (`create_articulated_joint`, no localPose baking), `:2227` (`move_to_pose` single-tick), `:6153` (`surface_gripper`, single-tool, attaches workpieces), `:6360` (localPose baking that exists only in surface_gripper)
- `service/.../handlers/scene_authoring.py:781` (`set_attribute` Bool inference for jointEnabled)
- `service/.../handlers/diagnostics.py:3920` (`simulate_traversal_check` = cube→target bbox delivery)
- `service/.../multimodal/verifier_registry.py` (512 lines; no joint-identity/tool-mounted check)
- `scripts/qa/gate_one.py:78` (gate reads only cube_path/target_path)
- `scripts/canonical_schema.py` (`pattern_hint='other'` = form-gate opt-out)
