# E2E trace — [humanoid-cabinet] T6 / g1 / bimanual-assist

**Scenario id:** `humanoid-cabinet`
**Persona:** home/industrial assist user
**One-sentence request:** *"a Unitree G1 humanoid opens a Sektion cabinet and places an item inside"*
**Tier:** T6 (multi-stage dialog, articulated mechanism + bimanual humanoid + place-inside)
**Robot:** Unitree G1 humanoid (`robot_family="g1_arm"`)
**Task:** bimanual-assist (open hinged door, then place item inside the enclosure)

**Template-match:** No single template covers this. The honest closest pair is
`workspace/templates/CP-NEW-g1-bimanual-tabletop.json` (the ONLY G1 bimanual canonical;
gate-blocked on the NVIDIA Nucleus G1 asset) for the robot + controller, and
`workspace/templates/CP-NEW-drawer-open.json` (the ONLY articulated-mechanism manipulation
canonical) for the cabinet. Both are **drafts**: the G1 one has never passed its function gate
(asset blocker), and the drawer one is recorded `stable_fail` — its own controller cannot drive
the joint. The requested scene needs a **hinged (revolute) door**, which neither template builds,
plus a **place-inside** outcome, which the gate cannot measure. So this trace is a synthesis, and
the verdict is **build-then-fail** with two hard tool gaps and one static-eyes blind spot.

---

## Cast of real code this trace is grounded in

| Thing | File:line | State |
|---|---|---|
| G1 bimanual controller tool | `service/.../handlers/humanoid.py:23` `_gen_setup_bimanual_pick_place_controller` | landed, V0, sequential-only |
| G1 bimanual schema (enum `g1_arm` only) | `service/.../tools/tool_schemas.py:5654` | landed |
| Closest robot template | `workspace/templates/CP-NEW-g1-bimanual-tabletop.json` | draft, gate-blocked on Nucleus asset (`verified_status` line 39) |
| Closest cabinet template | `workspace/templates/CP-NEW-drawer-open.json` | `stable_fail` (line 39) — **drawer, not door** |
| G1 asset resolution | `service/.../handlers/robot.py:3968` (`"g1": "g1.usd"`), registry `:431` | needs Nucleus / `ASSETS_ROOT_PATH` |
| Revolute-joint authoring | `service/.../handlers/physics.py:286,311` (`UsdPhysics.RevoluteJoint.Define`) | low-level; **no door-controller** consumes it |
| `create_articulated_joint` tool | registered `service/.../handlers/robot.py:7273` | builds a joint; does NOT open it with an arm |
| Static-eyes pre-filter | `scripts/qa/scene_validate.py` (REACH `:264`, TARGET_REACH `:289`, INTERPEN `:309`, SUPPORT `:324`) | **drops humanoids from REACH**, lines 154-158 |
| Function gate | `scripts/qa/gate_one.py` → `simulate_traversal_check` in `service/.../handlers/diagnostics.py:4446-4449` | XY-in-bbox + above-floor + at-rest + upright |

---

## The complete numbered flow

Each step tagged **[USER]/[LLM]/[SYSTEM]** and **[CHEAP-static]** (no physics — USD authoring,
geometry/reach math, schema validation) or **[EXPENSIVE-physics]** (settle/sim in Kit RPC).

### Phase A — request and clarification

1. **[USER] [CHEAP-static]** Types the one-liner: *"a Unitree G1 humanoid opens a Sektion cabinet
   and places an item inside."* This is the full Goal block; the assist user gives no coordinates,
   no joint axis, no "which hand."

2. **[LLM] [CHEAP-static]** Parses intent. Recognizes three sub-tasks: (a) build a hinged cabinet
   (Sektion = IKEA *hinged-door* base cabinet, NOT a drawer), (b) open the door, (c) place an item
   inside. Matches against the catalog and finds **no exact template**; the nearest are
   `CP-NEW-g1-bimanual-tabletop` (robot/controller) and `CP-NEW-drawer-open` (mechanism). The LLM
   must note the mismatch: the drawer template is a **prismatic** pull along X
   (`CP-NEW-drawer-open.json` joint axis `physics:axis="X"`, line in `code`), whereas a Sektion door
   is a **revolute** swing about a vertical hinge.

