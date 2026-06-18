#!/usr/bin/env python3
"""Modal cloud pool — serverless Kit workers for template gate measurement.

Each container = ONE Kit (single-tenant RPC on :8001, same as local).
Physics runs on CPU (templates set enable_gpu_dynamics=False), the GPU only
serves Kit's RTX renderer -> smallest RT-core GPU (T4; switch POOL_GPU=L4 if
Kit refuses T4). Serverless: containers scale to zero when idle, billed per
second — nothing to switch off manually.

Layout mirrors the local machine: the repo is baked at the SAME absolute path
so gate_one.py's hardcoded REPO and template paths work unchanged.

Usage:
    modal run scripts/cloud/modal_isaac_pool.py::boot_test          # smoke: Kit boots?
    modal run scripts/cloud/modal_isaac_pool.py --templates CP-45,CP-49
Results land in workspace/qa_runs/cloud_results/ as JSONL (ledger them
locally with the existing record_gate_run — the ledger stays local-only).
"""
import json
import os
import re
import time
from pathlib import Path

import modal

try:
    REPO_LOCAL = Path(__file__).resolve().parents[2]
except IndexError:  # in-container: __file__ sits near /, only the local
    REPO_LOCAL = Path("/root")  # entrypoint + image build use this path

REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"  # same path in-container
GPU = os.environ.get("POOL_GPU", "T4")
CUROBO_COMMIT = "ca941586c33b8482ed9c0e74d60f23efd64b516a"  # == local install

app = modal.App("isaac-pool")

cache_vol = modal.Volume.from_name("isaac-kit-cache", create_if_missing=True)

image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04",
                              add_python="3.11")
    .apt_install(
        "git", "curl", "ninja-build",
        # Kit headless runtime libs (RTX renderer needs EGL/Vulkan + X client libs)
        "libatomic1", "libegl1", "libgl1", "libglu1-mesa", "libgomp1",
        "libsm6", "libice6", "libxi6", "libxrandr2", "libxt6", "libxext6",
        "libxcursor1", "libxinerama1", "libxxf86vm1", "libx11-6",
        "libfreetype6", "libfontconfig1", "libglib2.0-0", "libxkbcommon0",
        "libvulkan1", "vulkan-tools",
    )
    .env({
        "OMNI_KIT_ACCEPT_EULA": "YES",
        "OMNI_KIT_ALLOW_ROOT": "1",
        "ACCEPT_EULA": "Y",
        "PRIVACY_CONSENT": "Y",
        "NVIDIA_DRIVER_CAPABILITIES": "all",   # vulkan/EGL injection, not just compute
        "TORCH_CUDA_ARCH_LIST": "7.5;8.9+PTX",  # T4 + L4
    })
    .pip_install("torch==2.7.0", index_url="https://download.pytorch.org/whl/cu128")
    .pip_install(
        "isaacsim==5.1.0.0",
        "isaacsim-extscache-kit==5.1.0.0",
        "isaacsim-extscache-kit-sdk==5.1.0.0",
        "isaacsim-extscache-physics==5.1.0.0",
    )
    .pip_install("warp-lang==1.11.0", "aiohttp", "pandas", "requests",
                 "pyyaml", "ninja", "packaging", "wheel")
    # cuRobo: same commit as local; compiles CUDA kernels (nvcc from devel base)
    .run_commands(
        "pip install --no-build-isolation "
        f"git+https://github.com/NVlabs/curobo.git@{CUROBO_COMMIT}",
        # curobo deps bump numpy/websockets/scipy past isaacsim-kernel's pins;
        # restore the locally-proven versions or Kit breaks on numpy 2.x ABI.
        # pandas reinstalled HERE: the earlier layer built it against numpy
        # 2.x, and downgrading numpy under it breaks the C ABI at import.
        "pip install --force-reinstall numpy==1.26.0 websockets==12.0 "
        "scipy==1.15.3 pandas==2.3.3",
        # the pip wheel drops curobo/content (robot configs, collision yml) —
        # without franka.yml setup_pick_place_controller dies and no
        # controller ever runs (cloud-RCA 2026-06-11)
        "mkdir /tmp/curobo_src && cd /tmp/curobo_src && git init -q && "
        "git remote add origin https://github.com/NVlabs/curobo.git && "
        f"git fetch -q --depth 1 origin {CUROBO_COMMIT} && "
        "git checkout -q FETCH_HEAD && "
        "cp -r curobo/content "
        "/usr/local/lib/python3.11/site-packages/curobo/ && "
        "cd / && rm -rf /tmp/curobo_src && "
        "ls /usr/local/lib/python3.11/site-packages/curobo/content/configs/robot/franka.yml",
    )
    # Warp symlink chain (local-proven): Kit's bundled omni.warp.core 1.8.2
    # must resolve to site-packages warp 1.11.0 or cuRobo collision kernels
    # fail (CuboidDataWarp undefined). Hardcoded path: importing isaacsim in
    # a $() prints banner text that corrupts the variable.
    .run_commands(
        "SP=/usr/local/lib/python3.11/site-packages/isaacsim && "
        "ln -sfn /usr/local/lib/python3.11/site-packages/warp $SP/warp && "
        "found=0; for d in $SP/extscache/omni.warp.core-*/; do "
        '[ -d "$d" ] || continue; found=1; '
        "rm -rf ${d}warp && ln -s ../../warp ${d}warp; done; "
        "ls -la $SP/warp && echo extscache_warp_found=$found"
    )
    # warp 1.11's cuda.core backend imports `cuda` — cuRobo's MotionPlanner
    # dies without it ("No module named 'cuda'", cloud-RCA 2026-06-11).
    # Locally-proven versions; own layer to keep the curobo layer cached.
    .run_commands("pip install cuda-bindings==12.9.6 cuda-core==0.7.0 "
                  "cuda-pathfinder==1.5.3")
    # Repo subsets, baked last (cheap re-upload on change)
    .add_local_dir(str(REPO_LOCAL / "exts"), f"{REPO}/exts")
    .add_local_dir(str(REPO_LOCAL / "service"), f"{REPO}/service")
    .add_local_dir(str(REPO_LOCAL / "scripts" / "qa"), f"{REPO}/scripts/qa")
    .add_local_dir(str(REPO_LOCAL / "workspace" / "templates"),
                   f"{REPO}/workspace/templates")
    .add_local_dir(str(REPO_LOCAL / "workspace" / "knowledge"),
                   f"{REPO}/workspace/knowledge")
    .add_local_dir(str(REPO_LOCAL / "config" / "curobo"),
                   f"{REPO}/config/curobo")
    .add_local_dir(str(REPO_LOCAL / "scripts" / "cloud"),
                   f"{REPO}/scripts/cloud")
)

