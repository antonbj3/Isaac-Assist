# E2E Trace — quadruped-terrain: "a quadruped robot traverses uneven terrain to reach a goal"

- **Scenario ID:** e2e2_quadruped-terrain
- **Domain:** mobility / legged-locomotion
- **Robot:** ANYmal-C (resolve.py:88 `"quadruped" → "anymal_c"`)
- **Task:** legged-locomotion-to-goal over uneven terrain
- **Date traced:** 2026-06-09
- **Verdict:** **NEW CLASS-LEVEL ARCHITECTURAL GAP CONFIRMED.** The whole `mobility.legged` runtime family has no controller, no terrain primitive, and no gate verdict. It is the legged-locomotion analogue of the humanoid-cabinet finding: the system can *train* a quadruped policy (RL loop) but cannot *deploy* one to walk a robot to a goal over terrain at runtime.

---

## 0. What the user actually asked vs. what the library has

The request is a **runtime deployment / navigation** task: spawn a quadruped on uneven ground, command it to a goal pose, watch it walk there, judge whether it arrived. This is the locomotion equivalent of "pick the cube and put it in the bin."

The two closest real templates are **both RL TRAINING loops**, not runtime deployments:

- `workspace/templates/CP-NEW-anymal-locomotion-baseline.json` — `pattern_hint: "train"` (line 73). Goal: "Run the IsaacLab Anymal-C velocity-tracking BASELINE **training loop**." Success = `steps_completed >= 1000 AND checkpoint_path exists AND fitness != 0` (lines 38-44). The robot never leaves `/World/envs/env_0/Robot`; there is no goal, no terrain, no arrival.
- `workspace/templates/CP-NEW-isaaclab-humanoid-locomotion.json` — same shape, biped.

There is **no** `*-locomotion-deploy`, `*-walk-to-goal`, `*-traverse-terrain`, or `*-quadruped-nav` template anywhere in the 504-template library (grep for `anymal|quadruped|legged|terrain|locomotion|walk` returns only the two training baselines + the RL-eureka wheeled diff-drive + `CP-NEW-rl-correlated-dr-baseline`/scaffold templates). **The runtime locomotion task class does not exist as a template.**

So the LLM must *compose* the scenario from atomic tools. The trace below follows what it would actually do, and where each step lands.

---

## STEP-BY-STEP TRACE

### Step 1 — User opens the session
- **[USER]** types: *"a quadruped robot traverses uneven terrain to reach a goal"*
- **[CHEAP-static]** — pure text.

### Step 2 — Retrieval + planning
- **[SYSTEM]** retrieval matches on `isaac:rl.locomotion` + `isaac:robot.quadruped.anymal` tags → fetches `CP-NEW-anymal-locomotion-baseline` as the nearest neighbor.
- **[LLM]** reads the template, sees it is a *training* loop. The user did NOT ask to train; they asked to *deploy and traverse*. The LLM is now off-template — it has no canonical for "run a trained quadruped policy to a goal." It must improvise from atomic handlers.
- **[CHEAP-static]** — retrieval + reasoning, no Kit.
- **FIRST GAP SURFACES:** the retrieval layer cannot distinguish "train an Anymal policy" from "deploy an Anymal policy" — both map to the same tags. There is no `isaac:rl.locomotion.deploy` / `isaac:mobility.legged.runtime` structural tag.

