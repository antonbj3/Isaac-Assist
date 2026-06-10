# E2E Trace — snap-fit press-and-retry (Franka, assembly domain)

**Scenario id:** `e2e2-snap-fit`
**Request (verbatim):** *"press two parts together until a snap-fit click, retry if it does not seat"*
**Robot:** franka (Franka Panda, torque-mode-capable)
**Domain:** assembly / force-gated insertion
**Tier:** EXPENSIVE-physics (contact-rich compliance descent) — but the *retry* clause makes it a **closed-loop EXPENSIVE** task, which is the crux.

Closest real template: **`workspace/templates/CP-NEW-yrkesroll-assembler-snap-fit.json`** (exact
domain + gesture match). Sibling force-gated inserts: `CP-NEW-maniskill-peg-insertion.json`,
`CP-NEW-screw-driving-impedance.json`, `CP-NEW-peg-bushing-impedance.json`,
`CP-NEW-bottle-cap-tighten.json`, `CP-NEW-tactile-insertion.json`.

---

## 0. Headline finding (read this first)

The request has TWO halves:

1. **"press two parts together until a snap-fit click"** — *structurally* covered by the
   existing snap-fit template + `setup_insertion_controller(strategy="snap_fit")`
   (`handlers/insertion.py:83`, `:178`) + `get_contact_report` (`handlers/physics.py:1639`).
   But every compliance leg is `dry_run=True`; live mode raises `NotImplementedError`
   (`handlers/insertion.py:351`, `handlers/compliance.py:186/399`). So the press is a
   **plan artifact, not an executed motion**, and the click is **never physically produced**.

2. **"retry if it does not seat"** — has **NO implementation anywhere in the stack**. There is
   no controller that re-attempts a seat on a failed-seat predicate, no gate that emits a
   seat/no-seat verdict to branch on, and no force-guarded abort-and-retry primitive. The two
   things that *look* like retry are both the wrong kind:
   - `execute_with_retry` (`handlers/workflow.py:930`) retries **broken Python code** through the
     LLM error-fix loop — it is a *codegen* retry, not a *physical-seat* retry.
   - `execute_contact_sequence_plan` carries a `retry_count` field (`handlers/contact_sequence.py:118`)
     but the runtime (`multimodal/execute_contact_sequence_runtime.py:333` `execute_plan`) **never
     reads it** — the loop walks steps once and `abort_on_failure` just stops early; there is no
     re-press-on-predicate-fail anywhere.

**→ This scenario reveals a genuine NEW CLASS-LEVEL gap (see §6): a missing closed-loop
force-gated-assembly *controller class* AND a missing assembly-seat *gate class*. It is the
direct assembly-domain analogue of the humanoid-cabinet trace that revealed pick-place breaks on
articulated doors.**

---

## 1. User action sequence → target scene → outcome

Legend: `[USER]` / `[LLM]` / `[SYSTEM]` and `[CHEAP-static]` (USD authoring, ~ms, no PhysX
stepping) / `[EXPENSIVE-physics]` (settle + simulate, seconds–minutes of stepped PhysX).

### Phase A — request intake & retrieval

1. `[USER]` Types: *"press two parts together until a snap-fit click, retry if it does not seat."*
2. `[SYSTEM] [CHEAP-static]` Chat service embeds the query; retrieval ranks canonicals by
   `structural_tags`. Top hit is `CP-NEW-yrkesroll-assembler-snap-fit` via
   `isaac:gesture.press_and_click` + `isaac:assembly.contact_event_gated` +
   `isaac:industry.snap_fit_assembly` (template lines 136–149). Strong, unambiguous match —
   the word "snap-fit click" maps 1:1.
3. `[LLM] [CHEAP-static]` Reads the template `intent`/`roles`/`role_defaults`. Recognizes the
   "retry if it does not seat" clause has **no field in the template** — there is no
   `retry`, `max_attempts`, `reseat`, or `seat_predicate` key anywhere in the snap-fit JSON
   (grep-confirmed: `retry` appears only in `extension_notes` prose, never as a parameter).
   The LLM must therefore either (a) ignore the retry clause, or (b) hand-roll a retry loop in
   emitted code. **Both are failure paths — see §3.**

### Phase B — scene authoring (build the target scene)

All `[CHEAP-static]` — `execute_template_canonical` (canonical_instantiator) replays the
template `code` block tool-by-tool through `execute_tool_call`:

4. `[LLM→SYSTEM]` `create_prim` DomeLight + Ground + Table (`handlers/scene_authoring.py`).
5. `[LLM→SYSTEM]` `set_physics_scene_config(enable_gpu_dynamics=False, broadphase="MBP")` —
   **CPU deterministic**, deliberately chosen so the contact-report stream is reproducible
   (template line 8 comment). Relevant because the click detection depends on per-step impulse
   ordering.