BOOT_PY = f'''
import os, sys
import isaacsim as _isaacsim
base = os.path.dirname(_isaacsim.__file__)
sys.path.append(os.path.join(base, "kit"))
from kit_app import KitApp
app = KitApp()
app.startup([
    os.path.join(base, "apps", "isaacsim.exp.base.kit"),
    "--ext-folder", "{REPO}/exts/isaac_5.1",
    "--enable", "omni.isaac.assist",
    "--headless", "--no-window",
])
while app.is_running():
    app.update()
app.shutdown()
'''

_VOLUMES = {"/root/.cache": cache_vol}


def _stage_custom_curobo() -> str:
    """Install repo-versioned custom cuRobo robot configs (ur10_scene.yml)
    into the container's curobo content, rewriting the local-machine
    asset_root_path to wherever the motion_generation ext data lives here.
    Call AFTER Kit boot: the ext is registry-downloaded at runtime, not
    part of the pip extscache. Returns the resolved path for telemetry."""
    import glob as _glob

    src_dir = Path(f"{REPO}/config/curobo")
    dst_dir = Path("/usr/local/lib/python3.11/site-packages/curobo/content/"
                   "configs/robot")
    if not src_dir.is_dir() or not dst_dir.is_dir():
        return "no-src-or-dst"
    hits: list[str] = []
    # registry roots FIRST (Kit's runtime-downloaded ext beats the pip
    # extscache copy when both exist — audit MED-8a), newest version wins
    for root in (
        "/root/.local/share/ov/data/exts/v3",
        "/root/.local/share/ov/data/exts/v2",
        "/usr/local/lib/python3.11/site-packages/isaacsim/extscache",
    ):
        hits += sorted(
            _glob.glob(f"{root}/isaacsim.robot_motion.motion_generation-*/"
                       "motion_policy_configs/universal_robots/ur10"),
            reverse=True)
    if not hits:
        # audit MED-8b: copying ymls with the local machine's absolute
        # paths intact installs guaranteed-broken configs — skip instead
        return "NO-MOTION-GEN-DATA-FOUND (configs NOT staged)"
    for yml in src_dir.glob("*.yml"):
        text = yml.read_text()
        if hits:
            # rewrite EVERY absolute reference to the ext data root
            # (asset_root_path AND urdf_path — missing urdf_path was the
            # second CP-70 cloud iteration)
            text = re.sub(r"/\S*?motion_policy_configs/universal_robots/ur10",
                          hits[0], text)
        (dst_dir / yml.name).write_text(text)
    return hits[0] if hits else "NO-MOTION-GEN-DATA-FOUND"


