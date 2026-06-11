# Introspection gate classes — design [P5-22 breadth, build-ready]

**The gap (measured 2026-06-11):** four template families declare gates that
are ASSERTIONS ABOUT THE SESSION, not physics outcomes — and the traversal
gate either arg-validates them to `gate=None` (CP-63, CP-64,
ik-singularity) or force-fits wrong semantics (teaching-mode graded
`/World/Table` as a deliverable cube). They are unmeasurable until they get
their own gate classes.

## Family inventory (verify_args evidence)

| family | exemplar | declared expectations | what would prove them |
|---|---|---|---|
| sampler | CP-63 grasp-pose-sampler | `expected_n_samples`, `expected_sampling_mode` | sampler output artifact (pose list) length + mode field |
| nav | CP-64 Nav2 Carter | `expected_nav_topic`, `expected_odom_topic` | live ROS2 graph — **bridge-gated** |
| trajectory | ik-singularity-avoidance | `expected_check_singularity_calls=3`, `wp1_expected_condition_number_min`, `expected_plan_trajectory_planner=lula_rrt` | tool-call trace (calls + args) and per-call outputs |
| pose-replay | teaching-mode-pose-replay | `check` (+ broken cube/target args) | recorded-vs-replayed EE pose series delta |

Plus likely members once tagged: controller-benchmark-shootout,
controller-shootout-cp, cad-revision-drift, reward-review-iterate,
dr-curriculum, eureka families (RL-meta: expectations about generated
configs, not physics).

## Key observation: two sub-classes, very different cost

1. **BUILD-introspection** (sampler, trajectory, RL-meta, cad-drift):
   every expectation is checkable against data that ALREADY EXISTS after
   `execute_template_canonical` — the per-call record (tool name, args,
   output) plus produced artifacts. No physics run, no extra sim time.
   The gate is a pure function: `expected_* x call_trace -> verdict`.
2. **RUNTIME-introspection** (nav topics, rosbag-replay, plc/mqtt/opcua
   bridges): expectations about EXTERNAL systems. These stay unmeasurable
   until the bridge infra exists — the gate class should EXPLICITLY return
   `blocked_on: bridge` instead of None/False, so the ledger separates
   "can't measure yet" from "measured and failed".

## Design

1. **`gate_class: "introspection"`** in simulate_args + a checks list:
   ```json
   "simulate_args": {
     "gate_class": "introspection",
     "checks": [
       {"kind": "call_count", "tool": "check_singularity", "expect": 3},
       {"kind": "call_arg", "tool": "plan_trajectory", "arg": "planner", "expect": "lula_rrt"},
       {"kind": "output_min", "tool": "check_singularity", "field": "condition_number", "min": 100, "which": 0},
       {"kind": "artifact_len", "artifact": "grasp_poses", "min": 24}
     ]
   }
   ```
   Templates' existing `expected_*` args map mechanically onto these four
   check kinds (count / arg / output-field / artifact).
2. **Evaluator** `service/.../qa/introspection_gate.py`: pure function over
   the canonical build result (which must RETAIN per-call args+outputs —
   `execute_template_canonical` already returns calls; verify field
   coverage). Unit-testable without Kit (l0).
3. **gate_one dispatch**: third branch beside traversal/articulation —
   build the canonical, run evaluator, print `INTROSPECTION_GATE={...}`
   with per-check verdicts. `blocked_on` checks (e.g. `kind: "ros2_topic"`)
   short-circuit to a BLOCKED verdict, never False.
4. **Ledger**: axis stays `function_gate`; extras get
   `gate_class: introspection` + per-check vector (mirrors TS verdict_vector
   so diagnose tooling reads both the same way).
5. **teaching-mode special**: needs a small runtime series (EE pose during
   replay vs recorded) — implementable as a `pose_series_delta` check that
   reads the existing ctrl:* timeline after a SHORT sim run; phase 2.

## Build order (1 short session, Kit only for step 4)
- [ ] evaluator + four check kinds + l0 tests (pure, no Kit)
- [ ] map CP-63 + ik-singularity expected_* -> checks (template edits)
- [ ] gate_one dispatch branch
- [ ] live: gate CP-63 + ik-singularity fresh-Kit; CP-64 returns BLOCKED
- [ ] teaching-mode pose_series_delta (phase 2, needs ctrl timeline read)

## Non-goals
- No physics judgement: introspection gates NEVER claim delivery/motion
  quality. A template wanting both declares BOTH gate classes (future:
  `gate_classes: [...]`, out of scope here).
- No bridge mocking: runtime-introspection without the real bridge stays
  BLOCKED — mocks would manufacture false greens (silent-success class).