6. `[LLM→SYSTEM]` `robot_wizard(robot_name="franka_panda", position=[0,0,0.75])` — spawns the
   arm at HOME via the wound-start-repair path (memory: raw `add_reference` starts the arm
   wound; `robot_wizard` is the correct spawn).
7. `[LLM→SYSTEM]` `create_prim` **BottomShell** Cube `[0.0,-0.25,0.795]` scale `[0.06,0.05,0.015]`,
   `PhysicsCollisionAPI` + **`PhysxContactReportAPI`**, NO RigidBodyAPI → static-by-absence
   (template lines authoring `/World/BottomShell`). Top rim z≈0.8025.
8. `[LLM→SYSTEM]` `create_prim` **StagingPad** + **TopClip** (dynamic, mass 0.04 kg, rubber
   material, `PhysxContactReportAPI`) + **4 Prong proxies** (rigid 1×1×2 cm Cubes at the clip's
   lower corners, prong-tip lowest face z≈0.790).
9. `[LLM→SYSTEM]` `bulk_set_attribute` sleepThreshold=0 (so the press signal is not lost to
   sleep) + solverPositionIterationCount=16 on clip+prongs+shell.
10. `[LLM→SYSTEM]` `define_grasp_pose(TopClip, approach_direction=[0,0,-1])` — top-down grasp.

   **Scene authored OK.** The static scene IS buildable today — this half works.

### Phase C — the press (PHASE 1 transit + PHASE 2 compliance descent)

11. `[LLM→SYSTEM] [EXPENSIVE-physics]` `setup_pick_place_controller(... source=[TopClip],
    destination=BottomShell, drop_target=[0.0,-0.25,0.825], target_source="curobo", ...)` —
    cuRobo-planned transit: pick clip off the staging pad, hover it 10 mm above the shell rim.
    This leg is real (cuRobo, `handlers/pick_place.py`), the same machinery used by every CP-NN
    delivery template.
12. `[LLM→SYSTEM] [CHEAP-static]` `get_world_transform(TopClip)` — read landed xy.
13. `[LLM→SYSTEM]` `setup_insertion_controller(strategy="snap_fit",
    start_pose=[0,-0.25,0.825], target_pose=[0,-0.25,0.800], dry_run=True)`
    (`handlers/insertion.py:276`). Composite installs impedance gains
    `Kx=[400,400,60] Kr=[40,40,40]` (X/Y stiff for alignment, Z soft for the 25 N surrender,
    all rotation rigid — `_STRATEGY_DEFAULTS["snap_fit"]` lines 83–93), generates a 3-waypoint
    pure-Z descent (`_gen_snap_fit` lines 178–202: hover→contact→seated, identity quat
    throughout), and calls `follow_trajectory_with_compliance(dry_run=True)`.

    **→ `[SYSTEM]` returns a *plan dict*, NOT an executed motion.** Live mode
    (`dry_run=False`) raises `NotImplementedError` (`insertion.py:351`): *"setup_insertion_controller
    live mode requires Kit RPC + ros2_control bridge + torque-mode robot."* No torque-mode
    bridge exists. **The clip never actually descends under compliance. No click is ever
    physically generated.**

### Phase D — the verify (PHASE 3 click detection)

14. `[LLM→SYSTEM] [CHEAP-static]` `get_contact_report(BottomShell, max_contacts=50)`
    (`handlers/physics.py:1639`). Scans for the prong-tip rim-strike impulse spike (>0.5 N·s)
    then drop. **But because the press in step 13 was a dry-run plan, the clip is still at its
    pre-press pose — there is no rim strike, the contact report is empty/static.**
15. `[LLM→SYSTEM]` `get_joint_torques(Franka)` — wrist torque trace (would confirm the
    detent transient; reads zero/static).
16. `[LLM→SYSTEM]` `get_world_transform(TopClip)` — clip Z must be ≤ 0.802 to count as seated;
    reads ≈ 0.815 (unmoved or only transit-dropped). **Seat predicate FALSE.**

### Phase E — the gate (how the platform scores this)

17. `[SYSTEM] [EXPENSIVE-physics]` `gate_one.py` → `simulate_traversal_check`
    (`handlers/diagnostics.py:3920`) with `cube_path=/World/TopClip`,
    `target_path=/World/BottomShell`, `duration_s=180`, `xy_tolerance=0.01`.
    The gate verdict is **purely delivery**: it reads `ctrl:cubes_delivered`
    (`diagnostics.py:3458`) and checks `in_xy + under_target + above_floor`
    (`:3968`/`:3976`). **It has NO concept of a snap-fit click, a seated-Z threshold, an
    impulse spike, or a seat/no-seat verdict.** A clip that the transit phase merely *dropped
    near* the shell xy scores `success=True` — even though nothing clicked and nothing seated.