def _boot_kit(timeout_s: int = 600):
    """Start Kit, wait for RPC health + a real exec. Returns (proc, boot_s)."""
    import subprocess

    # STALE-KIT GUARD (cloud CP-28, 2026-06-11): if a reused container's
    # previous Kit survived terminate(), the health probe answers within
    # seconds and the gate runs against the OLD session. Kill leftover Kit
    # processes and wait until :8001 is actually silent before booting.
    out = subprocess.run(["pgrep", "-f", "boot_kit[.]py"],
                         capture_output=True, text=True).stdout
    for pid in out.split():
        subprocess.run(["kill", "-9", pid], check=False)
    for _ in range(10):
        probe = subprocess.run(["curl", "-s", "-m", "2",
                                "http://127.0.0.1:8001/health"],
                               capture_output=True, text=True).stdout
        if not probe:
            break
        time.sleep(2)
    else:
        # audit HIGH-1: falling through here would let the OLD session
        # answer the new gate's RPC — a silently-wrong verdict
        raise RuntimeError("port 8001 still answering after stale-kill")

    Path("/tmp/boot_kit.py").write_text(BOOT_PY)
    log = open("/tmp/kit.log", "w")
    proc = subprocess.Popen([sys_exe(), "/tmp/boot_kit.py"],
                            stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        time.sleep(6)
        if proc.poll() is not None:
            raise RuntimeError("Kit died during boot:\n" + _kit_log_tail())
        try:
            r = subprocess.run(
                ["curl", "-s", "-m", "30", "-X", "POST",
                 "http://127.0.0.1:8001/exec_sync",
                 "-H", "Content-Type: application/json",
                 "-d", '{"code": "import omni.usd\\nprint(omni.usd.get_context()'
                       '.get_stage() is not None)"}'],
                capture_output=True, text=True, timeout=40).stdout
            if '"success": true' in r:
                return proc, round(time.time() - t0, 1)
        except Exception:
            pass
    raise RuntimeError(f"Kit not healthy within {timeout_s}s:\n" + _kit_log_tail())


def _kill_kit(proc) -> None:
    """Reap the WHOLE Kit tree: start_new_session=True makes pgid==pid, so
    killpg catches shader workers etc. that plain kill() orphans (audit
    HIGH-3 — orphans fed the stale-Kit class on container reuse)."""
    import os as _os
    import signal as _sig

    try:
        _os.killpg(proc.pid, _sig.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
    try:
        proc.wait(timeout=10)
    except Exception:  # noqa: BLE001
        pass


def sys_exe() -> str:
    import sys
    return sys.executable


def _kit_log_tail(n: int = 4000) -> str:
    try:
        return Path("/tmp/kit.log").read_text()[-n:]
    except Exception:
        return "<no kit.log>"


@app.function(image=image, gpu=GPU, cpu=6.0, memory=12288, timeout=2700,
              volumes=_VOLUMES)
def build_probe(template_id: str) -> dict:
    """Build the canonical and report per-call honesty: n_ok/n_calls, errors,
    capture_warnings — catches a silently-failing controller-setup call."""
    import subprocess

    for d in ("/home/anton/.isaac_qa/run", "/root/.isaac_qa/run"):
        Path(d).mkdir(parents=True, exist_ok=True)
    res: dict = {"template": template_id}
    try:
        proc, res["boot_s"] = _boot_kit()
    except Exception as e:  # noqa: BLE001
        res["error"] = "boot: " + str(e)[-4000:]
        return res
    res["curobo_stage"] = _stage_custom_curobo()
    probe_py = f'''
import asyncio, json, sys
sys.path.insert(0, "{REPO}")
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.canonical_instantiator import (
    execute_template_canonical)
async def m():
    await kit_tools.exec_sync("import omni.usd\\nomni.usd.get_context().new_stage()\\n", timeout=20)
    tpl = json.load(open("{REPO}/workspace/templates/{template_id}.json"))
    b = await execute_template_canonical(tpl)
    keep = {{k: b.get(k) for k in ("n_ok", "n_calls", "errors",
                                   "capture_warnings", "instantiated")}}
    calls = b.get("calls") or b.get("call_results") or []
    keep["per_call"] = [
        {{"tool": c.get("tool") or c.get("name"),
          "ok": c.get("success", c.get("ok")),
          "err": str(c.get("error") or "")[:300]}}
        for c in calls if isinstance(c, dict)]
    print("BUILD_JSON=" + json.dumps(keep, default=str))
asyncio.run(m())
'''
    Path("/tmp/build_probe.py").write_text(probe_py)
    try:
        p = subprocess.run([sys_exe(), "/tmp/build_probe.py"],
                           capture_output=True, text=True, timeout=1200)
        out = p.stdout + p.stderr
        m = re.search(r"BUILD_JSON=(.*)", out)
        res["build"] = m.group(1)[:8000] if m else out[-3000:]
    except Exception as e:  # noqa: BLE001
        res["build"] = f"probe-error: {e}"
    finally:
        _kill_kit(proc)
        cache_vol.commit()
    return res


@app.local_entrypoint()
def buildprobe(template: str = "CP-45"):
    print("BUILD_PROBE_RESULT:")
    print(json.dumps(build_probe.remote(template), indent=1)[:9000])


@app.function(image=image, gpu=GPU, cpu=6.0, memory=12288, timeout=1500,
              volumes=_VOLUMES)
def boot_test() -> dict:
    """Milestone 1: does Kit boot + answer RPC in this runtime at all?"""
    import subprocess

    try:
        vk = subprocess.run(["vulkaninfo", "--summary"], capture_output=True,
                            text=True, timeout=60)
    except Exception:  # noqa: BLE001
        import subprocess as _sp
        vk = _sp.CompletedProcess([], 1, stdout="", stderr="vulkaninfo hung/failed")
    vk_out = (vk.stdout + vk.stderr)[-1500:]
    drv = subprocess.run(
        ["bash", "-c",
         "nvidia-smi -L; echo ---; ls /usr/share/vulkan/icd.d/ 2>&1; "
         "ls /usr/lib/x86_64-linux-gnu/ | grep -i nvidia | head -20"],
        capture_output=True, text=True)
    drv_out = (drv.stdout + drv.stderr)[-1200:]
    try:
        proc, boot_s = _boot_kit()
        _kill_kit(proc)
        ok = True
        err = ""
    except Exception as e:  # noqa: BLE001
        ok, boot_s, err = False, -1.0, str(e)[-6000:]
    cache_vol.commit()
    return {"kit_ok": ok, "boot_s": boot_s, "vulkan": vk_out,
            "driver": drv_out, "error": err}


_BAD_STATES = {"FLUNG", "ON_FLOOR", "TOPPLED", "MISROUTED", "ALOFT",
               "NOT_SEATED", "UNROUTABLE_NO_BIN", "OFF_TARGET", "IN_FLIGHT",
               "UNSETTLED"}
_ITEM_RE = re.compile(r"^\s{2}(\w[\w/]*): bin=.*\|\s*([A-Z_,]+|OK)\s*\|\s*final=",
                      re.M)


@app.function(image=image, gpu=GPU, cpu=6.0, memory=12288, timeout=3600,
              volumes=_VOLUMES, max_containers=6, single_use_containers=True)
# single_use_containers=True (2026-06-14; was max_inputs=1, now deprecated by Modal):
# retire each container after ONE template so every
# run gets a FRESH cold Kit. A reused/warm container re-boots a DEGRADED Kit
# (boot~18s vs ~190s cold) that fails picks spuriously regardless of template —
# a 100%-confounded false-NEG class in the 12-tpl parity batch (all fails were
# warm-reuse, boot<25s; all passes were fresh, boot~190s). The Modal analog of
# the local "restart-before-every-measurement" rule. See memory parity_11.
def run_template(template_id: str, skip_ts: bool = False,
                 env_flags: dict | None = None, eyes: bool = False) -> dict:
    """Fresh-Kit single-template measurement: gate_one + scene_timeseries (+ scene_eyes if eyes).

    Fresh-Kit-per-template is free here: every call gets a new container,
    so the local session-degradation class is structurally impossible.
    """
    import subprocess

    res: dict = {"template": template_id}
    try:
        import torch as _t
        res["gpu"] = _t.cuda.get_device_name(0) if _t.cuda.is_available() else "none"
    except Exception:  # noqa: BLE001
        res["gpu"] = "unknown"
    for d in ("/home/anton/.isaac_qa/run", "/root/.isaac_qa/run"):
        Path(d).mkdir(parents=True, exist_ok=True)
    try:
        import torch
        res["cuda"] = (f"avail={torch.cuda.is_available()} "
                       f"dev={torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-'} "
                       f"cap={torch.cuda.get_device_capability(0) if torch.cuda.is_available() else '-'}")
    except Exception as e:  # noqa: BLE001
        res["cuda"] = f"probe-failed: {e}"
    try:
        proc, boot_s = _boot_kit()
        res["boot_s"] = boot_s
    except Exception as e:  # noqa: BLE001
        res.update(gate=None, error="boot: " + str(e)[-6000:])
        return res
    res["curobo_stage"] = _stage_custom_curobo()

    try:
        kp = subprocess.run(
            ["curl", "-s", "-m", "120", "-X", "POST",
             "http://127.0.0.1:8001/exec_sync",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"code":
                 "import torch\n"
                 "print('KITCUDA avail=%s n=%s' % (torch.cuda.is_available(),"
                 " torch.cuda.device_count()))\n"})],
            capture_output=True, text=True, timeout=130)
        res["kit_cuda"] = kp.stdout[-400:]

        genv = {**os.environ, **(env_flags or {})}
        # pinned-asset root (UR10 revision parity, 2026-06-12): the volume
        # carries the exact local UR10 closure; other robots fall back to
        # the Isaac asset root via import_robot's portable fallback
        genv.setdefault("ASSETS_ROOT_PATH", "/root/.cache/qa_assets")
        genv.setdefault("ASSETS_ROBOTS_SUBDIR", "Collected_Robots")
        p = subprocess.run([sys_exe(), f"{REPO}/scripts/qa/gate_one.py",
                            template_id], capture_output=True, text=True,
                           timeout=1500, env=genv)
        out = p.stdout + p.stderr
        res["gate_out_head"] = out[:3000]
        if env_flags:
            res["env_flags"] = env_flags
        m = re.search(r"GATE success=(\w+)", out)
        res["gate"] = (m.group(1) == "True") if m else None
        mf = re.search(r"GATE_FULL=(.*)", out)
        if mf:
            res["gate_full"] = mf.group(1)[:4000]
        if res["gate"] is not True:
            # cloud-vs-local delta debugging: surface the controller story
            res["gate_out_tail"] = out[-3000:]
            res["kit_log_tail"] = _kit_log_tail(5000)
            kit_log = _kit_log_tail(400_000)
            marks = [ln for ln in kit_log.splitlines()
                     if re.search(r"curobo|plan_fail|cp_planfail|Traceback|"
                                  r"CUDA error|warp", ln, re.I)]
            res["kit_log_marks"] = marks[-40:]
            # post-run pick localizer: reads the always-on ctrl:* timeline
            # off the robot prim while the gate run's stage is still live
            tpl = json.load(open(f"{REPO}/workspace/templates/{template_id}.json"))
            rp = ((tpl.get("verify_args") or {}).get("robot_path")
                  or (tpl.get("simulate_args") or {}).get("robot_path"))
            if not rp:
                mrp = re.search(r'robot_path="([^"]+)"', tpl.get("code", "") or "")
                rp = mrp.group(1) if mrp else None
            census = subprocess.run(
                ["curl", "-s", "-m", "60", "-X", "POST",
                 "http://127.0.0.1:8001/exec_sync",
                 "-H", "Content-Type: application/json",
                 "-d", json.dumps({"code":
                     "import omni.usd\n"
                     "st = omni.usd.get_context().get_stage()\n"
                     "kids = [p.GetName() for p in st.GetPrimAtPath('/World')"
                     ".GetChildren()]\n"
                     "rb = st.GetPrimAtPath('" + (rp or "/World/Franka") + "')\n"
                     "n_desc = sum(1 for _ in iter(st.Traverse())) \n"
                     "print('CENSUS kids=%s robot_valid=%s n_prims=%s'"
                     " % (kids, bool(rb and rb.IsValid()), n_desc))\n"})],
                capture_output=True, text=True, timeout=70)
            res["scene_census"] = census.stdout[-1500:]
            if rp:
                diag_py = (
                    f'import asyncio, json, sys\n'
                    f'sys.path.insert(0, "{REPO}")\n'
                    f'from service.isaac_assist_service.chat.tools.tool_executor '
                    f'import execute_tool_call\n'
                    f'r = asyncio.run(execute_tool_call('
                    f'"diagnose_pick_execution", {{"robot_path": "{rp}"}}))\n'
                    f'print("DIAG_JSON=" + json.dumps(r, default=str))\n'
                )
                Path("/tmp/diag.py").write_text(diag_py)
                pd = subprocess.run([sys_exe(), "/tmp/diag.py"],
                                    capture_output=True, text=True, timeout=300)
                md = re.search(r"DIAG_JSON=(.*)", pd.stdout + pd.stderr)
                res["diagnose"] = (md.group(1)[:5000] if md
                                   else (pd.stdout + pd.stderr)[-1200:])

        if not skip_ts:
            p2 = subprocess.run([sys_exe(),
                                 f"{REPO}/scripts/qa/scene_timeseries.py",
                                 template_id], capture_output=True, text=True,
                                timeout=900)
            out2 = p2.stdout + p2.stderr
            vec = {mm.group(1): mm.group(2) for mm in _ITEM_RE.finditer(out2)}
            if vec:
                res["ts"] = not any(s in _BAD_STATES for st in vec.values()
                                    for s in st.split(","))
                res["vec"] = vec
            else:
                res["ts"] = None
                res["ts_tail"] = out2[-3000:]

        if eyes:
            # VIRTUAL EYES on cloud (Anton 2026-06-14: gates lie -> never trust
            # delivered-counts alone). scene_eyes captures CONTACTS + EJECTION +
            # GRIP-SLIP + per-object trajectory, so a cloud false-pass (e.g. a
            # SKU-sort that reaches the pallet UNION but the WRONG zone, or a
            # flung box) is visible cloud-side, not just locally.
            try:
                _etpl = json.load(open(f"{REPO}/workspace/templates/{template_id}.json"))
                _edur = int((_etpl.get("simulate_args") or {}).get("duration_s") or 120)
            except Exception:
                _edur = 120
            pe = subprocess.run([sys_exe(),
                                 f"{REPO}/scripts/qa/scene_eyes.py",
                                 template_id, str(_edur), "--noframes"],
                                capture_output=True, text=True,
                                timeout=_edur + 600, env=genv)
            # cont.306: a BLIND [-4800:] tail captured cuRobo PLANNER spam (plan#/seed_cost), burying the
            # scene_eyes VERDICT (CONVERG/GRIP-SLIP/SETTLED-Z/STACK/EJECT/TOPPLED/BELT). Extract the verdict
            # LINES (mirrors the local grep) so the cloud breadth signal is actually usable, not planner noise.
            _keep = ("EYES_DONE", "CONTACTS", "GRIP-SLIP", "RIGID HOLD", "GRIP CONTACT", "EJECTION", "EXPLOSION",
                     "OFF-SURFACE", "OBJECT-OBJECT", "STACK STRUCTURE", "SETTLED-Z", "ORIENTATION FAIL",
                     "TOPPLED", "TILTED", "BELT", "PICK CONVERGENCE", "CONVERGED", "NEAR-MISS", "THRASH", "-> ")
            _drop = ("cuRobo RESULT", "dir(res)", "plan#", "seed_cost", "seed_rank", "debug_info", "per-joint",
                     "object orientation relative")
            _vl = [l for l in (pe.stdout + "\n" + pe.stderr).splitlines()
                   if any(w in l for w in _keep) and not any(w in l for w in _drop)]
            res["eyes_summary"] = "\n".join(_vl)[-4800:]
            res["eyes_tail"] = (pe.stdout + pe.stderr)[-1200:]   # small raw tail for debugging
    except Exception as e:  # noqa: BLE001
        res["error"] = str(e)[-3000:]
    finally:
        _kill_kit(proc)
        cache_vol.commit()
    return res


