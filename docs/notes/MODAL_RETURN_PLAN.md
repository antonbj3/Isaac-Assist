# Modal-return plan — ✅ DONE 2026-06-14 (account up, #11 RESOLVED, pool production-ready)

STATUS 2026-06-14: new free-credit account live. Volume recreated (os.walk upload of all 60
qa_assets). Image builds. CP-01 smoke gate=True. 12-tpl parity batch ran. **#11 RESOLVED:
cloud is FAITHFUL to local (Franka AND UR10) on FRESH containers — the apparent "UR10
divergence" was a WARM-CONTAINER-REUSE Kit-degradation confound (boot<60s = degraded, fails
spuriously). PROOF: CP-70 x3 fresh = 3/3 PASS.** FIX committed: pool `max_inputs=1` (fresh
container per template). Tooling: parity_check.py (compares + flags warm-reuse boot<60s), pool
runs scene_eyes via `--eyes`. Memory: project_isaac_assist_modal_parity_11. Validated workflow:
  modal run scripts/cloud/modal_isaac_pool.py::main --templates "A,B,C" --skip-ts [--eyes]
  python3 scripts/cloud/parity_check.py            # compare cloud vs local, flag warm-reuse
Modal is now a production throughput tool for FRANKA + UR10 gate batches (fresh-Kit per tpl).
DON'T ledger cloud results into per-template verification (merges cross-platform counts).

--- original plan (historical) below ---
Brev is OUT (card rejected). Modal new-account is the throughput path. This makes it
immediately productive: import → #11 parity → parallel batch. Zero ramp.

## 0. Import (3 steps, from MODAL_MIGRATION.md — no setup beyond auth + 1 upload)
- `modal token new` (auth the new account)
- `modal run scripts/cloud/modal_isaac_pool.py --templates CP-45` (forces image rebuild:
  cuda12.8.1 + torch cu128 + **warp 1.11** [matches local Isaac → one fewer divergence
  source] + cuRobo pinned; ~first-run only)
- upload `~/modal_migration/qa_assets/` to the `isaac-kit-cache` volume `/qa_assets`
  (the only non-regenerable artifact, 47MB/60 files)

Pool interface: `modal run scripts/cloud/modal_isaac_pool.py --templates A,B,C` → parallel
serverless Kit workers, each runs `gate_one.py` UNCHANGED (fresh-Kit each) → verdict
directly comparable to local. THIS is the throughput win: N templates in parallel,
no in-session degradation, no serial-boot wait.

## 1. #11 cloud-parity batch (the RCA — do FIRST, before trusting any cloud verdict)
Run this set on Modal, compare cloud verdict vs the KNOWN local verdict per template.
Local baselines all measured 3/3 fresh-Kit-solo this session (trustworthy controls):

POSITIVE parity (must PASS on cloud too):
  yrkesroll-gripper-vacuum-pick (local 3/3 4/4), CP-10 (3/3 9/9), CP-35 (3/3 8/8),
  CP-48 (3/3 5/5), CP-19 (3/3 6/6), CP-47 (3/3 2/2)
NEGATIVE parity (must FAIL on cloud too — guards against cloud false-PASS):
  CP-59 (local 1/4 exec-gate), CP-38 (local ~50% flaky/11-12 marginal), mixed-sku
  (local 5/6 union-pass but sort-unverified), CP-43 (1/4 sphere), CP-44 (3/4)
Command: `modal run scripts/cloud/modal_isaac_pool.py --templates yrkesroll-gripper-vacuum-pick,CP-10,CP-35,CP-48,CP-19,CP-47,CP-59,CP-38,CP-NEW-palletizer-mixed-sku,CP-43,CP-44`
VERDICT: parity precedent was 8/9 (modal_20260612). Expect ~parity (warp 1.11 matches).
  Any divergence (cloud≠local) = the genuine #11 finding → RCA that template (likely a
  hardcoded /mnt path, asset-resolution, or CPU-physics-determinism difference — NOT a
  reason to distrust ALL cloud; localize the specific template).

## 2. Parallel batch throughput (after parity confirmed)
- 3/3 fresh-solo CONFIRMATIONS in PARALLEL (instead of 3 serial local boots): for any
  new fix, `--templates X,X,X`-equivalent across 3 workers → ~12 min wall vs ~36 local.
- Re-attack the deep frontier with cheap parallel measurement (sweep variants at once):
  e.g. CP-38 grid-tightening variants, CP-59 exec-gate instrumented runs, sphere-grip
  friction/force sweeps — measure many candidates per wall-clock-window.
- Memo caveat: Modal for **Franka batch-gate**, historically flagged **ej UR10** (UR10
  needed local asset specifics). The image now ships qa_assets (UR10/Isaac closure) so
  RE-TEST one UR10 (CP-70) cloud-parity before trusting UR10 cloud verdicts.

## 3. Guards (from 2026-06-14 warp audit)
- Modal is isolated → no sibling-project warp-1.13 contamination (that's local-only;
  see [[project_isaac_assist_warp_1130_red_herring]]). Cloud warp = 1.11 by image pin. Good.
- Cloud physics is CPU (enable_gpu_dynamics=False) → determinism differs subtly from local
  GPU-physics; that is itself a parity-divergence candidate (#11) — watch the stochastic
  templates (rotary CP-56, dual-arm) for cloud-vs-local flicker, use N-of-M not single-run.

## Net
Modal = ~2-3x measurement throughput (parallel fresh-Kit) for Franka gate batches; it is a
SPEEDUP, not a blocker. #11 parity must pass first (else cloud verdicts untrusted). It does
NOT unlock new wins that are otherwise impossible — the deep frontier (exec-gate, grip
physics, behind-robot reach) is analysis-bound, but Modal lets me sweep candidate fixes far
faster.

## Added 2026-06-14: sphere-grip finger-position sweep (CP-43/44) — UPDATED (sentinel cracked, preload exhausted)
BIG UPDATE 2026-06-14 fresh-context: the months-old "sentinel never fired" was a `\n`-in-generated-string
SyntaxError that BLOCKED the controller (see memory reference_generated_code_escaping). Now CONFIRMED:
curobo `_grip_close@6040` is the variant, S["picked_path"] IS the sphere, IsA(Sphere) detection works.
Object-aware close (override forward("close") action's joint_positions to per-finger=radius-preload, sphere-gated)
is BUILT and ELIMINATES the ejection at all preloads. BUT the **preload axis is EXHAUSTED locally**:
sweep 0.002..0.020 -> force 0.108..0.658 (all below the 0.84 eject point) yet Sphere_2 STILL drops at ~15s
(rolls up into panda_hand) -> the binding constraint is **transit roll-out (form-closure)**, NOT grip force.

MODAL SWEEP (2-axis, the new plan): `_sphere_grip_preload` (builtins flag, scene_eyes env `PRELOAD=`) is
already wired. Need a SECOND axis = **transit velocity-scale while carrying a sphere** (slow the swing ->
less rolling moment). Sweep preload {0.006,0.010,0.014} × transit_velscale {1.0,0.5,0.3} × {CP-44,CP-43},
3-fresh-solo each, gate-measured count (NOT scene_eyes drop — it doesn't predict gate count). Validate CP-01
cube control byte-identical (object-aware close is sphere-gated). HONEST: may be form-limited regardless ->
the real-world answer for round objects is suction/tool-change, not a parallel jaw (the task wants
heterogeneous types). If Modal confirms form-limited, re-class CP-44/43 as a gripper-mismatch finding.
Current local state: object-aware-close code + PRELOAD flag are committed OR reverted per the measured
full-gate count (see latest progress log / sphere memo).
