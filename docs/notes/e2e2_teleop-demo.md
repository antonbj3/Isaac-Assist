# E2E Trace — `teleop-demo`: "record a teleoperated demonstration of a pick task for imitation learning"

**Scenario id:** teleop-demo · **domain:** imitation-learning · **robot:** franka · **task:** teleop-record
**Date traced:** 2026-06-09 · **Mode assumed:** direct-eval (no human, no hardware on the dev box)

Closest real template: **`workspace/templates/CP-NEW-groot-teleop-demo-record.json`** (exact match — this scenario IS this canonical).
Handlers: `service/isaac_assist_service/chat/tools/handlers/teleop.py` + `…/diagnostics.py` (hardware probe + validate).

---

## 0. Verdict up front

The teleop **plumbing exists and is fully wired** (7 codegen + 2 data handlers, all registered, all in the schema). The scenario builds a scene, "records" 5 HDF5 files, and the canonical's structural form-gate is designed to pass. **But the recording is a hollow shell, and worse, it is internally self-contradictory:**

- **DECISIVE BUG (new):** `record_teleop_demo`'s finalizer writes `obs/{joint_positions, joint_velocities, ee_pose}` + `timestamps` but **never writes an `actions` dataset** (`teleop.py:545-556`). Yet `validate_teleop_demo` **requires** `actions` (`diagnostics.py:5184-5187`) and `summarize_teleop_session` **skips any demo lacking `actions`** (`teleop.py:945-947`). So a *genuinely recorded* file FAILS validation ("missing actions dataset") and summarizes to `demos=0` — the exact opposite of the template's claimed "T=0 passes" honesty note. The producer and the two consumers were written against **different schemas**.
- **No teleop signal is ever produced** even with the WebSocket bridge up: the recorder samples `DriveAPI.GetTargetPositionAttr()` (the *commanded drive target*), and nothing commands the drive unless a WebSocket client streams `joint_command` JSON. In direct-eval there is no client → targets never change → every sampled row is identical → the "demonstration" is a constant.
- This reveals a **CLASS-LEVEL gap**: there is no **human-input / device-driver class** in the platform. Every other controller class (cuRobo, RMPflow, pick_place, nav) closes its own loop in-sim; teleop is the only task family whose *defining input* lives outside the process and is never mocked. See §6.

---

## 1. Actors / legend

`[USER]` human typing the request · `[LLM]` the agent (tool-calling model) · `[SYSTEM]` the service / Kit RPC / gate.
`[CHEAP-static]` USD authoring, attr writes, dict lookups, HDF5 schema checks — no physics solve.
`[EXPENSIVE-physics]` `sim_control(play/step)`, physics-step callbacks, articulation stepping.

---

## 2. Full traced action sequence

### Phase A — request → retrieval → plan

1. `[USER]` "record a teleoperated demonstration of a pick task for imitation learning."
2. `[SYSTEM]` `[CHEAP-static]` Intent/retrieval embeds the request against `intent.structural_tags`. The tags `isaac:groot.demo_record`, `isaac:teleop.recording_session`, `isaac:teleop.spacemouse`, `isaac:dataset.hdf5_robomimic` are the discriminating signal → retrieves **`CP-NEW-groot-teleop-demo-record`** with high confidence. This is a clean hit; no disambiguation round needed.
3. `[LLM]` `[CHEAP-static]` Reads the `goal` + `code_template`. Note: the user said nothing about *5 demos*, *SpaceMouse*, or *HDF5* — the template's `role_defaults` supply all of that (`recording_output.n_demos=5`, `input_device.device=spacemouse`, `recording_output.frequency_hz=30`). The LLM adopts these defaults verbatim. **(Trace observation: the user asked for "a demonstration" — singular, device-agnostic — and the canonical silently upgrades it to a 5-episode SpaceMouse session. Acceptable defaulting, but the LLM never surfaces the device assumption to the user.)**

