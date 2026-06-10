# E2E Trace — [dc-cable-route]: "route a cable from one port to another between two servers"

**Scenario id:** dc-cable-route
**Domain:** datacenter · **Robot:** franka_panda · **Task:** deformable-cable-route
**User request (verbatim):** "route a cable from one port to another between two servers"
**Trace date:** 2026-06-09
**Verdict:** **FAIL — class-level architectural gap.** The request is for a *deformable 1D cable* whose endpoints *seat into two connector ports* on *two server assets*. Every one of those three nouns hits a missing class: (a) no 1D/Cosserat-rod cable controller; (b) no port/connector-insertion strategy or mate-detection gate; (c) the named datacenter server/port assets are **not on disk** (materials-only package). The closest canonical (`CP-NEW-wire-harness-route`) is an explicit *rigid-segment simplification* that deletes the cable.

---

## Stage 0 — Asset & capability reality check (grounding before the trace)

Three independent grounding checks, all run before tracing:

### 0a. Is there a cable/deformable template?
`grep -rli "cable|cord|wire|deformable|rope|hose"` over `workspace/templates/` → closest match is **`CP-NEW-wire-harness-route.json`**. Its own goal line is the headline finding:

> "Franka threads a **rigid-segment** wire harness (5 Cylinder proxies arranged head-to-tail)… Realizes industrial-wire-harness-route-001 with **rigid-segment simplification (no deformable cloth/wire physics — PhysX-unstable per backlog).**"

And `failure_modes[0]`:
> "STRUCTURAL SIMPLIFICATION: real wire harnesses are deformable (cloth/wire physics). This canonical models segments as rigid Cylinder proxies because **PhysX deformable-wire is numerically unstable (velocity blow-up under grip).** Consumers needing true deformable-harness behaviour should **NOT** retrieve this canonical."

So the single most-relevant template in the library *explicitly disclaims* the exact task we were asked to do.

### 0b. Is there a deformable-physics primitive at all?
Yes — `create_deformable_mesh` is a fully-wired tool:
- schema: `tool_schemas.py:167`, args model `_models.py:102` (`CreateDeformableMeshArgs`, `soft_body_type` field), registry `_models.py:4009`
- codegen: `physics.py:642 _gen_deformable` → `physics.py:681 _gen_deformable_body` / `physics.py:767 _gen_deformable_surface`
- presets: `workspace/knowledge/deformable_presets.json` — 15 presets incl. **`rope_nylon`**.

BUT the `rope_nylon` preset is:
```json
{ "type": "surface", "api": "PhysxDeformableSurfaceAPI",
  "params": {"stretch_stiffness": 80000.0, "bend_stiffness": 0.01, ...},
  "description": "Nylon rope — low stretch, flexible bending, 1D-like surface mesh" }
```
A cable is modelled as a **2D cloth surface ("1D-like surface mesh")**, not a 1D Cosserat/PhysX-rope rod. `_gen_deformable_surface` (physics.py:767) generates a *20×20 subdivided plane* (`physics.py:803`), and `_gen_deformable_body` (physics.py:715-742) falls back to a *10×10 plane mesh* if the prim has no points. **There is no rod/segment-chain/articulated-cable generator anywhere.** A cable routed as a cloth sheet does not bend like a wire, cannot be grasped by its tip, and tangles/blows up under grip — which is precisely why CP-NEW-wire-harness-route deleted it.

### 0c. Are the datacenter "server" + "port" assets actually present?
Kimate's `Datacenter_NVD` package exists (`/home/anton/kimate_assets/assets/Datacenter_NVD`) and its `asset_catalog.json` lists 36 assets including the exact nouns we need:
- `Rack_42U_A_01` (server rack)
- **`Fiber_Patch_Panel_1U_A_01`** (the literal "port" panel)
- DGX-skinned servers (materials `DGX_H100_Front_A.mdl`, `DGX_A100_Front_A.mdl`)

