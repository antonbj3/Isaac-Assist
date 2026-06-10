# E2E trace — `goods-to-person-fleet` (T7)

**Scenario id:** `goods-to-person-fleet`
**Tier:** T7 (multi-robot, multi-stage, mobile + manipulation)
**Robots:** Carter-fleet (N×Nova Carter AMR) + Franka Panda (fixed pick station)
**Task:** goods-to-person
**Persona:** fulfilment manager
**Request (verbatim):** *"a fleet of Carter AMRs brings shelves to a Franka pick station and returns them"*

---

## Verdict up front (honest)

There is **no template for this scenario**. It is a **synthesis** of three drafts, none of
which is verified, plus several capabilities that **do not exist as tools at all**:

| Building block | Closest real template | State |
|---|---|---|
| N-AMR fleet navigating + avoiding each other | `workspace/templates/CP-NEW-multi-amr-corridor.json` | build-only, `function-gate N/A` (its own `extension_notes`) |
| 1 Carter + Franka pick into onboard bin | `workspace/templates/CP-NEW-amr-pickup-handoff.json` | prior `stable_fail`; rewritten 2026-05-20; `verify_args=null` |
| 1 Carter + Nav2 config (mobile leg) | `workspace/templates/CP-64.json` | `function-gate diagnostic` only (prim/attr inspection, no runtime nav) |
| Arm grasps a cart/fixture, hands to AMR | `workspace/templates/CP-NEW-cart-handoff-amr.json` | `drafted-2026-05-16; function-gate ⏳` |