@app.function(image=image, gpu=GPU, cpu=6.0, memory=12288, timeout=5400,
              volumes=_VOLUMES, max_containers=6, single_use_containers=True)
def run_composition(cells: str, dur: int = 180) -> dict:
    """Fresh-Kit COMPOSITION measurement on cloud (the 6x speedup lever, 2026-06-16): mirrors local
    run_eyes_gold.sh — restart Kit before EACH instance (measurement integrity), run scene_eyes --compose
    per focus, then eyes_gold_gate. cells = comma-separated template ids, e.g. 'CP-13,CP-08'. Each container
    does ONE composition; the pool runs up to 6 in PARALLEL -> ~6x the local serial gold pipeline + frees the
    local Kit. The container's local edits (#40b composer fix etc.) are copied via add_local_dir."""
    import subprocess
    import os
    import re as _re

    names = [c.strip() for c in cells.split(",") if c.strip()]
    res: dict = {"cells": names}
    try:
        import sys as _sys
        _sys.path.insert(0, REPO)
        from service.isaac_assist_service.chat.composer import compute_layout_offsets
        tpls = [json.load(open(f"{REPO}/workspace/templates/{n}.json")) for n in names]
        offs = compute_layout_offsets(tpls, axis="x")
        spec = [f"{n}@{o['offset'][0]},0,0" for n, o in zip(names, offs)]
        res["spec"] = " ".join(spec)
    except Exception as e:  # noqa: BLE001
        res["error"] = "layout: " + str(e)[-1500:]
        return res
    genv = {**os.environ}
    genv.setdefault("ASSETS_ROOT_PATH", "/root/.cache/qa_assets")
    genv.setdefault("ASSETS_ROBOTS_SUBDIR", "Collected_Robots")
    genv["EYES_DUR"] = str(dur)
    inst_files = []
    try:
        for i, n in enumerate(names):
            proc, boot_s = _boot_kit()
            try:
                ev = {**genv, "EYES_FOCUS": f"inst{i}"}
                pe = subprocess.run([sys_exe(), f"{REPO}/scripts/qa/scene_eyes.py",
                                     "--compose", *spec, "--noframes"],
                                    capture_output=True, text=True,
                                    timeout=dur + 600, env=ev)
                fpath = f"/tmp/comp_inst{i}.txt"
                with open(fpath, "w") as _fh:
                    _fh.write(pe.stdout + pe.stderr)
                inst_files.append((n, fpath))
            finally:
                _kill_kit(proc)
        args = [f"{n}:{fp}" for n, fp in inst_files]
        gp = subprocess.run([sys_exe(), f"{REPO}/scripts/qa/eyes_gold_gate.py",
                             "--expect", str(len(names)), *args],
                            capture_output=True, text=True, timeout=180)
        out = gp.stdout + gp.stderr
        res["gold"] = "EYES_GOLD_VERDICT: GOLD" in out
        res["per_cell"] = [ln.strip() for ln in out.splitlines()
                           if "GENUINE" in ln or "REJECT" in ln]
        res["structure"] = _re.findall(r"STACK STRUCTURE \([^\n]*", "\n".join(
            open(fp).read() for _, fp in inst_files))[:20]
        res["gate_tail"] = out[-2000:]
    except Exception as e:  # noqa: BLE001
        res["error"] = str(e)[-3000:]
    cache_vol.commit()
    return res