### Phase B — scene build (all `[CHEAP-static]` USD authoring)

4. `[LLM]→[SYSTEM]` `create_prim` DomeLight + `set_attribute` intensity=1000.
5. `[LLM]→[SYSTEM]` `create_prim` Ground (Cube, z=-0.5, scale 20×20×1) + `apply_api_schema` PhysicsCollisionAPI.
6. `[LLM]→[SYSTEM]` `create_prim` Table (Cube, z=0.375) + PhysicsCollisionAPI.
7. `[LLM]→[SYSTEM]` `create_prim` `/World/SourceCube` (0.40, 0.20, 0.78; 4 cm) + PhysicsCollisionAPI + **PhysicsRigidBodyAPI** (the pick target).
8. `[LLM]→[SYSTEM]` `create_prim` `/World/Bin` (0.00, -0.30, 0.78; flat) + PhysicsCollisionAPI (static fixture, the place target).
9. `[LLM]→[SYSTEM]` `set_physics_scene_config(enable_gpu_dynamics=False, broadphase=MBP)` — CPU determinism.
10. `[LLM]→[SYSTEM]` `robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0,0,0.75], orientation=[0.7071,0,0,0.7071])`. **(Good: uses `robot_wizard`, the wound-start-safe spawn per MEMORY — not a raw `add_reference`.)**

### Phase C — sim start

11. `[LLM]→[SYSTEM]` `sim_control(action="play")` → `[EXPENSIVE-physics]` physics begins ticking.
12. `[LLM]→[SYSTEM]` `sim_control(action="step", step_count=30)` → `[EXPENSIVE-physics]` settle (cube drops onto table, arm at home).

### Phase D — teleop lifecycle

13. `[LLM]→[SYSTEM]` **`check_teleop_hardware(device="spacemouse")`** → `[CHEAP-static]`
    - Handler: `diagnostics.py:2718`. Looks up `_TELEOP_DEVICES["spacemouse"]` (`diagnostics.py:445`). Returns `supported=True, transport="usb-hid", latency_budget_ms=20, known_limitations=["6-DoF only — no hand retargeting"]`.
    - **The "probe" is a dict lookup, not a probe.** `supported:True` is hard-coded in the table regardless of whether a SpaceMouse is plugged in. The only real probe is `local_probe = {dev_input_exists, entries}` — it counts `/dev/input` entries but **never matches a 3Dconnexion vendor/product id**. So on a box with a keyboard and mouse, `dev_input_exists=True, entries=20` and the LLM reads this as "device present" → **false-positive hardware presence**. The template's own `thoughts` claim this is "the natural decision point for graceful degradation," but the handler gives the LLM no signal to degrade on.
14. `[LLM]→[SYSTEM]` **`configure_teleop_mapping(robot_path, device_axes=[6 spacemouse axes], joint_names=[7 panda joints], gains={position:400, velocity:40})`** → `[CHEAP-static]`
    - Handler: `teleop.py:247`. Writes the axis→joint table as USD custom attrs on the articulation. This is config persistence only; it installs **no IK** that turns 6-DoF Cartesian deltas into 7 joint targets. The template `thoughts` claim "resolved via IK to all 7 panda joints" — **that IK does not exist in the handler.** The mapping is a flat label table.
15. `[LLM]→[SYSTEM]` **`start_teleop_session(robot_path, input_device="spacemouse", stream_quality="medium")`** → `[EXPENSIVE-physics]` (registers a pre-step callback)
    - Handler: `teleop.py:40`. Tries to open a WebSocket server on **port 8766** (note: template `failure_modes` says 8765 — off by one, harmless). Registers `_teleop_physics_step` (`teleop.py:174`) which, **on each physics tick, reads `_teleop_state['last_joint_targets']` and applies them to the joints.** Those targets are populated *only* by an incoming WebSocket `{type:'joint_command'}` message (`teleop.py:135-137`).
    - **In direct-eval there is no WebSocket client.** `last_joint_targets` stays `None`; the watchdog zeroes velocity after 2 s. The arm does not move. There is no SpaceMouse driver, no keyboard hook into Kit, no scripted demonstrator. The "session" is a server waiting for a peer that never connects.
