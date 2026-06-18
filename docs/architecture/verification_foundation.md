# Kit-free verification foundation (PLC-export + composition)

Built 2026-06-18 (cont.297–303). A layer of **static, Kit-free** guards over the orchestration-export and
composition machinery, so claims about those tools are *measured* (by external parsers / ground-truth / negative
controls), not self-assessed. Every guard was added after an adversarial audit caught a real false-success on the
tool it now guards.

## Entry point

```
bash scripts/qa/run_static_checks.sh      # runs all 6 guards; explicit files, NO pytest/globs
```

No Kit, no Gemini, no ChromaDB. Run it before trusting any of the tools below. (Explicit-file runner by design —
the `no-local-pytest` / ChromaDB-freeze rule forbids directory-glob test runs here.)

## The 6 guards

| guard | asserts | how it can't lie |
|---|---|---|
| `test_plc_st_parses.py` | every emitted IEC 61131-3 **ST** parses under `blark` (a real IEC grammar); every emitted **ROS2** node is ast-valid Python | external grammar / `ast`, not self-judgement |
| `test_plc_roundtrip.py` | consume-IR round-trip is faithful: position + **literal** orientation + approach_height captured; **runtime-computed** orientation honestly flagged `lossless=False` | compares against fields the IR could otherwise silently drop |
| `test_plc_controlflow.py` | emitted ST state-machine control flow is correct (in-range, reachable, grip-abandon lands on Approach/terminal) | negative control: injects 3 bugs, must catch all 3 |
| `chain_registry_validate.py` | `chain_stages.json` consistent (stage existence, position capability first/mid/last, surface-not-bin, handoff reach band) | negative control: stale-ref / reach / bad-terminal |
| `test_chain_compat.py` | the handoff **predictor** (`compose_handoff.chain_compat`) agrees with ground truth: 9 proven pairs COMPAT, deep-bin INCOMPAT | negative control: flat→raised-pick INCOMPAT |
| `test_composable_blocks.py` | block catalog consistent; summary's genuine-vs-position-honest split matches per-block verdicts | recomputes the split from the data |

## False-successes these caught (on my own tooling)

1. **Pseudo-ST** — `emit_sfc` claimed "valid ST" but emitted code no IEC grammar accepts (slashes in identifiers,
   bare `0.4s` literals). Fixed to the standard command-word + PLCopen-feedback pattern; blark-verified.
2. **Orientation blindness** — `roundtrip_check` claimed "lossless" while the IR dropped `gripper_rotation`
   entirely (a tautological gate that couldn't see the dropped field). Now captured/compared.
3. **Hardcoded approach_height** — IR exported `0.10` ignoring the template's actual 0.05–0.2.
4. **Trusted-lump** — `composable_blocks.json` summary lumped 21 execution-GENUINE blocks with 43
   position-honest-ONLY (execution unverified) as one `trusted: 64`. Split surfaced + guarded.

## Hot-swap doctrine: evidence, not assertion

The orchestration of a pick-place template lifts into an engine-agnostic **Sequence-IR** (`plc_export_poc.py:
extract_ir`). "One IR, swappable backends" is now backed by **two concrete backends**:

- **IEC 61131-3 ST** (`emit_sfc`) — a CASE state machine for a PLC.
- **ROS2 / MoveItPy** (`emit_ros2`) — a pick-place node for a ROS2 cell.

**Agnosticism boundary (the finding):** the *sequence + targets* transfer cleanly across both (same recipe of
pick-object → place-pose+yaw, same 6-phase cycle, same grip-retry-3×). The one thing realized differently per
backend is the **transition-guard mechanism**: PLC *polls* a feedback bit (`ee_reached`); ROS2 *awaits* the
`plan()/execute()` result. So the IR's guards are an *interface* each backend fulfills natively, not a PLC
construct — the IR holds up as engine-agnostic.

## Honest scope (verified vs asserted vs gated)

- **Verified:** ST parses (blark); ROS2 ast-valid; consume-IR round-trip faithful; control-flow correct;
  registries consistent; predictor agrees with proven chains.
- **Asserted, NOT executed:** ST is **not** compiled to PLC bytecode (no IEC codegen); ROS2 node is **not** run
  against a live ROS2/MoveIt stack (no `rclpy`/`moveit_py` here) — its MoveItPy calls are the documented API
  surface, integrator-bound. Motion FBs / safety interlocks are stubbed.
- **Known limits:** the consume-IR captures *orchestration* (source/targets/orientation/approach), not full
  scene-build; runtime-computed orientation is not statically capturable (flagged, not silently dropped). The
  cross-Kit relay (`chain_xkit_gate`) carries **position only** + re-creates relayed objects as 0.05 cubes →
  multi-cube handoff is faithful only for homogeneous 0.05-cube chains.
- **Gated / deferred (not in this layer):** the sim-native "consume the IR" refactor (Anton-scoped); UR10
  grid-spread (deep cuRobo limit); LLM compose-reasoning (Gemini, run sparingly); real-assets / L3.
