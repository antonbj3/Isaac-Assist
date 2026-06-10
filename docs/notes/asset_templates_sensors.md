# Asset Templates — SENSORS + PERCEPTION

Category audit: perception-gated templates (vision sort, barcode divert, NIR material,
force-controlled insertion, multi-cam inspection). Tool existence and asset paths were
**verified with `grep` and `ls`** — not assumed.

Verification basis (2026-06-09):
- Tool surface: `service/isaac_assist_service/chat/tools/tool_schemas.py` + `handlers/sensors.py`, `handlers/vision.py`
- Assets: `/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Sensors/`
- Existing templates: `workspace/templates/CP-NEW-*.json` (440 templates total)

---

## 1. Tool inventory — what EXISTS vs what is MISSING

### The four named perception tools — ALL EXIST

| Tool | Status | Handler | Schema | Tier |
|------|--------|---------|--------|------|
| `add_vision_classifier_gate` | **EXISTS** | `handlers/sensors.py:562` (`_handle_add_vision_classifier_gate`), registered L1272 | `tool_schemas.py:2634` | A |
| `barcode_reader_sensor` | **EXISTS** | `handlers/sensors.py:880` (`_handle_barcode_reader_sensor`), registered L1273 | `tool_schemas.py:2470` | B |
| `nir_material_sensor` | **EXISTS** | `handlers/sensors.py:1005` (`_handle_nir_material_sensor`), registered L1275 | `tool_schemas.py:1898` | C |
| `add_force_torque_sensor` | **EXISTS** | `handlers/sensors.py:473` (`_handle_add_force_torque_sensor`), registered L1271 | `tool_schemas.py:1914` | C |

### Supporting perception/sensor tools (all verified present, 1 schema each)

| Tool | Schema line | Purpose |
|------|-------------|---------|
| `vision_detect_objects` | 1749 | Gemini Robotics-ER 2D point detection (the VLM behind the classifier gate) |
| `vision_bounding_boxes` | 1768 | Gemini 2D bbox detection (0-1000 normalized) |
| `vision_plan_trajectory` | 1782 | Gemini 2D visual pick-place trajectory |
| `vision_analyze_scene` | 1797 | Gemini free-form spatial reasoning |
| `setup_pick_place_with_vision` | 2611 | Composite: classifier gate + cuRobo controller in one call (1 Gemini call) |
| `add_sensor_to_prim` | 254 | Attach camera / `rtx_lidar` / `imu` / `contact_sensor` / `effort_sensor`; product-spec lookup |
| `lookup_product_spec` | 277 | Real datasheet FOV/res/range/FPS (RealSense, ZED, Velodyne…) |
| `add_proximity_sensor` | 4001 | Trigger-zone sensor that fires the pick sequence |
| `set_camera_params` / `set_camera_look_at` / `capture_camera_image` | 7532 / 7621 / 7588 | Camera intrinsics + aim + frame grab |
| `configure_camera` / `inspect_camera` | 3480 (DEPRECATED) / 3464 | Legacy intrinsics (prefer `set_camera_params`) |
| `setup_contact_sensors` / `get_contact_report` / `list_contacts` | 5631 / 6520 / 6867 | Contact-force readout for force-gated phases |
| `set_semantic_label` / `validate_semantic_labels` | 6472 / 8556 | Class/colour/material labels — the routing oracle `color_routing` reads |
| `setup_impedance_controller` / `setup_admittance_controller` | (present) / 1938 | Compliant Cartesian control for force-gated insertion |
| `setup_assembly_constraint` / `validate_assembly_constraint` | (present) / (present) | FixedJoint-on-success + tolerance check for insertion gates |

### MISSING / GAP tools

- **Local SAM2 + CLIP vision provider — NOT MISSING (it is now ON DISK and importable).**
  This contradicts the "missing — the Gemini-quota gap" framing in the task. Verified state:
  - Module: `service/isaac_assist_service/multimodal/vision_sam_clip.py` (`SamClipVisionProvider`)
  - Weight: `vision_models/sam2.1_hiera_small.pt` **present, 184 MB** (`sam2.1_hiera_small.pt`, dated 2024-09-29)
  - Packages: `sam2`, `open_clip`, `torch 2.10.0+cu128` all import OK
  - Selector: `handlers/_shared.py:515` `_get_vision_provider()`. Policy via `IA_VISION_PROVIDER`:
    `auto` (default) prefers local SAM2+CLIP when the weight exists → **so the default path is
    now LOCAL, not Gemini**. `sam_clip` forces local; `gemini` forces remote.
  - Model id reported: `sam2-hiera-s+clip-vit-b32-local` (`vision_sam_clip.py:235`)
  - **Conclusion**: the Gemini-quota gap is structurally closed for the classifier-gate path.
    `add_vision_classifier_gate` also has a USD colour-introspection fast-path that bypasses
    BOTH providers for colour-shaped templates (`sensors.py:732`, commit cee5cfcb).
  - **Residual gaps** (the real ones to flag):
    1. `add_vision_classifier_gate` v1 cube↔detection pairing assumes camera world-x ≈ image-x
       (`tool_schemas.py:2635` known-limitation note; CP-16 probe: 3/4 cubes, wrong mapping at
       arbitrary angles). **Production v2 needs world→image projection.** This is the real
       perception gap, not the provider.
    2. No dedicated 6-DoF pose-estimation tool (FoundationPose/MegaPose-class) — existing
       `CP-NEW-6dof-pose-estimate-pick` leans on `vision_*` heuristics, not a metric pose net.
    3. No depth/point-cloud segmentation tool (SAM2 is RGB-mask only; no depth fusion handler).