@app.local_entrypoint()
def compose(comps: str = "", dur: int = 180):
    """Run COMPOSITIONS in parallel on Modal (6x the local gold pipeline). comps = semicolon-separated
    compositions, each comma-separated cells. e.g.:
      modal run scripts/cloud/modal_isaac_pool.py::compose --comps 'CP-13,CP-08; CP-03,CP-08; CP-10,CP-13'
    """
    if not comps:
        print("usage: ...::compose --comps 'CP-13,CP-08; CP-03,CP-08'")
        return
    items = [c.strip() for c in comps.split(";") if c.strip()]
    outdir = REPO_LOCAL / "workspace" / "qa_runs" / "cloud_results"
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / "modal_compose.jsonl"
    n = 0
    with open(outfile, "a") as fh:
        for res in run_composition.map(items, kwargs={"dur": dur},
                                       order_outputs=False, return_exceptions=True):
            if isinstance(res, BaseException):
                print("MAP-EXC:", repr(res)[:300])
                continue
            n += 1
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"[{n}/{len(items)}] {'+'.join(res.get('cells', []))}: "
                  f"gold={res.get('gold')} | {res.get('per_cell')} "
                  f"{('ERR ' + res['error'][:250]) if res.get('error') else ''}", flush=True)
    print(f"results -> {outfile}")