3. **[LLM] [CHEAP-static]** Because this is T6 and the request is underspecified, asks 1-2
   clarifying questions: which hand opens the door (bimanual: one hand holds/steadies, one
   manipulates), and what the "item" is (a graspable cube proxy). A cooperative assist user answers
   "left hand opens the door, right hand places a small box inside." (If the user does not answer,
   the LLM defaults — left-open / right-place — and says so.)

### Phase B — scene authoring (all cheap, pure USD)

4. **[LLM] [SYSTEM] [CHEAP-static]** Emits world scaffold, mirroring
   `CP-NEW-g1-bimanual-tabletop.json` lines: `create_prim` DomeLight + `set_attribute` intensity
   1000; `create_prim` Ground cube at z=-0.5 scale [20,20,1] + `apply_api_schema`
   PhysicsCollisionAPI; `set_physics_scene_config({"enable_gpu_dynamics": False,
   "broadphase_type":"MBP"})` (CPU dynamics — the drawer template
   `CP-NEW-drawer-open.json` notes CPU is needed for *stable joint simulation*; doubly true for a
   hinged door).

5. **[LLM] [SYSTEM] [CHEAP-static]** Builds the Sektion cabinet from primitives (no Nucleus Sektion
   USD exists locally — same constraint that put `CP-NEW-drawer-open` on primitives, see its
   `thoughts`): `create_prim /World/Cabinet` Xform; `/World/Cabinet/Body` static Cube (no
   RigidBodyAPI → world-anchored, exactly the drawer template's trick); a **Door** rigid Cube on the
   front face; and a **vertical-hinge RevoluteJoint** authored via the low-level path
   (`physics.py:286` `UsdPhysics.RevoluteJoint.Define`, axis Z, limits e.g. 0°→100°). The LLM
   uses `create_articulated_joint` (registered `robot.py:7273`) or raw `create_prim` +
   `set_attribute` on `physics:axis`/`physics:lowerLimit`/`physics:upperLimit` — same authoring
   pattern the drawer template hand-wrote for its prismatic joint.

6. **[LLM] [SYSTEM] [CHEAP-static]** Adds a **door handle** (small Cube protruding from the door's
   robot-facing face — exact analog of `/World/Cabinet/Drawer/Handle` in the drawer template) so the
   arm has something to grasp; adds the **item** `/World/Item` as a rigid Cube (size 0.05) sitting on
   the table within right-arm reach; and the **interior target** — a bin/marker
   `/World/Cabinet/Interior` representing "inside the cabinet" where the item must end up.

7. **[LLM] [SYSTEM] [CHEAP-static]** Spawns the G1: `import_robot(file_path="G1",
   format="asset_library", dest_path="/World/G1")` then `teleport_prim` to stand facing the cabinet
   (mirrors `CP-NEW-g1-bimanual-tabletop` lines, hip z≈0.95). **HONEST RISK:** this is the canonical
   failure point — `import_robot` resolves `g1.usd` via `robot.py:3968`, which needs
   Nucleus/`ASSETS_ROOT_PATH`. On a machine without it, the G1 never loads (the exact reason
   `CP-NEW-g1-bimanual-tabletop` sits at `build 20/21`, `migration_deferred.reason =
   asset_blocked_on_nucleus_only`).

### Phase C — static-eyes pre-filter (CHEAP — catches problems before the expensive gate)

8. **[SYSTEM] [CHEAP-static]** Runs `scripts/qa/scene_validate.py` — builds + settles **once**
   then reads ACTUAL post-settle geometry and checks four classes with no per-cycle physics:
   - **SUPPORT** (`:324`): is `/World/Item` resting on the table (gap to nearest surface in
     [-0.02, 0.10])? Catches a floating or buried item *before* a 180 s sim. **This fires usefully
     here** — if the LLM mis-placed the item's z it is caught now, cheaply.
   - **INTERPENETRATION** (`:309`): only one pick item, so moot.
   - **TARGET_REACH** (`:289`): is the interior target within the *nearest robot's* reach shell?
     **See the blind spot below.**
   - **REACH** (`:264`): is the item within reach?

9. **[SYSTEM] [CHEAP-static] — STATIC-EYES BLIND SPOT (honest).** `scene_validate.py` lines
   **154-158** explicitly **drop legged/humanoid robots from the reach checks**:
   `_LEGGED = ("g1","h1","anymal","humanoid","pelvis","biped","quadruped","spot","go1","go2","unitree")`
   with the comment *"humanoid / legged articulations reach from a SHOULDER, not the pelvis/base …
   the distance-from-base reach heuristic does not apply. Drop them."* Consequence: with **only a G1
   in the scene**, `HAVE_ROBOT` is False → the validator prints *"NO ROBOT detected — reach +
   target-reach checks SKIPPED"* (`:260-261`). So the cheap pre-filter **cannot** tell us whether the
   G1's hand can actually reach the handle, swing the door, or place inside the cabinet. The one
   thing this scenario most needs verified statically — bimanual reach into an enclosure behind a
   swinging door — is the one thing the static eyes refuse to judge. The pre-filter still earns its
   keep on SUPPORT/INTERPEN, but **reach feasibility falls through to the expensive gate**.

10. **[SYSTEM] [CHEAP-static] — what static-eyes CANNOT model even in principle here.** Even if the
    humanoid drop were removed, `scene_validate` has no notion of an **articulated door sweep**: it
    checks a static AABB at settle time, when the door is CLOSED. It would (wrongly) judge the
    interior target as occluded/blocked, or (if the door AABB is thin) miss that the closed door
    *walls off* the interior. There is **no swept-volume / door-arc clearance check** anywhere in the
    validator. This is a genuine capability gap, not just a tuning issue.

### Phase D — controller install (CHEAP authoring of an EXPENSIVE-at-runtime plan)

11. **[LLM] [SYSTEM] [CHEAP-static]** Installs the bimanual controller via
    `setup_bimanual_pick_place_controller` (`humanoid.py:23`). Schema (`tool_schemas.py:5654`)
    forces `robot_family="g1_arm"` (enum, only value) and the handler raises `ValueError` for
    anything else (`humanoid.py:80-84`). The LLM wires `left_arm_sources=["/World/Cabinet/Door/Handle"]`,
    `left_destination=<door-open pose>`, `right_arm_sources=["/World/Item"]`,
    `right_destination="/World/Cabinet/Interior"`, `coordination_mode="sequential"`,
    `plant_feet=True`, `planning_obstacles=["/World/Cabinet/Body","/World/Table"]`.

12. **[LLM] [SYSTEM] [CHEAP-static] — TOOL GAP #1 (confirmed missing).** The controller is a
    **pick-place** state machine: each arm runs `_gen_pick_place_curobo` (`humanoid.py:93` LEFT,
    `:108` RIGHT) which approaches a source, closes the gripper, moves to a destination, releases. It
    has **no door-open / hinge-pull mode.** Grep confirms: `pick_place.py` has zero
    `door|hinge|revolute|swing|arc|articulated-pull|constraint_phrase` branches in its motion logic.
    Feeding the LEFT arm the handle as a "source" makes it try to **pick the handle up** (lift it),
    not **swing it through the hinge arc** — the exact failure the drawer template predicts:
    *"Sensor=handle path treats handle as movable cube — pick-place controller may try to LIFT handle
    vertically instead of pulling"* (`CP-NEW-drawer-open.json` failure_modes) and *"pick-place
    controller cannot drive PrismaticJoint; needs constraint-aware controller"* (its
    `verified_status`). The math kernel for this exists —
    `service/.../multimodal/sub_phase_70c_articulated_drag_controller.py` (PD + force ramp for
    "drawer-open, door-hinge, slider") — but its own docstring says *"the handler in
    handlers/articulated_pull.py will call"* it, and **`handlers/articulated_pull.py` does not
    exist** (confirmed: `ls` → No such file). So the door-opening capability is a **landed
    spec/kernel with no wired tool**.