### Phase F — the retry (THE REQUESTED BEHAVIOR — does not exist)

18. `[USER intent]` *"retry if it does not seat"* requires: read a seat verdict → if not seated,
    **re-press** (back off Z, re-align xy, descend again under force cap), up to N attempts.
19. `[SYSTEM]` **There is no tool, controller, or gate that does this.** The loop cannot be
    closed because:
    - No tool emits a `seated: bool` verdict the LLM can branch on at runtime
      (the gate emits delivery-only; `get_contact_report`/`get_world_transform` are raw probes
      the LLM would have to interpret, and the press they'd interpret never ran).
    - No controller takes a seat predicate + re-attempt budget. `setup_insertion_controller`
      runs the descent **once** and has no `max_attempts`/`reseat_on_fail` arg
      (`insertion.py:449` signature — none present).
    - `execute_contact_sequence_plan`'s `retry_count` is **dead** (carried into the dataclass at
      `contact_sequence.py:118`, never consumed by `execute_plan` at
      `execute_contact_sequence_runtime.py:333`).
    - The best the LLM can do is **unroll the retry in emitted Python** (`for attempt in range(3):`
      re-issuing the press + re-reading the probe). But since the press is `dry_run`, every
      attempt is identical and produces the same empty contact report — **the loop spins without
      changing physical state.** This is the same "LLM unrolls because no loop primitive exists"
      pattern flagged for `loop_workflow`/`repeat_cycle` in the gap inventory (Tier-4), but here
      it's worse because there is no live physics for the loop to converge on.

**OUTCOME:** Scene builds (Phase B ✓). Transit is real (Phase C step 11 ✓). The compliance
press, the click, the seat, and the retry are all **non-functional**: the press is a dry-run
plan, the click is never produced, the gate scores delivery-not-seat (false-positive risk), and
the retry has no substrate. **Net: structurally retrievable, behaviorally hollow on the two
load-bearing verbs ("click", "retry").**

---

## 2. Grounding — file:line citations

| Capability | Where | Status |
|---|---|---|
| Snap-fit template (exact match) | `workspace/templates/CP-NEW-yrkesroll-assembler-snap-fit.json` | Drafted; form-gate ⏳, function-gate ⏳ |
| `snap_fit` strategy (gains + 3-waypoint gen) | `handlers/insertion.py:83`, `:178` (`_gen_snap_fit`) | Exists, **dry_run only** |
| Insertion composite live-mode block | `handlers/insertion.py:351` `raise NotImplementedError` | No torque-mode bridge |
| Compliance sub-calls live-mode block | `handlers/compliance.py:186`, `:399` `NotImplementedError` | No ros2_control bridge |
| Contact-report probe | `handlers/physics.py:1639` `_handle_get_contact_report` | Exists (raw probe) |
| Codegen retry (NOT seat-retry) | `handlers/workflow.py:930` `_handle_execute_with_retry` | Wrong kind of retry |
| Contact-sequence `retry_count` (dead) | `handlers/contact_sequence.py:118` ; runtime `…runtime.py:333` | Field carried, never consumed |
| Gate = delivery-only | `handlers/diagnostics.py:3920` `simulate_traversal_check`; verdict `:3458`/`:3968`/`:3976` | **No seat verdict** |
| Grip-force calc (static, not a runtime guard) | `handlers/grip_config.py:9` | Calibration formula only |

---

## 3. Why the LLM cannot rescue this with cleverness

- **It cannot flip `dry_run=False`** — the handler raises `NotImplementedError` immediately; the
  arm has no torque-mode controller installed, so even if the bridge existed the impedance gains
  would have nothing to drive.
- **It cannot hand-roll the click** — there is no `apply_force` + per-step contact-poll loop
  primitive; `get_contact_report` returns the most-recent queued events but nothing is *driving*
  the clip down to generate them.
- **It cannot hand-roll the seat verdict for the gate** — `simulate_traversal_check` is fixed
  to delivery semantics; the LLM cannot pass it a "seated below z=0.802 AND impulse>0.5 N·s"
  predicate.
- **It cannot close the retry loop** — no controller consumes a seat predicate + attempt budget,
  and the codegen-retry path only re-runs broken *code*, not failed *seats*.

---

## 4. Tool gaps surfaced (NEW — not in TOOL_GAP_INVENTORY_V2's main body)

