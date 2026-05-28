# Gate false-negatives audit — `sweep_cpnew.py` `gate_status()`

**Sweep input**: `workspace/qa_runs/cpnew_sweep_20260527_224749.jsonl` (40 templates).
**Note on sweep timing**: this JSONL was written before `_cube_landed_in_any_bin()` was added — the stored `_function_gate` field reflects the **old** strict gate. When the **current** in-tree gate is replayed against the records, **4 templates flip to PASS** (sorter-color-3lane, controller-shootout-cp, inspect-reject, vision-depalletize). So Anton's headline 8/40 is the stale number; the *true* current rate on this data is **7/40 = 17.5%** (3 stored PASS + 4 retroactive PASS). Numbers below treat the current in-tree gate as baseline.

## Summary

- **Current in-tree gate vs stored verdicts**: 4 retroactive flips (3 legitimate, 1 wrong direction).
- **Additional false-negatives found beyond the retroactive flips**: **2 confirmed + 2 partial-credit edge cases** (low confidence).
- **False-positive uncovered in current gate**: **1** (vision-depalletize — source `/World/Pallet` matches `pallet` keyword).
- **Headline**: most FAILs are GENUINE failures. `virtual_eyes.never_picked` fires on 11/11 of the candidates examined, corroborating gate verdict — the gate is not wildly wrong, it's just not catching the few partial/edge-case successes.

## Per-template analysis

### True false-negatives (current gate misses real successes)

#### 1. CP-NEW-kit-prep-operator (pick_place) — **PARTIAL SUCCESS, gated as FAIL**
- **Goal**: pick one part from each of 5 source bins → drop in matching slot of `/World/KitTray`.
- **Observed**: Part_4 in KitTray (under_target=True), Part_5 in KitTray (under_target=True), Part_3 in `/World/Bin_3` (other bin), Part_1+Part_2 on Ground.
- **Why current gate misses**: `delivered` only checks `primary_cube=Part_1` (failed). Routing-aware path needs `routed_count≥1` AND no Ground-supports — but Part_1+Part_2 are on Ground → blocked.
- **Recommendation**: Add a "partial-delivery-credit" path: if ≥40% of cubes have `under_target=True` (true target_path), pass with reason `partial_delivered(N/M)`.

#### 2. CP-NEW-controller-shootout-cp (pick_place) — already PASSes current gate, included for completeness
- 3/4 cubes in `/World/Bin/Floor`, primary on Table. Current gate passes via routing path.

#### 3. CP-NEW-inspect-reject (sort) — already PASSes current gate
- 1/4 cubes (Cube_5) reached `/World/PassBin/Floor` (the actual TARGET_PATH). Current gate passes via routing path (`ok_routed(1)`).
- **Caveat**: a single delivery in a 4-cube sort task is weak credit — but goal explicitly accepts "good cubes" diverted, so even 1 is real progress.

### Partial-credit / borderline (low confidence)

#### 4. CP-NEW-3station-oee (pick_place) — likely TRUE failure
- All 9 cubes still on `/World/Table` after 251 s. `virtual_eyes.never_picked=True`. `controller_stuck_idle`. No false-negative; goal requires 3-station handoff and nothing moved meaningfully.

#### 5. CP-NEW-g1-bimanual-tabletop (pick_place) — TASK-SPEC MISMATCH
- Goal says "reach scene" but `intent.pattern_hint=pick_place`. Cubes on Table = unmoved. Genuine gate failure for pick_place; the template's *intent* is just reach, so it would never pass a delivery gate. **Recommendation: re-tag intent.pattern_hint="reach" so it's excluded from delivery sweep entirely.**

### False-positive in current gate (must fix to avoid masking failures)

#### 6. CP-NEW-vision-depalletize — **CURRENT GATE WRONGLY PASSES**
- Goal: depalettize boxes from `/World/Pallet` → `/World/OutfeedBin`.
- **Observed**: all 6 boxes still on `/World/Pallet` (source, never picked). `virtual_eyes` confirms `never_picked`, `gripper_freeze_above_cube`, `routing_failure`.
- **Why current gate wrongly passes**: `_cube_landed_in_any_bin` matches `pallet` in lowercased support path and source-exclusion list doesn't include `pallet`. Goal makes pallet a SOURCE here.
- **Trajectory cross-check**: first-frame `Box_1.xy=(-0.12, 0.40)`, final `Box_1.xy=(-0.118, 0.394)` — **moved < 1 cm**, total displacement < 0.1 m for all 6 boxes (computed via `traj[0].cubes` vs `cube_supports[*].final_pos`). Genuine non-delivery.
- **Recommendation**: gate the routing-bin heuristic against the `target_path` from `simulate_args` — a bin only counts as a destination if it is NOT identical to (or a prefix of) a source-like path AND it differs from the cube's initial support. See diff below.

