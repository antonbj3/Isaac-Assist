# Asset-Driven Template Specs — Robots + Grippers / EOAT

**Date:** 2026-06-09
**Category:** ROBOTS + GRIPPERS/EOAT
**Asset root:** `/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Robots/`
**Tool surface:** `service/isaac_assist_service/chat/tools/handlers/` + `tool_schemas.py` (445 schemas)
**Method:** Every asset path below was confirmed with `ls`/`-f`; every tool claim was confirmed with `grep` against the handlers. cuRobo robot configs were enumerated from the installed `curobo/content/configs/robot/`.

---

## 0. The capability matrix (READ THIS FIRST)

Buildability of any arm pick-place template is gated by **which planner backend can drive the arm**, not by whether the USD exists. The motion stack has three tiers:

| Backend (`target_source`) | Robots actually supported | Source of truth |
|---|---|---|
| **`curobo`** (collision-aware GPU, best) | `franka`, `ur10`/`ur10e`, `unitree_g1` (per-arm), `dual_ur10e` | `curobo/content/configs/robot/*.yml` — ONLY these 7 yml files exist: `franka.yml`, `ur10e.yml`, `ur10_scene.yml`, `dual_ur10e.yml`, `unitree_g1.yml`, `unitree_g1_29dof_retarget.yml`, `simple_mimic_robot.yml` |
| **native** (`isaacsim...examples`) | `franka`, `cobotta_pro_900` | `pick_place.py:1087` (franka), `:1142` (cobotta `CobottaPro900` + its bundled `PickPlaceController`) |
| **`spline` / `fixed_poses` / `sensor_gated`** | robot-agnostic (Cartesian waypoints + IK) — works for ANY arm with a valid articulation + ee frame | `pick_place.py` `_gen_pick_place_spline`, `_gen_pick_place_fixed_poses`, `_gen_pick_place_sensor_gated` |

**Consequence:** Franka and the UR family (via ur10/ur10e config) and G1 are the only "first-class" arms. Every OTHER arm (Cobotta beyond native, Kinova Gen3, Fanuc CRX, Yaskawa, xArm, Techman, Lite6, UF850) is buildable **only** through the robot-agnostic `spline`/`fixed_poses`/`sensor_gated` lane — which is real and shipping, but lower-fidelity (no collision-aware global plan).

`setup_pick_place_controller` auto-detects `robot_family` from the path (`pick_place.py:175`): `ur10/ur5/ur16 → ur10`, `cobotta → cobotta_pro_900`, `g1/unitree → g1_*`, else `franka`. So passing a Kinova/Fanuc path silently falls through to a **franka** Panda controller — a real footgun the templates must avoid by choosing `target_source="spline"`.

---

## 1. Asset inventory (verified on disk)

### Arms (manipulators)
| Robot | USD (verified) | DOF/notes |
|---|---|---|
| Franka Panda | `FrankaRobotics/FrankaPanda/franka.usd` | 7-DOF + parallel hand (built-in) |
| Franka FR3 | `FrankaRobotics/FrankaFR3/fr3.usd` | 7-DOF, newer gen |
| Factory Franka | `FrankaRobotics/FactoryFranka/factory_franka.usd` | factory-tuned |
| UR3/3e/5/5e/10/10e/16e/20/30 | `UniversalRobots/<model>/<model>.usd` | full family present (9 models) |
| UR10 + short suction | `UniversalRobots/ur10/grippers/short_gripper.usd` | suction EOAT |
| UR10 + long suction | `UniversalRobots/ur10/grippers/long_gripper.usd` | suction EOAT |
| Fanuc CRX-10iA/L | `Fanuc/CRX10IAL/crx10ial.usd` | collaborative |
| Kinova Gen3 (7-DOF) | `Kinova/Gen3/gen3n7_instanceable.usd` | + Jaco2 j2n6/j2n7 present |
| Denso Cobotta Pro 900/1300 | `Denso/CobottaPro900/cobotta_pro_900.usd` | 900 has native controller |
| Yaskawa Motoman NEX10 | `Yasakawa Motoman/NEX10/NEX10.usd` | (dir name has a space) |
| Techman TM12 | `Techman/TM12/tm12.usd` | cobot |
| Ufactory xArm6/xArm7/UF850/Lite6 | `Ufactory/<model>/<model>.usd` | + `xarm_gripper`, `lite6_gripper` |
| Kuka, Kawasaki, Flexiv, RethinkRobotics | dirs present | not deep-checked |