The inventory has ONE Tier-4 leaf line: *"force-guarded / abort-on-threshold trajectory +
retry-on-event … peg-insertion … M"*. That undersells it: it's filed as a single low-blast
leaf, but this trace shows it is the visible tip of a **class-level** gap spanning the entire
force-gated-assembly family (snap-fit, peg-insertion, screw-driving, bottle-cap, peg-bushing,
tactile-insertion — 6+ templates). The NEW, more specific gaps:

- **G1. Seat-verdict gate** (`verify_seat` / `simulate_assembly_check`): emit
  `{seated: bool, click_detected: bool, final_z, impulse_peak_Ns, attempts}` by reading
  `PhysxContactReportAPI` impulse stream + seated-Z threshold. Today NO gate scores a seat —
  `simulate_traversal_check` scores delivery, so all 6 force-gated-insert templates are
  **structurally unscorable on their actual success criterion** (same shape as the M2
  per-bin-sort gate gap, but for assembly).
- **G2. Closed-loop force-gated-assembly controller** (`setup_seat_controller` /
  `press_until_seated`): take `seat_predicate` + `max_attempts` + `force_cap_N` + `backoff_z`,
  run descend→sense→(seated? stop : back-off + re-align + re-descend) until seated or budget
  exhausted. This is the retry the request asks for; nothing today consumes a seat predicate or
  an attempt budget.
- **G3. Runtime force-guard / abort-on-threshold trajectory executor**: enforce the 25 N Z-cap
  *during* the descent and emit a contact-event signal — the live counterpart the dry-run
  `follow_trajectory_with_compliance` only describes. (Blocked on the ros2_control torque bridge,
  same `research` dependency as all impedance canonicals.)
- **G4. `loop_until` / `retry_until_predicate` control primitive** — a first-class
  attempt-budget loop so the LLM doesn't unroll N identical dry-run presses (generalizes the
  Tier-4 `loop_workflow` leaf to a *predicate-terminated* loop, which snap-fit specifically needs).

---

## 5. Kimate-assets relevance

- No snap-fit / clip / latch / peg asset in `/home/anton/kimate_assets/assets` (grep:
  `*snap* *clip* *latch* *peg* *assembl*` → only `plywoodcrateassembly_*` shipping crates,
  not articulated fasteners). The snap-fit template's clamshell+prong rig stays primitive-built.
- The **243 ArtVIP/Lightwheel articulated appliances** ARE relevant to the *broader* class:
  closing a real appliance door/lid to a latch is the same press-until-latched + retry-if-not-
  latched control shape (revolute-pull → detent), which couples this gap to the articulated-door
  controller gap (inventory M10). Worth noting: solving G1/G2 here would also serve
  "close the dishwasher until it latches" on those assets.
- No Allegro/3-finger/Shadow hand present (only the Reallusion **Worker** character mesh +
  Residential DoorHandle props) — so a dexterous-regrasp retry (re-grip then re-press) is also
  unavailable; retry is restricted to the parallel-jaw press axis.

---

## 6. THE CLASS-LEVEL FINDING

**Pick-place + delivery-gate is the platform's universal substrate, and it fundamentally does
not express "assemble until a state predicate holds, retry if not."** The humanoid-cabinet
trace showed pick-place breaks on *articulated doors* (needs a revolute-pull controller). This
snap-fit trace shows the symmetric break on the *assembly / force-gated-insertion* family:

- The **controller class is missing**: there is no closed-loop force-gated controller that takes
  a *seat predicate + attempt budget + force cap* and re-attempts on failure. Every insertion
  template (snap-fit, peg, screw, bottle-cap, peg-bushing, tactile) is a **single open-loop
  dry-run descent** — none can "press until click" let alone "retry if it does not seat."
- The **gate class is missing**: every gate in the repo scores *delivery* (`cube` in `target`
  xy, above floor). There is no gate that scores a *seat / click / engagement*. So even if the
  press were live, the platform could not measure success — and today it false-positives any
  near-xy drop as "delivered."

These are not two small tools; they are a missing **closed-loop-assembly capability layer**
(sense → predicate → re-attempt) that a whole family of contact-rich tasks needs. The request's
two verbs — **"click"** (a contact-event seat verdict) and **"retry"** (a predicate-terminated
re-attempt loop) — are precisely the two things this layer would provide and that the
pick-place + delivery-gate substrate structurally cannot.

**Build order suggestion:** G1 (seat-verdict gate, effort M, makes the whole insert family
scorable — highest measurement-honesty ROI) → G4 (loop_until primitive, S) → G2 (closed-loop
seat controller, M, *dry-run-scorable* immediately even before the live bridge) → G3 (live
force-guard, research, blocked on ros2_control torque bridge).