@app.function(image=image, gpu=GPU, cpu=6.0, memory=12288, timeout=1500,
              volumes=_VOLUMES)
def curobo_fingerprint() -> str:
    """UR10-divergence RCA: fingerprint the STAGED ur10_scene model so it
    can be md5-compared against the local machine's (sphere set + urdf)."""
    import hashlib
    import subprocess

    import yaml

    proc, boot_s = _boot_kit()
    staged = _stage_custom_curobo()
    out = [f"boot={boot_s}s staged={staged}"]
    cfg = ("/usr/local/lib/python3.11/site-packages/curobo/content/"
           "configs/robot/ur10_scene.yml")
    try:
        d = yaml.safe_load(open(cfg))
        kin = d["robot_cfg"]["kinematics"]
        sph = kin.get("collision_spheres") or {}
        vals = sph.values() if isinstance(sph, dict) else [sph]
        n = sum(len(v) for v in vals)
        blob = str(sorted(str(x) for v in (sph.values() if isinstance(sph, dict)
                                           else [sph]) for x in v))
        out.append(f"n_spheres={n} sphere_md5={hashlib.md5(blob.encode()).hexdigest()[:12]}")
        import os as _o
        for key in ("urdf_path", "asset_root_path"):
            pth = str(kin.get(key))
            out.append(f"{key}={pth} exists={_o.path.exists(pth)}")
        urdf = str(kin.get("urdf_path"))
        if _o.path.exists(urdf):
            u = open(urdf).read()
            out.append(f"urdf_md5={hashlib.md5(u.encode()).hexdigest()[:12]} len={len(u)}")
    except Exception as e:  # noqa: BLE001
        out.append(f"ERROR: {e}")
    _kill_kit(proc)
    cache_vol.commit()
    return "\n".join(out)