16. `[LLM]→[SYSTEM]` **loop i=0..4: `record_teleop_demo(output_path=demos/groot_recordings/demo_00{i}.hdf5, robot_path, frequency_hz=30)`** then `sim_control(step, 60)` between each → `[EXPENSIVE-physics]`
    - Handler: `teleop.py:349`. Registers a **second** physics-step callback `_record_physics_step` (`teleop.py:493`) that samples at 30 Hz:
      - `_get_joint_positions()` (`:428`) reads `DriveAPI.GetTargetPositionAttr()` — the **commanded target**, not the measured articulation joint angle. With no teleop input, this is the home pose, constant for the whole episode.
      - `_get_joint_velocities()` (`:441`) reads `GetTargetVelocityAttr()` — also commanded, default 0.
      - `_get_ee_pose()` (`:454`) does a real FK on a heuristically-found EE link — this *is* live, but it never moves because the joints never move.
    - **Each call REGISTERS a new recording sub but does NOT finalize.** Finalize happens only in `stop_teleop_session`/`_finalize_recording`. So calling `record_teleop_demo` 5 times in a loop stacks **5 recording callbacks all writing into 5 separate `_rec_data` dicts**, but only the LAST `_teleop_state['rec_data']` is the one `stop_teleop_session` will finalize. **The first 4 demo files are never written to disk.** (The template's loop assumes each call produces a file; the handler's lifecycle produces *one* file at stop-time.)
    - This is a structural mismatch between the template's loop contract and the handler's single-buffer/finalize-at-stop design. (New finding; see §5.)
17. `[LLM]→[SYSTEM]` **loop: `validate_teleop_demo(hdf5_path=demo_00{i}.hdf5)`** → `[CHEAP-static]`
    - Handler: `diagnostics.py:5153`. Opens each HDF5, iterates `/data/<demo>`, and **requires `demo["actions"]`** (`:5184`). The recorder never wrote `actions` → returns `issues=[{problem:"missing actions dataset"}]`, `ready_for_training=False` for every file that *does* exist; the 4 missing files return `available=False` ("file not found").
    - **Both branches fail.** This is the decisive contradiction: the producer's schema (`obs/*` + `timestamps`, no `actions`) and the validator's schema (`actions` mandatory) are incompatible.
18. `[LLM]→[SYSTEM]` **loop: `summarize_teleop_session(hdf5_path=...)`** → `[CHEAP-static]`
    - Handler: `teleop.py:904`. Also keys off `actions` (`:945-947`); `if actions is None: continue`. Every demo skipped → `demos=0`, `total_duration_s=0`. (Also a minor key mismatch: record writes `f.attrs['frequency_hz']` (`:560`); summarize reads `f.attrs.get("fps")` (`:921`) — non-fatal, falls back to 30.)
