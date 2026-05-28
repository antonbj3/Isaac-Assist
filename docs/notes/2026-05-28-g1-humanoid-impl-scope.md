# G1 humanoid bimanual pick-place — implementation scope

Date: 2026-05-28
Target canonicals: `CP-NEW-g1-bimanual-tabletop`, `CP-NEW-roco-bimanual-assembly` (dual-Franka — already buildable via two `setup_pick_place_controller(curobo)` calls; tracked here for shared lessons)
Blockers today: `setup_pick_place_controller` has NO humanoid `robot_family` branch (verified `pick_place.py:4097-4115`); `setup_whole_body_control` is **config-emitter only** (no runtime callback — `robot.py:3631-3696`).

---

## 0. What we already have (don't re-do)

- **cuRobo G1 yml ships natively** at `~/miniconda3/envs/isaac_lab_env/lib/python3.11/site-packages/curobo/content/configs/robot/unitree_g1.yml` (49-link, 29-DOF, collision spheres pre-baked for the entire body). `tool_frames: [right_hand_index_1_link, left_hand_index_1_link, right_ankle_roll_link, left_ankle_roll_link]` — both hand and both ankle TCPs already exposed. URDF at `.../assets/robot/g1/g1_29dof_with_hand_rev_1_0.urdf`. **No new URDF/yml extraction needed.**
- **`dual_ur10e.yml`** ships as a reference for the two-tool-frame planning pattern (`tool_frames: [tool1, tool0]`). Useful template for the per-call `ee_link_name` switch.
- **Per-robot subscription tag** (commit `337227f1` lineage, `pick_place.py:840/2425/2568/3249/4147` etc) already scopes ALL pick-place state under `_ROBOT_TAG = ROBOT_PATH.replace("/", "_")`. Two installs against the same `/World/G1` would COLLIDE on tag — fix below.
- **`builtins._curobo_pp_planner_v21`** is currently a single global. Sharing it between Franka and G1 in one session would clobber kinematics. Must key by `(_CUROBO_ROBOT_CFG, lock_joints_hash)`.

## 1. Phases

### P0 — cuRobo G1 single-arm pick-place (no WBC, planted feet)  [12-18h]

Goal: `setup_pick_place_controller(target_source="curobo", robot_family="g1_arm", arm_scope="right")` works for a fixed-base G1 reaching a tabletop cube. Both feet are assumed planted (USD `FixedJoint` on `left_ankle_roll_link` and `right_ankle_roll_link` → ground), torso/legs locked via `lock_joints`.

Tasks:
- **P0.1** [2h] Extend `_gen_pick_place_curobo` family branch (`pick_place.py:4097-4115`) with `elif ROBOT_FAMILY in ("g1_arm", "g1_left_arm", "g1_right_arm"):` setting `_CUROBO_ROBOT_CFG = "unitree_g1.yml"`, `_TOOL_FRAME = "left_hand_index_1_link" if arm_scope=="left" else "right_hand_index_1_link"`, `_ARM_DOF = 7`, `_FINGER_JOINTS = ()` (G1 hand is 7-DOF dex; no parallel-finger close — Phase 1 uses surface-gripper FJ-attach analogous to UR10 path).
- **P0.2** [3h] Plumb `arm_scope: Literal["left","right"]` through `_gen_setup_pick_place_controller` (`pick_place.py:293-540`) and `_models.py:SetupPickPlaceControllerArgs`. Default `None` keeps existing single-arm behavior.
- **P0.3** [3h] Add `lock_joints` computation: when `robot_family=="g1_arm"`, pass `lock_joints={joint: 0.0 for joint in NON_<scope>_ARM_JOINTS}` to `MotionPlannerCfg.create`. Need ~42 locked joints (legs + waist + opposite arm + opposite hand + head). Source the joint list once from the yml's `cspace`-aligned order.
- **P0.4** [2h] Re-key planner cache: change `_PLANNER_ATTR` to `f"_curobo_pp_planner_v22_{_CUROBO_ROBOT_CFG.replace('.yml','')}_{arm_scope or 'all'}"`. This lets Franka, G1-left, G1-right planners coexist in one Kit session.
- **P0.5** [1h] Gripper handling for the dex hand: emit `_FINGER_JOINTS = ("<scope>_hand_thumb_0_joint", ...)` with close-targets that just curl the thumb+index (good enough for cube grasp). Or short-circuit to `friction` grip-style via the existing pathway.
- **P0.6** [2h] Test on a stripped clone of `CP-NEW-g1-bimanual-tabletop`: single arm only, single cube, planted feet via FJ. Verify `_curobo_pp_planner` builds without OOM (G1 yml is 4.4k lines — collision-cache may need bumping from 32 OBB).

