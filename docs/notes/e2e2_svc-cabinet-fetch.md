# E2E trace — [svc-cabinet-fetch] service/domestic / franka / open-drawer + fetch

**Scenario id:** `svc-cabinet-fetch`
**Domain:** service / domestic
**One-sentence request:** *"open a Sektion cabinet drawer and fetch an item from inside"*
**Tier:** T6 (multi-stage: articulated prismatic-open → reach-INTO-cavity → grasp → EXTRACT-out)
**Robot:** Franka Panda (`robot_name="franka"`, parallel-jaw)
**Task:** open-drawer + fetch (pull a prismatic drawer open, then reach down/in and pick an item OUT)

**Template-match (grepped):** The honest closest single template is
`workspace/templates/CP-NEW-drawer-open.json` — the **only** articulated-prismatic-pull canonical,
recorded `stable_fail` (`verified_status` line 39: *"pick-place controller cannot drive
PrismaticJoint; needs constraint-aware controller"*) and `migration_deferred.reason="asset_blocked"`
(line 43-46: needs the Nucleus Sektion USD; built from primitive cubes instead). That template stops
at *opening* the drawer — its own success criterion (`verify_args.min_pull_distance_m=0.25`, line 27)
is a joint-position read. **It never fetches anything.** The "fetch from inside" half has **no template
at all**. So this trace is a synthesis and the verdict is **build-then-fail at the fetch stage**, with
one NEW class-level gap on top of the already-known drawer-open gap.

This is **NOT** the prior `e2e_humanoid-cabinet.md` trace. That one was G1-humanoid + **revolute hinged
door** + **place-INTO** (deposit). This one is Franka + **prismatic drawer** + **pick-OUT / extract**.
The extraction direction (reach into a shallow, overhung, robot-facing cavity, grasp, withdraw) is the
new axis.

---

## Cast of real code this trace is grounded in

| Thing | File:line | State |
|---|---|---|
| Closest template (open only) | `workspace/templates/CP-NEW-drawer-open.json` | `stable_fail`; prismatic axis=X, lower=-0.30 (`code` block); `migration_deferred` asset_blocked |
| Sektion asset (Nucleus, not local) | `Props/Sektion_Cabinet/sektion_cabinet_instanceable.usd` (`docs/notes/ASSET_TUTORIAL_IDEAS.md:11,118`) | NOT on Kimate disk; is the base of NVIDIA's Isaac-Franka-Cabinet RL task — **top DRAWER (prismatic) + lower doors (revolute)** |
| Real kitchen drawer scene (Kimate) | `/home/anton/kimate_assets/assets/Collected_kitchen_scene_teleop_closed_drawer/kitchen_scene_teleop_closed_drawer.usd` (USD crate 0.8.0, 11 MB) | local; `strings` shows `/Apple_group`, `CabinetsK…`, `…heckBox` — a closed-drawer teleop scene with an apple item; **teleop-recorded, no autonomous controller** |
| ArtVIP interactive kitchen | `/home/anton/kimate_assets/assets/ArtVIP/Interactive_scene/kitchen/{cupboard,largecabinet,Interactive_kitchen.usd}` | local; articulated cupboard/cabinet — candidate real-asset substitute |
| Prismatic-joint authoring | `CP-NEW-drawer-open.json` `code`: `create_prim PhysicsPrismaticJoint` + `set_attribute physics:axis/lowerLimit/localPos` | low-level, hand-written per template |
| `set_joint_targets` (drive a joint) | `service/.../handlers/physics.py:174` `_gen_set_joint_targets` (DriveAPI linear/angular, target_position/velocity) | EXISTS — can command the joint directly (the "cheat-open"), but is decoupled from the arm |
| `setup_pick_place_controller` | `service/.../handlers/pick_place.py:314` (RmpFlow + ArticulationMotionPolicy) | EXISTS; **top-down only**: APPROACH z+0.12 → DESCEND straight-down → GRASP → LIFT z+0.20 (`pick_place.py:392,586,754,776`) |
| Pull-via-spline workaround | `CP-NEW-drawer-open.json` `code`: `target_source="spline"`, `source_paths=[Handle]`, `grip_style="friction"` | the documented hack; `failure_modes` line 35-37 explain why it diverges |
| Function gate | `scripts/qa/gate_one.py` → `simulate_traversal_check` `service/.../handlers/diagnostics.py:3920` | scores **cube XY-in-target-bbox + above-floor + at-rest + upright** (`:3926,3968-3976`) — i.e. *delivered TO a place*, NOT *extracted FROM a cavity* |
| Static reach pre-filter | `scripts/qa/reach_validate.py:5` | doc string literally lists *"inside an enclosure (collision)"* as an UNREACHABLE class for a top-down approach |
| Static scene pre-filter | `scripts/qa/scene_validate.py` (SUPPORT `:357,367` "buried inside") | flags "nested inside a bin/tray" as buried; **has no notion of a moving prismatic lid/overhang** |

---

## The complete numbered flow

Each step tagged **[USER]/[LLM]/[SYSTEM]** and **[CHEAP-static]** (USD authoring, geometry/reach math,
schema validation — no physics) or **[EXPENSIVE-physics]** (settle/sim in the single-tenant Kit RPC).

### Phase A — request & clarification

1. **[USER] [CHEAP-static]** Types the one-liner: *"open a Sektion cabinet drawer and fetch an item
   from inside."* Full Goal block — no coordinates, no joint axis, no item named, no "which drawer."

2. **[LLM] [CHEAP-static]** Parses intent into **four** sub-tasks: (a) build/load a Sektion cabinet
   with a **prismatic drawer**, (b) put a graspable **item INSIDE** the drawer, (c) **pull the drawer
   open**, (d) **reach into the open drawer and pick the item OUT** ("fetch"). Catalog match: only
   `CP-NEW-drawer-open` is close, and only for sub-tasks (a)+(c). Sub-tasks (b)+(d) — *item-inside* and
   *extract* — have **no template**. The LLM should flag this honestly.

3. **[LLM] [CHEAP-static]** Underspecified → asks 1-2 clarifying questions: *which* item (defaults to a
   small graspable cube/`yellow_block` proxy, per `ASSET_TUTORIAL_IDEAS.md:118`), and *where to fetch it
   to* (a counter/tray, since "fetch" implies extract-and-deliver-out, not just pick). A cooperative user
   answers "a small block, set it on the table." If no answer, the LLM defaults and says so.

### Phase B — scene authoring (all CHEAP, pure USD)

4. **[LLM] [SYSTEM] [CHEAP-static]** World scaffold mirroring `CP-NEW-drawer-open.json` `code`:
   `create_prim` DomeLight + intensity 1000; Ground cube z=-0.5 scale[20,20,1] + PhysicsCollisionAPI;
   **`set_physics_scene_config({"enable_gpu_dynamics": False, "broadphase_type":"MBP"})`** — CPU dynamics
   for stable joint sim (template `thoughts`); a Table at z=0.375 with the Franka base ON it at z=0.75.

5. **[LLM] [SYSTEM] [CHEAP-static]** Cabinet. Two honest options, both with problems:
   - **(i) Nucleus Sektion** `add_reference(Props/Sektion_Cabinet/sektion_cabinet_instanceable.usd)` —
     faithful (real prismatic drawer + DriveAPI joints), but **not on disk** (`migration_deferred`
     asset_blocked; only on the Nucleus server the local install lacks).
   - **(ii) Primitive rebuild** (what the template actually does): `/World/Cabinet/Body` static Cube
     (no RigidBodyAPI → world-anchored), `/World/Cabinet/Drawer` rigid Cube,
     `create_prim PhysicsPrismaticJoint` with `physics:axis="X"`, `lowerLimit=-0.30`, `upperLimit=0.0`,
     plus a `/World/Cabinet/Drawer/Handle` Cube on the robot-facing face. This is what builds.
   - **(iii) Kimate local** `add_reference(.../Collected_kitchen_scene_teleop_closed_drawer/…usd)` or the
     ArtVIP cupboard — a REAL articulated drawer exists locally now, **but** no tool resolves it as a
     drawer (no name→USD lookup; cf. TOOL_GAP_INVENTORY_V2 M13 for *bins* — the drawer analog doesn't
     exist), and it was authored for **teleop**, not an autonomous arm.

   The LLM takes (ii) — same path the template took — to stay buildable.

6. **[LLM] [SYSTEM] [CHEAP-static]** **The NEW step the template never does: put an item INSIDE the
   drawer.** `create_prim /World/Cabinet/Drawer/Item` rigid Cube positioned in the drawer's interior
   volume (above the drawer floor, below the cabinet overhang, recessed behind the closed front face).
   This is geometrically fine to *author*, but it is the seed of the failure: the item now sits in a
   space that, when closed, is fully enclosed, and when open is **overhung by the static cabinet body**
   and **walled by the drawer sides** — a top-down gripper cannot drop straight onto it.

7. **[LLM] [SYSTEM] [CHEAP-static]** `robot_wizard(robot_name="franka", position=[0,0,0.75])` facing the
   drawer (template line). Franka home + parallel-jaw.

### Phase C — static pre-filter (CHEAP)

8. **[LLM] [SYSTEM] [CHEAP-static]** Runs the reach/scene pre-filter (`scene_validate.py` /
   `reach_validate.py`, if exposed — note these are bench scripts, not yet LLM-callable handlers; cf.
   TOOL_GAP_INVENTORY_V2 M6). Two things happen:
   - **REACH of the handle**: handle at x≈0.435, well inside Franka's ~0.85 m envelope → PASS.
   - **REACH of the ITEM when CLOSED**: the validator probes the item at its **closed** position. It is
     inside the cabinet → `reach_validate` would correctly call it UNREACHABLE ("inside an enclosure
     (collision)", `reach_validate.py:5`). But the LLM *expects* this (the drawer isn't open yet), so it
     can't act on the verdict — **the static eyes have no concept of "reachable AFTER the drawer opens."**
     There is no time/articulation-state axis in the pre-filter; it judges one frozen frame.
   - **SUPPORT**: `scene_validate.py:357,367` would read the item as "buried inside" the drawer/cabinet
     AABB and emit a false SUPPORT violation — it can't tell a drawer interior (legitimate rest) from a
     part penetrating its support.

   Net: the cheap filter is **blind to the entire articulated-fetch geometry**. It neither clears nor
   correctly blocks the scenario. (This is a static-eyes blind spot, not the headline gap.)

### Phase D — controller setup (CHEAP author, then EXPENSIVE run)

9. **[LLM] [SYSTEM] [CHEAP-static]** Must wire **two sequential behaviours**, and there is no single tool
   for it:
   - **D1 — open the drawer.** Per the template, `setup_pick_place_controller(target_source="spline",
     source_paths=["…/Handle"], grip_style="friction", pick_target=[0.435,0,0.95],
     drop_target=[0.135,0,0.95])`. The spline controller is asked to "carry the handle" 0.30 m in -X to
     fake a pull. The template's own `failure_modes` (lines 35,37) explain why this is wrong: the handle
     **moves with the drawer**, so a world-space waypoint plan diverges; and the pick-place controller
     treats the handle as a liftable cube and tries to **lift it vertically** (its hardcoded APPROACH→
     DESCEND→GRASP→**LIFT z+0.20**, `pick_place.py:392,754,776`) instead of pulling horizontally. The
     honest alternative is `set_joint_targets(joint=DrawerJoint, target_position=-0.30)`
     (`physics.py:174`) to **cheat-open** the joint directly — but that is *not the arm doing it*; it is
     a scripted joint write decoupled from the gripper. Either way, **no controller makes the arm grasp
     the handle and drive the prismatic joint through contact.**
   - **D2 — fetch the item.** A *second* `setup_pick_place_controller` whose `source_paths=["…/Item"]`,
     `destination_path` = the counter. This is the part with **no precedent**: the controller's only
     motion primitive is **top-down** (descend straight down onto `cube + [0,0,APPROACH_H]`,
     `pick_place.py:754`). The item is **under the cabinet overhang** and **between the drawer walls** —
     a straight-down descent collides with the cabinet body before reaching the item. There is no
     lateral / shelf-reach / tilt-and-extract primitive, and no `approach_direction` arg (only
     `approach_height`, `pick_place.py:392`). The withdraw/extract leg (pull the grasped item back out
     of the cavity along -X before lifting) does not exist either.

10. **[LLM] [SYSTEM] [CHEAP-static]** There is also **no sequencer** that says "controller D1 finishes
    (drawer ≥ 0.25 m open) → THEN controller D2 starts." `pose_sequence` / `fixed_poses`
    (`pick_place.py:8929`) replays *pre-taught arm poses* with no sensing and no inter-controller
    handoff; it cannot condition stage-2 on "the drawer is now open." Composing two `setup_pick_place_…`
    calls just installs two controllers that race (the same multi-controller race noted in M7/M11).

### Phase E — physics gate (EXPENSIVE)

11. **[SYSTEM] [EXPENSIVE-physics]** `gate_one.py` runs the scene in the single-tenant Kit RPC. Observed,
    grounded in the real code paths:
    - **Open leg**: with the spline hack, the arm reaches the handle but the pull diverges / it tries to
      lift the handle (template `stable_fail`, `verified_status` line 39). With the `set_joint_targets`
      cheat-open, the drawer slides to -0.30 but **the arm didn't do it** — the gate has no joint-pull
      verdict anyway (the template's own success is a manual `get_attribute` joint read in `verify_args`,
      not a gate metric).
    - **Fetch leg**: the top-down descend onto the recessed item **collides with the cabinet body** (the
      planner's `planning_obstacles` includes `/World/Cabinet/Body`) → cuRobo/RmpFlow `res_None` /
      descend-timeout (`pick_place.py:796` retry-then-give-up). The item is never grasped.

12. **[SYSTEM] [EXPENSIVE-physics]** `simulate_traversal_check` returns **`success=False`**. Root cause it
    *can* report: `carried_but_not_delivered` or `0 delivered` (`diagnostics.py:3505-3515`). What it
    **cannot** express is the real situation: *the item never left the drawer interior*. The gate scores
    "cube XY inside the destination bbox + above floor + upright" (`diagnostics.py:3926,3968-3976`) — a
    **delivery-TO** verdict. It has **no "item removed FROM an enclosure / drawer-still-open-after-fetch"
    verdict.** Even a hypothetical lucky grasp would be misgraded, because the gate has no notion of the
    extraction event.

### Phase F — outcome reported to user

13. **[LLM] [SYSTEM] [CHEAP-static]** Honest report: *"I built the cabinet + drawer + item and an
    open-then-fetch attempt. The drawer-open stage is a known `stable_fail` — the pick-place controller
    can't drive a prismatic joint, so the drawer either doesn't open (spline) or opens via a scripted
    joint write that isn't the arm grasping the handle. The fetch stage has no working path at all: the
    controller only descends straight down, which collides with the cabinet overhang above the recessed
    item, and there is no reach-in / extract / withdraw primitive. The function gate also can't score
    'fetched from inside' — it only scores 'delivered to a target bbox.' This scenario needs new
    capability, not tuning."*

---

## Outcome

**BUILD-THEN-FAIL at the fetch stage.** The scene authors cleanly (cheap). The drawer-open stage
reproduces the documented `CP-NEW-drawer-open` `stable_fail`. The fetch stage fails *before* the
drawer-open gap even matters: the top-down-only pick controller physically cannot reach a recessed item
under a cabinet overhang, there is no open→fetch sequencer, and the gate cannot measure extraction.

---

## NEW class-level gap this scenario reveals

The known `CP-NEW-drawer-open` gap and inventory **M10** cover *opening an articulated mechanism* (M10 is
explicitly a **revolute hinged DOOR** swing — "open_door / articulated_pull", blast = cnc-tend door,
humanoid-cabinet). They do **NOT** cover the second, distinct half this request forces:

> **A "reach-into-cavity → grasp → extract-out" manipulation CLASS, plus an articulated-state-aware
> sequencer that chains open→fetch, plus a containment/extraction GATE that scores
> "item-removed-from-interior."**

Concretely, three coupled new things a whole family needs (drawer-fetch, fridge-retrieve, dishwasher-
unload, oven-retrieve, KLT/tote deep-pick, machine-enclosure part-retrieval, mug-from-cabinet):

1. **Controller class — `reach_in_and_extract` (non-top-down approach + withdraw leg).** The only pick
   primitive is APPROACH(z+0.12)→DESCEND-straight-down→GRASP→LIFT(z+0.20) (`pick_place.py:392,754,776`).
   It has no `approach_direction` / shelf-reach / tilt-entry, and no **withdraw** segment (pull the
   grasped item out of the cavity along the open axis *before* lifting). Any item under a fixed overhang
   or inside walls is unreachable. This is the genuinely NEW class — orthogonal to M8 (3-finger),
   M10 (door swing), and M14 (rack-place, which is *out-of-shelf place*, not *in-cavity extract*).

2. **Sequencer — articulated-state-gated stage handoff.** "Run open-controller until
   `DrawerJoint ≥ 0.25 m`, THEN start fetch-controller." No tool conditions controller-2 on a
   joint/articulation state; `pose_sequence` is sensorless replay, and composing two
   `setup_pick_place_controller` calls just races them (the M7/M11 multi-controller race, but the new
   trigger is **a joint position**, not a robot-done flag).

3. **Gate class — containment / extraction verdict.** `simulate_traversal_check` scores delivered-TO-a-
   bbox (`diagnostics.py:3926,3968-3976`). It cannot express "the item that started INSIDE the drawer is
   now OUTSIDE the cabinet AABB and on the counter, and the drawer is still open." The whole retrieve-
   from-enclosure family is structurally **unscorable** today, exactly as the sort family was unscorable
   before M2.

A secondary (already-noted-but-here-sharpened) blind spot: the **static pre-filter has no articulation-
state axis** — it judges one frozen frame, so it both false-blocks the closed-drawer item ("inside an
enclosure", "buried") and cannot confirm "reachable once open." An articulated-aware
`scene_validate` (probe reach at the OPEN joint state) is the cheap prerequisite that would let the
expensive gate be avoided.

**Honest bottom line:** unlike the humanoid-cabinet trace (which needed a revolute-door controller +
place-inside gate), this scenario's load-bearing missing piece is the **extract-from-cavity controller +
joint-state sequencer + containment gate**. Opening the drawer is the *easy, already-catalogued* half;
**fetching from inside is the new class** and it is missing end to end.