**But the catalog points at `/home/kimate/Desktop/assets/...` and the geometry is not shipped.** `find Datacenter_NVD -name '*.usd*'` → **0 files.** The package contains only **15 `.mdl` material files** (PCB, DIMM, PDU_LCD, DGX skins) + the catalog JSON. So even though the catalog *names* a fiber patch panel with ports, **there is no server USD, no rack USD, and no port geometry to route between.** The assets are skins without bodies.

**Net of Stage 0:** the cable has no faithful physics primitive, the port-mate has no controller, and the two servers have no geometry. The scenario is un-buildable as requested with today's tools/assets.

---

## Stage 1 — User submits the request  [USER]  [CHEAP-static]

`[USER]` types into the Isaac Assist chat panel: *"route a cable from one port to another between two servers."*
`[SYSTEM]` the chat service (`service/isaac_assist_service/chat/`) embeds the prompt and runs canonical retrieval over `workspace/templates/`.

---

## Stage 2 — Retrieval + planning  [LLM]  [CHEAP-static]

`[LLM]` Retrieval surfaces **`CP-NEW-wire-harness-route`** as nearest neighbour (shared tags `isaac:industrial.wire_harness`, `isaac:assembly.routing`, `isaac:industry.electrical_assembly`). The LLM now faces a fork, and **both branches dead-end**:

**Branch A — honor the request (true deformable cable).** The LLM would call `create_deformable_mesh(soft_body_type="rope")`. This is *callable* but produces a cloth-surface plane, not a routable cable. There is **no tool** to (i) pin one cable end to a server-A port, (ii) have the Franka grasp the free end of a floppy surface mesh, (iii) thread it to server-B, (iv) seat/mate it into the port. `setup_pick_place_controller`'s runtime grasp is `_attach_cube_to_ee(cube_path)` (`pick_place.py:709`) — a FixedJoint/friction grip that reads a **single rigid-body** `get_world_pose()` (`pick_place.py:2578`) and closes fingers on a cube *center*. A `PhysxDeformableSurfaceAPI` mesh has **no rigid `get_world_pose()` and no single center** — the attach either raises or welds to a degenerate body. Branch A is not executable end-to-end.

**Branch B — copy the canonical (rigid simplification).** The LLM emits the CP-NEW-wire-harness-route code path: replace the cable with N rigid `Cylinder` proxies, replace the two ports with `Cube` clip-waypoints, and run `setup_pick_place_controller(target_source="curobo", drop_targets={...})`. This *builds and runs*, but it is no longer the asked task — it is a pick-and-place of rigid rods onto cube markers. The "cable" never bends, the "ports" never mate, and the "two servers" are absent (replaced by a `Panel` Cube, `code` line: `create_prim("/World/Panel", "Cube", scale=[0.40,0.02,0.20])`).

`[LLM]` In direct-mode the model takes **Branch B** (it is the only one that passes the form/function gate). It would honestly need to tell the user "I substituted rigid rods for the cable and cube markers for the ports."

---

## Stage 3 — Scene build (Branch B, the only runnable path)  [LLM→SYSTEM]  [CHEAP-static]

`[SYSTEM]` executes the CP-NEW-wire-harness-route `code` block inside Kit (CHEAP — pure USD authoring, no stepping):
1. `create_prim` DomeLight, Ground, Table — collision APIs. *(scene_authoring.py / physics.py codegen)*
2. `set_physics_scene_config({"enable_gpu_dynamics": False, ...})` — **note: GPU dynamics OFF.** PhysX deformables/cloth *require* GPU dynamics; this config alone forecloses a real cable even if Branch A were attempted.
3. `create_prim "/World/Panel"` Cube — **stands in for both servers** (no DGX/rack USD available; see Stage 0c).
4. `robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0,0,0.75])` — Franka spawns (verified-good spawn path per MEMORY robot_wizard notes).
5. 6× `create_prim "/World/Clip_i"` Cube 25 mm — **stand in for the two ports** (no `Fiber_Patch_Panel` geometry; ports degraded to solid cubes with "no physical slot," per template `failure_modes[6]`).
6. 5× `create_prim "/World/WireSegment_i"` Cylinder + `PhysicsRigidBodyAPI` + `convexHull` — **the cable, deleted into 5 rigid rods.**
7. `add_proximity_sensor("/World/PickSensor")`, `define_grasp_pose(...)`, `record_waypoints(...)`.

