# Controller-backend CONTRACT [P2-13 — design-first, no refactor]

**Why this document exists.** The 11 `target_source` variants are string-dispatched
codegen generators (`pick_place.py::_gen_setup_pick_place_controller`, dispatch at
~L356), not runtime objects — each emits a self-contained physics-callback program.
A MotionPolicy-style ABC would be a category shift; before deciding whether a thin
runtime wrapper earns its keep, the IMPLICIT contract every backend already honors
(or violates) must be written down. This is the stated prerequisite for the
GR00T-runtime architectural call, a future Motion-Gen-API adapter (Isaac 6.1), and
per-backend `motion_controllers` honesty.

Sources: full dispatch read 2026-06-10 evening + generator docstrings + the
measured corpus (verification ledger + P0-07 controller-honesty audit).

---

## 1. Backend inventory (the measured truth)

| selector | motion backend | grip mechanism | families | multi-item / routing | world model | sim2real class | verified (corpus) |
|---|---|---|---|---|---|---|---|
| `curobo` | cuRobo GPU global trajopt, 5 segments/cube | ParallelGripper (franka) / SurfaceGripper suction (ur10, cup-frame close-loop) / g1_arm | franka, ur10, g1_arm (auto-detect from path) | YES: `drop_targets`, `color_routing`, `mutex_path`, `arm_scope` | YES (manual `planning_obstacles` + `_ur10_multicube_obs` auto-add; **stale-world bug class — P2-12 generalizes**) | honest (suction = zero-compliance caveat) | **48 templates** |
| `spline` | Lula IK warm-start chain + CubicSpline, 6 waypoints, CPU | friction (FJ half of `grip_style` never emitted — audit 06-10) | franka-class | partial: `color_routing`, `mutex_path` | NO (cartesian lift-and-transit heuristic) | honest-deterministic | 0 |
| `native` | NVIDIA `PickPlaceController` (RMPflow), internal state machine | ParallelGripper | **Franka ONLY** (non-Franka auto-reroutes to `builtin`) | NO | NO | honest | 0 (work proven 2026-04-21, never corpus-tagged) |
| `builtin` | NVIDIA per-family `PickPlaceController` | per-family (parallel / surface) | franka, ur10/e, cobotta_pro_900 | NO | NO | honest | 0 |
| `diffik` | Isaac Lab DifferentialIKController (dls/pinv/svd/trans), local | franka gripper.forward | franka | NO | NO | honest | 0 |
| `osc` | Isaac Lab OperationalSpaceController, simplified J^T impedance | effort-mode (drives zeroed at install) | franka | NO | NO | honest-experimental (0–2/4 expected; **teardown missing: drive gains never restored**) | 0 |
| `sensor_gated` | pre-taught poses or RmpFlow-IK world-coords | friction ("ALWAYS friction — no EE↔cube FJ, Anton's rule"; FJ-claim REFUTED by audit 06-10) | any with taught poses | NO | NO | honest | 0 |
| `fixed_poses` | timer-driven pose replay (JSON pose files) | none (no grasp logic) | any (DOF-name remap at runtime) | n/a | NO | honest (no manipulation claim) | 3 as `direct_joint` |
| `cube_tracking` (default) | RmpFlow continuous retarget on live cube pose | friction (FRICTION-FIX; no FJ — audit 06-10) | franka-class | NO | NO | **omniscient — NOT sim2real-honest (declared)** | 0 |
| `ros2_cmd` | external controller via topics; Kit = physics+I/O only | external | any | external | external | honest-by-delegation (**loop never closed — X-08b**) | 0 |
| `auto` | resolver, see §4 | — | — | — | — | — | — |
| ~~`cortex`~~ | retired (P0-09) | — | — | — | — | — | 1 failed |

**Honesty note:** only `curobo` (48) and `direct_joint` (3) carry measured verified
status. Every other backend is *declared-not-verified* (P0-08) — claims about them
in docs/retrieval must read as such until N-of-M gates exist (P5-22 gate classes).

## 2. The shared codegen contract (MotionPolicy-equivalents)

Every `_gen_pick_place_*` emits a program that must honor C1–C9. New backends MUST
ship all nine; today's compliance varies (gaps in §5).

- **C1 — joint discovery** (`get_active_joints` equiv): resolve DOF names against
  the LIVE articulation at runtime; never hardcoded indices. (CP-84 wound-start +
  `fixed_poses` DOF-remap are the precedents.)
- **C2 — target derivation** (`compute_targets` equiv): each backend DECLARES its
  pick-pose source — live cube pose (omniscient), pre-taught pose (industrial),
  sensor-triggered station, or external topic. This is the sim2real axis; silent
  mixing is forbidden.