### Camera ASSETS on disk (verified `ls`) — real sensor USDs for inspection templates

| Vendor / model | Path under `…/Isaac/5.0/Isaac/Sensors/` | Modality |
|----------------|------------------------------------------|----------|
| Intel RealSense D455 | `Intel/RealSense/rsd455.usd` | RGB-D |
| Orbbec Gemini 335 | `Orbbec/Gemini335/orbbec_gemini_335.usd` | RGB-D |
| Orbbec Gemini 2 | `Orbbec/Gemini2/orbbec_gemini2_v1.0.usd` | RGB-D |
| Stereolabs ZED X | `Stereolabs/ZED_X/ZED_X.usdc` | Stereo |
| Leopard Imaging Hawk | `LeopardImaging/Hawk/hawk_v1.1_nominal.usd` | Stereo machine-vision |
| SICK Inspector83x | `SICK/Inspector83x/SICK_Inspector83x.usd` | 2D machine-vision smart camera |

(Lidars also present — HESAI/Ouster/Velodyne/SICK — relevant to AMR perception, out of scope here.)

---

## 2. Existing perception templates (do NOT duplicate)

Already cover the headline patterns; the 5 NEW specs below are gap-fillers, not repeats:

- `CP-NEW-nir-material-divert` — NIR material sort (the canonical `nir_material_sensor` template)
- `CP-NEW-barcode-scanner-divert` / `CP-NEW-nim-barcode-track` — barcode SKU lane divert
- `CP-NEW-inspect-reject` / `CP-NEW-yrkesroll-inspector-reject-divert` — vision good/defect reject
- `CP-NEW-sorter-color-3lane` / `CP-NEW-cross-belt-sorter` — vision colour sort
- `CP-NEW-peg-bushing-impedance` / `CP-NEW-screw-driving-impedance` / `CP-NEW-tactile-insertion`
  / `CP-NEW-narrow-clearance-insertion` — force/torque-gated insertion
- `CP-NEW-multi-sensor-fusion-rgbd-imu` / `CP-NEW-multi-rate-sensor-fusion` — RGB-D + IMU fusion
- `CP-NEW-6dof-pose-estimate-pick` / `CP-NEW-hand-eye-calibration` / `CP-NEW-vision-depalletize`

---

## 3. Proposed NEW perception-gated templates (5)

Each follows the CP-NEW template contract verified in `CP-NEW-nir-material-divert.json`
(keys: `task_id, goal, tools_used, thoughts, code, code_template, failure_modes, intent,
roles, role_defaults, settle_state, verify_args, simulate_args, diagnose_args,
motion_controllers, verified_status`). All five reuse only EXISTING tools.

### T1 — `CP-NEW-vision-sort-samclip-local` (Tier A)
**Pattern**: vision colour/class sort, but **provider-pinned to local SAM2+CLIP**
(`IA_VISION_PROVIDER=sam_clip`) to prove the Gemini-quota-free path end-to-end.
3 cubes (red/green/blue) on a static table, overhead `Camera`, Franka routes each to its bin.
- Tools: `create_prim`, `apply_api_schema`, `set_semantic_label`, `set_camera_look_at`,
  `set_camera_params`, `add_vision_classifier_gate`, `setup_pick_place_controller`.
- Asset: `Intel/RealSense/rsd455.usd` as the overhead camera body (cosmetic + intrinsics).
- Gate: ≥2 of 3 cubes reach their colour-matched bin (lenient — v1 pairing caveat).
- Novelty: first template that exercises the LOCAL provider as the routing oracle; closes
  the "Gemini-quota gap" claim with a measurable canonical.

