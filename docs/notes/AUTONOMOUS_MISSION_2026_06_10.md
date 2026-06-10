# Autonomous build run — 2026-06-10 (~08:00 → 20:00)

**Mandate (Anton, "kör"):** 12h non-stop build against `IMPLEMENTATION_PLAN.md`, commit per completed
item to `feat/foundation-build`, continuous backup-push to the `anton` remote. **Read this doc first
on every cron wake.**

## Hard rules
1. **NEVER self-terminate.** Grind until 20:00. No "checkpoint and rest". If the cron is gone, re-create it (session-only).
2. **No pauses for permission.** Architectural calls (faithful suction, default-flips on passers, template re-specs) → FLAG in the log below, move on.
3. **NO push to origin (k3street), NO PR creation.** Private branch only. Anton slices topic-PRs after review.
4. **QC is mine, never delegated:** adversarial diff-read + run the tests MYSELF before every commit. Subagent claims are unverified until I check them. **⚠️ Anton 09:1x: session effort is LOW — Opus/Sonnet output may be subpar. Tightened QC:** (a) read delegated LOGIC line-by-line, not just diff shape; (b) verify delegated TESTS actually bite (would they catch an obvious break? beware trivially-passing tests); (c) for gate/controller code (P0-18 class): verify legacy behavior unchanged by RUNNING the pre-existing suite + reading the default path; (d) expect higher bounce rate — re-delegate with tighter spec or take over, never patch mush; (e) keep delegation scopes SMALL and mechanically verifiable.
5. **Leak guard before EVERY commit:** `grep -riE "robotics.lab|sibling-project" <staged files>` must be empty + `python3 scripts/lint_mandate.py` exit 0. Internal research → `docs/research/` (ignored), never notes.
6. **Kit is single-tenant + serial.** One Kit consumer at a time; restart before measurements; N-of-M on stochastic verdicts. Subagents do NO-Kit work only.
7. **Commits:** topic-clean, one per completed item, message cites the item ID. Tests green before commit (l0 + the item's done-criterion).
8. **Conductor model:** Sonnet = mechanical/specced; Opus = mid-complexity builds (worktree-isolated when touching shared files); me = hardest items + all QC + all commits.

## Work queue (in order; skip blocked with a note, never stall)
1. **P1-10** static_eyes tool registration (schema + handler + no_handler_tools + l0; tools-resolve green) — ME
2. **P0-20** version-control scene_timeseries.py (+why_classify.py) into scripts/qa/ — SONNET
3. **P1-01** populate height_m on all PALETTE classes; static_eyes prefers palette, fallback shrinks — SONNET
4. **P0-18** honest delivery gate: (a) multi-target per-bin, (b) completeness mode, (c) all-workpieces-graded lint — OPUS (worktree)
5. **P1-11** wire static_eyes into verifier_registry form_gate (fill the reach stub)
6. **P1-12..14** dual-verify: metric pairs + skip-or-gate policy + fidelity tags (spec local: docs/research/DUAL_VERIFICATION_SPEC.md)
7. **P1-15** calibration on the UR10-cluster + CP-NEW sample (KIT — serial, fresh-Kit discipline)
8. **P1-09** tier-2 reach probe wrapper (KIT)
9. **P0-07/P0-08** motion_controllers honesty audit + declared-not-verified marking — SONNET audit, me apply
10. **P0-19** structured verified_status + re-validation ledger
11. **P1-18..20** Relation edge + validator + static_eyes declared-relations
12. **P2-01** semantic-USD-diff verifier — OPUS
13. Continue down IMPLEMENTATION_PLAN.md (P2-02b expand=True contract, P2-06 diagnose_task_outcome, X-05 inert-tool audit, P5-22 gate classes…)

## Flags for Anton (decisions parked here, not asked)
- (none yet)

## Progress log (append per wake/commit)
- 08:00 run start. Branch `feat/foundation-build` @ 64fa1733, tree clean, 6/6 static_eyes l0 green.
- 08:4x P0-20 ✓ c43b79e1 (scene_timeseries+why_classify versioned, QC'd) · P1-01 ✓ 630ceca2 (60 palette heights, 6/6 green) · P1-10 ✓ (static_eyes tool: handler+schema+5 l0, audit 0 ghosts). Opus P0-18 (honest gate) still running in worktree. Next: P1-11 (verifier_registry wiring).
- 09:0x P1-11 ✓ (verify:reach fylld — static_eyes-verdikt i form_gate; 12/12 + 16/16). Kö-nästa: P1-12..14 (dual-verify) medan Opus P0-18 kör.
- 09:3x P1-12..14 ✓ (dual_verify: pairs+policy+tiers; SKIP hårt grindad bakom kalibrering; 21/21). Opus P0-18 kör än. Nästa: P1-15 (kalibrering, KIT) förbereds; P0-07-audit kan delegeras under tiden.
- 10:0x P0-07+P0-08 ✓ (audit spot-checkad; 28 osynliga templates fick ärliga mc-fält, kirurgisk insättning efter att MIN egen json-roundtrip-diff underkändes i QC ×2; R2-writeback avstådd medvetet — parkerad till efter P0-18). Opus P0-18 kör fortfarande.
- 08:42 P1-18..20 ✓ (Relation-kant v1.1 + validator + static_eyes-verifiering; relation-fails når decide via geometry-pair; 25/25 + 104 regression). Opus P0-18 fortfarande i luften.
- 08:53 P0-18 ✓ portad+committad efter djup-QC: fel worktree-bas (master!) upptäckt, funktions-region verifierad identisk, 2 konflikter lösta mot vår verifierade _cube_support, TRASIG IMPORT fångad (agentens tester exekverade aldrig handlern — handler-test tillagt), _models regenererad. 36/36 + audit 0 ghosts. Kvar i kön: P0-19, P1-15/P1-09 (Kit), P2-01.

## RULE UPDATE (Anton ~11:0x) — delegation slicing
- SLICE delegations smaller: ≤20-30 min agent work, ONE file/module per task, never a multi-file gate change in one go. (P0-18: one 50-min Opus task returned wrong-base + broken import + duplicate logic; three 15-min tasks would each be trivially QC-able.)
- Worktree agents MUST report `git log --oneline -1` of their base as their FIRST action.
- Agent output is never trusted: handler/entry paths must be EXECUTED by a test, not just imported.
- 09:03 P0-19 slice 1 ✓ (verification_ledger: wilson+surgical writes+ledger+summary, 6 l0; egen-QC fångade konvolverad status-logik + skör comma-regex + float-epsilon). Kit UPPE — påbörjar Kit-spåret (P1-09 tier-2 wrapper, sen P1-15-kalibrering).
- 09:05 P1-09 ✓ (tier2_reach_probe, live-smoked CP-70 2/2 REACHABLE). Kit UPPE o fungerar. 2 små Sonnet-slices i luften (X-05-rapport + P0-19-backfill-förslag). Nästa: P1-15-kalibrering (stora Kit-svepet).
- 09:07 P0-19 KOMPLETT ✓ (ledger-modul + 228-backfill; 52-claims korsvaliderade mot P0-07:s 52 verified; ärlig 0-measured-baseline). X-05-rapporten väntas; sen P1-15-kalibreringsdesign.
- 09:31 Post-plan-delta bedömt+infört (X-09/P2-12/P2-13 nya, X-10 BYGGD, fakta-noter, statussync 17 poster). Kalibrerings-svepet kör fortfarande.
- 09:34 X-09 QC-RÄTTAD efter Antons syning: importport=liten (verifierad), full 6.0-uppgradering=BLOCKERAD på cuRobo-kompat + korpus-omvalidering (det glömda skälet, nu protokollfört).
- 09:38 P2-01 ✓ (semantic_usd_diff, usd-core, 5 l0 — toolify-migreringens billiga verifierare). Kalibrering 17/20.
- 09:43 P1-15 första data ✓: UR10 13/13 GRÖNT (recordat); Franka 6/6 fail KARANTÄN (varm-Kit-misstanke, fresh CP-01 kör); SKIP förblir AV (ingen pair klarar tröskeln, n=20).
- 09:45 AVGÖRANDE: CP-01 fresh-Kit PASS → Franka-failsen var degraderings-artefakter (P0-18 friad, karantänen validerad). Kör resterande 5 nära-färskt.
- 09:53 Franka-karantänen STÄNGD: 6/6 pass fresh (CP-58:s legacy-FAIL motbevisad också); CP-02-'static-vinsten' RETRAKTERAD (extraktor-artefakt). 19/19 mätta pass idag. Verktygskarta skriven. Nästa: P0-06-harness m TS-integration.
- 10:04 P0-06 ✓ (nofm_validate: restart+gate+TS per template, smoke CP-70 3/3 w0.438) · P2-02b ✓ (expand-kontraktet) · FULL N-of-M-BATCH IGÅNG (18 templates, ~2.5h, bd22tw07f). Nästa wake: QC batch-interim + P2-02 create_scene_baseline.
- 10:41 P2-02 ✓ (create_scene_baseline i ny scene_body-modul; expand-bar; 4 l0; audit 0 ghosts). N-of-M-batch ~halvvägs, alla pass hittills.
- 11:09 N-of-M-BATCH KLAR: 18/18 leverans, 16/18 trohet (CP-71=P0-18-hål-b live, CP-09 torn). P0-06 DONE. Refinement köad: separera trohets-axeln i ledgern. Nästa: P2-03 asset_ref-toolet.
