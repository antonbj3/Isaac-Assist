# Multi-cube chain handoff — "relays 1/N" diagnosed (cont.319hh, Kit-free)

NULÄGE named the multi-cube handoff ("relayar nu 1/N") as the BREADTH blocker for authoring
more chain-ready operation-stages (stack/palletize-receivers). A Kit-free read of the cross-Kit
chain (`scripts/qa/chain_xkit_gate.py`) **redefines** the blocker:

## The relay infrastructure is already N-capable — NOT the bottleneck
- `run_stage0` line 138: `r["handoff"] = {cp: poses[cp] for cp in cubes ...}` records **all N**
  delivered cube world poses.
- `run_stage_k` lines 187 / 199: re-instantiates **all N** relayed cubes (`relay_paths` /
  `measure_cubes` are length-N lists).
- line 200: `execute_template_canonical(..., source_override=measure_cubes)` hands the receiver
  controller **all N** relay paths.
- line 243: `_play_and_measure` measures **all N**; line 113 already scales the measurement
  window with N (`1700 * len(cubes)`).

So record → re-instantiate → source_override → measure are all N-capable. The plumbing is done.

## ⚠️ EMPIRICAL CORRECTION (cont.319hh, Kit-verified) — multi-pick receivers EXIST and WORK
The hypothesis below ("proven receivers are single-pick") is **REFUTED** by the registered stages
+ Kit runs. `chain_stages.json` already has **CP-CHAIN-STACK-RECV** (n=1..N, cap=3) and
**CP-CHAIN-PALLETIZE-RECV** (n=1..N, flat-grid) — multi-pick receivers. Prior + new cross-Kit runs:
- **CP-12 (3) → CP-CHAIN-STACK-RECV: 3/3 + 3/3 ALL DELIVERED** (reproducible 2×; relay cubes
  stacked z 0.825→0.875→0.925 on one xy = a real column). Multi-cube handoff is PROVEN for N=3.
- **CP-08 (4) → CP-CHAIN-STACK-RECV: 4/4 + 3/4** = CAPACITY overflow (cap=3), not a relay defect —
  exactly what compose_handoff's capacity pre-filter catches.
- **CP-08 (4) → CP-CHAIN-PALLETIZE-RECV: 4/4 + 3/4** (cont.319hh, cap=None so NOT overflow). RAW:
  3 cubes form a genuine grid (all z=0.785, pitch ~0.13, single layer); **Cube_4 at [-0.368,-0.833,
  0.775]** = z 10mm BELOW the grid → dropped on the bare TABLE off the pallet footprint, settled
  (not carried at window-end → not a window cutoff). A genuine **early-drop of the 4th pick**.

So NULÄGE's "relays 1/N" is OUTDATED: the relay infra is N-capable AND multi-pick receivers work
for N=3. The open frontier is the **4th cube in a palletize sequence drops off-pallet** (3/4).

### Original hypothesis (kept for the record — partly wrong)
Earlier I read chain_xkit_gate and guessed the proven receivers were single-pick (CP-CHAIN-FLAT,
CP-CHAIN-UR10-SRC are). That was true for those two but missed the STACK/PALLETIZE multi-pick
receivers already registered. Lesson: a code-read across one slice of the harness under-counted the
capability — the Kit run corrected it.

## The remaining gap: the 4th palletize pick drops off-pallet (3/4)
Candidate causes (need a chain-measure trajectory upgrade to disambiguate — the current
_play_and_measure logs only FINAL poses, no per-object trajectory/grip/plan_fail):
- **offset-from-X0**: run_stage_k derives the receiver origin_offset from X0 (first relayed cube,
  line 151-153). The 4 relayed cubes sit at their scattered stage-(k-1) grid positions; the
  receiver's pick is aligned to X0, so the 4th cube (farthest from X0) may be at the edge of the
  reach/grip envelope → early release.
- **4th-pick IK/reach degradation** at the far grid cell (a known palletize tail-off; cf. CP-25
  PARTIAL 8/16 tight-grid, CP-20 PARTIAL 6/18).
Focused follow-up (Kit-bound, deferred per be-sparing/diagnose-once): upgrade chain_xkit_gate's
MEASURE to log per-object trajectory + grip + plan_fails (like scene_eyes), re-run, read which of
the two causes fires for Cube_4, then fix (re-target the 4th pick, or per-cube offset).

## To unblock stack/palletize-receivers (the BREADTH work)
Author + Kit-verify a **chain-ready MULTI-PICK receiver** whose controller iterates picks over
the N source_override'd cubes and stacks/palletizes them. Open design question (decide in-Kit):
- The N relayed cubes are re-instantiated at their **scattered** stage-(k-1) delivery positions
  (offset aligns only X0 = first cube to the receiver pick-zone, line 151-153). A palletize
  receiver must therefore either (a) pick each cube from its **own** recorded handoff position
  (multi-position pick), or (b) the handoff must **queue** all N at one pick-zone (e.g. a feeder /
  end-stop the receiver picks from repeatedly).
- Candidate existing multi-pick template to test as a receiver: **CP-08** (two-palletizer, picks
  4 cubes → grid). Check whether its controller accepts `source_override` of N cubes + iterates.
  If yes, a chain-ready palletize-receiver may be CP-08 + a handoff that lands the N relayed cubes
  where CP-08 expects its source cubes.

## Known generality limit (line 204-211, honestly documented — deferred)
The handoff carries **position only**; each relayed object is re-created as a hardcoded 0.05
`UsdGeom.Cube`. So multi-cube relay is faithful only for **homogeneous 0.05-cube** chains (all
proven chains are). A heterogeneous handoff (Brick/Box, different size) relays a wrong-shape
stand-in. To generalize: carry the measured bbox size (`bb()` already computes it) + the source
prim type through the handoff dict, re-create with that type/size. No heterogeneous use-case yet
→ deferred per feedback_phantom_rootcause_and_optional_bug_overinvest.

## Verify-when-GPU-free
This diagnosis is Kit-free (code-read). Closing it = authoring a multi-pick chain-ready receiver
+ `scene_eyes` RAW verify that it picks all N relayed cubes into a grid/stack (per-object
trajectories, not delivered-count). Gated now by the GPU hosting an active foreign sibling-project
Isaac service (do not boot a competing Kit → degradation risk).