13. **[SYSTEM] [CHEAP-static]** `plant_feet=True` emits the ankle-FixedJoint snippet
    (`humanoid.py:136-161`). If the G1 USD link `…/left_ankle_roll_link` is absent (placeholder
    asset), it **soft-fails with a print** and continues (`:144-146`) — the body may then be
    unanchored, but no error is raised. Another quiet way the run proceeds to the expensive gate on
    a scene that is already compromised.

### Phase E — the expensive gate (EXPENSIVE-physics)

14. **[SYSTEM] [EXPENSIVE-physics]** `gate_one.py` builds the canonical, **settles**, then runs
    `simulate_traversal_check` for the template's `duration_s` (the G1 template asks for **180 s**,
    `CP-NEW-g1-bimanual-tabletop.json` `simulate_args.duration_s`). This is the costly full-physics
    rollout. **Sequential V0:** LEFT arm runs to completion, THEN RIGHT (Kit RPC is single-tenant —
    `humanoid.py` header + the template's failure_modes both call this out).

15. **[SYSTEM] [EXPENSIVE-physics] — gate success-criterion (the OUTCOME measure).** From
    `diagnostics.py:4446-4449`: for a single delivered item,
    `success = bool(in_xy and above_floor and at_rest and upright_ok)` — i.e. the item's final XY is
    inside the target bbox, it is above the floor, has stopped moving (`speed < rest_speed`), and is
    upright (`_world_up_dot >= upright_tol`, `:4443-4444`). For multi-item it is
    `bool(delivered) and upright_ok` (any one delivered + primary upright).

16. **[SYSTEM] [EXPENSIVE-physics] — GATE GAP #2 (confirmed missing): no "open door / inside
    enclosure" semantics.** The gate measures *"is the item's XY inside the target AABB and at
    rest."* It has **no concept of the door state**. Grep of `diagnostics.py` shows containment is
    purely `in_target_xy` against a bbox (`:3975`) plus `_cube_support` `under_target` (`:4464`);
    there is **no check that the door was opened**, no check that the item reached the interior
    *through* an open door rather than clipping through closed geometry, and no
    "place-inside-an-enclosure" verifier. So even a *physically nonsensical* run — item tunnels
    through a still-closed door into the interior bbox — would be scored `success=True`. Conversely,
    a correct door-open where the item lands 1 cm outside the interior AABB scores `False`. The gate
    is a flat-bbox delivery test borrowed from the cube-in-bin canonicals; **it does not model this
    task's actual outcome.** (Compare the drawer template, which had to *abandon* the gate entirely
    and measure success via a raw `DrawerJoint` position attribute ≥ 0.25 m —
    `CP-NEW-drawer-open.json` `verify_args` — because cube-in-bin delivery is meaningless for
    articulated mechanisms. The door scenario would need the same kind of custom verifier, which does
    not exist for revolute joints + containment.)

