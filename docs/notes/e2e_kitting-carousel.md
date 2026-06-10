# E2E trace — `kitting-carousel` (T5, Franka, kitting)

**Persona:** kitting assembler
**One-sentence request:** *"pull 4 SKUs from a rotary carousel into a kit tray, then a vision completeness check"*
**Scenario id:** `kitting-carousel` · tier **T5** · robot **franka** · task **kitting**
**Traced:** 2026-06-09

---

## 0. Template-match verdict (read this first)

There is **no single template** that matches the request. The request is the *union* of two
distinct canonicals, and the closest one is built for the **wrong robot** and the **wrong SKU count**:

| Capability the request needs | Closest real template | Gap |
|---|---|---|
| rotary carousel feeding source SKUs | `CP-NEW-kitting-station-6sku.json` | robot is **UR10**, not Franka; **6** SKUs not 4; carousel rotation is a documented *non-modelled* limitation |
| Franka picking labeled parts into a kit tray | `CP-NEW-kit-prep-operator.json` | **no carousel** (5 static bins); 5 parts not 4 |
| overhead-camera vision completeness check + re-pick | `CP-NEW-kit-prep-vision-gate.json` | **no carousel**; 5 parts; `extends` kit-prep-operator |

So the requested scene = **carousel feeder (from the 6sku template) + Franka arm + vision
completeness gate (from the vision-gate template)**, trimmed from 6/5 SKUs to 4. That fusion
**does not exist as a canonical** and the carousel + Franka + vision combination is **unverified**
(every candidate template carries `verified_status` of `drafted` / `form-gate pending` /
`carousel-rotation-limitation documented`).

Files:
- `/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-NEW-kitting-station-6sku.json`
- `/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-NEW-kit-prep-operator.json`
- `/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-NEW-kit-prep-vision-gate.json`

---

## 1. The full action sequence (USER / LLM / SYSTEM · CHEAP-static / EXPENSIVE-physics)

Cost legend: **[CHEAP-static]** = scene authoring + static-eyes geometry reads (build + ~2.5 s
settle, no controller, no full physics run); **[EXPENSIVE-physics]** = a real cuRobo-driven
pick-place sim run inside Kit (the function-gate).

### Step 1 — USER states the goal
- **[USER] [CHEAP-static]** The kitting assembler types: *"pull 4 SKUs from a rotary carousel into
  a kit tray, then a vision completeness check."* No prim paths, no robot named, no coordinates.

### Step 2 — LLM disambiguates the request into a structural intent
- **[LLM] [CHEAP-static]** The LLM maps the NL to structural tags. The matching intent block lives
  in `CP-NEW-kitting-station-6sku.json` (`intent.structural_tags`):
  `isaac:feeder.rotary_carousel`, `isaac:kitting.multi_sku`, `isaac:industry.kitting_assembly`,
  `isaac:destination.kit_tray`, plus the vision tag `isaac:vision.completeness_check` from
  `CP-NEW-kit-prep-vision-gate.json`. **Honest gap:** the carousel template's robot tag is
  `isaac:robot.ur10`; the scenario pins **franka**. The LLM must override the carousel template's
  default robot — there is no franka+carousel canonical to copy.

### Step 3 — LLM retrieves and fuses templates (the hard part)
- **[LLM] [CHEAP-static]** Best single retrieval is the 6-SKU carousel template, but it is UR10 and
  has no vision pass. The LLM has to graft three pieces:
  1. carousel feeder geometry from `CP-NEW-kitting-station-6sku` (lines 18–195, the `code` block),
  2. Franka body + reach geometry from `CP-NEW-kit-prep-operator` (`robot_wizard(franka_panda, …)`),
  3. overhead camera + vision gate from `CP-NEW-kit-prep-vision-gate` (`set_camera_look_at` +
     `add_vision_classifier_gate` + `setup_pick_place_with_vision`).
  Trim 6→4 SKUs. This is **synthesis, not instantiation** — the produced canonical is new code with
  no `verified_status` history behind it.

### Step 4 — LLM authors the scene skeleton
- **[LLM] [CHEAP-static]** Emits lighting + ground + physics config:
  `create_prim(DomeLight)`, `create_prim(Ground)`, `apply_api_schema(PhysicsCollisionAPI)`,
  `set_physics_scene_config({"enable_gpu_dynamics": False, "broadphase_type": "MBP"})`
  (CPU/MBP, matching both source templates — chosen for deterministic carousel + grasp).
