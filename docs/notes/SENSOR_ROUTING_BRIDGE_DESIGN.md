# Sensor→controller routing bridge — design [P2-11, build-ready]

**The gap (blast-4):** sorts route off the USD-Semantics ORACLE — the
controller's `_cube_semantic_class` reads ground-truth class labels straight
off the prim, so classification sensors (barcode/NIR/vision) are decorative
and a misclassification can never occur, let alone be measured. The
PROXIMITY sensor is already honest (trigger volume writes
`isaac_sensor:triggered` attrs the controller reads; sensor_gated consumes
it) — the bridge below extends the same attr-mediated pattern to
CLASSIFICATION.

## Target architecture (one sentence)
Classification flows **sensor → `isaac_sensor:class` attr at scan time →
controller routes from the attr**, while raw Semantics stay GATE-side truth
— so a misroute finally means "sensor or controller failed", measurably.

## Design

1. **Scan-time attr write (new codegen, `add_classification_sensor`):**
   a trigger volume at the scan station (same mechanics as proximity);
   when an item enters, the sensor writes `isaac_sensor:class` (string) +
   `isaac_sensor:class_confidence` (float) on the ITEM prim.
   - V0 honesty model: the sensor reads Semantics INTERNALLY but through a
     declared ERROR MODEL: `accuracy` (default 1.0) + optional
     `confusion: {true_class: {wrong_class: p}}`. Interface-honest
     (controllers see only the attr), oracle-inside-with-declared-noise —
     the same pattern as sim2real domain randomization, and the error model
     is the measurable knob.
   - V1 (later): vision-NIM/barcode decode replaces the internal oracle;
     interface unchanged.

2. **Controller read-order change (ONE function,
   `pick_place.py::_cube_semantic_class` — UR10-TRACK FILE, coordinate):**
   prefer `isaac_sensor:class` when authored, fall back to Semantics. One
   added attr-read; all routing modes (color_routing/destination_map)
   inherit it. Templates without a classification sensor behave byte-
   identically (no attr → fallback).

3. **Gate stays oracle-side (NO change):** P0-18b's gate resolution reads
   raw Semantics = ground truth. With the controller on the sensor path,
   `misrouted`/`MISROUTED` now MEASURES the sensor+controller chain.
   honest_per_cube + diagnose_task_outcome need zero changes.

4. **Pilot + proof plan (1 Kit-hour):**
   - sorter-color-3lane + `add_classification_sensor(accuracy=1.0)` →
     expect identical 9/9 (regression leg).
   - accuracy=0.8 → expect ~2 MISROUTED, gate FAIL under completeness=all,
     `misrouted_count` > 0 — the FIRST measured misclassification in the
     corpus, and diagnose_task_outcome shows which item went where.
   - Ledger both runs; the delta IS the bridge's proof.

5. **Rollout after pilot:** barcode-divert (decode = class from the
   barcode-pattern semantics), nir-material-divert (material map), the
   vision-kitting family. Template edit = add one sensor call + nothing
   else (controller change is global via the read-order).

## Coordination & risks
- The read-order edit touches `pick_place.py` (UR10-track). It is one
  function, additive, byte-identical without the attr — but lands ONLY
  after UR10-track sign-off. Everything else (sensor codegen, schema,
  tests, pilot templates) is foundation-track and can be built first; the
  pilot just can't run end-to-end until the read-order lands.
- Error-model determinism: seed the confusion sampling from the template
  seed so N-of-M runs are reproducible.
- Don't conflate axes: sensor accuracy is a SCENARIO parameter (declared in
  simulate_args), not hidden noise.

## Build checklist (morning-ready)
- [ ] `add_classification_sensor` codegen (sensors.py) + schema + Args + l0
- [ ] seeded error model (pure helper + tests)
- [ ] UR10-COORD: `_cube_semantic_class` read-order (one-liner + l0)
- [ ] pilot runs per §4 (fresh-Kit, ledger both)
- [ ] rollout list per §5
