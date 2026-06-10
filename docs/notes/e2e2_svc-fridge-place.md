# E2E trace — [svc-fridge-place] T6 / g1 / open-door + place-on-shelf-inside

**Scenario id:** `svc-fridge-place`
**Domain:** service / domestic
**One-sentence request:** *"a robot opens a fridge door and places an item on a shelf inside"*
**Tier:** T6 (multi-stage dialog; articulated appliance + place-inside-a-nested-mechanism)
**Robot:** Unitree G1 humanoid (`robot_family="g1_arm"`) — the only bimanual canonical robot
**Task:** open hinged (revolute) fridge door → place item on an interior shelf

**Template-match (grep-confirmed).** No template covers this. Closest set:
- `workspace/templates/CP-NEW-g1-bimanual-tabletop.json` — the ONLY G1 bimanual canonical; gate-blocked on the NVIDIA SimReady G1 asset (`build 20/21`).
- `workspace/templates/CP-NEW-drawer-open.json` — the ONLY articulated-mechanism manipulation canonical; recorded `stable_fail` (its own controller can't drive the joint). It is a **prismatic drawer**, not a **revolute door**.
- `workspace/templates/CP-NEW-turn-faucet.json` — the only **revolute**-handle template, but it opens the joint by **commanding `set_joint_targets` on a DriveAPI** (a joint-teleport, not a physical pull).
- `workspace/templates/CP-NEW-machine-tender-door-interlock.json` — has a "door," but it is **visual-only**: the door state is a `displayColor` toggle + a custom `door_closed:bool` attr (`code`: `set_attribute(... "primvars:displayColor" ... red=open)`). No joint, no arm interaction.

This trace is a synthesis. The verdict is **build-then-fail**, and it reveals a **NEW class-level gap** the prior `e2e_humanoid-cabinet` trace did NOT surface (see "New class-level finding").

---

## Cast of real code/assets this trace is grounded in

| Thing | Path : line | State |
|---|---|---|
| Target appliance (real articulation) | `/home/anton/kimate_assets/assets/Lightwheel_oz5iukPxYq_KitchenRoom/Refrigerator001/Refrigerator001.usd` | **complete**, 14 joints under articulation root `/root` |
| ArtVIP fridges (8 variants) | `/home/anton/kimate_assets/assets/ArtVIP/Articulated_objects/major_appliances/refrigerator/fridge_{1..4}, refrigerator_{1,6,7,8}` | **broken copy** — every `resource/` dir is EMPTY (0 files); main USD references missing sublayers `resource/material.usd`, `resource/v_0/link_default_0.usd` → 0 joints, 0 rigids load |
| G1 bimanual controller | `service/.../handlers/humanoid.py:23` `_gen_setup_bimanual_pick_place_controller` | landed, V0, sequential-only, **pick-place only** |
| G1 asset resolution | `service/.../handlers/robot.py:3968` (`"g1": "g1.usd"`), `scene_blueprints.py:43` | needs Nucleus / `ASSETS_ROOT_PATH` |
| Revolute-joint authoring (low-level) | `service/.../handlers/physics.py:286` `UsdPhysics.RevoluteJoint.Define` | builds a joint; nothing **opens** it with an arm |
| `set_joint_targets` (joint-teleport cheat) | `service/.../handlers/physics.py:174` `_gen_set_joint_targets` | applies DriveAPI + sets target — drives the joint **directly**, not via the arm |
| `create_articulated_joint` tool | `service/.../handlers/robot.py:4522` / register `:7273` | builds a joint; does NOT open it |
| Drag-controller math kernel | `service/.../multimodal/sub_phase_70c_articulated_drag_controller.py` | landed kernel; **its handler `handlers/articulated_pull.py` does NOT exist** (`ls` → No such file) |
| Static-eyes pre-filter | `scripts/qa/scene_validate.py` (REACH `:264`, TARGET_REACH `:289`, SUPPORT `:324`) | **drops humanoids from REACH** (`:154-158`) |
| Function gate | `scripts/qa/gate_one.py` → `simulate_traversal_check` `service/.../handlers/diagnostics.py:4436-4449` | XY-in-bbox + above-floor + at-rest + upright; multi-cube = `bool(delivered) and upright_ok` |
| `place_on_shelf` / `place_inside` resolver | (none) | **MISSING** — grep `service/` → 0 hits |

### The target asset, characterized (live USD read)

`Refrigerator001.usd` is a **2.05 m tall, ~1.04 × 1.08 m** appliance, articulation root `/root`, 14 joints:

- **4 revolute DOORS** — `Door1/Door2` axis Z, limits `[-150°, 0°]`; `Door3/Door4` axis Z, limits `[0°, 150°]`. **The door joints have ZERO applied API schemas** (`GetAppliedSchemas() == []`): **no DriveAPI** → they are **passive free-swinging hinges**. There is nothing to "command"; the only way to open them is to physically pull the handle.
- **8 prismatic CONTAINERS** — `Container1..8`, axis Y, travel `[0, 0.20 m]`. These are the **pull-out interior shelves / drawers**. *"A shelf inside"* is one of these — a **movable prismatic body**, not a static ledge.
- **1 revolute SWITCH** (axis X, `[-20°, 0°]`) + **1 FixedJoint** body→world anchor.

This is a far richer articulation than the Sektion cabinet of the prior trace (one revolute door + a static interior bin).

---

## The complete numbered flow

Tags: **[USER]/[LLM]/[SYSTEM]** and **[CHEAP-static]** (USD authoring, reach/geometry math, schema validation — no physics) or **[EXPENSIVE-physics]** (settle/sim in Kit RPC).

### Phase A — request and clarification

1. **[USER] [CHEAP-static]** Types the one-liner: *"a robot opens a fridge door and places an item on a shelf inside."* No robot named, no coordinates, no which-shelf, no which-hand.

2. **[LLM] [CHEAP-static]** Parses intent → three sub-tasks: (a) build/instantiate an articulated fridge, (b) **open a hinged (revolute) door**, (c) **place an item on an interior shelf**. Catalog match → no exact template; nearest are the four listed above, all drafts/fails. The LLM must flag the mismatch: drawer-open is **prismatic**, faucet "opens" by **joint-teleport**, the interlock door is **visual-only**.

3. **[LLM] [CHEAP-static]** Robot selection: the request says "a robot." The prior cabinet trace shows the in-house articulated-mechanism story is built around the G1 bimanual canonical (one hand steadies, one manipulates), so the LLM picks **G1** (`robot_family="g1_arm"`, the only enum value the schema accepts — `humanoid.py:80-84` raises `ValueError` otherwise). Asks 1–2 clarifying Qs: *which door* (the 4-door fridge has Door1/2 swinging one way, Door3/4 the other) and *which shelf* (Container1..8). Cooperative user: "the main left door, place a small box on the top pull-out shelf." If unanswered, LLM defaults (Door1 + Container1) and says so.

### Phase B — scene authoring (CHEAP, pure USD)

4. **[LLM] [SYSTEM] [CHEAP-static]** World scaffold, mirroring `CP-NEW-g1-bimanual-tabletop.json` / `CP-NEW-drawer-open.json`: `create_prim` DomeLight + intensity 1000; Ground cube z=-0.5 scale [20,20,1] + `apply_api_schema` PhysicsCollisionAPI; **`set_physics_scene_config({"enable_gpu_dynamics": False, "broadphase_type":"MBP"})`** — CPU dynamics, which the drawer template documents as required for *stable joint sim*; **doubly true here with a 13-DOF passive articulation**.

5. **[LLM] [SYSTEM] [CHEAP-static] — ASSET FORK.** Two ways to get the fridge, both with a real defect:
   - **(i) Reference the real articulated asset.** `import_robot`/`create_reference` the **Lightwheel** `Refrigerator001.usd` (the ONLY locally-complete articulated fridge). It loads with all 14 joints. **NEW ASSET-INTEGRITY GAP:** the 8 **ArtVIP** fridges — the "243 articulated appliances" pitch — are **broken in this copy**: every `resource/` dir is empty, so `Usd.Stage.Open(model_fridge_1.usd)` yields **0 joints / 0 rigids** (the mesh+joint sublayers `resource/material.usd`, `resource/v_0/link_default_0.usd` are missing). An LLM that picks an ArtVIP fridge by name builds an **invisible, un-articulated stub** and never knows (USD sublayer-miss is a *warning*, not an error). Only the single Lightwheel fridge is usable.
   - **(ii) Build from primitives** (the drawer-template path): `create_prim /World/Fridge/Body` static Cube + `/World/Fridge/Door` rigid Cube + a **vertical-hinge RevoluteJoint** via `physics.py:286` (axis Z, `[0°,120°]`) + an **interior shelf** as a **prismatic** body (`create_articulated_joint`, axis Y) to honor "a shelf inside" being a pull-out. This is a lot of hand-authoring and still inherits every controller gap below.

6. **[LLM] [SYSTEM] [CHEAP-static]** Adds: a **door handle** Cube on the door's robot-facing face (grasp target — analog of `/World/Cabinet/Drawer/Handle` in the drawer template); the **item** `/World/Item` rigid Cube (size 0.05) on a table within reach; and the **place target** = the top pull-out shelf body (`Refrigerator001_Container1` for option i, or `/World/Fridge/Shelf` for option ii).

7. **[LLM] [SYSTEM] [CHEAP-static]** Spawns the G1: `import_robot(file_path="G1", format="asset_library", dest_path="/World/G1")` + `teleport_prim` to stand facing the door (hip z≈0.95). **HONEST RISK (same as cabinet trace):** `g1.usd` resolves via `robot.py:3968` and needs Nucleus/`ASSETS_ROOT_PATH`; on a machine without it the G1 never loads → `BUILD_FAIL` at this step (documented state of `CP-NEW-g1-bimanual-tabletop`, `build 20/21`).

### Phase C — static-eyes pre-filter (CHEAP)

8. **[SYSTEM] [CHEAP-static]** `scripts/qa/scene_validate.py` settles **once** and reads post-settle geometry: SUPPORT (`:324`, item resting on table, gap in [-0.02,0.10]) and INTERPEN (`:309`) fire usefully and cheaply.

9. **[SYSTEM] [CHEAP-static] — STATIC-EYES BLIND SPOT (carried over).** `scene_validate.py:154-158` drops `g1`/`unitree`/`humanoid` from REACH + TARGET_REACH (shoulder-based reach ≠ base-distance heuristic). With only a G1 present, `HAVE_ROBOT=False` → *"NO ROBOT detected — reach checks SKIPPED"* (`:260-261`). The one thing this scene most needs verified — can the G1's hand reach the handle, swing a 1m-deep door, and reach a shelf **1.0–1.6 m up** on a 2.05 m fridge — is the one thing the cheap eyes refuse to judge.

10. **[SYSTEM] [CHEAP-static] — what static-eyes CANNOT model even in principle.** No **swept-door arc** check (door AABB is read CLOSED, so the interior reads as walled off or, if the door panel is thin, the validator misses that the closed door occludes the shelf). **NEW:** and no **nested-articulation reach** notion — the shelf's reachable position depends on **how far the prismatic container is pulled out** AND **how far the revolute door is swung**; a static AABB at settle (door closed, shelf in) cannot represent the *operative* configuration the place must target.

### Phase D — controller install (CHEAP authoring of an EXPENSIVE-at-runtime plan)

11. **[LLM] [SYSTEM] [CHEAP-static]** Installs `setup_bimanual_pick_place_controller` (`humanoid.py:23`): `left_arm_sources=["…/Handle"]`, `left_destination=<door-open pose>`, `right_arm_sources=["/World/Item"]`, `right_destination=<shelf>`, `coordination_mode="sequential"`, `plant_feet=True`, `planning_obstacles=["…/Body","/World/Table"]`.

12. **[LLM] [SYSTEM] [CHEAP-static] — TOOL GAP (door-open controller, carried over + sharpened).** The controller is **pick-place only**: each arm runs `_gen_pick_place_curobo` (`humanoid.py:93` left, `:108` right) = approach source → close gripper → move to dest → release. Grep confirms `pick_place.py` has **no** `door|hinge|revolute|swing|arc` motion branch. Feeding the handle as a "source" makes the arm try to **lift** it, not **swing the hinge arc** — exactly the drawer template's failure (*"pick-place controller may try to LIFT handle vertically instead of pulling"*). The PD/force-ramp kernel exists (`sub_phase_70c_articulated_drag_controller.py`) but its handler **`articulated_pull.py` does not exist**. **Sharper than the cabinet case:** the Lightwheel door joint has **no DriveAPI at all** (applied schemas `[]`), so even the **turn-faucet joint-teleport cheat** (`set_joint_targets` → `physics.py:174`) cannot be used as-authored — it would have to first `DriveAPI.Apply`, then command an angle, which is **not a manipulation at all** (the arm never touches the door; the joint is teleported open). There is no honest controller path.

13. **[SYSTEM] [CHEAP-static]** `plant_feet=True` emits the ankle-FixedJoint snippet (`humanoid.py:136-161`); if `…/left_ankle_roll_link` is absent (placeholder G1) it **soft-fails with a print** (`:144-146`) and proceeds unanchored. A quiet way the run reaches the gate already compromised.

### Phase E — the expensive gate (EXPENSIVE-physics)

14. **[SYSTEM] [EXPENSIVE-physics]** `gate_one.py` builds, **settles**, runs `simulate_traversal_check` for `duration_s` (G1 template: **180 s**). Sequential V0: LEFT then RIGHT (Kit RPC single-tenant).

15. **[SYSTEM] [EXPENSIVE-physics] — gate success-criterion (`diagnostics.py:4436-4449`).** Single item: `success = in_xy and above_floor and at_rest and upright`. Containment is a flat **target-AABB XY test** (`:4436-4438`) + `_cube_support` `under_target` (`:4464`).

16. **[SYSTEM] [EXPENSIVE-physics] — GATE GAP (place-inside, carried over) + NEW nested-shelf failure.** The gate has **no door-state concept** — an item that tunnels through a still-closed door into the interior AABB scores `True`; a correct open where the item lands 1 cm outside scores `False`. **NEW and worse here:** the **target shelf is a moving prismatic body**. The gate computes the target bbox **once** (`bb` from `target_path`); if the shelf is pulled out during the run, the AABB the gate measured is **stale** — the item can be perfectly placed on the *moved* shelf and read OUTSIDE the gate's frozen bbox (false-negative), or read INSIDE the bbox while actually resting on the fridge floor / a different container (false-positive). The gate also has **no "on the shelf vs in the fridge cavity"** discrimination and **no joint readout** confirming the door opened or the shelf extended. The drawer template had to **abandon the gate** and measure a raw `DrawerJoint` position attr ≥ 0.25 m; this scenario needs **that AND a containment check against a moving frame** — neither exists.

### Phase F — outcome

17. **[SYSTEM] [EXPENSIVE-physics] — outcome on a Nucleus-equipped machine: `success=False`.** LEFT arm grasps the handle but pick-place tries to **lift** → the passive door barely rotates (or the handle slips) → interior stays walled off → RIGHT arm cannot reach a shelf behind a near-closed door (door is a `planning_obstacle` → cuRobo plan_fail or collision) → item never reaches the shelf frame → gate `False`. `diagnose_pickplace` (`diagnostics.py:~3505`) reports `carried_but_not_delivered` + a planfail/contact trace; only `scene_eyes` joint readouts would reveal the door barely moved and the shelf never extended.

18. **[SYSTEM] [EXPENSIVE-physics] — more likely on a typical machine: `BUILD_FAIL`.** Either `import_robot("G1")` can't resolve `g1.usd` (no Nucleus, step 7), **or** the LLM picked an ArtVIP fridge → silent empty-`resource/` stub (step 5) → the "fridge" is an invisible un-articulated Xform and the gate runs against geometry that isn't there.

19. **[LLM] [CHEAP-static]** Reports honestly: the scene **builds** (with the Lightwheel fridge + G1-if-asset-present), but the task **cannot be completed or graded** today: (a) no controller physically opens a passive revolute door (kernel exists, handler missing; the joint-teleport cheat isn't manipulation and isn't even pre-wired here), and (b) the gate cannot score "placed on a movable interior shelf behind an opened door." Recommends the gaps below rather than claiming a pass.

---

## Tool gaps (NEW — beyond the 4 in `e2e_humanoid-cabinet.md`)

The cabinet trace already logged: (1) missing `articulated_pull` door controller, (2) missing place-inside gate verifier, (3) missing swept-door static check, (4) humanoid reach disabled in static eyes. **This fridge scenario surfaces FOUR additional, distinct gaps:**

1. **Nested-articulation place target (prismatic shelf inside a revolute door) — UNMODELED end-to-end.**
   The place target is a **movable prismatic body** that must first be **pulled out** (a *second* articulated-pull, on top of the door). No controller pulls a shelf; no resolver maps "a shelf inside" → "extend Container_k then place on its top face." Grep: no `place_on_shelf` / `place_inside` / `interior_shelf` resolver anywhere in `service/`. This is a genuinely new topology vs the cabinet's single door + static bin.

2. **Gate containment against a MOVING target frame — false-pos/neg by construction.**
   `simulate_traversal_check` (`diagnostics.py:4436`) freezes `target_path`'s AABB once. A pulled-out shelf invalidates it. No "place relative to the shelf's *current* pose" verifier and no joint-position readout for the shelf/door. The drawer template's raw-joint-attr workaround does not compose with a containment requirement.

3. **Asset-integrity pre-flight for articulated USDs — MISSING.**
   8/9 local fridges (all ArtVIP) load with **empty `resource/`** → 0 joints, silently. Nothing validates that a referenced articulated asset actually resolved its sublayers / has the expected DOF before the LLM builds on it. A `verify_articulation(path, min_joints=…)` pre-flight would catch the invisible-stub class (which extends to the broader "243 appliances" claim — most are unverified in this copy).

4. **Passive-joint manipulation has NO honest path; the only "open" tool teleports the joint.**
   The Lightwheel door joints carry **no DriveAPI** (`[]`) — they are free hinges, the physically-correct model of a real fridge. The single revolute-open mechanism in the codebase (`set_joint_targets`, used by turn-faucet) **commands a drive target** = teleports the joint open without the arm doing work. So the only "door-open" capability that exists is a sim2real cheat in the same family as the banned FixedJoint grip. A force/contact-driven pull (the `70c` kernel) is the only honest option and has no handler.

## New class-level finding (the KEY deliverable)

**Pick-place — even the articulated-aware version the cabinet trace asked for — fundamentally breaks on a *nested, multi-DOF container whose interior surface is itself a movable joint*.** The humanoid-cabinet trace established that a single revolute door needs a **revolute-pull controller** + a **place-inside gate**. This fridge scenario shows that is **necessary but not sufficient**: a fridge is a **chained articulation** — *open the revolute door, THEN extend a prismatic shelf, THEN place onto the shelf's moving top face, while the door must be held open by a second arm.* This is a whole task family (fridge / oven / dishwasher rack / filing cabinet / tool chest / parts bin drawer — exactly the "243 articulated appliances" Kimate shipped) that needs THREE new classes the codebase lacks:

- a **constraint-aware sequenced-articulation controller** (pull-door → pull-shelf → place), driving **passive** joints by **contact force**, not by joint-target teleport;
- a **moving-frame containment gate** that scores "item came to rest ON the shelf in its *current* extended pose, behind an *actually-opened* door," reading live joint positions;
- an **articulated-asset pre-flight** (`verify_articulation`) so the agent doesn't silently build on a broken empty-`resource/` appliance.

Without these, the entire articulated-appliance asset library is buildable-but-ungradeable, and every "open X and put Y inside" service/domestic task fails the same way: the door barely moves, the shelf never extends, and the gate either lies or can't see it.

## Honesty ledger

- The **G1 template** has never passed its gate (Nucleus asset blocker).
- The **only complete local fridge** is the single Lightwheel `Refrigerator001.usd`; the **8 ArtVIP fridges are broken** in this copy (empty `resource/`).
- The **bimanual controller is real and landed** but pick-place only — no articulated-mechanism mode.
- The **revolute door joints are passive** (no DriveAPI); the only existing "open" tool (`set_joint_targets`) **teleports** the joint and never touches the door — not a faithful manipulation.
- The **gate cannot model** open-door + place-on-a-moving-shelf; a pass would be a false positive and a fail could be a false negative.

**Bottom line:** the scene is buildable **only** with the one Lightwheel fridge + a Nucleus-resident G1; the *task* is neither completable nor gradeable today, and it defines a new task class (sequenced nested-articulation place-inside) that needs three missing capabilities.