- **C3 — world sync** (`update_world` equiv): collision-world updates before each
  plan. Only `curobo` has one (manual list + UR10 multi-cube auto-add). The
  stale-world signature bug (CP-83) lives here. P2-12 (WorldBinding-style auto-sync)
  is the generalization; until then every planning backend must document what its
  world DOESN'T contain.
- **C4 — family/base** (`set_base_pose` equiv): family detection from
  `robot_family` arg, else path heuristics (documented per backend); a backend that
  cannot serve a family must REROUTE (native→builtin precedent) or raise — never
  emit a crashing program (panda-fingers-on-UR10 class).
- **C5 — observability**: emitted programs author the always-on `ctrl:*` records
  (plan calls/fails, grip latch, per-cube status) — `diagnose_pick_execution`
  reads ONLY these. A backend without ctrl:* is invisible to the diagnose loop.
- **C6 — grip honesty**: the grip mechanism is part of the public contract.
  FixedJoint transport = simulation shortcut class. AUDIT 2026-06-10: no current
  backend emits an EE↔cube FJ (sensor_gated/cube_tracking/spline are friction;
  the g1 V0 dex hand uses a surface-gripper FJ-ATTACH, declared). Any future
  FJ-transport must be declared here + in `motion_controllers`.
- **C7 — scoping**: `phase_id` prefixes all controller state (multi-controller
  scenes); `mutex_path` is the cross-arm protocol (CP-52 per-cube mutex precedent).
  Kit RPC is single-tenant — emitted programs must never assume exclusive tenancy.
- **C8 — grader contract**: success is OWNED BY THE GATE, not the controller:
  deliver to assigned dest (per-cube `targets`/routing), at rest, upright,
  completeness mode (P0-18). Controllers must release in a way the grader can
  measure (no end-of-run FixedJoints left latched).
- **C9 — args honesty**: accepting-and-ignoring an arg is a defect (X-05 class).
  The dispatch forwards per-backend whitelists; an arg outside the whitelist must
  error or be documented as unsupported.

## 3. Auto-resolution policy (`target_source="auto"`)

Priority: `curobo` (GPU≥Volta + cuRobo) → `spline` (scipy; CPU winner 3/4 vs
native 0/4) → `native` (Franka) → `diffik` → native fallback.
NEVER auto-selected: `sensor_gated`, `fixed_poses`, `cube_tracking`, `ros2_cmd` —
they require explicit opt-in (mandatory config or sim2real-honesty).
`osc`/`builtin` are also never auto-returned (osc experimental; builtin only via
native's non-Franka reroute) — undocumented until now.

## 4. The runtime-wrapper decision (recommendation)

**NO ABC refactor now.** Grounds:
1. The generators are not objects with a lifecycle — they are program EMITTERS;
   the real lifecycle lives in the emitted physics callback. An ABC would wrap the
   wrong layer.
2. The string dispatch is load-bearing for L1.5 honesty (internal dispatchers are
   implementation detail, not tool-surface taxonomy).
3. What the GR00T call and the 6.1 Motion-Gen adapter actually need is a
   MACHINE-READABLE version of §1+§2 — not a class hierarchy.

**The additive step that earns its keep instead:** a `BACKEND_CONTRACT` dict in
`pick_place.py` (selector → {families, grip, world_model, multi_item, sim2real,
ctrl_records, never_auto}) consumed by (a) the dispatcher for C4 reroute/raise
decisions, (b) `motion_controllers` honesty tagging, (c) retrieval surface. A new
backend = one generator + one contract row + one gate class (P5-22). Revisit a
runtime wrapper ONLY when GR00T integration forces a live policy object into the
loop — then wrap the EMITTED program, not the generator.

## 5. Gaps found during the contract read (filed, not fixed here)

1. **OSC teardown missing** — drive gains zeroed at install, never restored
   (documented in its own docstring). Any template running OSC then another
   controller inherits dead drives.
2. **`events_dt` only honored by `native`** — accepted in the dispatch surface for
   others (X-05 class).
3. **Auto-resolver never returns `builtin`/`osc`** — undocumented before §3.
4. **`ros2_cmd` loop never closed** (X-08b): compiles, wires topics, 0 physics-gated
   templates.
5. **Per-backend gate classes missing** (P5-22): only the delivery gate exists;
   spline/diffik/osc/builtin have no measured rows at all — their honesty rests on
   docstrings.
6. **C5 compliance — AUDITED 2026-06-10 (source-level):** only `curobo`
   (18 ctrl:* refs) and `sensor_gated` (15) author observability records;
   native/builtin/spline/diffik/osc/fixed_poses/ros2_cmd author ZERO and are
   therefore INVISIBLE to `diagnose_pick_execution`. Drift-guarded in
   `tests/test_backend_contract.py::test_ctrl_records_matches_generator_source`.
   Adding ctrl:* to the zero-backends is the C5-compliance work item.