`[SYSTEM]` Build result: **succeeds** structurally (this is a known-good rigid pick-place skeleton). The form-gate (schema lint) passes.

---

## Stage 4 — Controller install + grasp definition  [LLM→SYSTEM]  [CHEAP-static]

`[LLM]` `setup_pick_place_controller(robot_path="/World/Franka", target_source="curobo", source_paths=[WireSegment_0..4], drop_targets={seg_i: clip_i_pos}, planning_obstacles=[Panel, Table, Clip_0..5])` *(pick_place.py:293 `_gen_setup_pick_place_controller`)*.

This is the per-segment cuRobo routing path. It is real and works for **rigid** cylinders. The grasp at runtime is `_attach_cube_to_ee` (pick_place.py:709, friction-grip, FixedJoint-free per the 2026-05-26 friction-fix). **It can only grasp a rigid body** — which is exactly why the cable had to become rods.

---

## Stage 5 — Physics simulation + gate  [SYSTEM]  [EXPENSIVE-physics]

`[SYSTEM]` runs the function-gate (`scripts/qa/gate_one.py`) with `simulate_args` (`duration_s: 360`, `cube_paths`=5 segments, `target_path="/World/Clip_4"`).

**How the gate actually grades (gate_one.py:15-94):** it builds the scene, steps physics for `duration_s`, then reads the **last JSON line** as `verdict` and checks `verdict["success"]`. The underlying success test is the rigid-body-center logic: `_is_in_bin(cube_path)` (pick_place.py:2879/3611/6099) and `_is_near_dest(cube_path, tolerance=0.15)` (pick_place.py:6119) — an **AABB/Euclidean test on a single rigid-body world position** via `get_world_pose()`.

**Why this gate cannot grade a cable, even in principle:**
- A cable is a *continuous curve*, not a point. "Routed correctly" means *the whole path* clears obstacles and *both ends* seat in ports — a curve-shape + dual-endpoint-mate predicate. The gate has exactly **one** `target_path` and tests **one** body center. It is the same single-target limitation flagged for multi-bin sorts (TOOL_GAP_INVENTORY_V2 Tier-1 M2), but worse: there is no rigid center to read off a deformable at all (`GetPointsAttr` is never called anywhere in the grade loop).
- The template's *own* verify is offline + ordering-only: "‖segment_leading_end(i) − clip_position(i)‖ < 0.01 m AND ordering preserved" (`verify_args.ordering_required: true`). That grades *rod tips landing on cube markers* — it says nothing about cable continuity, slack, bend radius, or a seated connector.

**Outcome of Branch B run:** the rigid-rod pick-place *can* pass its own ordering gate (cuRobo transit to clip Z=0.92; template flags a reachability risk at the +X corner clip, `failure_modes[7]`). **But passing means "5 rods placed on 5 cubes in order" — it does NOT mean "a cable was routed between two server ports."** The gate is **green on a task that is not the user's task.** This is a measurement-honesty trap: the gate would report success for a scene that contains no cable, no ports, and no servers.

---

## Stage 6 — Outcome reported to user  [SYSTEM→USER]

`[SYSTEM]` Honest report: "I could not route a deformable cable. I substituted 5 rigid cylinder rods for the cable and 6 cube markers for the connector ports, on a single cube panel standing in for the two servers, and placed the rods onto the markers in order. True cable deformation, port mating, and the DGX/rack server geometry are **not supported / not on disk.**"

A *dishonest* (gate-trusting) report would say "cable routed successfully" — which is the failure mode this trace exists to expose.

---

## NEW class-level architectural gaps revealed

This scenario is unusually productive: it reveals **three** distinct missing classes, none of which are in `TOOL_GAP_INVENTORY_V2` (verified by grep — that doc has zero hits for deformable/cable/cosserat/rope/connector/port/datacenter). These are *not* incremental — each blocks a whole family.