### Phase F — outcome

17. **[SYSTEM] [EXPENSIVE-physics]** **Realistic outcome on a Nucleus-equipped machine:**
    `success=False`. The LEFT arm grasps the handle but the pick-place state machine tries to **lift**
    it instead of swinging the hinge → the door barely moves (or the handle slips) → the interior
    stays walled off → the RIGHT arm cannot place the item *inside* (it collides with the
    still-mostly-closed door, registered as a `planning_obstacle`) → item never reaches the interior
    AABB → gate `False`. **Diagnosis (`diagnose_pickplace`, `diagnostics.py:~3505`):** likely
    `carried_but_not_delivered` for the item, plus a planfail/contact trace for the door arm. The
    door-state and "did we actually open it" truth is invisible to the gate; only `scene_eyes` joint
    readouts would reveal the door barely rotated.

18. **[SYSTEM] [EXPENSIVE-physics]** **More likely outcome on a typical machine:** `BUILD_FAIL` /
    asset-blocked at step 7 — `import_robot("G1")` cannot resolve `g1.usd` (no Nucleus), so the
    pipeline never reaches the gate at all. This is the documented state of the only G1 canonical
    (`CP-NEW-g1-bimanual-tabletop.json` line 39: *"build 20/21 (G1 SimReady asset missing on local
    Nucleus)"*).