### Step 3 — Import the quadruped
- **[LLM]** calls `import_robot(robot_class="anymal", dest_path="/World/Anymal")` (or `add_reference`).
- **[SYSTEM]** robot.py:3962 maps `"anymal" → "anymal_c.usd"`, resolved under `config.assets_root_path/<robots_subdir>`.
- **[CHEAP-static]** — USD reference add.
- **GAP (asset):** `anymal_c.usd` is a **Nucleus-only** asset (the template's own blocker note, CP-NEW-anymal line 31 + verified_status line 47: *"requires Anymal-C asset via NVIDIA Nucleus"*). Kimate's local asset drop has **NO quadruped at all** — `find /home/anton/kimate_assets/assets -iname '*anymal*' -o -iname '*go1*' -o -iname '*spot*'` returns nothing. So if Nucleus is unauthenticated/offline (the project's normal state — see the G1 `nucleus_only_asset` blocker referenced in the humanoid template line 18), **the robot never even loads.** Outcome here = empty-stage or broken reference.

### Step 4 — Build the uneven terrain
- **[LLM]** wants uneven ground. Searches its tool set for a terrain primitive… and finds **none.**
- **[SYSTEM]** There is no `create_terrain`, `import_terrain`, `add_heightfield`, `TerrainImporter`, `rough_ground`, `generate_terrain`, `add_stairs`/`add_ramp`/`add_slope` tool anywhere in the handler tree or `tool_schemas.py`. The only "terrain"-adjacent things that exist:
  - `scene_authoring.py:1416-1430` — a **material** `roughness` float (reflection_roughness_constant shader input). That is *visual* roughness, not geometric height variation.
  - The RL nav template config carries `terrain_height_m: [0.0, 0.15]` (training.py:504) as a **domain-randomization range string**, not a constructor — nothing reads it to build geometry.
  - Default ground is a flat `GroundPlane` (USD physics plane).
- **[CHEAP-static]** — whatever the LLM does here is authoring, not physics.
- **CLASS GAP (primitive):** **there is no uneven-terrain primitive.** The best the LLM can do is reference a Kimate terrain *appearance* asset:
  - `kimate_assets/.../Locomotion/GravelGround/dirt_grass_track/dirt_grass_track.usd` (204 MB) — this IS a genuine non-flat mesh track (the one real "uneven" candidate).
  - `.../Locomotion/{SLATEGround,MudGround,SnowGround,Grass}.usd` — large but predominantly **flat textured ground planes** (terrain *appearance*, not height-varying collision geometry).
  - `.../Locomotion/2-StoryStaircase/` — discrete stairs (a different locomotion sub-class).
  - These are scene-dressing assets with their own collision meshes; the LLM can `add_reference` one, but it has **no tool to parameterize roughness/amplitude/slope**, and no guarantee the referenced mesh even has a collider authored. The system cannot *generate* terrain to spec.

### Step 5 — Place the robot on the terrain + a goal marker
- **[LLM]** sets the Anymal root pose above the terrain; drops a goal Xform/marker at the target xy.
- **[SYSTEM]** `create_prim` / `set_transform`. Goal is just a marker prim — nothing consumes it as a locomotion target.
- **[CHEAP-static]** — authoring.
- Note: with no terrain-height query tool, the LLM has to guess the spawn z. On `dirt_grass_track` (height-varying) this is a coin-flip between clipping into the mesh or spawning in the air → fall on `Play`.

### Step 6 — "Make it walk to the goal" — THE CORE STEP
- **[LLM]** needs a controller that converts "go to goal_xy over terrain" into joint commands. It searches and finds exactly two candidates, both wrong:

  **(a) `navigate_to`** (robot.py:1594 `_gen_navigate_to`, schema tool_schemas.py:3816)
  - Hardwired to **wheeled robots**: `from isaacsim.robot.wheeled_robots.controllers import WheelBasePoseController, DifferentialController` with `wheel_radius=0.05, wheel_base=0.3` (robot.py:1690, 1723). The schema description literally says *"Navigate a **wheeled** robot."*
  - A quadruped has **no wheels and no DifferentialController** — feeding Anymal joint targets through a diff-drive wheel controller is a category error. It produces no leg motion.
  - Even for wheeled robots it is a **scaffold, not a closed-loop driver**: both planners hardcode `start_position=np.array([0,0,0])` / `start_world=np.array([0,0])` and never read the live robot pose (robot.py:1704, 1731-1733). The comment admits it: *"current_pos would come from robot state in real usage"* (line 1703) and *"In production, read actual robot pose from ArticulationView"* (line 1729). So it cannot actually converge to a goal even on a JetBot.

  **(b) `load_rl_policy`** (training.py:3263) — to deploy the trained Anymal velocity policy.
  - This handler **only writes USD metadata attributes**: `rl:policy_path`, `rl:observation_keys`, `rl:action_dim`, and — tellingly — `rl:policy_loaded = False` (training.py:3304). The docstring is explicit: *"For canonical-time, sets metadata attrs on robot for policy reference. **Runtime policy execution requires controller integration**"* (training.py:3266-3268).
  - There is **no inference loop**: nothing loads the `.pt`/`.onnx`, builds the observation vector (base lin/ang vel, projected gravity, joint pos/vel, last action, **height-scan around the feet**, velocity command), runs the network each physics step, and applies the joint targets. `load_groot_policy` (training.py:1877) only returns *download/launch shell commands* for a GR00T server — also not an in-Kit stepper.

- **[EXPENSIVE-physics]** would be required here (a per-physics-step policy-inference + joint-target loop), but **no handler emits one.**
- **CLASS GAP (controller):** **there is no legged-locomotion controller class.** Confirmed exhaustively:
  - No `gait` / `trot` / `footstep` / `foot_placement` / `swing_leg` / `stance_phase` controller anywhere — the only `gait` hits are a diagnostic-advice string (diagnostics.py:3315, 3321) and a sim-to-real metric field (`ee_accel_threshold_m_s2`, _models.py:2568).
  - The motion-controller registry is entirely **fixed-base-arm**: `rmpflow` / cuRobo / `direct_joint` / `linear_motion` (pick_place.py). None of these command a floating-base legged articulation.
  - `execute_contact_sequence_plan` (contact_sequence.py) is a **grasp/manipulation** contact runtime ("make_contact", "contact_established"), not footstep contacts.
  - So the link from "trained quadruped policy" (which the *training* template can produce) to "robot actually walks" is **missing**: `load_rl_policy` sets `policy_loaded=False` and stops. The capability dead-ends exactly where the humanoid-cabinet trace dead-ended — the moment a *non-pick-place body motion* is needed.

### Step 7 — Press Play and "traverse"
- **[LLM]** calls `play` / steps the sim.
- **[EXPENSIVE-physics]** — PhysX runs.
- **[SYSTEM]** With no policy-inference loop and no gait controller, the Anymal articulation has **no joint targets driving it**. On `Play` it does the only thing an undriven legged articulation can do: **collapse under gravity** (legs buckle, body drops onto the terrain). On the height-varying `dirt_grass_track` it may also tip/roll. It does not take a single step toward the goal.
- **Outcome:** robot at rest near spawn, goal never approached. Distance-to-goal ≈ initial distance.

### Step 8 — Grade it
- **[LLM/SYSTEM]** tries to score arrival.
- **[CHEAP-static]** — reading final pose.
- **GAP (gate):** **no gate can judge this task.**
  - `scripts/qa/gate_one.py` is 100% pick-place: it measures `cube_path` reaching `target_path` / `under_target`, with suction-cup flags. It has **no** concept of a robot base reaching a goal pose. Running it here is meaningless.
  - `scripts/qa/reach_validate.py` is arm-reachability (cuRobo IK to a pick) — N/A.
  - `scripts/qa/scene_validate.py` **explicitly excludes legged robots** from its only spatial check: lines 154-155 — *"humanoid / legged articulations (G1, H1, Anymal, Spot, Go1/2) reach from a SHOULDER, not the pelvis/base … the distance-from-base reach heuristic does not apply. **Drop them.**"* So even the scene validator returns **no verdict** for an Anymal.
  - There is **no** `base-reached-goal` / `distance-to-goal-under-threshold` / `traversal-success` gate primitive anywhere.

---

## OUTCOME (honest)

**The scenario cannot complete.** Best case (Nucleus up, terrain asset referenced): the Anymal loads on a flat-ish ground asset and **collapses on Play** because no controller drives its legs — distance-to-goal unchanged. Worst case (Nucleus offline — the project's normal state): the **robot asset never loads at all**. Either way there is **no terrain-to-spec, no locomotion controller, no traversal, and no gate verdict.** Every load-bearing piece of a "traverse terrain to a goal" task is absent at runtime; only the *offline RL training* half of legged locomotion exists in the library.

This is the **exact same failure shape as the humanoid-cabinet trace**: the moment the task needs body motion that isn't fixed-base pick-place, the controller layer, the success-gate layer, and (here) the world-construction layer all run out simultaneously.

---

## NEW CLASS-LEVEL ARCHITECTURAL GAP

> **`mobility.legged` runtime is a missing capability AXIS, not a missing template.** A whole family of tasks — "quadruped walks to goal," "Anymal traverses stairs," "Go1 climbs a slope," "Spot patrols rough ground," "biped walks across a room" (deploy, not train) — needs THREE new classes that don't exist:
>
> 1. **A legged-locomotion CONTROLLER class** — a per-physics-step velocity-command → joint-target loop that runs a trained RL policy (or a parametric gait generator) on a floating-base articulation. This is the bridge `load_rl_policy` explicitly punts on (`policy_loaded=False`, "runtime execution requires controller integration"). It is the locomotion sibling of cuRobo/rmpflow for arms. **Without it, every trained quadruped/biped policy in the library is undeployable.**
> 2. **An uneven-TERRAIN primitive** — `create_terrain(kind=rough|stairs|slope|noise, amplitude, slope_deg, ...)` that authors actual collision-bearing height-varying geometry (IsaacLab ships exactly this: `TerrainImporter` + `terrain_generator`). Today the only "terrain" knobs are a material-roughness shader float and a dead DR-range string; the only uneven *geometry* is a single 204 MB scene-dressing mesh with no parameterization and no guaranteed collider.
> 3. **A traversal / reached-goal GATE class** — `base_reached_goal(robot, goal_xy, tol)` + an upright/no-fall predicate, multi-robot-aware. Today `gate_one` is pick-place-only, `reach_validate` is arm-IK-only, and `scene_validate` **deliberately drops legged robots**. There is no verdict primitive for "did the robot get there."
>
> These three are coupled: a locomotion controller is untestable without a terrain to walk and a goal-gate to score, which is why the gap is *class-level* (an axis the architecture has only ever served on the **training** side, never the **deployment** side) rather than one missing tool.

---

## Tool/Capability gaps found (NEW — not in TOOL_GAP_INVENTORY_V2)

1. **`load_rl_policy` is metadata-only — no runtime policy-inference loop** (training.py:3263-3304, `policy_loaded=False`). No handler steps a trained locomotion policy in-Kit. This is the central deploy-side dead-end.
2. **No legged-locomotion controller class** (no gait/footstep/velocity-command joint-target runtime; registry is fixed-base-arm only). The locomotion analogue of cuRobo/rmpflow is absent.
3. **No uneven-terrain construction primitive** (`create_terrain`/heightfield/stairs/ramp/slope generator). Only a material-`roughness` shader float (scene_authoring.py:1430) and a dead DR-range string `terrain_height_m` (training.py:504).
4. **No traversal / reached-goal gate** — `gate_one.py` is pick-place-only; `scene_validate.py:154-155` explicitly drops legged robots from its spatial check; no `base-reached-goal` verdict exists.
5. **`navigate_to` is wheeled-only AND open-loop-scaffold** (robot.py:1594; never reads live robot pose, hardcodes start at origin — robot.py:1704/1731). It cannot drive a quadruped, and cannot truly converge even a wheeled robot.
6. **Asset reality gap for legged robots:** all quadrupeds (anymal_c/d, spot, go1/2, a1) are **Nucleus-only** (robot.py:3962-3967; CP-NEW-anymal verified_status line 47). Kimate's local drop has **zero** quadruped/biped *robots* and its `Locomotion/` ground assets are mostly **flat textured planes** (terrain appearance, not height geometry); the lone genuinely-uneven mesh (`dirt_grass_track.usd`) is unparameterized scene-dressing.
7. **Retrieval cannot separate train-vs-deploy locomotion** — both map to identical `rl.locomotion` + `robot.quadruped.anymal` tags; no `mobility.legged.runtime` / `rl.locomotion.deploy` discriminator tag exists.