### Grippers / EOAT (verified)
| Gripper | USD (verified) | Type |
|---|---|---|
| Robotiq 2F-85 | `Robotiq/2F-85/Robotiq_2F_85_edit.usd` | 2-finger parallel |
| Robotiq 2F-140 | `Robotiq/2F-140/2f140_instanceable.usd` | 2-finger parallel (wide) |
| Robotiq Hand-E | `Robotiq/Hand-E/Robotiq_Hand_E_edit.usd` | 2-finger parallel (precision) |
| UR10 short/long suction | `.../ur10/grippers/{short,long}_gripper.usd` | suction |
| Allegro Hand | `WonikRobotics/AllegroHand/allegro_hand.usd` | 4-finger dexterous (16-DOF) |
| Shadow Hand | `ShadowRobot/ShadowHand/shadow_hand.usd` | 5-finger dexterous (24-DOF) |
| Unitree Dex3 / Dex5 | `Unitree/Dex3/dex3_1_r.usd`, `Unitree/Dex5/...` | dexterous hands |
| xArm / Lite6 gripper | `Ufactory/xarm_gripper/xarm_gripper.usd` | parallel |

> NOTE: Robotiq, Shadow, Dex3/Dex5, and the bare xArm/Lite6 gripper USDs are **stand-alone EOAT** — none is pre-mounted on an arm in the asset library. Mounting them on an arm is an open authoring task (no `attach_gripper`/`mount_eoat` tool exists — see §4 gaps).

### Humanoids / legged / mobile (verified)
| Robot | USD | class |
|---|---|---|
| Unitree G1 | `Unitree/G1/g1.usd` (+ 29-DOF with-hand variant) | humanoid (curobo-supported per-arm) |
| Unitree H1 | `Unitree/H1/h1.usd` (+ `h1_hand_{left,right}.usd`) | humanoid |
| Fourier GR-1 | `FourierIntelligence/GR-1/...` | humanoid |
| Sanctuary Phoenix, Agility Digit/Cassie, Agibot A2D | dirs present | humanoid/biped |
| Boston Dynamics Spot | `BostonDynamics/spot/spot.usd`, `spot_with_arm.usd` | quadruped (+ arm variant) |
| ANYmal B/C/D | `ANYbotics/anymal_{b,c,d}/...` | quadruped |
| Unitree Go1/Go2/A1/B2/Aliengo/Laikago | `Unitree/<model>/...` | quadruped |
| NVIDIA Carter v1 / Nova Carter | `NVIDIA/Carter/carter_v1.usd`, `NVIDIA/NovaCarter/nova_carter.usd` | AMR |
| NVIDIA Jetbot / Kaya / Leatherback | `NVIDIA/Jetbot/jetbot.usd` etc | small mobile |
| iRobot Create3, Clearpath Dingo/Jackal | `iRobot/Create3/create_3.usd`, `Clearpath/...` | AMR |
| Idealworks iw.hub | `Idealworks/iwhub/iw_hub.usd` | industrial AMR (has lift) |
| **Clearpath Ridgeback+Franka** | `Clearpath/RidgebackFranka/ridgeback_franka.usd` | **mobile manipulator** |
| **Clearpath Ridgeback+UR5** | `Clearpath/RidgebackUr/ridgeback_ur5.usd` | **mobile manipulator** |

---

## 2. Tool existence audit (grepped, not assumed)

