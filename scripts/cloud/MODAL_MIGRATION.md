# Modal migration — bring `isaac-pool` up on a new account (no setup)

Written 2026-06-13. The old Modal account (antonbj3) ran out of credits;
nothing else changed. This is how to stand the Isaac-Sim GPU pool back up on a
NEW account with zero manual setup beyond auth + one asset upload.

## The bundle
`~/modal_migration_bundle.tgz` (≈20 MB; also unpacked at `~/modal_migration/`):
- `qa_assets/` — the pinned UR10/Isaac asset closure (47 MB, 60 files). The
  ONLY non-regenerable artifact. Re-upload to the new account's volume.
- `modal_isaac_pool.py` — copy of the app (canonical lives here in the repo).
- `ledger_cloud_results.py` — ingest cloud JSONL results into the verdict ledger.
- `upload_qa_assets.py` — SDK fallback uploader (see CLI-bug note below).
- `MODAL_MIGRATION_README.md` — same content as this file.

## What migrates automatically (so you don't re-do it)
- **App `modal.App("isaac-pool")`** and the **image** are defined 100% in code
  in `scripts/cloud/modal_isaac_pool.py` (in git). The image
  (`nvidia/cuda:12.8.1-devel` + torch cu128 + warp 1.11 + cuRobo pinned +
  cuda-bindings + repo dirs `exts/ service/ scripts/qa/ workspace/templates|
  knowledge/ config/curobo/ scripts/cloud/`) **rebuilds itself on the first
  `modal run`** — no manual image setup.
- **Secrets: NONE.** No `modal.Secret` anywhere — nothing to recreate.
- **Volume `isaac-kit-cache`** (`/root/.cache`, `create_if_missing=True`): only
  `/qa_assets` is irreplaceable; `warp/ torch/ mesa_shader_cache/ ov/ qa_export/`
  are regen-on-run cache/output — do not migrate.

## Import (3 steps, run from the repo root)
```bash
# 1. Auth the new account
modal token new

# 2. App + image: nothing to do — first run builds the image (~10-15 min once)
cd ~/projects/Omniverse_Nemotron_Ext            # repo must be present (image pulls local dirs)

# 3. Upload the pinned assets to the volume
modal volume create isaac-kit-cache             # or let create_if_missing handle it
modal volume put isaac-kit-cache ~/modal_migration/qa_assets /qa_assets
#   If that errors (see CLI-bug note), use the SDK fallback instead:
python3 ~/modal_migration/upload_qa_assets.py
```

## Verify
```bash
modal run scripts/cloud/modal_isaac_pool.py::main --templates "CP-01" --skip-ts
```
Expect a gate verdict + `boot_s`. If `/qa_assets` is missing, UR10 templates
fail with `res_None` (the asset-closure path) — that's the only thing the
upload fixes; everything else is baked into the image.

## modal 1.5.0 CLI bug (worked around in this bundle)
`modal volume get <vol> <dir>` throws `[Errno 21] Is a directory` on recursive
directory downloads (that's why `qa_assets` was pulled via the Python SDK).
`modal volume put` of a directory MAY hit the same bug — if it does, the
bundled `upload_qa_assets.py` (SDK `batch_upload(force=True)`) is the fallback.

## Usage reminders (post-migration)
- Sweep: `modal run scripts/cloud/modal_isaac_pool.py::main --templates "a,b,c" --skip-ts`
- Concurrency cap is `max_containers=6` (T4). ~5 min/template, 6 in parallel.
- Ingest results: `python3 scripts/cloud/ledger_cloud_results.py workspace/qa_runs/cloud_results/modal_<stamp>.jsonl`