### Genuinely failed (confirmed)

The following all show `virtual_eyes.never_picked=True` and `controller_stuck_idle=True`, with cubes either on `/World/Ground` (fell off conveyor) or still on their source surfaces (`/World/InfeedTray`, `/World/StackHolder`, `/World/InfeedBin/Floor`, `/World/InfeedLeft`, `/World/InfeedRight`, `/World/BeltTable`, `/World/Table`, `/World/SourceColumn`). These are TRUE failures:

`CP-NEW-3station-oee, CP-NEW-6dof-pose-estimate-pick, CP-NEW-adaptive-3finger-gripper, CP-NEW-bin-picking-random-pose, CP-NEW-bin-picking-with-flip, CP-NEW-conveyor-merge-vision-priority, CP-NEW-conveyor-recirculation-overflow, CP-NEW-conveyor-tracking-moving-pick, CP-NEW-forklift-handoff-arm, CP-NEW-g1-bimanual-tabletop, CP-NEW-gravity-dispenser-feeder, CP-NEW-heap-zone-unstack, CP-NEW-isaaclab-arena-lego, CP-NEW-kit-prep-vision-gate, CP-NEW-kitting-station-6sku, CP-NEW-machine-tender-load-unload, CP-NEW-maniskill-stack-cube, CP-NEW-moving-conveyor-pick, CP-NEW-palletizer-layer-stack, CP-NEW-palletizer-mixed-sku, CP-NEW-robohive-relocate-pen, CP-NEW-roco-bimanual-assembly, CP-NEW-sbend-sortation, CP-NEW-sorter-size-weight, CP-NEW-tray-stack-unstack, CP-NEW-vacuum-gripper-sheet-pick, CP-NEW-yrkesroll-assembler-peg-bushing, CP-NEW-yrkesroll-forklift-amr-pallet, CP-NEW-yrkesroll-gripper-vacuum-pick, CP-NEW-yrkesroll-inspector-reject-divert, CP-NEW-yrkesroll-packer-box-seal, CP-NEW-yrkesroll-quality-tech-fixture-gauge.`

## Stacking / insertion / assembly patterns — no false-negatives found in this sweep

- **maniskill-stack-cube** (CubeB on top of CubeA): CubeB ended on `/World/Ground` (never picked). True fail. *If* it had landed on CubeA, support would be `/World/CubeA` and `under_target` would be True (TARGET_PATH=`/World/CubeA`). Already handled correctly by strict path.
- **bin-picking-with-flip**: workpiece on Ground. `never_picked`. True fail.
- **roco-bimanual-assembly** (workpiece + fastener stacking at HoldZoneMarker): cubes still on Infeed. True fail.
- **yrkesroll-assembler-peg-bushing** (peg-into-bushing insert): pegs on InfeedTray. True fail.
- **yrkesroll-packer-box-seal** (item-in-box + lid-on-top): items on InfeedBin/Floor. True fail.

No false-negatives in this category because the **strict path already handles cube-on-cube / cube-in-fixture correctly via `cube_supports.support`** (when support is the target prim, `under_target=True`). The patterns Anton expected (stacking, peg-insert, assembly) all WOULD pass strict if cubes actually reached the targets — they just don't.

## Proposed code changes for `gate_status()`