| Tool | Status | Evidence |
|---|---|---|
| `setup_pick_place_controller` | EXISTS | `pick_place.py:293`; schema `tool_schemas.py:3921`. Branches: franka (curobo+native), ur10/ur10e (curobo), cobotta_pro_900 (native only), g1_left/right_arm (curobo). Auto-detect at `:175`. |
| `list_available_controllers` | EXISTS | `tool_schemas.py:3994` — probes env, returns runnable `target_source` list |
| `surface_gripper` | EXISTS | `robot.py:6153` (`_handle_surface_gripper`); schema `:2525`. UR10 suction variant + `CreateSurfaceGripper` fallback + direct `IsaacSurfaceGripper` author |
| `create_gripper` | EXISTS | `robot.py:1443`. `gripper_type ∈ {parallel_jaw, suction}` only. Hard-codes panda finger joint names as default → Franka-biased |
| `grasp_object` | EXISTS | `robot.py:2844`. RmpFlow approach/grasp/lift; `grasp_type ∈ {top_down, from_file}`; parallel-jaw oriented. NOT a 3-finger / dexterous-hand grasp |
| `setup_bimanual_pick_place_controller` | EXISTS (G1 only) | `humanoid.py:23`. V0 = two per-arm cuRobo controllers, sequential. This IS the "humanoid pick-place" tool, but locked to G1 |
| `robot_wizard` | EXISTS | `robot.py:_gen_robot_wizard`. Registry (`_shared.py:155+`): franka_panda, h1, g1, spot, anymal_c, nova_carter, ur10/ur10e, allegro, jetbot, carter. UR10e ships `home_joints` + `ee_link` |
| `import_robot` / `anchor_robot` | EXISTS | `robot.py:3940+` map: franka, spot(+arm), carter, jetbot, ur10, ur5e, anymal_*, a1/go1/go2, g1/h1(+hands), allegro, ridgeback_franka, humanoid |
| `assemble_robot` | EXISTS | `robot.py:_gen_assemble_robot` — generic multi-part assembly |
| `create_wheeled_robot` / `navigate_to` | EXISTS | `robot.py:_gen_create_wheeled_robot`, `_gen_navigate_to` (A* `astar`) — AMR navigation lane |
| **`setup_amr_with_manipulator`** | **MISSING** | No handler/schema. Ridgeback USDs are in import maps but no coordinated base+arm pick-place controller. Grep for `amr_with_manip\|mobile_manip\|setup_amr` → 0 hits |
| **`setup_humanoid_pick_place`** (generic) | **PARTIAL** | Only `setup_bimanual_pick_place_controller`, hard-locked to G1 (`unitree_g1.yml`). H1, GR-1, Digit, Phoenix have NO controller path |
| **3-finger / dexterous grasp** (Allegro/Shadow/Dex) | **MISSING** | No grasp synthesis/controller for multi-finger hands. `grasp_object` is parallel-jaw RmpFlow. Allegro is in registries as an *asset* but has no closing/grasp tool |
| `setup_surface_gripper` alias | n/a | the tool is named `surface_gripper` (no `setup_` prefix) |

---

## 3. Proposed template specs

Tiering: **A = first-class** (curobo/native backend exists for this exact arm — highest fidelity, lowest risk).
**B = robot-agnostic lane** (buildable today via `spline`/`fixed_poses`/`sensor_gated`, no per-arm planner config — medium fidelity).
**C = blocked** (needs a missing tool before it can be built — listed to scope the gap).

### Tier A — first-class arms (curobo / native)

**RG-A01 — Franka + parallel hand: conveyor pick-and-place**
Robot `franka.usd`; built-in parallel hand. `setup_pick_place_controller(target_source="curobo", robot_family="franka")` over a `create_conveyor` belt with a `add_proximity_sensor` gate. This is the proven CP-* pattern. Tools: all EXIST.

**RG-A02 — Franka: 3-bin color sort**
Franka + curobo, `drop_targets` dict routing 3 cube colors to 3 bins. Extends CP-13 drop_targets. Tools EXIST.

**RG-A03 — Franka: 2-cube column stack (assemble)**
Exactly CP-13's pattern, stacking with per-layer z drop targets. Tools EXIST.

**RG-A04 — UR10 + short-suction gripper: bin-stacking / palletize**
`ur10.usd` + `grippers/short_gripper.usd` + `surface_gripper(robot_path, ee_link="...ee_link")` to author the IsaacSurfaceGripper suction; `setup_pick_place_controller(target_source="curobo", robot_family="ur10")` (uses `ur10_scene.yml`, the cup-frame-matched config). Mirrors NVIDIA's own `ur10_bin_stacking_short_suction.usd` sample. Tools EXIST (this is the most battle-tested non-Franka path — see MEMORY UR10 cup-frame work).

**RG-A05 — UR10 + long-suction: deep-bin depalletize**
Same as A04 but `long_gripper.usd` for reach into a deep bin. `surface_gripper` selects `Long_Suction` variant automatically (`robot.py:6180`). Tools EXIST.

**RG-A06 — UR10e + suction: machine-tend (load/unload a fixture)**
`ur10e.usd` (registry has `home_joints`+`ee_link`), curobo `ur10e.yml`, suction pick from input tray → place into a machine fixture → retrieve finished part. `target_source="curobo", robot_family="ur10e"`. Tools EXIST.