19. `[LLM]→[SYSTEM]` **`stop_teleop_session()`** → `[EXPENSIVE-physics]` teardown
    - Handler: `teleop.py:576`. Zeros velocities, unsubscribes callbacks, closes WS, calls `_finalize_recording()` on the one live `rec_data` → writes **`demo_004.hdf5` only** (the last loop iteration's buffer) with `obs/*` + `timestamps`, **no `actions`**.
20. `[LLM]→[SYSTEM]` `sim_control(action="stop")` → physics halts.
21. `[LLM]→[SYSTEM]` `get_console_errors(last_n=10, min_level="error")` → `[CHEAP-static]` cleanup probe.

### Phase E — gate

22. `[SYSTEM]` `[CHEAP-static]` **Form-gate / verifier** (`verify_args.stages[0].check = "n_demo_files_written"`, `expected_n_demos=5`). Counts HDF5 files under `workspace/demos/groot_recordings/`. **Reality: 1 file on disk** (`demo_004.hdf5`), not 5, because finalize runs once at stop. → `files_on_disk=1 != 5` → **gate FAIL** on file count *alone*, before validation even matters.
    - `simulate_args.check="teleop_session_complete"` (`duration_s=180`) — there is **no registered `teleop_session_complete` simulate verifier**; the function-gate has nothing to run. The template's own `verified_status` admits "function-gate BLOCKED (requires SpaceMouse hardware + human operator)".

---

## 3. OUTCOME

| Path | Result |
|---|---|
| **Scene build** | OK — Franka + cube + bin + table author cleanly. |
| **Hardware probe** | Returns `supported:True` (hard-coded), false-positive presence; LLM cannot detect "no SpaceMouse." |
| **Mapping/session start** | Config attrs + WS server up. No IK, no input source. Arm never moves. |
| **Recording (5×)** | Only the LAST buffer finalizes → **1 file on disk, not 5.** That 1 file has `obs/*`+`timestamps`, **no `actions`.** |
| **validate_teleop_demo** | **FAIL** on every file: missing-actions (the one real file) + file-not-found (the 4 phantom files). |
| **summarize_teleop_session** | `demos=0` (skips actions-less demos). |
| **Form-gate** | **FAIL** — `files_on_disk=1 ≠ 5`, `all_valid=False`, `demo_count=0`. The template's `session_ok` is False. |
| **Function-gate** | **BLOCKED / unrunnable** — no `teleop_session_complete` verifier; no human/hardware in the loop. |

**Net:** the scenario produces **zero usable imitation-learning data** and **fails its own gate**, even though every individual tool "succeeds" (returns without raising). The template's claimed graceful-degradation story (`T=0 HDF5 passes structural checks`) is **false against the actual handler code** — the validator demands `actions`, which the recorder never writes. This is a silent-success / honesty hole at the *canonical* level, not just the handler level.

---

## 4. Grounding (file:line)

- Closest template: `workspace/templates/CP-NEW-groot-teleop-demo-record.json` (full match).
- Registration: `teleop.py:1027-1036` (7 codegen + summarize), `diagnostics.py:5845/5870` (check_teleop_hardware, validate_teleop_demo).
- **Producer schema (no `actions`):** `teleop.py:545-556` — writes `obs/joint_positions`, `obs/joint_velocities`, `obs/ee_pose`, `timestamps`.
- **Validator requires `actions`:** `diagnostics.py:5184-5187`.
- **Summarize requires `actions`:** `teleop.py:945-947`.
- Commanded-target sampling (not measured state): `teleop.py:434-436` (`GetTargetPositionAttr`).
- Input only via WebSocket client: `teleop.py:130-143` (`_ws_handler`), applied at `teleop.py:174-217` (`_teleop_physics_step`).
- Hardware "probe" is a dict lookup: `diagnostics.py:2722-2757` + table `diagnostics.py:445-480`.
- fps/frequency_hz attr mismatch: `teleop.py:560` vs `diagnostics`/`teleop.py:921`.
- Gate: `verify_args.stages[0].check="n_demo_files_written"`, `simulate_args.check="teleop_session_complete"` (no verifier registered).

---

## 5. NEW tool-level gaps (not in TOOL_GAP_INVENTORY_V2)

V2 lists nothing for teleop/imitation/HDF5/XR (grep clean). All of the following are new:

1. **HDF5 schema split — `actions` required by validate/summarize but never written by record.** A real recording fails its own validator. The single highest-impact fix; without it, the entire teleop family is structurally un-passable on honest data. (teleop.py:545 vs diagnostics.py:5184.)
2. **`record_teleop_demo` lifecycle vs loop contract.** Per-call registration + finalize-only-at-stop means a 5× loop yields 1 file, and 4 buffers leak. Either `record_teleop_demo` must finalize per call, or the canonical must record-stop-record-stop. Today neither the template nor handler reconcile this. (teleop.py:349 + 535 + 576.)
3. **`check_teleop_hardware` cannot detect device absence.** `supported` is table-constant; `local_probe` counts `/dev/input` entries but never matches a 3Dconnexion HID id. No signal for the documented "fall back to keyboard" decision. (diagnostics.py:2722.)
4. **No 6-DoF→7-joint IK in `configure_teleop_mapping`.** The mapping is a label table; the Cartesian-delta→joint resolution the template's `thoughts` describe is absent. (teleop.py:247.)
5. **No registered `teleop_session_complete` function-gate verifier.** `simulate_args.check` points at a verifier that doesn't exist → function-gate is permanently un-runnable, not merely hardware-blocked.

---

## 6. KEY DELIVERABLE — NEW CLASS-LEVEL architectural gap

**Missing class: a HUMAN-INPUT / DEVICE-DRIVER controller class (and its in-sim mock), distinct from the planner/controller classes.**

Every controller family the platform supports so far — cuRobo, RMPflow, pick_place, nav2/Lula, suction — **closes its own loop inside the Kit process**: given a scene, the handler computes targets and drives the articulation each tick, and a gate can score the physical result. Teleop is the **first and only task family whose defining input originates OUTSIDE the process** (a SpaceMouse over USB-HID, a Quest 3 over WebXR, a Vision Pro over CloudXR, or a human at a keyboard). The platform has **no abstraction for an external/human action source**, and — critically — **no in-sim mock of one**.

The blast radius is the whole imitation-learning / foundation-model-data branch, all of which presuppose a *real demonstration*:
- `CP-NEW-groot-teleop-demo-record` (this scenario) — produces the corpus.
- `CP-NEW-groot-finetune-n10-demos`, `CP-NEW-groot-export-dataset-hdf5`, `CP-NEW-groot-redact-finetune`, `CP-NEW-groot-data-mix-multitask` — **CONSUME** this corpus. If the corpus is hollow (constant joints, no `actions`), every downstream "fine-tune" trains on a no-op. The hollowness propagates silently through the entire GR00T chain.
- `CP-NEW-teaching-mode-pose-replay` is the *near-miss that proves the gap*: it sidesteps human input by capturing **programmatic waypoints** — i.e. the platform already needed, and improvised, a non-human action source because no proper one exists.

**Why this is class-level, not a bug:** the humanoid-cabinet trace showed pick-place breaks on articulated doors → needs a *revolute-pull controller class*. This is the exact analogue on the input side: imitation-learning breaks on teleop because there is no *demonstration-source class*. You cannot patch it with another `obs` key. What's needed is a new primitive — call it a **`scripted_demonstrator` / `teleop_mock` action source** — that, in direct-eval, drives the articulation through a *real* pick-place trajectory (reuse the existing pick_place controller as the "expert") and **records the resulting joint targets AS `actions`**. That single primitive would:
- make `record_teleop_demo` produce non-constant `actions` (fixing the schema split by *populating the missing dataset from the expert*),
- give the function-gate something to score (`teleop_session_complete` = N files, each with `actions.shape[0] ≥ min_actions_per_demo`, EE actually traversed pick→place),
- and turn the entire GR00T-finetune branch from "trains on no-ops" into "trains on synthetic-expert demos" — honest, reproducible, hardware-free.

Until that class exists, **every teleop/imitation canonical can only ever pass structurally with empty data, or fail honestly with real data** — there is no path to an honest pass. That is the architectural verdict.

---

## 7. One-line summary

Teleop tooling is fully wired but architecturally hollow: the recorder and its validator disagree on the HDF5 schema (`actions` written by neither but required by both consumers), no external/human action source exists or is mocked, so the imitation-learning family has **no honest-pass path** — it needs a new **demonstration-source (scripted_demonstrator/teleop_mock) controller class** that drives an expert trajectory and records it as `actions`.