### T2 — `CP-NEW-barcode-recirc-divert` (Tier B)
**Pattern**: barcode SKU divert WITH a recirculation loop — unread/no-read items recirculate
instead of falling through. Combines `barcode_reader_sensor` + `create_recirculation_loop`.
- Tools: `create_conveyor`, `create_recirculation_loop`, `barcode_reader_sensor`,
  `add_proximity_sensor`, `set_semantic_label`, `setup_pick_place_controller`.
- Distinct from `barcode-scanner-divert` (straight belt, fallthrough catch-all) by the
  closed-loop no-read handling (real postal cross-belt behaviour, canonical #17).
- Gate: a known-SKU item reaches its lane bin; a deliberately-unlabelled item completes ≥1
  loop pass (recirc state advances).

### T3 — `CP-NEW-ft-insertion-noisy-compliant` (Tier C)
**Pattern**: force-controlled peg insertion with **sensor noise injection** + admittance
control — the sim-to-real-gap variant of `peg-bushing-impedance`.
- Tools: `add_force_torque_sensor` (with `noise_std` > 0 + `publish_topic`),
  `setup_admittance_controller`, `setup_assembly_constraint`, `validate_assembly_constraint`,
  `setup_pick_place_controller`, `add_proximity_sensor`.
- Novelty: exercises the `noise_std`/`publish_topic` branches of `add_force_torque_sensor`
  (handler L497-514) that no current template covers; admittance (not impedance) law.
- Gate: peg seats in bushing (assembly constraint validates) with insertion force capped
  under threshold despite injected Gaussian F/T noise.

### T4 — `CP-NEW-multicam-inspect-stereo` (Tier B)
**Pattern**: multi-camera inspection — two real stereo/RGB-D camera assets view a part from
two angles; a vision pass on EACH viewport must agree (logical-AND) before pass/reject divert.
- Tools: `add_sensor_to_prim` (×2, `sensor_type="camera"`, `product_name` lookup),
  `set_camera_look_at` (×2), `vision_detect_objects` (×2), `setup_pick_place_controller`.
- Assets: `Stereolabs/ZED_X/ZED_X.usdc` + `LeopardImaging/Hawk/hawk_v1.1_nominal.usd`
  (or `SICK/Inspector83x/SICK_Inspector83x.usd` for a 2D smart-cam variant).
- Novelty: first MULTI-camera consensus gate (existing inspect-reject is single-cam);
  reduces the single-view false-accept failure mode.
- Gate: a defect-free part reaches PassBin only when BOTH cameras classify "good".

### T5 — `CP-NEW-nir-barcode-dual-oracle` (Tier C)
**Pattern**: dual-sensor recycling line — `nir_material_sensor` (material) AND
`barcode_reader_sensor` (SKU) both read each item; routing key = material×SKU cross-product
(e.g. metal+SKU-A → BinAlu, plastic+SKU-B → BinPET). Canonical #18 Recycling Multi-Sensor.
- Tools: `nir_material_sensor`, `barcode_reader_sensor`, `add_proximity_sensor`,
  `set_semantic_label` (`class` for material), `set_attribute` (SKU attr),
  `setup_pick_place_controller` (composite `color_routing`).
- Novelty: first template fusing TWO non-vision sensor oracles into one routing decision;
  both existing NIR and barcode templates use a single oracle.
- Gate: a metal+SKU-A item reaches the correct cross-product bin (distinct from a
  metal+SKU-B item) — proves both reads gate the same dispatch.

---

## 4. Tool-implementation notes for template authors (gotchas verified in code)

1. **`color_routing` reads `Semantics_class` / `Semantics_color` / `Semantics_colour` ONLY**
   (`_cube_semantic_class`). A `Semantics_material` instance is silently ignored → use
   `set_semantic_label(..., semantic_type="class")` even for NIR/material sorts
   (`CP-NEW-nir-material-divert` failure_mode #2).
2. **Leave one class out of `color_routing`** → it becomes the `destination_path` fall-through
   catch-all (else the default bin goes unused).
3. **Scan-before-pick ordering**: keep belt ≤ 0.20 m/s so the NIR/barcode/vision read fires
   before the proximity pick-trigger (handler does not re-order events).
4. **`scan_radius` ≥ half belt width** or edge items miss the scan volume.
5. **`add_vision_classifier_gate` is camera-axis-fragile** — only trust it for 2-cube
   left-right sorts or agent-validated mappings until world→image projection lands (v2).
6. **`add_force_torque_sensor` noise/publish branches** are opt-in (`noise_std>0`,
   `publish_topic` set) — handler L500-514 only injects those blocks when args present.
7. **Local provider is default-on when the weight exists** — set `IA_VISION_PROVIDER=gemini`
   explicitly if a template must measure the remote path.