**RG-A07 — Cobotta Pro 900 + parallel gripper: tabletop pick-place (native)**
`cobotta_pro_900.usd`; `setup_pick_place_controller(target_source="native", robot_family="cobotta_pro_900")` → uses the bundled `CobottaPro900` + its `PickPlaceController` (`pick_place.py:1142`). NO curobo config, so native only. Tools EXIST (native lane).

**RG-A08 — Unitree G1: bimanual pick-place (humanoid)**
`g1.usd` + `setup_bimanual_pick_place_controller` (two per-arm curobo controllers, sequential). Left arm sources → left destination, right arm → right. Tools EXIST (G1-only).

**RG-A09 — Dual UR10e: shared-belt two-arm sort**
`dual_ur10e.yml` curobo config exists. Two UR10e arms over one belt; this is the CP-52/dual-franka class but with the UR10e config that actually ships. Tools EXIST for the per-arm controllers; coordination via per-cube mutex pattern (CP-52 lesson). Medium-high risk (shared-belt exec-gate root, see MEMORY).

### Tier B — robot-agnostic lane (spline / fixed_poses / sensor_gated)

These are buildable TODAY because `spline`/`fixed_poses`/`sensor_gated` need only a valid articulation + an `ee_link`, not a per-arm planner config. Lower fidelity (no collision-aware global plan) but real and shipping.

**RG-B01 — Kinova Gen3 (7-DOF): pick-place via spline waypoints**
`gen3n7_instanceable.usd`; `setup_pick_place_controller(target_source="spline", robot_family="auto")` with explicit Cartesian waypoints + IK. MUST set `target_source="spline"` to avoid the franka-fallback footgun. Tools EXIST.

**RG-B02 — Fanuc CRX-10iA/L: collaborative tabletop pick-place (spline)**
`crx10ial.usd` + spline lane. CRX is a cobot → good fit for cautious waypoint motion. Tools EXIST (spline lane).

**RG-B03 — Yaskawa Motoman NEX10: sensor-gated machine tend (PLC-mimic)**
`NEX10.usd` + `target_source="sensor_gated"` (belt pause on photoelectric sensor, pre-taught poses) — the industrial-realistic lane. Tools EXIST.

**RG-B04 — Ufactory xArm7 + xArm gripper: pick-place (spline)**
`xarm7.usd` + `Ufactory/xarm_gripper/xarm_gripper.usd`; `create_gripper(gripper_type="parallel_jaw", gripper_dof_names=[...xarm joints...])` then spline pick-place. Tools EXIST (must override panda default dof names).

**RG-B05 — Ufactory Lite6 + lite6 gripper: compact-cell pick-place (fixed_poses)**
`lite6.usd` + `lite6_gripper/uf_lite_gripper.usd`; `target_source="fixed_poses"` timer-driven replay for a small fixed-station cell. Tools EXIST.

**RG-B06 — Techman TM12: vision-guided-style sort (spline)**
`tm12.usd` + spline; pairs naturally with a `vision`/SDG camera over the belt. Tools EXIST (spline + vision handlers).

**RG-B07 — Franka FR3: tabletop pick-place (spline or native-as-franka)**
`fr3.usd`. FR3 ≠ Panda kinematics, so curobo `franka.yml`/native Panda may mis-plan — recommend `target_source="spline"` first; flag as a verify-before-trust spec. Tools EXIST.

**RG-B08 — UR16e / UR20 heavy-payload palletize (spline)**
`ur16e.usd` / `ur20.usd`. No `ur16e.yml`/`ur20.yml` curobo config → auto-detect routes to `ur10` config (wrong kinematics). Use `target_source="spline"` with the correct articulation. Tools EXIST (spline lane); curobo path would be WRONG.

### Tier C — blocked on a missing tool (gap-scoping specs)

**RG-C01 — Ridgeback+Franka mobile manipulator: drive-to-station then pick**
Asset EXISTS (`ridgeback_franka.usd`) and is in the import map; `navigate_to`/A* base nav EXISTS; Franka curobo arm EXISTS. **Blocked** because there is NO `setup_amr_with_manipulator` that sequences base-park → arm-pick → base-move. Today you'd hand-stitch `navigate_to` + a separately-anchored arm controller, but the base and arm are one articulation in this USD, so the arm controller needs base-aware framing. **Gap: `setup_amr_with_manipulator`.**