A `grep` over every handler module (`comm -23` of model-registered vs codegen-registered
tools) confirms the load-bearing fleet/shelf verbs are **missing** (see Step-by-step §"tool
gaps" and the final table). The exact match query

```
grep N>=2 AMRs AND franka AND return  → 0 templates (only CP-NEW-occupancy-map-nav, no return)
```

returns nothing. So the flow below traces what the LLM *would actually do* with the real
tools it has — and where it dead-ends.

---

## Dramatis personae of the pipeline

- **[USER]** = the fulfilment manager typing into the Isaac Assist chat.
- **[LLM]** = Claude acting as the agent, selecting tools / templates.
- **[SYSTEM]** = the Isaac Assist service: `canonical_instantiator.py`, the Kit RPC bridge,
  the handlers under `service/isaac_assist_service/chat/tools/handlers/`, and the gate.
- **[CHEAP-static]** = no physics step; prim/attr reads, reach math, occupancy grid, form-gate
  (`verify_pickplace_pipeline`), `scene_validate.py`, `reach_validate.py`.
- **[EXPENSIVE-physics]** = a `play()`-and-settle Kit run: `gate_one.py` / the
  `verify_pickplace_pipeline` delivery gate stepping PhysX for `duration_s` (90–180 s sim).

---

## Numbered narrative

### 1. [USER] — types the request  ·  [CHEAP-static]
> "a fleet of Carter AMRs brings shelves to a Franka pick station and returns them."

A single NL sentence. No counts, no map, no shelf SKUs, no dock coordinates. This is the
*context sentence*, not a fully-specified goal (per `feedback`: task-spec sentence-1 is
context, use the full Goal block — but here there is no fuller Goal; the user gave one line).

### 2. [LLM] — intent parse + template retrieval  ·  [CHEAP-static]
The LLM decomposes the request into the canonical shape:

- a **fleet** (N≥2 mobile robots) — role like `amr_fleet` (`min:3,max:3` in
  `CP-NEW-multi-amr-corridor.json` `roles`);
- a **Franka pick station** — `primary_robot: {constraints:[franka_panda]}`
  (`CP-NEW-amr-pickup-handoff.json` `roles`);
- **shelves as payload** carried *by* the AMR;
- a **return leg** (depart → come back to dock).

It searches the 504-template library. **Best three hits, all partial:**
`CP-NEW-multi-amr-corridor` (fleet, no arm/shelf), `CP-NEW-amr-pickup-handoff`
(arm + 1 AMR, no fleet, no return), `CP-64` (1 AMR nav config). **No single template
covers fleet + pick station + shelf + return.** The LLM must compose — this is where a
T7 synthesis silently becomes a draft-on-draft stack.

### 3. [LLM] — picks `CP-NEW-amr-pickup-handoff` as the spine, plans to clone the AMR ×N  ·  [CHEAP-static]
Rationale: it is the only one with both `franka_panda` and `carter`/`nova_carter` roles
(`CP-NEW-amr-pickup-handoff.json` `roles`). The LLM intends to (a) instantiate it, (b)
duplicate the AMR leg into a fleet, (c) add a return `navigate_to`, (d) replace the "cube
into bin" goal with "shelf onto pick station / shelf back to dock."

> **Honest flag:** this template's `verified_status` says the *prior* version was
> `stable_fail` — *"controller plans 30x but cube never picked — root cause was AMR missing
> from scene due to create_wheeled_robot producing placeholder geometry."* The 2026-05-20
> rewrite swapped to `robot_wizard('carter')` and added a departure `navigate_to`, but
> `verify_args` is still `null` — **it has never passed a function gate.**

### 4. [SYSTEM] — `canonical_instantiator.execute_template_canonical(tpl)` runs the build code  ·  [CHEAP-static]
`service/isaac_assist_service/chat/canonical_instantiator.py`. The template's
`code_template` is rendered with role bindings and exec'd over the Kit RPC bridge. For the
spine template the tool sequence (`tools_used`) is:

```
create_prim · set_attribute · apply_api_schema · robot_wizard ·
navigate_to · create_bin · setup_pick_place_controller
```

- `robot_wizard('carter')` → resolves alias `carter → nova_carter`
  (`CP-NEW-amr-pickup-handoff.json` `failure_modes[0]`), spawns the AMR USD reference. Uses
  `robot_wizard` deliberately because `create_wheeled_robot` only builds a **controller
  object, not a USD prim** (`_gen_create_wheeled_robot`, `robot.py:1517`) — that was the
  root of the old `stable_fail`.
- `setup_pick_place_controller` → wires the Franka pick controller (the same machinery the
  CP-NN cube gate uses).

### 5. [LLM] — clones the AMR leg into a fleet (the synthesis step the template does not do)  ·  [CHEAP-static]
The spine has `amr.expected_count = 1`. To make a *fleet*, the LLM either re-emits
`robot_wizard('carter')` at N dock poses, or borrows the `amr_fleet {min:3,max:3}` role
from `CP-NEW-multi-amr-corridor.json`. **No fleet-spawn or fleet-manager tool exists** — see
Step 9. So "fleet" = N hand-placed Carter prims with no shared scheduler.

### 6. [SYSTEM] — `setup_nav_robot` authors nav metadata (NOT a planner)  ·  [CHEAP-static]
`_handle_setup_nav_robot`, `robot.py:6780`. **Critical honesty point:** this handler only
writes USD attributes — `nav:occupancy_map`, `nav:goal_topic`, `nav:odom_topic`,
`nav:current_goal`, `nav:reached=True` (`robot.py:6826-6830`). Its own docstring:
*"For canonical-time, stores nav config on robot. Runtime nav execution requires Nav2 +
ROS2 bridge integration."* If the prim is missing it **auto-creates a placeholder Xform**
(`robot.py:6808-6823`) so the build-gate passes — i.e. it can paper over a Carter that never
actually spawned. `setup_nav_robot` is registered as an async handler but has **no codegen
emitter** and runs **no Nav2** — it is bookkeeping.

### 7. [SYSTEM] — `navigate_to` drives each AMR  ·  [EXPENSIVE-physics] (but collision-naive)
`_gen_navigate_to`, `robot.py:1594`. Two planners: `direct` (reactive single-step
`WheelBasePoseController`) and `astar` (inline A* over an **80×80 static occupancy grid,
0.25 m res, centred on origin**, `robot.py:1642-1644`). It subscribes a physics-step
callback and drives toward `target_position [x,y]`. This *does* step physics, but:
- `direct` is **collision-unaware** (`CP-NEW-multi-amr-corridor.json` `failure_modes`:
  *"navigate_to without ROS2 nav2 may use simple Vector-to-goal (collision unaware)"*);
- the A* grid is **static** — it does not see the *other moving AMRs*. Fleet
  anti-collision would need `register_moving_obstacle` per peer AMR.

### 8. [SYSTEM] — `register_moving_obstacle` per peer AMR (fleet anti-collision)  ·  [CHEAP-static]
`_handle_register_moving_obstacle`, `robot.py:4776`. Tags a prim as a dynamic obstacle for
the planner. `CP-NEW-multi-amr-corridor` lists it in `tools_used` precisely for fleet
coordination, but its own `failure_modes` admit: *"AMR fleet coordination — without claim
mutex, AMRs may collide in narrow corridor."* **There is no claim-mutex / lane-reservation
tool** (Step 9). So with N AMRs converging on one Franka pick station, head-of-line traffic
is unmanaged.

### 9. [LLM] — needs to make the AMR *carry a shelf*, hand it to the Franka, then *return it*  ·  [tool gaps]
This is the heart of "brings **shelves** … and **returns** them," and it is where the tool
surface runs out. The LLM reaches for verbs that **do not exist** (each confirmed missing by
`grep -rE 'codegen\["X"\]|def _gen_X|"X":' handlers/*.py`):

| Needed capability | Tool the LLM would call | Status (grep-confirmed) |
|---|---|---|
| Spawn/coordinate a fleet | `fleet_manager`, `fleet_dispatch`, `fleet_coordinator`, `assign_task`, `queue_task`, `multi_robot_schedule` | **MISSING** |
| Corridor traffic control | `traffic_control`, `claim_lane`, `reserve_lane` | **MISSING** |
| AMR docks / undocks at pick station & charger | `amr_dock`, `dock_undock`, `return_to_dock`, `charge_robot` | **MISSING** |
| AMR lifts/carries a shelf (latch payload to chassis) | `lift_shelf`, `carry_rack`, `shelf_carry`, `rack_lift`, `attach_payload`, `attach_to`, `parent_prim`, `weld_payload`, `create_fixed_joint`, `payload_parent` | **MISSING** |
| Author the shelf/rack geometry itself | `create_shelf`, `create_rack` | **MISSING** |

The only carry mechanism that exists is `_gen_grasp_object` (`robot.py:2844`), which for a
placeholder target degrades to a **parent-attach, not a motion-planned grasp** (Round 7
repair note, `robot.py:2844` block: *"the grasp action is then performed as a parent-attach
rather than a real motion-planned grasp"*). That attaches an object to an **arm**, not a
shelf to a **moving AMR chassis**. So the LLM's only honest fallback is:
**model the "shelf" as a rigid `Cube`/`slab` sitting on top of the Carter and pray
friction holds it** — exactly the brittle path `CP-NEW-cart-handoff-amr.json`
`failure_modes` calls out: *"if the cart sitting on top of the AMR shifts and falls in
front of the wheels during transit, the AMR will collide with it … CPU dynamics with
rubber-like friction holds the cart stable for short straight transits."*

The **"returns them"** half of the request has **no tool at all** — there is no return-loop
or dock-cycle primitive; the LLM can only emit a second `navigate_to(target=dock)` and
hope, with no verification that the shelf went back.

### 10. [SYSTEM] — STATIC pre-filter (the cheap eyes), BEFORE any expensive gate  ·  [CHEAP-static]
Two static checks run with **no physics** and would catch problems here:

**(a) Form-gate / reach advisory** — `canonical_instantiator.py:1084-1110`. If the template
has `verify_args.stages`, the instantiator calls `verify_pickplace_pipeline` and logs any
out-of-reach pick/place using `_ROBOT_REACH_M` (franka_panda = **0.855 m**). For
goods-to-person this catches the **#1 layout bug**: the LLM parks the AMR/shelf where the
**shelf face is outside the 0.855 m Franka shell**. Mirrored in `reach_validate.py`
(`ROBOT_REACH` table) and `scene_validate.py` (REACH / INTERPENETRATION / SUPPORT,
post-settle). **Cost: a prim read + 3D distance math; no `play()`.**

> But two honest gaps: (i) the spine template's `verify_args` is **null**, so the
> form-gate caller **skips** it (`if _stages:` guard, `:1091`) — the cheap eyes never fire
> unless the LLM adds stages; (ii) `verify_pickplace_pipeline` and `scene_validate` have
> **no concept of a mobile robot** (`grep carter|wheeled|amr diagnostics.py` → empty). They
> reach-check the *Franka*, not the AMR's navigability or the corridor. So the static
> pre-filter catches "shelf out of arm reach" but is **blind to "two AMRs will collide"**
> and **blind to "shelf will slide off the chassis."**

**(b) `reach_validate.py`** — cup/EE IK probe per declared pick target. Caveat in its own
header: *REACHABLE = "necessary, not sufficient"* (CP-81 probed REACHABLE yet the gate
FAILED). It is arm-only; the fleet legs are out of scope.

**Where the cheap eyes save an expensive run:** if the LLM placed the shelf at, say,
`[1.4, 0, h]` (beyond 0.855 m), the form-gate advisory logs `out-of-reach` at
*build* time (microseconds) instead of burning a 90–180 s PhysX gate that fails with
`carried_but_not_delivered`. That is the entire point of the static pre-filter.

### 11. [SYSTEM] — EXPENSIVE physics gate  ·  [EXPENSIVE-physics]
The delivery gate (`verify_pickplace_pipeline` / `scripts/qa/gate_one.py`, criterion in
`diagnostics.py:4413-4449`):

```
multi-cube (len(cube_paths) > 1):  success = any(cube delivered) AND primary upright
single-cube:                       success = in_xy AND above_floor AND at_rest AND upright_ok
  where delivered = in target bbox XY (±xy_tol) AND above floor (−floor_tol) AND at_rest (speed < rest_speed)
```

**This is the outcome metric and it is the problem for T7 goods-to-person:** the gate scores
**a cube coming to rest inside a target bounding box.** It has **no notion of**:
- *which* AMR brought the shelf, or whether the **fleet** coordinated;
- whether the shelf was **returned** to the dock (return leg is unmeasured);
- AMR-AMR collisions, dock occupancy, or traffic.

So even a "passing" run only proves *a payload ended up at the pick station and settled
upright* — it cannot certify the actual request. `CP-NEW-multi-amr-corridor`'s
`extension_notes` say it plainly: *"Function-gate N/A — AMR navigation, not cube delivery.
Validation = each Carter reaches its goal_position within 30s"* — i.e. the fleet leg has
**no gate**; it is validated by a hand-written position check, not the standard gate.

### 12. [SYSTEM] — diagnose on failure  ·  [CHEAP-static]
If 0 delivered, `diagnostics.py:3505` reports `carried_but_not_delivered` /
`delivered_ok` root causes. For this scenario the realistic failure string is the AMR's
own: prior `stable_fail` was *"controller plans 30x but cube never picked"* because the
AMR/shelf was outside the Franka shell or the placeholder geometry was absent. The diagnose
loop is cube-centric; it will **not** diagnose "the second AMR rear-ended the first."

### 13. [LLM] → [USER] — honest outcome report  ·  [CHEAP-static]
The LLM reports back. The truthful answer to the fulfilment manager:

> *"I can build a single Carter docking at a Franka and the arm placing a cube into its
> onboard bin (CP-NEW-amr-pickup-handoff, unverified), and I can build 3 Carters driving a
> corridor avoiding each other (CP-NEW-multi-amr-corridor, build-only, no gate). I cannot
> currently (a) make an AMR lift/latch a shelf as a payload, (b) coordinate a fleet with
> traffic/dock scheduling, or (c) verify the 'returns them' leg — those tools don't exist.
> The shelf would be faked as a cube balanced on the chassis, and the physics gate only
> checks that a cube settles in a box, not that the fleet round-tripped the shelves."*

---

## Outcome (gate success-criterion, stated)

- **Gate that would run:** the standard pick-place delivery gate on the Franka leg
  (`diagnostics.py:4446-4449`). **Success = the payload cube comes to rest inside the
  target bbox XY, above floor, at rest, primary upright.**
- **What that does NOT certify:** fleet coordination, AMR-AMR avoidance, dock/undock,
  shelf-latch integrity, and the entire **return** leg — none are in the success criterion.
- **Predicted real result:** **UNVERIFIED / would-fail-or-fake.** The spine template has
  never passed a function gate (`verify_args=null`, prior `stable_fail`); the fleet and
  shelf-carry and return capabilities are tool-gaps. A "green" gate here would be a
  **false-positive** w.r.t. the user's actual request.

## Where static eyes beat the expensive gate (summary)
The form-gate advisory (`canonical_instantiator.py:1084`) + `scene_validate.py` /
`reach_validate.py` catch **shelf-out-of-Franka-reach (0.855 m)** and
**clump/float/support** violations at build time with prim-math only — saving a 90–180 s
PhysX gate. They are **blind to the mobile/fleet half** (no carter/wheeled awareness in
`diagnostics.py`), which is exactly the half this scenario lives in.

## Tool gaps (grep-confirmed missing)
`fleet_manager`, `fleet_dispatch`, `fleet_coordinator`, `assign_task`, `queue_task`,
`multi_robot_schedule`, `traffic_control`, `claim_lane`, `reserve_lane`, `amr_dock`,
`dock_undock`, `return_to_dock`, `charge_robot`, `lift_shelf`, `carry_rack`, `shelf_carry`,
`rack_lift`, `attach_payload`, `attach_to`, `parent_prim`, `weld_payload`,
`create_fixed_joint`(as a tool), `payload_parent`, `create_shelf`, `create_rack`.
Plus two **validated-but-stub** verbs: `setup_nav_robot` (metadata only, no Nav2) and
`register_moving_obstacle` (no claim-mutex companion).