19. **[LLM] [CHEAP-static]** Reports honestly to the user: the scene **builds** (cabinet, hinge,
    G1-if-asset-present), but the task **cannot be completed end-to-end** because (a) no controller
    drives a revolute door — the kernel exists but its handler does not, and (b) the gate cannot
    score "placed inside an opened cabinet." Recommends the two missing pieces below rather than
    claiming a pass.

---

## Tool gaps (every tool needed that does NOT exist — grep-confirmed)

1. **`articulated_pull` / door-open controller handler — MISSING.**
   `handlers/articulated_pull.py` does not exist (`ls` → No such file). The PD/force-ramp math
   kernel for *"drawer-open, door-hinge, slider"* is landed at
   `service/.../multimodal/sub_phase_70c_articulated_drag_controller.py`, but nothing in
   `tool_executor.py` codegen calls it, and `pick_place.py` has no
   `door|hinge|revolute|swing|constraint_phrase` motion branch. Without it, the only way to "open"
   anything is to mis-use pick-place, which lifts instead of swings.

2. **Door-aware / place-inside-enclosure gate verifier — MISSING.**
   `simulate_traversal_check` (`diagnostics.py:4446`) only knows XY-in-bbox + at-rest + upright. No
   verifier reads the door's `RevoluteJoint` position to confirm it opened, and none checks the item
   entered the interior *via the opening* (vs. clipping through closed geometry). The drawer template
   had to bypass the gate with a hand-written joint-position criterion; an equivalent revolute+
   containment verifier is absent.

3. **Static swept-door / arc-clearance pre-filter — MISSING.**
   `scene_validate.py` checks only static settle-time AABBs (REACH/INTERPEN/SUPPORT/TARGET_REACH).
   It has no door-sweep volume, so it cannot cheaply confirm the door clears the G1/table as it
   swings, nor that the open-door interior is reachable.

4. **Humanoid (G1) reach in the static pre-filter — DISABLED BY DESIGN.**
   Not "missing code" but a deliberate gap: `scene_validate.py:154-158` drops `g1`/`unitree`/
   `humanoid` from the reach + target-reach checks (shoulder-based workspace ≠ base-distance
   heuristic). So for a G1-only scene the cheap pre-filter skips reach entirely (`:260-261`),
   pushing all reach risk to the expensive gate. A shoulder-anchored humanoid reach model would be
   needed to close this.

## Honesty ledger

- The **robot template is a draft** that has never passed its gate (Nucleus asset blocker).
- The **cabinet template is `stable_fail`** AND is a *drawer (prismatic)*, not the requested
  *hinged door (revolute)* — a structural mismatch, not a parameter tweak.
- The **bimanual controller is real and landed**, but it is pick-place only — its V0 scope
  explicitly defers WBC and has no articulated-mechanism mode.
- The **door-open capability is unverified**: a math kernel exists, its handler does not.
- The **gate does not measure this task's real outcome** (open + place-inside); a pass here would be
  a false positive and a fail could be a false negative.

**Bottom line:** the scene is buildable; the *task* is not completable or gradeable today without
the four tool gaps above being closed.