**RG-C02 — Ridgeback+UR5 mobile sort across stations**
Same gap as C01 with `ridgeback_ur5.usd`. Plus UR5 has no curobo config (would need spline arm + base nav). **Gap: `setup_amr_with_manipulator` + UR5 spline integration.**

**RG-C03 — Spot-with-arm: mobile fetch (quadruped manipulation)**
`spot_with_arm.usd` EXISTS; Spot locomotion path exists. **Blocked**: no controller couples Spot's gait to its arm for a pick. **Gap: legged-base + arm coordination (a Spot-arm variant of `setup_amr_with_manipulator`).**

**RG-C04 — Unitree H1 + hands: bimanual pick-place**
`h1.usd` + `h1_hand_{left,right}.usd` EXIST. **Blocked**: `setup_bimanual_pick_place_controller` is hard-locked to `unitree_g1.yml`; no H1 curobo config and no H1 branch. **Gap: generalize bimanual controller beyond G1 (add `h1` config + branch).**

**RG-C05 — Allegro Hand: dexterous in-hand / 4-finger power grasp**
`allegro_hand.usd` EXISTS and is in registries. **Blocked**: no multi-finger grasp synthesis/controller. `grasp_object` is parallel-jaw RmpFlow; `create_gripper` only knows `parallel_jaw`/`suction`. **Gap: `setup_dexterous_grasp` / 3-finger+ grasp controller.**

**RG-C06 — Robotiq 2F-85 / 2F-140 / Hand-E on UR10: parallel-jaw industrial pick (mounted EOAT)**
Robotiq USDs are stand-alone EOAT (not pre-mounted). **Blocked** on mounting: no `attach_gripper`/`mount_eoat` tool to weld a Robotiq finger assembly onto a UR `tool0` and wire its mimic joints. Once mounted it would be a Tier-B spline pick-place. **Gap: `mount_eoat` / gripper-attach tool.** (UR10 native suction sidesteps this because it's a USD variant; Robotiq is a separate articulation.)

**RG-C07 — Shadow Hand: 5-finger dexterous manipulation**
Same gap as C05, higher DOF (24). **Gap: dexterous grasp controller.**

---

## 4. Gap summary (what to build, in priority order)

1. **`setup_amr_with_manipulator`** — unlocks Ridgeback+Franka and Ridgeback+UR5 (2 verified mobile-manipulator assets sitting unused). Highest ROI: assets + base-nav + arm controller all already exist; only the sequencing glue is missing.
2. **Generalize `setup_bimanual_pick_place_controller` beyond G1** — add an `h1` curobo config + branch (and a path for GR-1/Digit). Unlocks the H1 humanoid line.
3. **`setup_dexterous_grasp` (3-finger+)** — Allegro/Shadow/Dex3/Dex5 are all on disk with zero grasp tooling. Needed before ANY dexterous-hand template.
4. **`mount_eoat` / `attach_gripper`** — to put Robotiq 2F-85/2F-140/Hand-E and bare xArm/Lite6 grippers onto arms (they're stand-alone EOAT USDs). Unlocks the entire Robotiq-on-UR/Franka industrial-jaw class.
5. **Per-arm curobo configs for UR5/UR16e/UR20/Kinova/Fanuc/xArm/Techman** — would promote ~8 Tier-B specs to Tier-A fidelity. Currently those arms only get the robot-agnostic spline lane.

## 5. Footguns for the template author (verified in code)

- `setup_pick_place_controller` **auto-detects `robot_family` from the path** (`pick_place.py:175`). Any non-{franka,ur,cobotta,g1} arm silently becomes a **Franka Panda** controller. For Kinova/Fanuc/Yaskawa/xArm/Techman/UR16e/UR20/FR3, **explicitly set `target_source="spline"`** (or `fixed_poses`/`sensor_gated`) — do NOT rely on curobo/native.
- `cobotta_pro_900` has a native controller but **no curobo config** — `target_source="curobo"` will fail; use `"native"`.
- UR10 (not e-series) must use `ur10_scene.yml` (auto-selected at `pick_place.py:4051`) — the cup-frame-matched config; `ur10e.yml` mis-places the EE on the real UR10 (MEMORY: cup-frame work).
- `create_gripper` defaults to **panda finger joint names** — override `gripper_dof_names` for any non-Franka jaw.
- Always call **`list_available_controllers`** first (`tool_schemas.py:3994`) to confirm the backend is runnable on the box before committing a `target_source`.