@app.function(image=image, gpu=GPU, cpu=6.0, memory=12288, timeout=2000,
              volumes=_VOLUMES)
def scene_export(template_id: str) -> str:
    """UR10-divergence RCA final probe: build the template in-cloud and
    export the stage to the cache volume for a local semantic USD diff."""
    import subprocess
    from pathlib import Path

    proc, boot_s = _boot_kit()
    _stage_custom_curobo()
    probe_py = f'''
import asyncio, json, sys
sys.path.insert(0, "{REPO}")
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.canonical_instantiator import (
    execute_template_canonical, settle_after_canonical)
async def m():
    await kit_tools.exec_sync("import omni.usd\\nomni.usd.get_context().new_stage()\\n", timeout=20)
    tpl = json.load(open("{REPO}/workspace/templates/{template_id}.json"))
    b = await execute_template_canonical(tpl)
    try:
        await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
    except Exception:
        pass
    r = await kit_tools.exec_sync(
        "import omni.usd, os\\n"
        "os.makedirs('/root/.cache/qa_export', exist_ok=True)\\n"
        "st = omni.usd.get_context().get_stage()\\n"
        "st.Export('/root/.cache/qa_export/{template_id}_cloud.usda')\\n"
        "print('EXPORTED')\\n", timeout=120)
    print("EXPORT_RESULT=" + json.dumps(r)[:300])
    print("BUILD n_ok=%s/%s errors=%s" % (b.get("n_ok"), b.get("n_calls"), str(b.get("errors"))[:200]))
asyncio.run(m())
'''
    Path("/tmp/scene_export.py").write_text(probe_py)
    pr = subprocess.run([sys_exe(), "/tmp/scene_export.py"],
                        capture_output=True, text=True, timeout=1200)
    _kill_kit(proc)
    cache_vol.commit()
    return (pr.stdout + pr.stderr)[-1500:]