### GAP-NEW-1 (CONTROLLER CLASS): 1D deformable-linear-object (DLO) route controller — **MISSING**
- **What's missing:** a controller class that (a) instantiates a cable as a *1D rod chain* (PhysX rope / articulated capsule-chain / Cosserat rod), (b) grasps it by a *moving point on a deformable* (not a rigid center), (c) drags the free end along a planned path while the body follows compliantly, (d) maintains tension/slack within bounds. Today: `create_deformable_mesh` makes a **cloth sheet**, and `_attach_cube_to_ee` (pick_place.py:709) grasps only **rigid** bodies via `get_world_pose()`. The two cannot compose.
- **Why a whole family needs it:** cable-route, wire-harness (faithful), hose/tube routing, rope/strap/cinch, sutures, belt-threading, draping a cloth, bag-handling, deformable-insert (gasket/o-ring). Today *every one* of these must be faked as rigid proxies (the CP-NEW-wire-harness-route pattern). This is the deformable analogue of "pick-place breaks on articulated doors → needs a revolute-pull controller": **pick-place breaks on deformables → needs a DLO/grasp-follow controller.**
- **Effort: research** (PhysX rope stability under grip is the open problem the backlog itself flagged: "velocity blow-up under grip"). Requires GPU dynamics ON + a grasp-on-deformable attach (vertex-pin FixedJoint to a rod link, not a body weld).

### GAP-NEW-2 (CONTROLLER + GATE CLASS): connector/port mate-and-seat — **MISSING**
- **What's missing:** a *port-insertion* strategy ("plug A into port B until latched") AND a *mate-detection gate* ("connector is seated + retained"). The insertion handler (`insertion.py:51` strategy registry) has `spiral_search`, `helical_screw`, `snap_fit`, `impedance_descent` — peg-in-hole, screws, caps. **None model a keyed/genderless connector mating into a socket with a detent/latch.** And there is no gate that reads "mated" (no contact-pair-latched predicate; the gate reads a body center, Stage 5).
- **Why a whole family needs it:** RJ45/fiber/USB/power-connector insertion, blind-mate backplanes, hot-swap drive/blade insertion, hose quick-connects, electrical terminal seating. The entire "datacenter/electrical-assembly cable" domain rests on this, plus any connectorized assembly task.
- **Effort: M–L.** A new insertion strategy (keyed approach + latch-force signature) + a mate gate (contact-persistence + retention test). The impedance substrate (`compliance.py`) is reusable.

### GAP-NEW-3 (ASSET/RESOLVER CLASS): datacenter server/rack/port asset binding — **MISSING (assets absent)**
- **What's missing:** the `Datacenter_NVD` package is **materials-only** — 15 `.mdl` skins, **zero geometry USD** (Stage 0c). `asset_catalog.json` *names* `Rack_42U_A_01`, `Fiber_Patch_Panel_1U_A_01`, DGX servers, but the `usd_path`s point at an absent `/home/kimate/Desktop/...` tree. There is also no name→USD resolver for datacenter nouns (analogous to the missing container-name resolver, TOOL_GAP_INVENTORY_V2 T3 M11).
- **Why it matters cross-family:** *any* datacenter scenario ("rack a server," "swap a blade," "route between racks," "patch a panel," "pull a drive") has no body to act on. This is a hard blocker for the whole datacenter domain, independent of the cable controller — even a *rigid* connector task can't be staged without the patch-panel + rack geometry.
- **Effort: S (re-acquire assets) + S (name→path resolver).** First confirm whether the geometry tier of `Datacenter_NVD` was simply not synced; if so, this is an asset-fetch, not a code build.

---

## Honest bottom line

The request decomposes into **deformable cable (GAP-NEW-1) + two connector ports (GAP-NEW-2) + two server bodies (GAP-NEW-3)** — and the platform is missing **all three classes.** The nearest canonical (`CP-NEW-wire-harness-route`) is a self-admitted rigid simplification that satisfies the *gate* while satisfying *none* of the request's semantics, and the gate (`gate_one.py`, single-`target_path`, rigid-body-center) is **structurally incapable** of telling the difference. The highest-leverage single finding is **GAP-NEW-1: the missing 1D-DLO grasp-follow controller class** — it is the deformable counterpart to the articulated-door discovery and unblocks the entire flexible-object manipulation family.
