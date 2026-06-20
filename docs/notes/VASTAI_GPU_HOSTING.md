# Vast.ai GPU-hosting för Isaac Assist (vs Brev)

**Datum:** 2026-06-16 · **Verifierat denna vecka:** TPU v5e spot körbar på GCP-trial (`spot:true`/READY, ~$0.28–0.35/chip-h, 16 GB HBM, kvot 16 chip, ~$250 krediter), allt via Mullvad · Gemini/Vertex på krediter funkar.

Alla kod-citat nedan är verifierade mot live-kod i denna session (rad-nummer stämmer). De fyra mindre felen som en adversariell granskning hittade (felattribuerat commit-citat, ofullständigt torch_xla-install, oflaggad full-requirements-fälla, gissad obs-dim + sampel-tal) är RÄTTADE i denna revision. Kärnteserna (A100/RT-core-domen, kapabilitet-vs-kostnad-distinktionen) står oförändrade — de var dubbel-belagda och faller inte.

---

## DEL 1 — Vast.ai/A100 för Isaac Assist (vs Brev)

### Rakt svar: A100/H100 DUGER INTE. Köp den BILLIGASTE GPU:n MED RT-cores (T4/L4), inte den kraftigaste compute-GPU:n.

Detta är raka motsatsen till intuitionen "hyr en stark A100". Isaac Assist-setupen är **rendering-bunden, inte compute-bunden**, och rendering kräver RT-cores som A100/H100 saknar i hårdvara — ingen mjukvarufix finns.

**Det avgörande beviset står i er egen molnkod** (`/home/anton/projects/Omniverse_Nemotron_Ext/scripts/cloud/modal_isaac_pool.py:5-8`):

> `Physics runs on CPU (templates set enable_gpu_dynamics=False), the GPU only serves Kit's RTX renderer -> smallest RT-core GPU (T4; switch POOL_GPU=L4 if Kit refuses T4).`

Och defaulten är redan satt till T4, inte A100 (`:33`: `GPU = os.environ.get("POOL_GPU", "T4")`). Templates sätter `enable_gpu_dynamics=False` → **fysiken körs på CPU, GPU:n driver bara Kit:s RTX-renderer**. Renderern är inte valfri: gaten använder viewport-capture/vision (`capture_viewport_png`), så Kit måste boota RTX-renderern.

**NVIDIA:s officiella krav bekräftar:** Isaac Sim listar uttryckligen A100/H100/H20 som EJ stödda — de saknar RT-cores + NVENC som krävs för rendering/streaming. Alla stödda configs är RTX-klass (min RTX 3070, rek RTX 4080). IsaacLab-issue #3421 visar att headless camera-render på A100 hårdkraschar (`createDLSSContext error: unable to initialize context`). RT-cores är **hårdvara** — det finns ingen `--headless`-flagga eller driver-workaround som tillför dem.

**Skilj de två workload-klasserna åt (annars blir man för defensiv åt fel håll):**
- A100 **duger utmärkt** för ren GPU-PHYSICS headless (Isaac Lab/Gym, PhysX-på-GPU, rendering AV — 540K env-steps/s @ 4096 envs är ett verkligt tal). Det är en ANNAN workload.
- A100 **duger INTE** för Isaac Assists Kit-app med RTX-renderern aktiv. A100-physics-talet räddar inte denna setup. Bara om ni NÅGON gång porterar bort Kit-renderern till ren Isaac Lab-physics blir A100/H100 relevant.

### GPU-val på Vast.ai

| GPU | RT-cores | VRAM | Duger för Isaac Assist? | Vast.ai-pris (2026) |
|---|---|---|---|---|
| **T4** | 40 (Turing) | 16 GB | ✅ JA — er Modal-default | ~$0.04–0.29/h |
| **L4** | 3:e-gen Ada | 24 GB | ✅ JA (POOL_GPU=L4-fallback finns redan) | ~$0.31/h |
| RTX 4090 | Ada | 24 GB | ✅ JA (mer RT-kraft, realworld-bekräftad) | ~$0.31–0.40/h |
| RTX A6000 | Ampere RTX | 48 GB | ✅ JA (mest VRAM-headroom) | ~$0.39/h |
| **A100 / H100** | **INGA** | 40/80 GB | ❌ **NEJ — saknar RT-cores** | $0.67 / $0.90/h (bortkastat) |

Eftersom fysiken körs på CPU och GPU:n bara driver renderern räcker **T4 eller L4**. RTX 4090/A6000 ger marginal men behövs inte för gate-körningar. Realworld-bekräftat: användare kör Isaac Sim 4.5/5.x headless i Docker på Vast.ai RTX 4090 ("function quite well", NVIDIA-forum).

### Kostnad vs Brev

**Brev är redan dött för er** — `docs/notes/MODAL_RETURN_PLAN.md:16`: "Brev is OUT (card rejected)". Brev är dessutom uppköpt av NVIDIA. Brev/generisk A100-on-demand ligger ~$1.49–3.43/GPU-h. Vast.ai T4/L4 (~$0.04–0.31/h) är **5–40× billigare per GPU-timme OCH rätt hårdvara** — Brevs A100 var fel hårdvara för rendering från början. En gate-körning är ören per template.

### Korrigering av en ÖVER-OPTIMISM i befintlig plan (ej över-defensivitet)