- **[SYSTEM] [CHEAP-static]** Each call dispatches through `register_handlers()` in
  `service/isaac_assist_service/chat/tools/handlers/_dispatch.py:116`. `create_prim`,
  `apply_api_schema`, `set_physics_scene_config` all have real handlers.

### Step 5 — LLM creates the rotary carousel
- **[LLM] [CHEAP-static]** `create_rotary_table(table_path="/World/Carousel", position=[0,0,0.75],
  radius≈0.45, height=0.05, angular_velocity_deg=0)` (passive, stepped manually).
- **[SYSTEM] [CHEAP-static]** Handler `_handle_create_rotary_table`
  (`service/isaac_assist_service/chat/tools/handlers/robot.py:4685`) builds a composite:
  a static **Base**, a rigid rotating **Disc** (Cylinder), and a revolute **Joint** between them
  (`robot.py:4708-4743`). **REAL tool, works.**
  - **BUG the LLM will inherit:** the handler creates the joint at **`/World/Carousel/Joint`** as a
    standard `UsdPhysics.RevoluteJoint` (`robot.py:4710,4736`). The 6-SKU template's `failure_modes`
    instructs the runtime to step the carousel via
    `set_attribute(prim_path="/World/Carousel/RevJoint", attr_name="physics:revJoint:targetPosition")`
    — **wrong path and wrong attribute** (real attr is the drive target on `…/Joint`). If the LLM
    copies the template's guidance verbatim, the carousel never rotates. Confirmed: handler path is
    `…/Joint`, template references `RevJoint` ×2 and `physics:revJoint:targetPosition` ×3.

### Step 6 — LLM creates 4 source bins + 4 SKU cubes on the carousel rim
- **[LLM] [CHEAP-static]** Bins at 90° spacing (4-SKU): `/World/Carousel/Bin_0..3`, each with one
  semantically-labeled SKU cube (`set_semantic_label`, e.g. `PCB / screw / housing / bracket`).
  In the 6-SKU template these are emitted as `create_prim(...Cube...)` + `apply_api_schema`
  (template lines 18: `create_prim(prim_path="/World/Carousel/Bin_0/Cube" …)`).
- **[SYSTEM] [CHEAP-static] — TOOL GAP:** the template *names* `create_bin` in `tools_used`, but
  **`create_bin` has no runtime executor**. It is registered **only as a codegen lowering**
  (`codegen["create_bin"] = _gen_create_bin`, `robot.py:7306`) and an args model
  (`_models.py:4176`); there is **no `data["create_bin"] = …`** entry. A live `create_bin` call
  fails dispatch — so the LLM must use raw `create_prim` boxes (which the template's actual `code`
  block does). Cosmetic vs the `tools_used` manifest, but a real honesty hole in the manifest.
- **PHYSICS GAP (unverified):** bins/cubes parented under `/World/Carousel` are placed in world
  space; they are **not jointed/welded to the Disc**. The carousel handler only makes Base+Disc+Joint
  — nothing carries the child bins when the disc revolves. A rotating disc would **slide out from
  under** static bins rather than indexing them. This is the substance behind the template's own
  "Carousel child-prim world position [KNOWN LIMITATION]" note.

### Step 7 — LLM places the Franka and a robot table
- **[LLM] [CHEAP-static]** `create_prim(/World/RobotTable …)` then
  `robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[…,0.75],
  orientation=[0.7071,0,0,0.7071])` — overriding the carousel template's UR10 default with the
  Franka geometry from `CP-NEW-kit-prep-operator`.