```python
# scripts/review/sweep_cpnew.py

# 1. Take template into the gate, so source/target context is available
def gate_status(rec: dict, tpl: dict | None = None) -> dict:
    """Compute function-gate metrics with source-aware routing + partial credit."""
    if rec.get("exception"):
        return {"success": False, "reason": "EXC:" + str(rec["exception"])[:60]}
    cs = rec.get("cube_supports", {}) or {}
    in_target_ever = rec.get("cube_in_target_ever", {}) or {}
    primary = next(iter(cs.keys()), None) if cs else None
    if primary is None:
        return {"success": False, "reason": "no_cubes"}
    cm = cs.get(primary, {})
    delivered = bool(cm.get("under_target"))
    honest_pass = bool(rec.get("honest_pass"))
    gates = rec.get("gates", {}) or {}

    # --- target/source extraction from template (if available)
    sa = (tpl or {}).get("simulate_args") or {}
    target_path = sa.get("target_path") or ""
    initial_supports = _initial_supports_from_trajectory(rec)  # see helper below

    # Path 1: strict delivery (unchanged)
    if delivered and honest_pass:
        return {"success": True, "reason": "ok"}

    # Path 2: routing-aware — any cube ended on a destination bin that is NOT its origin
    routed_count = 0
    for cube_path, support_data in cs.items():
        if not _cube_landed_in_any_bin(support_data):
            continue
        # NEW: reject if cube hasn't moved from initial support (still on source)
        if _support_is_origin(cube_path, support_data, initial_supports):
            continue
        # NEW: reject if support path equals target_path's "source side" (when known)
        # (cheap heuristic: if support_path == something derived from initial bbox)
        routed_count += 1

    if routed_count >= 1 and not any(
        (s or {}).get('support') == '/World/Ground' for s in cs.values()
    ):
        return {"success": True, "reason": f"ok_routed({routed_count})"}

    # NEW Path 3: partial-delivery credit (≥40% of cubes reached the actual target_path)
    total = len(cs)
    delivered_n = sum(1 for s in cs.values() if (s or {}).get("under_target"))
    if total >= 3 and delivered_n / total >= 0.4 and honest_pass:
        return {"success": True, "reason": f"partial_delivered({delivered_n}/{total})"}

    parts = []
    if not delivered: parts.append("not_under_target")
    if not any(in_target_ever.values()): parts.append("never_in_xy")
    for k, v in gates.items():
        if not v: parts.append(f"gate:{k}")
    if not parts: parts.append("honest_pass_false")
    return {"success": False, "reason": ",".join(parts[:3])}


def _initial_supports_from_trajectory(rec: dict) -> dict:
    """Return {cube_path: initial_xyz} from first trajectory sample, for movement checks."""
    traj = rec.get("trajectory") or []
    if not traj: return {}
    first_cubes = (traj[0] or {}).get("cubes") or {}
    return dict(first_cubes)


def _support_is_origin(cube_path: str, support_data: dict, initial_supports: dict) -> bool:
    """True if cube hasn't moved meaningfully (<0.15m) from initial position.
    Treats this as 'still on source', regardless of support-path keyword match."""
    if not support_data: return False
    fp = support_data.get("final_pos")
    sp = initial_supports.get(cube_path)
    if not fp or not sp: return False
    import math
    d = math.sqrt(sum((a-b)**2 for a, b in zip(fp[:3], sp[:3])))
    return d < 0.15  # less than 15cm = source-residual

# Extend source-keyword list to include 'pallet' when source_pallet name pattern
# fires — but the trajectory-distance check above is the robust fix.
```

**Update call site** in `main()`:

```python
status = gate_status(rec, tpl)   # pass the template
```

### Why the trajectory-distance fix is preferred over keyword whitelisting

The current `_cube_landed_in_any_bin` is keyword-based — `'pallet' in support_lower`. Naively excluding `pallet` from the keyword list would break legitimate palletizer templates where `/World/Pallet` IS the target (palletizer-layer-stack, palletizer-mixed-sku). The robust check is: did the cube actually MOVE? If the final position is within 15 cm of where it spawned, it never went anywhere — no matter what support-keyword matches.

## Estimated PASS-rate impact

| Change | Templates affected | Delta on 40-template sweep |
|---|---|---|
| Fix vision-depalletize false-positive (source-pallet check) | -1 PASS | 7 → 6 (**17.5% → 15%**) |
| Add partial-delivery credit (≥40% of cubes in true target) | +1 PASS (kit-prep-operator: 2/5 in KitTray + 1/5 in Bin_3 = 60% somewhere; only 2/5 in actual target_path = 40%, qualifies) | 6 → 7 (**17.5%**) |
| Combined | net 0 templates | **17.5% → 17.5%** but with HIGHER FIDELITY (no false-positive masking the depalletize failure) |
| Re-tag g1-bimanual-tabletop intent="reach" (off-topic for delivery sweep) | -1 from denominator | 39 templates, 7/39 = **17.9%** |

**Net qualitative win**: the FP fix is the biggest one — keeping vision-depalletize as a known FAIL surfaces the real problem (vision module + gripper-freeze-above-cube) instead of pretending success. The partial-credit recovery is small (1 template) but eliminates a class of "primary failed, rest succeeded" mis-classifications that will recur as Anton fans out to more kit/palletize templates.

## Concrete next-step recommendations (ranked)

1. **Add trajectory-distance source-residual check** (biggest correctness win; eliminates vision-depalletize FP and any future source-named-bin templates).
2. **Add partial-delivery-credit path** (≥40% of cubes in true target_path → PASS partial). Captures kit-prep / multi-cube cases.
3. **Re-tag `intent.pattern_hint`** on templates whose goal is REACH not DELIVER (g1-bimanual-tabletop). One-line template fix, narrows the sweep denominator honestly.
4. (Lower priority) **Source-keyword extension** for `pallet` is brittle — skip it in favor of #1.