Repots A100-MIG-plan (`docs/deployment/brev-multi-kit.md` + `scripts/deploy/brev/setup_mig.sh`) ville ha A100/H100 SPECIFIKT för MIG (Multi-Instance GPU) för att köra 3 parallella isolerade Kits. **Den planen kördes ALDRIG och är blockerad.**

> **Citat-disciplin (rättad):** commit `c165df2f` DOKUMENTERAR A100-80GB-MIG×3-planen (brev-multi-kit.md) och VARFÖR den är blockerad — ordagrant ur commit-meddelandet: *"why it's blocked (BREV out, Modal flopping, local multi-Kit 2.4-2.7x slowdown)"*. Frasen "Scripts ready when a rented A100 is available" kommer INTE från den commiten (verifierat med `git show c165df2f`) — häng den inte på commiten. Substansen (blockerad, BREV ute) är korrekt belagd; den ordagranna källan för "scripts ready"-frasen är en separat anteckning, inte commit-body.

Planen vilar dessutom på en otestad, troligen trasig premiss: **MIG finns bara på A100/A30/H100/H200/B200 — som ALLA saknar RT-cores.** Detta är dubbel-belagt i er egen `brev-multi-kit.md`: rad 29 ("MIG is only available on **A100 / A30 / H100 / H200 / B200**") + rad 40 ("Avoid | A10G, L40S, RTX-series | No MIG → CUDA-context contention dominates"). MIG-parallellism och RT-core-rendering är alltså ömsesidigt uteslutande på NVIDIA:s nuvarande utbud. Varje MIG-slice skulle köra en officiellt OSTÖDD config.

**Skrota A100-MIG-vägen för Isaac Assist.** Få parallellism via N separata billiga T4/L4/4090-instanser (en Kit per instans, helt isolerade CUDA-contexts) — speglar exakt er Modal-`single_use_containers=True`-modell (`modal_isaac_pool.py:362`) och kringgår de fyra MIG-motiverande contention-problemen. 3× L4 @ ~$0.31/h = ~$0.93/h totalt, billigare OCH med rätt hårdvara, vs en A100-MIG @ $0.67–1.49/h som inte ens kan rendera.

### Konkret setup-väg på Vast.ai

1. **Återanvänd er Modal-image nästan rakt av.** `modal_isaac_pool.py`-receptet (nvidia/cuda:12.8.1-devel + torch cu128 + isaacsim 5.1.0 pip + warp 1.11 + cuRobo, plus EGL/Vulkan/X-client-libs `:45`, `TORCH_CUDA_ARCH_LIST="7.5;8.9+PTX"` för T4+L4 `:58`) blir en Vast.ai-template (Docker-image + env + portar 8000 FastAPI / 8001+ Kit RPC).
2. **Filtrera värdar:** RT-core-GPU (T4/L4/4090/A6000), CUDA 12.x-driver (helst ≥12.8 — er image är cuda-12.8.1; 13.x-driver kör INTE 12.x-image), `reliability ≥0.95`, verified DC om känsligt (gate-data är det inte).
3. **On-demand, INTE interruptible** för gate-körningar (interruptible kan dödas mitt i av högsta bud).
4. **Ladda UR10-asset-closuren** (47 MB, 60 filer — det enda icke-regenererbara, per MODAL_MIGRATION.md) via provisioning-script/volym.
5. **Smoke FÖRST:** kör `boot_test`-ekvivalenten (`modal_isaac_pool.py::boot_test`: "kit_ok" + vulkaninfo) på EN hyrd T4/L4 innan en batch.
6. **Checkpointa resultat-JSONL kontinuerligt** till extern lagring (samma mönster som Modals `cache_vol.commit()` per template) — Vast.ai har INGEN inbyggd persistens.

### Fallgropar (rakt)

- **Trust/säkerhet:** community-värdar = okänd hårdvara. Filtrera på verified DC + hög reliability. Gate-data är ej känsligt → reliability-score räcker.
- **Efemärt:** ingen persistens; data förloras vid destroy. Disk debiteras även pausad. → checkpointa till extern lagring varje template.
- **Drivrutin/CUDA:** 12.x och 13.x är separata familjer. Pinna 12.x-driver (samma pin ni redan har på Modal).
- **Image-pull/nätverk:** Isaac Sim-imagen är flera GB; er custom-image cachas inte hos värden. Första pull tar tid — välj god bandbredd.
- **Mullvad-netns:** MODAL_RETURN_PLAN.md flaggade "Modal flopping (Mullvad netns)". Om Vast.ai-CLI/SSH/docker-pull körs genom samma netns: **verifiera att API + SSH + registry-pull fungerar genom VPN-netns INNAN ni litar på vägen** — det var blockeraren för Modal denna vecka.

**Caveat (ärlig sista mil):** Kravet RT-cores→T4/L4/4090/A6000 är hårt belagt (NVIDIA-docs + er egen kod). Men er exakta isaacsim 5.1.0 + cuRobo-image x en specifik Vast.ai-host är INTE boot-renderad denna session — det är ett smoke-test bort, inte bevisat här.

---

---
*(TPU-om-reviewn — forna DEL 2–3, gäller sibling-project/sibling-project EJ Isaac Assist (Isaac Assist kör RTX-GPU, aldrig TPU) — flyttad till `/home/anton/projects/TPU_REREVIEW_AND_RUNPLAN.md`.)*