@app.local_entrypoint()
def export_scene(template: str = "CP-70"):
    print("SCENE_EXPORT:")
    print(scene_export.remote(template))


@app.local_entrypoint()
def fingerprint_ur10():
    print("CLOUD_FINGERPRINT:")
    print(curobo_fingerprint.remote())


@app.local_entrypoint()
def boot():
    res = boot_test.remote()
    print("BOOT_TEST_RESULT:")
    print(json.dumps(res, indent=2)[:8000])


@app.local_entrypoint()
def main(templates: str = "", skip_ts: bool = False, env: str = "", eyes: bool = False):
    if not templates:
        print(__doc__)
        return
    names = [t.strip() for t in templates.split(",") if t.strip()]
    outdir = REPO_LOCAL / "workspace" / "qa_runs" / "cloud_results"
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    outfile = outdir / f"modal_{stamp}.jsonl"
    n_done = 0
    with open(outfile, "a") as fh:
        flags = dict(kv.split("=", 1) for kv in env.split(",") if "=" in kv)
        import subprocess as _sp
        sha = _sp.run(["git", "rev-parse", "--short", "HEAD"],
                      cwd=str(REPO_LOCAL), capture_output=True,
                      text=True).stdout.strip()
        for res in run_template.map(names,
                                    kwargs={"skip_ts": skip_ts,
                                            "env_flags": flags or None,
                                            "eyes": eyes},
                                    order_outputs=False,
                                    return_exceptions=True):
            if isinstance(res, BaseException):
                # audit HIGH-4: an aborting iterator silently truncated the
                # wave's JSONL; record the loss instead (identity unknown
                # with unordered map — the missing template = set diff)
                res = {"template": None, "gate": None,
                       "error": f"map-exception: {res!r}"[:600]}
            res["sha"] = sha  # measurement-time HEAD (audit LOW-9)
            n_done += 1
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"[{n_done}/{len(names)}] {res.get('template')} "
                  f"gate={res.get('gate')} ts={res.get('ts', '-')} "
                  f"boot={res.get('boot_s', '?')}s "
                  f"{('ERR ' + res['error'][:200]) if res.get('error') else ''}",
                  flush=True)
    print(f"results -> {outfile}")
