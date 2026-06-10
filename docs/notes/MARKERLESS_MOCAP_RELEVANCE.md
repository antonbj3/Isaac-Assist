# Markerless Motion Capture — Relevance to Isaac Assist

**Research question:** Is markerless motion capture (anchored on MAMMA) relevant to Isaac Assist's use case — specifically, can "learn from human video" leapfrog our hardest gaps (EC-1 articulated manipulation, humanoid, dexterous, HRC), or is it a research bet?

**Bottom line:** **WATCH-ITEM with one near-term carve-out.** Markerless mocap is the *research successor* to a primitive we should build now (the synthetic `scripted_demonstrator`), not a substitute for the hand-coded EC-1 controllers. It cannot leapfrog our hardest gap, because that gap is the *measurement* (the absent `articulation_angle` joint-state gate), not the controller — and mocap *consumes* a retarget solver + policy-replay path + faithful articulated physics that don't exist yet.

---

## 1. What is now POSSIBLE — the explainer (anchored on MAMMA)

**MAMMA = Markerless Accurate Multi-person Motion Acquisition** (MPI-IS / Michael J. Black's Perceiving Systems + CMU / Eni Halilaj). **CVPR 2026 oral** (award candidate, ~top 1.75%); arXiv preprint 2506.13040 (June 2025). *Venue note: the task brief dated it CVPR 2025; every primary source says CVPR 2026 — the June-2025 arXiv preprint is the likely source of the "2025" framing.*

**What it does:** multi-camera RGB video in → per-frame, per-person **SMPL-X** out (body pose + shape + **fully articulated hands** + facial expression). It's a deliberate "virtual marker then solve" pipeline that mirrors marker-based mocap with *learned* virtual markers:
- **MammaNet** — transformer dense 2D surface-landmark estimator (ViT-Base + CNN mask branch). Predicts **512 dense surface landmarks** per person, each with pixel coordinate + uncertainty + visibility + contact probability. **Learnable per-landmark queries** (generalize to extreme out-of-distribution poses) and **mask-conditioning** (person-specific correspondence under heavy mutual occlusion).
- **Multi-view matching** — symmetric epipolar distance + Hungarian assignment across views.
- **Optimization** — multi-stage SMPL-X fit: reprojection-error min → pose/shape refine → **contact optimization** (repulsion = no interpenetration, attraction = enforce predicted contacts).
- **MammaSyn** — ~**2.5M synthetic image crops** (single, close-interaction, hand-focused) with SMPL-X + dense landmark GT.

**The headline result — "marker accuracy":**
- Held-out **Vicon** markers (MammaEval-Extra): MAMMA **22.097 mm** vs **Vicon + MoSh++ 20.486 mm** → a **1.611 mm** gap. *Sub-2 mm from a commercial gold standard, without the manual cleanup.*
- **Hi4D** (close two-person): MPJPE **13.43 mm** vs prior SOTA AvatarPose **32.10 mm** (~2.4× better).
- RICH ~22–24 mm; CHI3D 38 mm; Harmony4D 45 mm (in-the-wild close contact).
- **Hands:** ~21.7 mm on RICH — authors candidly flag **"still lower than we would like,"** but note marker systems usually skip hands entirely, so capturing them at all is a net gain.

**Practical requirements:** GT/training rig = **33 cameras** (studio) + 54 Vicon for ground truth — BUT the project page demonstrates the method on **four iPhones** indoor/outdoor, i.e. it degrades gracefully to consumer multi-cam. Needs calibrated + synchronized (TTL/PTP/LTC) views. Compute: **~8 h on one RTX-4090** vs **~72 h** for the marker-based equivalent (~47 h manual cleanup + ~25 h MoSh++) → **~9× faster, near-zero manual labor.**

**What this unlocks that wasn't possible before:** full-body **+ hands** at near-marker accuracy, markerless; contact-rich two-person interaction where markers swap/occlude; ~order-of-magnitude less labor; high-quality capture on a **4-iPhone** rig instead of a $100k+ studio. Separately, monocular world-grounded methods (**WHAM** 57.8 mm 3DPW, **GVHMR**) recover global body trajectory from a single moving phone — a different, lower-accuracy frontier.

*Sources:* MAMMA https://mamma.is.tue.mpg.de/ · https://arxiv.org/abs/2506.13040 · SMPL-X https://smpl-x.is.tue.mpg.de/ · 4D-Humans/HMR2.0 https://shubham-goel.github.io/4dhumans/ · WHAM https://arxiv.org/abs/2312.07531 · GVHMR https://arxiv.org/html/2409.06662v1 · EasyMocap https://github.com/zju3dv/EasyMocap · Hi4D https://ar5iv.labs.arxiv.org/html/2303.15380 · Harmony4D https://arxiv.org/html/2410.20294v1 · BEDLAM 2.0 https://arxiv.org/pdf/2511.14394

---

## 2. The flywheel: video → mocap → retarget → sim-replay (Isaac) → policy

The full chain is real and being assembled, but **no single production system runs all of it end-to-end autonomously** — each link is productized in isolation. Two distinct "video" tracks feed robot learning and must not be conflated:

- **Track A — geometric retargeting:** reconstruct explicit 3D human/hand/object motion → map onto the robot's kinematics → replay/track (in sim, or as RL reward). Used for humanoid whole-body + dexterous-hand manipulation.
- **Track B — representation/policy pretraining:** human video as *weak supervision* (visual features, latent actions, task semantics) inside a large VLA, **without ever reconstructing a skeleton.** Used by GR00T, R3M.

**The retarget step (Track A).** Three method families to map SMPL-X → robot (G1, GR-1, 1X): (1) kinematics-aware IK pipelines (pick ~14 joints, **height-ratio scale** into the reachable workspace, two-stage IK) — the workhorse; (2) a small NN mapping SMPL pose → robot joint vector; (3) **RL-as-retargeting** where the simulator enforces dynamics/contacts so the output is physically *executable*. General Motion Retargeting (GMR, ICRA 2026) runs real-time on CPU across embodiments.

**The embodiment gap is routed around, not solved.** Humans have ~200+ DoF and different proportions/mass/contact geometry than a G1 (29 DoF) or a robot hand. Kinematic retargeting *looks* right but is often **dynamically infeasible** (balance, joint limits, torque, self-collision). The field's honest consensus: **don't copy human joints — extract object-centric / task-level signal from video and let sim-RL own the robot's body.** `Human2Sim2Robot` states it cleanest: from a *single RGB-D human video*, extract (1) object-pose trajectory → embodiment-agnostic reward, (2) pre-manipulation hand pose → RL exploration seed, then cross the gap with **sim-to-real RL** (beats open-loop replay by 55%, IL+aug by 68%).

**Two flywheel variants:**
- **Classic geometric (Track A):** mocap → SMPL → retarget to robot twin → **Isaac Sim/Lab** RL tracking + domain randomization → policy. WPP reports **~10× training speedup** on this exact loop. Dominates **whole-body locomotion / expressive motion** where physics fidelity is good.
- **Generative (the 2025–26 shift, partly *replacing* sim):** NVIDIA **DreamGen / GR00T-Dreams** uses video world models (Cosmos-Predict2) to generate "neural trajectories" (synthetic robot video), then recovers pseudo-actions via latent-action/IDM — went real2real, generating **780K trajectories in 11 h (≈6,500 h of demos)**. Overtaking sim for **contact-rich manipulation** where sim physics is the weak link.

**GR00T's data pyramid (the canonical Track B flywheel):** internet/web video + human egocentric video (broad base, labeled via **LAPA** latent-actions / **IDM**) → Omniverse sim + neural-generated video (middle) → real teleop on GR-1/1X (88 h, narrow grounded peak). It's a VLA dual-system: System 2 = Eagle-2 VLM @ 10 Hz (semantics), System 1 = diffusion transformer @ 120 Hz (motor). **MimicGen / DexMimicGen** amplify few demos → many (DexMimicGen: **60 → 21K** demos) and are the engine behind GR00T-Mimic.

*Sources:* GR00T N1 https://arxiv.org/html/2503.14734v2 · DreamGen https://research.nvidia.com/labs/gear/dreamgen/ · DexMimicGen https://dexmimicgen.github.io/ · Human2Sim2Robot https://human2sim2robot.github.io/ · ArticuBot https://arxiv.org/html/2503.03045v1 · AnyTeleop https://arxiv.org/html/2307.04577v3 · dex-retargeting https://github.com/dexsuite/dex-retargeting · R3M https://arxiv.org/pdf/2203.12601 · OpenVLA https://openvla.github.io/ · GMR https://github.com/YanjieZe/GMR · ASAP https://github.com/LeCAR-Lab/ASAP · CIA https://arxiv.org/pdf/2408.05485 · Gen2Act https://homangab.github.io/gen2act/ · DexMV https://geometry.stanford.edu/struco3d/papers/07.pdf · WPP/Isaac flywheel https://cloud.google.com/blog/products/infrastructure/wpp-humanoid-robots-ai-training · Isaac Lab Mimic https://isaac-sim.github.io/IsaacLab/main/source/overview/imitation-learning/teleop_imitation.html

---

## 3. Relevance to OUR tracks (which would mocap-driven imitation serve?)

| Track | Served? | Evidence |
|---|---|---|
| **Teleop / imitation-learning** | **Directly — its native slot.** The one family whose defining input lives *outside* the process and is never mocked. Markerless mocap is one realization of the missing "external action source" class (EC-14). | `e2e2_teleop-demo.md:130-146`, `E2E_GAP_FINDINGS.md:122-123` |
| **GR00T finetune branch** | **Indirectly — it's the data producer.** finetune/export/redact/data-mix all CONSUME the demo corpus; today they train on no-ops because the corpus is hollow. Mocap demos = one corpus source. | `e2e2_teleop-demo.md:136-138`; `CP-NEW-groot-finetune-n10-demos.json:22,81-83` |
| **Humanoid (G1) — Phase 5** | **Best structural fit.** Mocap → biped/whole-body retarget is the canonical use; plan already carries a WBC emitter (G1/H1 HOVER+Pink-IK). But G1 SimReady is Nucleus-gated; local humanoid is *Onshape CAD parts*, not a drop-in articulation. | `KIMATE_ASSETS_ANALYSIS.md:69-76,285-291`; `MASTER_EXECUTION_PLAN.md:71`; `tool_schemas.py:5700` |
| **3-finger dexterity** | **Partial / aspirational.** Schema references `dex-retargeting` config shape — but it's a YAML *emitter*, no solve. Dex controller itself is research (EC-6). Hand-mocap retarget presupposes a multi-finger controller that doesn't exist. | `_models.py:2218`, `tool_schemas.py:4962`; `E2E_GAP_FINDINGS.md:58-64`; `diagnostics.py:469` |
| **HRC (tracking the human)** | **Adjacent, not the same.** HRC needs a *driven, collidable* human agent (`setup_human_walker` + presence collider), not a learned robot policy. Mocap could *author the walk clip* the catalog lacks (only `Idle`) → a content feeder, not the controller. | `e2e2_hrc-shared-cell.md:27,60,89-90`; `E2E_GAP_FINDINGS.md:106-112` |
| **Service/domestic articulated (EC-1)** | **Possible in principle, weakest in practice** — see §4. | `E2E_GAP_FINDINGS.md:14-25` |

### §4 — Can learning-from-human-video REPLACE hand-coding the EC-1 controllers? **No.**

Not as a near-term alternative; at best a long-horizon complement — and **it does not dissolve the load-bearing gap.** The EC-1 finding is explicit: the highest-ROI missing piece is not the controller but the **measurement** — the `articulation_angle` joint-state success gate, which is *completely absent* (`E2E_GAP_FINDINGS.md:21,132,193`). A learned fridge-opening policy still emits a trajectory that must be *graded* against `joint_path + target_angle + tolerance_deg`, and that gate has to be built either way. Three concrete blockers:

- **The anti-oracle problem is identical.** Whether a controller or a policy "opens" the door, the platform must prove the robot *touched it and moved it by contact*, not that the joint teleported (`E2E_GAP_FINDINGS.md:22,176`). A retargeted policy buys no free pass. *(This is the same lesson the gate work keeps surfacing — delivered/joint-state truth over arm-path mimicry.)*
- **The physics substrate is broken for the target family.** Kimate's Lightwheel fridges carry RevoluteJoints with **no DriveAPI** (free-swinging); 8/9 local fridges have *empty `resource/` dirs* → silent un-articulated stubs (`E2E_GAP_FINDINGS.md:18,94`). A policy cannot learn to drive a passive joint that doesn't physically exist; you still need `verify_articulation` (S-effort) first.
- **EC-1b/EC-1c are three distinct controller sub-classes** (twist-a-knob = pure EE roll; pull-a-drawer = arc/line; nested passive-driven = door→shelf, second arm holds door — `E2E_GAP_FINDINGS.md:16-19`). One human demo covers one of them; generalizing across 243 appliances by imitation is a *research program*, while the per-sub-class hand-coded controllers are M-effort *each* and shippable now.

This matches ArticuBot — the strongest articulated-object result — which deliberately **does not use human video**: it generates **42,300 demos across 322 objects** in sim from PartNet-Mobility and achieves zero-shot real transfer. Human video contributes priors/semantics; the bulk of trainable signal for articulated manipulation comes from **procedurally-generated sim demos.**

---

## 5. What Isaac Assist would need to ADD to consume mocap data

None of this exists today (all grep-confirmed absent — `vision.py` only renders/SAM/CLIP-segments, no human pose; no cv2/mediapipe/smpl/pose-estimation in handlers):

1. **Video/sequence intake + monocular pose estimation** — decode → 3D human/hand keypoints (SMPL / WHAM / HaMeR class).
2. **A real retarget solver** — human/hand keypoints → robot joint trajectory under the robot's kinematics. Today `configure_teleop_mapping` is a **flat label table with no IK** (`e2e2_teleop-demo.md:58,125`); the dex-retarget "tool" only emits a YAML config shape (`_models.py:2218`, `tool_schemas.py:4962`). The 6-DoF→7-joint IK the templates *claim* "does not exist in the handler."
3. **A demo-intake / action-source primitive** — the `scripted_demonstrator`/`teleop_mock` class (EC-14). Mocap = one driver behind it. **Does not exist.**
4. **The HDF5/LeRobot-v2 schema fix** — recorder must write `actions` (the decisive blocker; recorder writes none while both consumers require it — `teleop.py:545` vs `diagnostics.py:5184`).
5. **A policy-replay / inference-loop controller** — to *deploy* a learned policy. `load_rl_policy` is metadata-only with no inference loop (`E2E_GAP_FINDINGS.md:116`); the same EC-13 deployment gap that strands every locomotion policy strands an imitation policy. Plus a `teleop_session_complete` function-gate verifier (none registered).

That's a 5-piece subsystem (intake + pose + retarget + record-schema + replay) — **L-effort, research-flavored**, gated on the same missing gates/assets as everything else.

**Tie to GR00T + the L1/L2/L3 flywheel — and the honest near-term lever:** The GR00T branch is **fully wired but hollow** — `video_demos` is a **bare integer** fed to a ratio-recommender (`suggest_data_mix` caps it at ¼ of real, `training.py:3763`); there is *no video decode, no pose-estimation, no retarget* anywhere. So "video demos" today is a **planning placeholder, not a pipeline.** The flywheel the plan wants (`MASTER_EXECUTION_PLAN.md:81`) prescribes a *synthetic* first fill: the **`scripted_demonstrator`** reuses the existing pick-place controller as the "expert" and records its joint targets AS `actions` (`e2e2_teleop-demo.md:141-144`). That converts the whole GR00T branch from "trains on no-ops" to "trains on synthetic-expert demos" — hardware-free, M-effort. **Mocap is the higher-fidelity, much-more-expensive successor to that same socket** — build the synthetic source first; it de-risks the schema + gate, and a mocap intake later writes into the *identical* `actions`/LeRobot-v2 slot.

---

## 6. Honest maturity verdict

| Capability | Maturity |
|---|---|
| Markerless video → SMPL/SMPL-X (WHAM/TRAM/MAMMA) | **Mature / near-production** (reliable enough to auto-build retargeted datasets) |
| Hand retarget for **teleop** (AnyTeleop, dex-retargeting) | **Production-adjacent** — but human-in-the-loop teleop, *not* autonomous learning-from-video |
| MimicGen/DexMimicGen demo amplification | **Productized** inside Isaac (GR00T-Mimic) where a sim of the task exists |
| Humanoid whole-body retarget → Isaac RL | **Late research / early production** (G1/GR-1/1X walk from this; still per-deployment engineering) |
| GR00T-style VLA on human+sim+internet video | **Research foundation model, openly released** — short-horizon tabletop by NVIDIA's own admission |
| Human-video → autonomous articulated/dexterous policy | **Research.** The *winning* articulated result (ArticuBot) leans on **sim demos, not human video** |
| Generative neural-trajectory flywheel (DreamGen) | **Cutting-edge research, just open-sourced** — physics-faithfulness of generated video is an explicit open problem |

**Recommendation — WATCH-ITEM with one near-term carve-out:**
- **Near-term lever (do now, NOT mocap):** the synthetic **`scripted_demonstrator`/`teleop_mock`** primitive (EC-14, M-effort) + the `actions`-schema fix. It unblocks the *whole* GR00T/imitation branch honestly and hardware-free, and builds the exact `actions`/LeRobot socket a future mocap intake would write into.
- **Research bet (defer):** true markerless-mocap → retarget → policy. Natural successor for the **humanoid (G1)** rung and the long-tail of EC-1 appliances — but presupposes (a) a retarget solver + IK that don't exist, (b) a policy-replay controller that doesn't exist (EC-13), (c) faithful articulated physics + the `articulation_angle` gate (EC-1, the actual blocker), (d) Nucleus-gated G1 assets. **Mocap consumes all of these — it cannot leapfrog the hand-coded EC-1 controllers.**
- **Why not zero:** the conceptual slots are already *named* in the codebase (`video_demos`, dex-retarget config, GR00T finetune, the `Worker` actor, the kitchen-teleop scene) and the master plan lists "teleop→imitation-learning" as a Phase-5 new family. The seams exist — which is why it's a *watch-item*, not out-of-scope — but every slot is hollow today, so it's not a lever.

**Sequencing:** EC-1 controller-trio + joint-state gate + `verify_articulation` → `scripted_demonstrator` (synthetic) + `actions`-schema fix → (only then, as a research track) mocap intake + retarget solver + policy-replay, riding on the G1 humanoid rung.

**Key files:** `docs/notes/e2e2_teleop-demo.md` (EC-14, decisive evidence) · `docs/notes/E2E_GAP_FINDINGS.md:14-25,58-64,106-123` (EC-1/EC-6/EC-12/EC-14) · `service/isaac_assist_service/chat/tools/handlers/training.py:3726-3787` (hollow `video_demos`) · `service/isaac_assist_service/chat/tools/handlers/teleop.py:545` + `diagnostics.py:5184` (schema split) · `workspace/templates/CP-NEW-groot-finetune-n10-demos.json:22,81-83` (demo corpus = absent offline asset).