Risks: **Self-collision check** for G1 spans the whole body and may explode trajopt budget. Mitigation: `self_collision_check=False` for V0, re-enable with budget tuning later.

### P1 — `setup_bimanual_pick_place_controller` tool  [6-10h]

Goal: a single tool call installs two coordinated pick-place state machines (one per arm) sharing one G1 articulation.

Tasks:
- **P1.1** [2h] New handler in `handlers/robot.py` (humanoid section, near `_gen_setup_whole_body_control`): `_gen_setup_bimanual_pick_place_controller(args)` that emits ONE Python module containing TWO embedded P0 controllers (or invokes `_gen_pick_place_curobo` twice with `arm_scope="left"` and `arm_scope="right"`, concatenating output with shared imports deduped).
- **P1.2** [1h] Coordination-mode dispatch (V0: only `sequential` works because Kit RPC is single-tenant — memory `kit-concurrency`). `parallel` / `handoff` modes accept the args but log warning + fall back to `sequential` in V0.
- **P1.3** [1h] Register tool in `_models.py:tool_handlers` + `_dispatch.py`.
- **P1.4** [2h] Per-arm `_ROBOT_TAG` disambiguator: append `_left` / `_right` to the tag so the two physics-step subscriptions don't collide on `_curobo_pp_sub_World_G1`.
- **P1.5** [1h] Shared `MUTEX_PATH` plumb-through so left arm's `held_pose` state is observable to right arm's planner (writes mutex `claimed_by` → right waits then plans w/ updated obstacle snapshot of left's pose).

Risks: **Planning_obstacles snapshot staleness** (already documented in roco-bimanual `failure_modes`). The mutex-poll workaround works for sequential; true parallel needs a multi-articulation cuRobo install (one planner for the WHOLE G1, 14-DOF active across both arms) — defer to P3.

### P2 — Canonical wiring + smoke test  [3-5h]

- **P2.1** [1h] Update `CP-NEW-g1-bimanual-tabletop` template `code` to call `setup_bimanual_pick_place_controller(robot_path="/World/G1", left_arm_sources=["/World/Cube_left"], right_arm_sources=["/World/Cube_right"], left_destination="/World/DropLeft", right_destination="/World/DropRight", coordination_mode="sequential")`. Add `setup_pick_place_controller` to `tools_used`, leave `setup_whole_body_control` for the WBC-aware future variant.
- **P2.2** [1h] Add a `g1-left-arm-only-cube-pick` micro-canonical (CP-NEW) — narrowest test that exercises P0 without P1.
- **P2.3** [2h] Live-smoke (Kit RPC) per `feedback_diligence_no_false_positives.md`. Record success → set `verified_status` accordingly, drop `migration_deferred`.

### P3 — WBC runtime integration  [40-80h, defer]

Out of scope for first ship. Today's `setup_whole_body_control` only emits an `ActionGroupCfg` import-block (`robot.py:3642-3695`). Real runtime WBC needs:
- IsaacLab `LocomotionPolicyCfg` checkpoint loader (currently undefined symbol)
- Pink-IK / Pinocchio Python integration (extra dep)
- Dual-rate physics-step (50 Hz lower / 100 Hz upper) — `_gen_setup_multi_rate` exists as wrapper (`robot.py:3725-3776`) but is config-only
- Verification: standing balance under arm-payload disturbance (covered conceptually in `_gen_diagnose_humanoid_balance` `diagnostics.py:3286`)

**Defer rationale**: P0+P1 unblocks BOTH bimanual canonicals (g1-tabletop with planted feet via FJ, roco-bimanual already works). WBC is needed for canonicals that involve walking-while-manipulating (humanoid yrkesroller phase 8 #2-#24). Tackle as a separate spec.

### P4 — True simultaneous bimanual (single planner, 14-DOF active)  [16-24h, defer]

V1 sequential is fine for `CP-NEW-g1-bimanual-tabletop` and `roco-bimanual-assembly`. Truly synchronous bimanual (both arms moving at once) needs ONE `MotionPlanner` instance with TWO active tool-frames + concatenated 14-DOF goal. cuRobo supports this (see `dual_ur10e.yml`'s two `tool_frames`), but the `_gen_pick_place_curobo` state machine is single-trajectory. Re-architecting to multi-trajectory is a larger lift; defer until a canonical demands it.

---

## 2. Risks / unknowns

| ID | Risk | Mitigation |
|----|------|------------|
| R1 | G1 yml self-collision check explodes trajopt budget (49 collision links vs Franka's 11) | V0: `self_collision_check=False`; revisit with `collision_cache.obb` bumped 32→128 |
| R2 | Single-tenant Kit RPC blocks parallel coordination_mode | Already documented (memory `kit-concurrency`); V0 supports `sequential` only |
| R3 | Planner cache global key collision Franka↔G1 | P0.4 re-key by `(cfg, arm_scope)` |
| R4 | G1 dex hand grasp dynamics (no parallel-jaw equivalent) | Use friction grip per memory `feedback_isaac_assist_no_fj_fusk` (thumb+index curl) OR fall back to surface-gripper FJ-attach for V0 |
| R5 | G1 USD asset not on local Nucleus (template `verified_status` notes 20/21 build failure) | Use `import_robot(format="asset_library", file_path="G1")` — already wired; or bundle the URDF→USD via cuRobo's shipped URDF |
| R6 | `lock_joints` joint-name mismatch between cuRobo yml and Isaac Sim USD G1 articulation | Cross-check at `MotionPlanner` build time; emit diagnostic |
| R7 | Planning_obstacles snapshot staleness between LEFT-finish and RIGHT-start (when same arm scope wraps a hand-off) | Re-install RIGHT after LEFT parks — already the documented workaround in roco-bimanual failure_modes |

## 3. Recommended order (ship-now)

**Ship P0 → P1 → P2 WITHOUT WBC.** Both target canonicals (g1-tabletop, roco-bimanual-assembly) can be function-gate-green with planted feet + sequential bimanual + cuRobo per-arm. WBC is a separate Phase 8 yrkesroller dependency, not a bimanual-pick-place dependency.

## 4. Concrete tool signature

```python
# handlers/_models.py
class SetupBimanualPickPlaceControllerArgs(BaseModel):
    """Install TWO coordinated cuRobo pick-place state machines on a single humanoid
    articulation (one per arm). Sequential coordination only in V0 (Kit RPC is
    single-tenant — left arm completes its pick-place fully before right arm starts).

    Today only G1 (`robot_family="g1_arm"`) is supported. Both arms share one
    Articulation; per-arm cuRobo planners are cached separately under
    `builtins._curobo_pp_planner_v22_<cfg>_<scope>`.
    """
    robot_path: str = Field(..., description="USD prim path of the humanoid articulation root (e.g. /World/G1).")
    robot_family: Literal["g1_arm"] = Field("g1_arm", description="Humanoid family. Only 'g1_arm' supported in V0.")
    left_arm_sources: list[str] = Field(..., description="Cube prim paths for the LEFT arm to deliver, in pick order.")
    right_arm_sources: list[str] = Field(..., description="Cube prim paths for the RIGHT arm to deliver, in pick order.")
    left_destination: str = Field(..., description="Drop prim path for LEFT arm.")
    right_destination: str = Field(..., description="Drop prim path for RIGHT arm.")
    coordination_mode: Literal["sequential", "parallel", "handoff"] = Field(
        "sequential",
        description=(
            "sequential: LEFT runs to completion, then RIGHT. V0 only supports this. "
            "parallel: both arms move simultaneously — NOT IMPLEMENTED in V0, falls back to sequential with warning. "
            "handoff: LEFT picks then places into shared hold zone; RIGHT picks from hold zone — implemented via mutex_path."
        ),
    )
    plant_feet: bool = Field(True, description="When True, add USD FixedJoint between each ankle_roll_link and ground (default — V0 has no WBC, balance is assumed via planted feet).")
    planning_obstacles: list[str] = Field(default_factory=list, description="Extra prim paths to register as cuRobo collision obstacles. The OTHER arm is auto-included via lock_joints state.")
    mutex_path: Optional[str] = Field(None, description="Shared coordination mutex prim path for handoff mode.")
    ee_offset: list[float] = Field([0.0, 0.0, 0.10], description="EE→fingertip offset (m), same convention as setup_pick_place_controller.")
    scenario_profile: Optional[str] = Field(None, description="Forwarded to per-arm cuRobo handler (single_belt_pick / obstacle_rich / None).")
```

Internal composition (pseudo):
```python
def _gen_setup_bimanual_pick_place_controller(args):
    left_code  = _gen_pick_place_curobo(robot_path=args["robot_path"],
                                        source_paths=args["left_arm_sources"],
                                        destination_path=args["left_destination"],
                                        robot_family="g1_arm",
                                        arm_scope="left",
                                        mutex_path=args.get("mutex_path"),
                                        ...)
    right_code = _gen_pick_place_curobo(robot_path=args["robot_path"],
                                        source_paths=args["right_arm_sources"],
                                        destination_path=args["right_destination"],
                                        robot_family="g1_arm",
                                        arm_scope="right",
                                        mutex_path=args.get("mutex_path"),
                                        ...)
    return _merge_with_shared_imports(left_code, right_code,
                                      plant_feet=args.get("plant_feet", True),
                                      coordination_mode=args["coordination_mode"])
```

## 5. Sample LLM tool calls (for `g1-bimanual-tabletop`)

```python
# Replaces today's stub setup_whole_body_control(...) call:
setup_bimanual_pick_place_controller(
    robot_path="/World/G1",
    robot_family="g1_arm",
    left_arm_sources=["/World/Cube_left"],
    right_arm_sources=["/World/Cube_right"],
    left_destination="/World/Bin",
    right_destination="/World/Bin",
    coordination_mode="sequential",
    plant_feet=True,
    planning_obstacles=["/World/Table"],
    ee_offset=[0.0, 0.0, 0.10],
)
```

For roco-style hold-and-fasten (humanoid variant of dual-Franka roco):
```python
setup_bimanual_pick_place_controller(
    robot_path="/World/G1",
    left_arm_sources=["/World/Cube_workpiece"],
    right_arm_sources=["/World/Cube_fastener"],
    left_destination="/World/HoldZoneMarker",
    right_destination="/World/HoldZoneMarker",
    coordination_mode="handoff",
    mutex_path="/World/MutexHoldZone",
    plant_feet=True,
    planning_obstacles=["/World/Workbench", "/World/InfeedLeft", "/World/InfeedRight"],
)
```

Existing dual-Franka `CP-NEW-roco-bimanual-assembly` keeps its two-`setup_pick_place_controller` shape (different articulations) — no migration needed.

---

## 6. Test canonicals

| Template | Uses today | Uses post-P1 | Notes |
|----------|------------|--------------|-------|
| `CP-NEW-g1-bimanual-tabletop` | `setup_whole_body_control` (config-only stub, no runtime) | `setup_bimanual_pick_place_controller` | Primary unblock target. Drop `migration_deferred`. |
| `CP-NEW-roco-bimanual-assembly` | Two `setup_pick_place_controller(curobo)` (dual-Franka) | Same | No change — works today, listed for shared coordination lessons. |
| Future: `phase-8-yrkesroll-*-humanoid` | — | `setup_bimanual_pick_place_controller` + future `setup_whole_body_control` runtime | Will need P3 (WBC) for walk-while-manipulate yrkesroller. |
| Future: GR00T-comparison bench | — | `setup_bimanual_pick_place_controller` is the classical baseline; GR00T policy is the comparison | P0+P1 unblocks the baseline arm. |

---

## Go / No-go

**GO on P0+P1+P2 (~21-33h).** All prerequisites verified: cuRobo G1 yml + URDF ship in `isaac_lab_env`; existing per-robot `_ROBOT_TAG` scoping supports two parallel-subscription controllers; `MotionPlanner.lock_joints` is a first-class cuRobo API; planted-feet via USD FixedJoint sidesteps WBC entirely for V0. No new external deps.

**DEFER P3 (WBC runtime) and P4 (true parallel bimanual planner)** — neither blocks the two target canonicals.
