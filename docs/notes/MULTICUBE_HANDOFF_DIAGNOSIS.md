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

## The real bottleneck: proven chain RECEIVERS are SINGLE-PICK
The proven chain receivers (CP-CHAIN-FLAT, sensor path; CP-CHAIN-UR10-SRC, source_paths path)
pick **one** cube at their single pick-zone → deliver to one target. Even with N cubes
source_override'd, a single-pick controller picks 1. "Relays 1/N" = single-pick receiver, not a
relay defect.

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