- **[SYSTEM] [CHEAP-static]** `robot_wizard` is real
  (`service/isaac_assist_service/multimodal/onboarding_tutorial.py`). **Reach concern:** Franka reach
  ≈ **0.855 m** (`scripts/qa/scene_validate.py:32`), vs UR10's 1.30 m. The 6-SKU layout was sized for
  UR10 (handoff at 0.35 m lateral, but the tray slots sit **1.38–1.62 m** from the UR10 base per the
  template's own `failure_modes`). For a Franka those tray slots are **far outside the 0.855 m shell**
  unless the LLM re-centers the carousel, tray, and robot. This is exactly the class the static-eyes
  pre-filter exists to catch (Step 11).

### Step 8 — LLM creates the kit tray
- **[LLM] [CHEAP-static]** `create_kit_tray(tray_path="/World/KitTray", position=[…],
  tray_size=[…], slot_layout="grid_2x2", slot_size=0.05, slot_spacing=0.12)` — `grid_2x2` = 4 slots
  for the 4 SKUs (vs `grid_2x3`/`linear_5` in the source templates).
- **[SYSTEM] [CHEAP-static]** `_handle_create_kit_tray` (`robot.py:4416`) parses the layout
  (`grid_RxC`, `row_N`, `linear_N`, `col_N` all supported — `robot.py:4445-4460`), creates the tray
  Cube + N marker `slot_<n>` Xforms each tagged `kit:slot_index / kit:slot_size / kit:occupied`
  (`robot.py:4490-4509`). **REAL tool, works.** Slots are **markers only** — no physical walls;
  occupancy is judged by xy-proximity later (Step 14).

### Step 9 — LLM sets up the overhead inspection camera
- **[LLM] [CHEAP-static]** `create_prim(/World/InspectCamera, Camera)` →
  `set_camera_params(focal_length=18.0, horizontal_aperture=20.955)` →
  `set_camera_look_at(target=<tray center>, eye=<tray center + z≈0.85>)` (nadir view).
- **[SYSTEM] [CHEAP-static]** Both camera handlers are real
  (`service/isaac_assist_service/chat/tools/handlers/sensors.py`). Pure scene authoring; no physics.

### Step 10 — LLM installs the pick-place controller (still pre-sim)
- **[LLM] [CHEAP-static]** `setup_pick_place_controller(robot_path="/World/Franka",
  target_source="curobo", robot_family="franka_panda", source_paths=[4 SKU cube paths],
  destination_path="/World/KitTray", drop_targets={cube→slot}, planning_obstacles=[Table, KitTray,
  Carousel, Bin_0..3], grip_style="friction")`.
- **[SYSTEM] [CHEAP-static]** Real handler in
  `service/isaac_assist_service/chat/tools/handlers/pick_place.py`. This *installs* the cuRobo
  controller (a PhysX pre-step subscription); it does not yet *run* the pick. The 6-SKU template
  warns: putting the whole `/World/Carousel` disc in `planning_obstacles` can over-constrain cuRobo
  IK when the arm reaches into a rim bin (template `failure_modes`).

---

## 2. Where the CHEAP static-eyes pre-filter catches problems before the EXPENSIVE gate

### Step 11 — SYSTEM runs the static scene validator (the pre-filter)
- **[SYSTEM] [CHEAP-static]** `scripts/qa/scene_validate.py` builds the canonical
  (`execute_template_canonical`), runs a **~2.5 s passive settle with the arm PARKED at home**
  (it unsubscribes the pick controller so the arm doesn't move — `scene_validate.py:68-75,97-101`),
  then reads **actual post-settle prim geometry** and checks three violation classes
  (`scene_validate.py:3-19`):
  - **REACH** — each pick object AND each delivery target inside the nearest arm's reachable shell.
    Uses `ROBOT_REACH["franka_panda"] = 0.855` (`scene_validate.py:32`), mirroring the controller's
    own reach gate in `handlers/resolve._ROBOT_REACH_M`. **This is the check that catches Step 7's
    Franka-vs-UR10-layout problem:** with the UR10-sized tray slots at 1.3–1.6 m, the validator flags
    `REACH` violations on the kit-tray drop targets and on far-rim SKU bins **before any physics run
    is spent.** Pick paths come from `simulate_args.cube_paths`, targets from
    `simulate_args.target_path` (`scene_validate.py:44-52`).
  - **INTERPENETRATION** — SKU cubes clumped/overlapping in 3D (the dispenser-clump class).
  - **SUPPORT** — each SKU rests on a surface (carousel rim), not floating or buried.
  - It also captures pre-settle vs post-settle positions to flag a **physics explosion** (parts
    spawned overlapping a bin get ejected metres away — `scene_validate.py:88-101`), and excludes
    gripper sub-prims from the robot-detection heuristic (`scene_validate.py:_GRIP_MARK`).
- **What the static-eyes pre-filter CANNOT catch here (honest limits):**
  - It reads the carousel children at their **authored index=0** positions only. The "carousel
    rotation never modelled" limitation (Step 5/6) is invisible to it — it validates one static
    frame, so a scene that can only present 1 of 4 SKUs at the handoff still looks reach-clean.
  - It does **not** check the revolute-joint path/attr bug (Step 5) — that surfaces only at runtime
    when the carousel fails to step.
  - It does **not** verify the vision pass at all (no camera/VLM in the validator).
- A companion **`scripts/qa/reach_validate.py`** exists but is a **UR10 cup-down** suction
  reachability probe (`reach_validate.py:2-8`) — **not applicable to a Franka parallel-jaw kitting
  scene.** So for this scenario the relevant pre-filter is `scene_validate.py` only.

---

## 3. The EXPENSIVE physics gate and its success criterion

### Step 12 — SYSTEM runs the function-gate (first pick pass)
- **[SYSTEM] [EXPENSIVE-physics]** `scripts/qa/gate_one.py` builds + settles the canonical, then
  calls `simulate_traversal_check` with the template's own `simulate_args`
  (`gate_one.py:71-80`): `target_path=/World/KitTray`, `cube_paths=[4 SKU paths]`,
  `duration_s` (the 6-SKU source uses **300 s**; trimmed 4-SKU would be lower). This **runs the real
  cuRobo controller** through the full multi-pick sequence in Kit — the expensive step.
- **GATE SUCCESS-CRITERION (the OUTCOME):** in
  `service/isaac_assist_service/chat/tools/handlers/diagnostics.py:4446-4449`:
  ```
  if len(cube_paths) > 1:
      success = bool(delivered) and upright_ok          # multi-cube: ANY cube delivered + primary upright
  else:
      success = bool(in_xy and above_floor and at_rest and upright_ok)
  ```
  For this 4-SKU (multi-cube) scene the gate passes when **at least one** SKU is delivered into the
  kit-tray xy region, at rest, and the primary cube is upright. **It does NOT require all 4.**
  Note the template metadata says `min_items_delivered: 6` / `min_slots_filled: 6`
  (`verify_args`/`simulate_args`) — but those fields are **not** what the gate boolean reads; the
  lenient ANY-cube rule above is the live criterion. This is a known gate-leniency (per project
  memory: "multi-cube = ANY cube delivered + primary upright").

### Step 13 — SYSTEM runs the vision completeness check
- **[LLM/SYSTEM] [EXPENSIVE-physics]** `add_vision_classifier_gate(cube_paths, class_labels,
  camera_path)` + `setup_pick_place_with_vision(...)` classify which tray slots appear occupied from
  the overhead camera and trigger a re-pick of any empty slot.
- **[SYSTEM]** Both are real: `_handle_add_vision_classifier_gate`
  (`service/isaac_assist_service/chat/tools/handlers/sensors.py:562`) captures the viewport and runs
  a **VLM (Gemini)** classification (`_get_vision_provider`); `_handle_setup_pick_place_with_vision`
  (`robot.py:5826`) chains vision → semantic relabel → cuRobo re-pick.
- **Honest caveats:**
  - The vision gate is **"v1 simplification"** — it matches cubes to detections by 2D image distance
    without true world→image projection (`sensors.py` docstring), and assumes left-to-right ordering.
  - In **headless Kit the GPU rasterizer is mocked → vision returns 0 detections**, so
    `setup_pick_place_with_vision` falls back to a **path-name heuristic** (cube path contains a class
    token) — `robot.py:5886-5900`. So the "vision completeness check" passes the *gate* via a name
    heuristic, not via actual pixels, unless a real camera/credentials are wired. This is the
    scenario's biggest **unverified** claim.
  - Each live vision call **consumes one Gemini API call** (`robot.py:5843-5844`) — cost-relevant.
- **[SYSTEM]** Completeness is then read with `track_slot_occupancy(tray_path, cube_paths)`
  (`robot.py:5965`): for each `slot_<n>` marker it finds the nearest cube within **60 % of slot_size**
  (`robot.py:6015`) and returns `filled_count`. This is the human-readable "are all 4 slots filled?"
  answer — but it is a **read-out, not the gate boolean**.

### Step 14 — SYSTEM reports the outcome
- **[SYSTEM] [CHEAP-static]** Gate verdict printed as `GATE success=<bool>` (`gate_one.py:88`).
  `track_slot_occupancy` gives `filled_count / n_slots` for the assembler-facing completeness number.

---

## 4. Tools needed that DO NOT exist (grep-confirmed missing)

Confirmed absent as runtime handlers in
`service/isaac_assist_service/chat/tools/handlers/` (no `data["…"] = …` registration):

1. **`step_rotary_table` / `advance_carousel` / `rotate_to_index`** — MISSING. There is **no tool to
   index the carousel by N degrees and present the next SKU at the handoff.** The handler builds a
   passive joint but nothing steps it. The template's documented workaround (loop:
   `set_attribute` joint target → step physics → `get_world_transform` → re-`setup_pick_place_controller`)
   is **not implemented as a tool** — and its `set_attribute` path/attr is the wrong-joint-path bug
   from Step 5. This is the single biggest capability gap for a *real* 4-SKU carousel kit.
2. **`sim_control`** — MISSING as a handler (appears only in `tool_descriptions_polish.py`). The
   template's rotation workaround calls `sim_control(action="step", step_count=30)` to settle between
   indexes; there is no executor, so the settle-between-rotations step cannot be invoked as written.
3. **`create_bin`** — MISSING as a runtime executor (codegen-only: `robot.py:7306`,
   `_models.py:4176`). Listed in the 6-SKU template's `tools_used` but never dispatchable live; must
   be substituted with raw `create_prim` boxes.
4. **`refresh_pick_targets` / `recompute_pick_targets`** — MISSING. After each carousel rotation the
   child SKU world positions change; nothing re-feeds updated pick targets to the installed
   controller. (`get_world_transform` exists at `handlers/scene_authoring.py` to *read* a pose, but
   there is no tool to *push* the refreshed targets back into the live cuRobo controller.)
5. **`vision_completeness_check` / `verify_kit_complete`** — MISSING as first-class tools. The
   completeness verdict is assembled from `add_vision_classifier_gate` + `track_slot_occupancy`; there
   is no single "is the kit complete?" tool, so the LLM must compose and interpret two outputs.

Tools that DO exist and are real (for contrast): `create_rotary_table`, `create_kit_tray`,
`track_slot_occupancy`, `add_vision_classifier_gate`, `setup_pick_place_with_vision`,
`setup_pick_place_controller`, `robot_wizard`, `set_camera_params`, `set_camera_look_at`,
`get_world_transform`.

---

## 5. Honest outcome summary

- **Template match:** **partial / synthesis required.** No franka+carousel+vision canonical exists;
  the closest (`CP-NEW-kitting-station-6sku`) is UR10/6-SKU with a *documented non-functional*
  carousel rotation. The deliverable scene is a fusion of three drafts.
- **Static-eyes pre-filter:** **`scene_validate.py` catches the Franka-reach / layout mismatch
  cheaply** (UR10-sized tray slots at 1.3–1.6 m fail Franka's 0.855 m reach shell) before any
  physics is spent — but it is blind to the carousel-rotation limitation and to the vision pass.
- **Gate criterion (OUTCOME):** multi-cube → `success = (≥1 SKU delivered to tray xy, at rest)
  AND primary upright` (`diagnostics.py:4446-4449`). The "all 4 slots filled" target in the template
  metadata is **not** enforced by the gate boolean; full completeness is only a `track_slot_occupancy`
  read-out.
- **Biggest unverified / missing pieces:** (a) no `step_rotary_table`/`sim_control` → the carousel
  can't actually index 4 SKUs at runtime; (b) bins aren't jointed to the disc → physical carousel
  carry is unmodelled; (c) headless vision returns 0 detections and falls back to a name heuristic →
  the "vision completeness check" is not pixel-verified without a real camera + Gemini credentials;
  (d) the template's carousel-step guidance cites the wrong joint path/attr
  (`/World/Carousel/RevJoint` + `physics:revJoint:targetPosition` vs the real `/World/Carousel/Joint`
  revolute drive).
