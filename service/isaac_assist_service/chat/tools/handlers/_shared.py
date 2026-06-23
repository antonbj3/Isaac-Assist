"""Cross-handler shared utilities.

Phase 8 contract per spec — this module is the *future* home for the
twelve cross-handler utilities currently living at module-level inside
`tool_executor.py`. As each theme moves out of the monolith (Phases
3-7), the utilities its handlers depended on move here.

The Phase 2b cross-reference audit identified ten high-fan-in
utilities (each called by ≥3 handlers — `docs/audits/handler_cross_refs.md`
for the live list):

  execute_tool_call          — dispatcher entry, stays in tool_executor
                                (special case — not migrated here)
  _get_viewport_bytes        — viewport capture helper (vision theme)
  _get_vision_provider       — vision-LLM provider selector
  _query_run_ipc             — training IPC helper
  _resolve_run_id            — training run-id resolver
  _check_real_data_path      — finetune / sim data validator
  _wf_now_iso                — workflow timestamp helper
  _parse_last_json_line      — subprocess output parser
  _safe_robot_name           — USD-path sanitiser
  _validate_env_id           — IsaacLab env-id validator

Phase 8's "Files (changes)" — the import-swap from `tool_executor`
globals to `handlers._shared` — requires the themed modules to actually
contain handler code first. That's Phases 3-7. Until then, this module
is a documented re-export façade: themed modules can already
`from ._shared import _safe_robot_name` and the import resolves to the
existing implementation in `tool_executor.py`, so no behaviour change.

Once Phase 3-7 land, the re-exports in this file are replaced by the
moved function bodies; tool_executor.py loses those module-level
definitions; nothing in the consumer themed modules has to change
(their imports already point here).

Per `specs/IA_FULL_SPEC_2026-05-10.md` Phase 8.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Type-only re-exports for theme handlers that want signatures
    # without circular-import risk.
    pass


# ---------------------------------------------------------------------------
# Read-only cross-handler constants (Phase 8 §Risk mitigation: keep
# read-only constants here, NOT in `_state.py`'s mutable dataclasses).
# Populated as Phase 3-7 lift them out of tool_executor.py.

# Phase 8 wave 3 (2026-05-13): _SAFE_XFORM_SNIPPET migrated from
# tool_executor.py:1596. Used by animation/sensors/scene_blueprints/
# scene_authoring code generators to inject safe transform setters.
_SAFE_XFORM_SNIPPET = '''\

def _safe_set_translate(prim, pos):
    """Set translate as LOCAL position (reusing existing op if present).

    Sensor mounts (lidar/camera under robot frame) expect LOCAL offset semantics.
    For WORLD coords use _safe_set_world_translate.
    """
    xf = UsdGeom.Xformable(prim)
    for op in xf.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            op.Set(Gf.Vec3d(*pos))
            return
    xf.AddTranslateOp().Set(Gf.Vec3d(*pos))

def _safe_set_world_translate(prim, pos):
    """Set translate to WORLD position; subtracts parent world-pos when parented.

    Used by create_prim (where position is documented as world coords).
    Translation-only correction (assumes parent has no rotation, which holds
    for axis-aligned scene primitives in 99% of templates).
    """
    from pxr import Sdf as _Sdf
    xf = UsdGeom.Xformable(prim)
    parent = prim.GetParent()
    if parent and parent.IsValid() and parent.GetPath() != _Sdf.Path("/"):
        try:
            pxf = UsdGeom.Xformable(parent)
            if pxf:
                pw = pxf.ComputeLocalToWorldTransform(0).ExtractTranslation()
                pos = (pos[0] - float(pw[0]), pos[1] - float(pw[1]), pos[2] - float(pw[2]))
        except Exception:
            pass
    for op in xf.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            op.Set(Gf.Vec3d(*pos))
            return
    xf.AddTranslateOp().Set(Gf.Vec3d(*pos))

def _safe_set_scale(prim, s):
    """Set scale, reusing existing op if present."""
    xf = UsdGeom.Xformable(prim)
    for op in xf.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeScale:
            op.Set(Gf.Vec3d(*s))
            return
    xf.AddScaleOp().Set(Gf.Vec3d(*s))

def _safe_set_rotate_xyz(prim, r):
    """Set rotateXYZ, reusing existing op if present."""
    xf = UsdGeom.Xformable(prim)
    for op in xf.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeRotateXYZ:
            op.Set(Gf.Vec3d(*r))
            return
    xf.AddRotateXYZOp().Set(Gf.Vec3d(*r))
'''

# Phase 8 wave 5 (2026-05-13): _OG_NODE_TYPE_MAP migrated from
# tool_executor.py:1900. Used by scene_authoring + ros2 OmniGraph
# code generators to remap legacy omni.isaac.* → isaacsim.* node types.
_OG_NODE_TYPE_MAP = {
    # ROS2 bridge nodes (Isaac Sim 5.1 uses isaacsim.ros2.bridge.*)
    "omni.isaac.ros2_bridge.ROS2Context": "isaacsim.ros2.bridge.ROS2Context",
    "omni.isaac.ros2_bridge.ROS2PublishClock": "isaacsim.ros2.bridge.ROS2PublishClock",
    "omni.isaac.ros2_bridge.ROS2PublishJointState": "isaacsim.ros2.bridge.ROS2PublishJointState",
    "omni.isaac.ros2_bridge.ROS2SubscribeJointState": "isaacsim.ros2.bridge.ROS2SubscribeJointState",
    "omni.isaac.ros2_bridge.ROS2PublishTransformTree": "isaacsim.ros2.bridge.ROS2PublishTransformTree",
    "omni.isaac.ros2_bridge.ROS2PublishImage": "isaacsim.ros2.bridge.ROS2PublishImage",
    # ArticulationController is in core.nodes, NOT ros2.bridge
    "omni.isaac.ros2_bridge.ROS2ArticulationController": "isaacsim.core.nodes.IsaacArticulationController",
    "isaacsim.ros2.bridge.ROS2ArticulationController": "isaacsim.core.nodes.IsaacArticulationController",
    "omni.isaac.core_nodes.IsaacArticulationController": "isaacsim.core.nodes.IsaacArticulationController",
}


# Phase 8 wave 5: _open_hdf5_safely migrated from tool_executor.py:3808.
# Used by teleop (validate demo) + diagnostics (check teleop hardware).
def _open_hdf5_safely(path: str):
    """Return (h5py_File, None) or (None, reason_str). Never raises."""
    from pathlib import Path
    try:
        import h5py  # type: ignore
    except ImportError:
        return None, "h5py is not installed"
    p = Path(path)
    if not p.exists():
        return None, f"file does not exist: {path}"
    try:
        return h5py.File(str(p), "r"), None
    except Exception as e:  # noqa: BLE001
        return None, f"failed to open HDF5: {e}"



# Phase 8 wave 8 (2026-05-13): cross-theme symbols used by resolve + robot.

_ROBOT_WIZARD_REGISTRY = {
    "franka_panda": {
        "rel_path": "Isaac/Robots/FrankaRobotics/FrankaPanda/franka.usd",
        "cloud_url": "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Robots/FrankaRobotics/FrankaPanda/franka.usd",
        "robot_type": "manipulator",
        # Franka-specific profile — overrides generic `manipulator` defaults.
        # Added after 2026-04-21 conveyor_pick_place debugging; generic
        # kp=1000/kd=100 is too weak for Franka position control, and the
        # default Gripper variant doesn't render fingers in some Kit
        # builds. Full profile lets `robot_wizard` configure an
        # out-of-the-box working Franka without downstream patches.
        "drive_stiffness": 6000,
        "drive_damping": 500,
        "variants": {"Gripper": "AlternateFinger"},
        "home_joints": [0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785, 0.04, 0.04],
        "ee_link": "panda_hand",
        "gripper_joints": ["panda_finger_joint1", "panda_finger_joint2"],
        "gripper_open": 0.04,
        "gripper_close": 0.0,
        "rmpflow_config_rel": "motion_policy_configs/franka/rmpflow/franka_rmpflow_common.yaml",
    },
    # Aliases
    "franka": "franka_panda",
    "panda": "franka_panda",
    "franka_emika_panda": "franka_panda",

    # Additional robots — minimal entries (cloud URL only, no fine-grained
    # profile). Sufficient for robot_wizard / resolve_robot_class pipelines:
    # the wizard's `if registry_hit:` branch fills in defaults from the
    # generic robot_type table when a profile isn't specified. Cloud URLs
    # follow Isaac Sim 5.1 conventions; if a specific path drifts, edit
    # here once rather than every caller.
    # Paths verified against the user's local 5.0 asset bundle on
    # /mnt/shared_data/isaac-sim-assets-complete-5.0.0; cloud_url uses
    # the same relative path against the public S3 prefix. _resolve_robot_asset
    # prefers local-disk lookup when ASSETS_ROOT_PATH is set, falling back
    # to the cloud URL when it isn't.
    "h1": {
        "rel_path": "Isaac/Robots/Unitree/H1/h1.usd",
        "cloud_url": "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Robots/Unitree/H1/h1.usd",
        "robot_type": "humanoid",
    },
    "g1": {
        "rel_path": "Isaac/Robots/Unitree/G1/g1.usd",
        "cloud_url": "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Robots/Unitree/G1/g1.usd",
        "robot_type": "humanoid",
    },
    "spot": {
        "rel_path": "Isaac/Robots/BostonDynamics/spot/spot.usd",
        "cloud_url": "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Robots/BostonDynamics/spot/spot.usd",
        "robot_type": "mobile",
    },
    "anymal_c": {
        "rel_path": "Isaac/Robots/ANYbotics/anymal_c/anymal_c.usd",
        "cloud_url": "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Robots/ANYbotics/anymal_c/anymal_c.usd",
        "robot_type": "mobile",
    },
    "nova_carter": {
        "rel_path": "Isaac/Robots/NVIDIA/NovaCarter/nova_carter.usd",
        "cloud_url": "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Robots/NVIDIA/NovaCarter/nova_carter.usd",
        "robot_type": "mobile",
    },
    "ur10e": {
        "rel_path": "Isaac/Robots/UniversalRobots/ur10e/ur10e.usd",
        "cloud_url": "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Robots/UniversalRobots/ur10e/ur10e.usd",
        "robot_type": "manipulator",
        # 2026-05-20: Added after Anton observed 11 UR10 templates starting
        # with arm horizontal at z=0 → physics yanks limbs around. UR-style
        # default 0-joints = arm extended sideways. Standard Isaac "home"
        # pose: shoulder up, elbow bent forward, wrists neutral.
        # Joints: shoulder_pan, shoulder_lift, elbow, wrist_1, wrist_2, wrist_3
        "home_joints": [0.0, -1.5708, 1.5708, -1.5708, -1.5708, 0.0],
        "ee_link": "ee_link",
    },
    "allegro": {
        "rel_path": "Isaac/Robots/WonikRobotics/AllegroHand/allegro_hand.usd",
        "cloud_url": "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Robots/WonikRobotics/AllegroHand/allegro_hand.usd",
        "robot_type": "manipulator",
    },
    # Round 6 repair (2026-05-18): Jetbot was used by ROS2-bridge canonicals
    # (jetbot-sensor-bridge, multi-sensor-fusion-rgbd-imu, occupancy-map-nav)
    # but never landed in the registry, so robot_wizard rejected every call.
    # Jetbot is a differential-drive mobile robot — robot_type='mobile' so
    # the wizard skips arm-specific drive defaults.
    "jetbot": {
        "rel_path": "Isaac/Robots/NVIDIA/Jetbot/jetbot.usd",
        "cloud_url": "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Robots/NVIDIA/Jetbot/jetbot.usd",
        "robot_type": "mobile",
    },
    # Aliases for the robots above
    "unitree_h1": "h1",
    "unitree_g1": "g1",
    "carter": "nova_carter",
    "ur10": "ur10e",
    "nvidia_jetbot": "jetbot",
}


def _wire_yaskawa_gp25() -> None:
    """Phase 71 — attach the Yaskawa GP25 spec into _ROBOT_WIZARD_REGISTRY.

    Pulls the registry entry from ``multimodal.yaskawa_gp25_onboarding`` so
    the GP25 spec data (payload, reach, joint limits, controller protocol,
    Nucleus asset path, gripper recommendations) is reachable through
    ``robot_wizard`` and ``resolve_robot_class`` without duplicating the
    onboarding module's content here.
    """
    try:
        from service.isaac_assist_service.multimodal.yaskawa_gp25_onboarding import (
            gp25_to_robot_wizard_entry,
        )
    except Exception:  # pragma: no cover — defensive in case import order shifts
        return
    entry = gp25_to_robot_wizard_entry()
    _ROBOT_WIZARD_REGISTRY.setdefault("yaskawa_gp25", entry)
    _ROBOT_WIZARD_REGISTRY.setdefault("gp25", "yaskawa_gp25")
    _ROBOT_WIZARD_REGISTRY.setdefault("yaskawa_motoman_gp25", "yaskawa_gp25")


_wire_yaskawa_gp25()

# Version-robust Isaac asset resolution (Anton 2026-06-23: "härda det så det
# fungerar med alla Isaac Sim versioner 5 och framåt, 6 släpps snart"). The
# per-entry cloud_url hardcodes ONE version (/Assets/Isaac/5.1/...), which breaks
# in a 5.0/5.2/6.x environment. rel_path is version-agnostic ("Isaac/Robots/.../x.usd"),
# so we DERIVE candidate URLs from a base + a version list and let the importer try
# each until one resolves (AddReference is lazy + won't 404, so an empty prim = wrong
# version -> try next). Works across Isaac 5.x AND the upcoming 6.x with no per-asset edits.
_ISAAC_CLOUD_BASE = ("https://omniverse-content-production.s3-us-west-2.amazonaws.com"
                     "/Assets/Isaac")


def _isaac_asset_versions() -> "list[str]":
    """Ordered Isaac asset-version candidates. ISAAC_ASSETS_VERSION env pins/leads;
    else detect from the ASSETS_ROOT_PATH dir name (e.g. ...-complete-5.0.0); else a
    sensible newest-known order. Add new versions (6.x) here as they ship."""
    import os as _os, re as _re
    order = ["5.1", "5.0", "5.2", "5.3", "6.0", "6.1"]
    v = _os.environ.get("ISAAC_ASSETS_VERSION", "").strip()
    if v:
        return [v] + [x for x in order if x != v]
    m = _re.search(r"(\d+\.\d+)(?:\.\d+)?", _os.environ.get("ASSETS_ROOT_PATH", ""))
    if m and m.group(1) in order:
        d = m.group(1)
        return [d] + [x for x in order if x != d]
    return order


def _robot_asset_candidates(entry: Dict) -> "list[str]":
    """Ordered asset-URL candidates for a registry entry: local disk first (fastest,
    offline), then cloud derived from rel_path across Isaac versions, then the legacy
    hardcoded cloud_url as a final fallback. The importer tries each until one loads."""
    import os as _os
    out: "list[str]" = []
    rel = (entry.get("rel_path") or "").lstrip("/")
    assets_root = _os.environ.get("ASSETS_ROOT_PATH", "").rstrip("/")
    if assets_root and rel:
        local = f"{assets_root}/{rel}"
        if _os.path.exists(local):
            out.append(local)
    if rel:
        for v in _isaac_asset_versions():
            url = f"{_ISAAC_CLOUD_BASE}/{v}/{rel}"
            if url not in out:
                out.append(url)
    cu = entry.get("cloud_url")
    if cu and cu not in out:
        out.append(cu)
    return out


def _resolve_robot_asset(entry: Dict) -> str:
    """Best single asset path for a robot entry (backward-compat). Returns the FIRST
    version-robust candidate (local if present, else the leading-version cloud URL).
    Callers wanting full version-fallback should use ``_robot_asset_candidates``."""
    cands = _robot_asset_candidates(entry)
    return cands[0] if cands else entry.get("cloud_url", "")


def _version_robust_asset_candidates(path: str) -> "list[str]":
    """Version-robust candidates for an arbitrary Isaac asset PATH (the templates'
    hardcoded ``.../Assets/Isaac/5.0/...`` refs). Extracts the rel-path after
    ``/Assets/Isaac/{V}/`` and re-derives it across Isaac versions: the original path
    (if it resolves), the same local install root with the version substituted (in BOTH
    the ``complete-X`` dir name and the ``/Isaac/{V}/`` segment), then cloud across
    versions. Non-Isaac paths (custom URDFs, omniverse://, no Isaac/{V} segment) pass
    through unchanged. Makes templates portable across Isaac 5.x and the upcoming 6.x
    with NO template edits (Anton 2026-06-23 — harden asset resolution for all versions)."""
    import os as _os, re as _re
    if not path:
        return [path]
    m = _re.search(r"^(.*?/Assets/Isaac/)(\d+\.\d+)/(.+)$", path)
    if not m:
        return [path]  # not a version-pinned Isaac asset path
    base_dir, _orig_v, rel = m.group(1), m.group(2), m.group(3)
    out: "list[str]" = []
    _is_url = path.startswith(("omniverse://", "http://", "https://", "file://"))
    if _is_url or _os.path.exists(path):
        out.append(path)  # original first (usually the env's working version)
    versions = _isaac_asset_versions()
    for v in versions:  # local: substitute version in install-dir name + /Isaac/{v}/
        local_base = _re.sub(r"complete-\d+\.\d+(?:\.\d+)?", f"complete-{v}.0", base_dir)
        cand = f"{local_base}{v}/{rel}"
        if cand not in out and not cand.startswith(("omniverse://", "http://", "https://")) \
                and _os.path.exists(cand):
            out.append(cand)
    for v in versions:  # cloud across versions
        cu = f"{_ISAAC_CLOUD_BASE}/{v}/{rel}"
        if cu not in out:
            out.append(cu)
    return out or [path]

# from: feat/addendum-phase8F-ros2-quality
# _ROS2_QOS_PRESETS migrated to handlers/ros2.py (Phase 8 wave 4, 2026-05-13).

# from: feat/atomic-tier13-rl-runtime
_RUN_REGISTRY: Dict[str, Dict[str, Any]] = {}

# from: feat/new-quick-demo-builder-v2
# _SCENE_STYLE_PRESETS migrated to handlers/vision.py (Phase 8 wave 4, 2026-05-13).

# from: feat/6A-physx-validation
# _SCENE_TEMPLATES migrated to handlers/scene_blueprints.py (Phase 8 wave 7, 2026-05-13).

# from: feat/new-onboarding



# Phase 8 wave 17 (2026-05-13): probe functions used by pick_place + robot.

def _probe_gpu_capability():
    """Return dict with gpu_available, compute_capability, arch_name, vram_gb."""
    out = {"gpu_available": False, "compute_capability": None,
           "arch_name": None, "vram_gb": None, "cuda_available": False,
           "reason": None}
    try:
        import torch
        out["cuda_available"] = bool(torch.cuda.is_available())
        if not out["cuda_available"]:
            out["reason"] = "torch.cuda.is_available() = False"
            return out
        out["gpu_available"] = True
        cap = torch.cuda.get_device_capability(0)
        out["compute_capability"] = f"{cap[0]}.{cap[1]}"
        arch_map = {
            (6,0): "Pascal", (6,1): "Pascal", (6,2): "Pascal",
            (7,0): "Volta", (7,2): "Volta",
            (7,5): "Turing",
            (8,0): "Ampere", (8,6): "Ampere", (8,7): "Ampere", (8,9): "Ada",
            (9,0): "Hopper",
            (10,0): "Blackwell",
            (12,0): "Blackwell",
        }
        out["arch_name"] = arch_map.get(cap, f"compute_{cap[0]}.{cap[1]}")
        props = torch.cuda.get_device_properties(0)
        out["vram_gb"] = round(props.total_memory / 1024 / 1024 / 1024, 1)
    except ImportError:
        out["reason"] = "torch not importable"
    except Exception as e:
        out["reason"] = f"{type(e).__name__}: {e}"
    return out

def _probe_scipy():
    """Probe scipy availability and return version metadata."""
    try:
        import scipy.interpolate  # noqa: F401
        import scipy
        return {"available": True, "version": getattr(scipy, "__version__", "?")}
    except ImportError:
        return {"available": False, "reason": "scipy not importable"}
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}: {e}"}

def _probe_curobo():
    """Probe cuRobo availability. Valid = importable AND content/ present.

    The `isaac_lab_env/site-packages/curobo` is usable ONLY if we also
    monkey-patch wp.func (see I-28) AND have franka.yml + internal
    YAMLs (see I-27). This install lacks content/ so full MotionPlanner
    integration is blocked, but the env-bridge pattern works and core
    modules import.
    """
    import os, glob
    # In-Kit or direct import
    try:
        import curobo  # noqa: F401
        return {"available": True, "note": "curobo imports; content/ may still be absent"}
    except ImportError:
        pass
    # Check isaac_lab_env candidate paths
    for pat in [
        "/home/anton/miniconda3/envs/isaac_lab_env/lib/python3.*/site-packages/curobo",
        os.path.expanduser("~/miniconda3/envs/isaac_lab_env/lib/python*/site-packages/curobo"),
        os.path.expanduser("~/isaac_lab_env/lib/python*/site-packages/curobo"),
    ]:
        hits = glob.glob(pat)
        if hits:
            env_path = hits[0]
            content_dir = os.path.join(env_path, "content")
            has_content = os.path.isdir(content_dir) and any(
                f.endswith((".yml", ".yaml"))
                for f in os.listdir(content_dir) if os.path.isfile(os.path.join(content_dir, f))
            ) if os.path.isdir(content_dir) else False
            return {
                "available": False,
                "reason": "env-bridge required (sys.path.insert + invalidate_caches + wp.func patch); MotionPlanner additionally blocked on missing content/ YAMLs" if not has_content else "env-bridge required",
                "env_bridge_path": env_path,
                "has_content_yamls": has_content,
                "bridgeable": True,
            }
    return {"available": False, "reason": "curobo not found in current env or isaac_lab_env", "bridgeable": False}

def _probe_isaac_lab():
    """Probe Isaac Lab availability. In practice, isaaclab is importable
    inside Kit AFTER sys.path.insert + importlib.invalidate_caches (see I-29).
    So the controller generators are bridgeable even when `import isaaclab`
    fails from the main process.
    """
    import os, glob
    try:
        import isaaclab  # noqa: F401
        return {"available": True}
    except ImportError:
        pass
    for pat in [
        "/home/anton/miniconda3/envs/isaac_lab_env/lib/python3.*/site-packages/isaaclab-*.dist-info",
        os.path.expanduser("~/miniconda3/envs/isaac_lab_env/lib/python*/site-packages/isaaclab-*.dist-info"),
    ]:
        hits = glob.glob(pat)
        if hits:
            return {
                "available": False,
                "reason": "env-bridge required (sys.path.insert + invalidate_caches); controller generators handle this automatically",
                "env_bridge_path": hits[0],
                "bridgeable": True,
            }
    return {"available": False, "reason": "isaaclab not importable and not found in isaac_lab_env", "bridgeable": False}


    # _handle_list_available_controllers moved to handlers/robot.py (Phase 7 wave 16).




# _resolve_auto_target_source migrated to handlers/pick_place.py (Phase 8 wave 9, 2026-05-13).



# Phase 8 wave 18 (2026-05-13): cross-theme vram detection helper.

def _detect_local_vram_gb() -> Optional[float]:
    """Best-effort GPU VRAM detection via the existing fingerprint collector."""
    try:
        from ...fingerprint.collector import get_gpu_info
    except Exception:
        return None
    try:
        gpus = get_gpu_info() or []
    except Exception:
        return None
    if not gpus:
        return None
    # Use the largest-VRAM GPU (matches Isaac Sim's preferred device)
    best = max(g.get("vram_mb", 0) for g in gpus)
    if best <= 0:
        return None
    return round(best / 1024.0, 2)

CONSTANTS: dict[str, object] = {
    "SAFE_XFORM_SNIPPET": _SAFE_XFORM_SNIPPET,
    "OG_NODE_TYPE_MAP": _OG_NODE_TYPE_MAP,
}


# ---------------------------------------------------------------------------
# Utility surface contract — names that consumer themed modules expect
# to import. Until Phase 3-7 actually move the implementations,
# `_resolve_from_legacy` is the bridge: it pulls the name out of
# `tool_executor.py`'s module namespace and re-exports it under
# `_shared.<name>`.
#
# This is a deliberate bridge — when a theme like handlers/training.py
# does `from ._shared import _resolve_run_id`, the import resolves
# transparently regardless of whether the function has moved yet.

_LEGACY_REEXPORT_NAMES: tuple[str, ...] = (
    "_get_viewport_bytes",
    "_get_vision_provider",
    "_query_run_ipc",
    "_resolve_run_id",
    "_check_real_data_path",
    "_wf_now_iso",
    "_parse_last_json_line",
    "_safe_robot_name",
    "_validate_env_id",
)


def _resolve_from_legacy(name: str):
    """Pull `name` from `tool_executor.py`'s module namespace.

    Used by __getattr__ below to provide transparent re-exports for any
    high-fan-in utility that hasn't been physically moved out of the
    monolith yet.
    """
    # Lazy import — avoid pulling tool_executor at module load (it's
    # 35k lines and loading it eagerly would change import-time cost
    # for any _shared consumer that doesn't actually use the legacy
    # utilities).
    from .. import tool_executor as _te  # type: ignore[no-redef]

    return getattr(_te, name)



# ---------------------------------------------------------------------------
# Phase 14 (2026-05-13): physically moved from tool_executor.py.
# These were in _LEGACY_REEXPORT_NAMES as lazy bridges; the bodies now live
# here and consumers import via `from ._shared import _X`.

from datetime import datetime as _wf_dt, timezone as _wf_tz  # noqa: E402
from pathlib import Path as _Path  # noqa: E402
from typing import Tuple as _Tuple  # noqa: E402

async def _get_viewport_bytes() -> tuple:
    """Capture the viewport and return (raw_bytes, mime_type)."""
    from .. import kit_tools  # local import: avoid module-level circular w/ tools pkg
    result = await kit_tools.get_viewport_image(max_dim=1280)
    b64 = result.get("image_b64") or result.get("data", "")
    if not b64:
        return None, None
    import base64
    return base64.b64decode(b64), "image/png"

_VISION_PROVIDER_SINGLETON = None


def _get_vision_provider():
    """Return a vision provider per the IA_VISION_PROVIDER policy.

    Selection precedence (env-driven, set via ``IA_VISION_PROVIDER``):

    - ``"sam_clip"``: force local SAM2+CLIP only (no Gemini fallback).
        Use when quota is exhausted or for offline deployments.
    - ``"gemini"``: force Gemini Vision only (legacy behaviour).
    - ``"auto"`` (default): prefer local SAM2+CLIP if the SAM2 weight
        file is present on disk, otherwise fall back to Gemini.

    The colour-introspection USD fast path in
    ``handlers/sensors.py:_handle_add_vision_classifier_gate`` is tried
    independently before this provider is consulted (commit cee5cfcb),
    so colour-shaped templates never reach either provider regardless
    of this setting.

    Round 3 repair (2026-05-17): the legacy import path
    ``from ..vision_gemini`` resolved to ``chat.tools.vision_gemini``
    which doesn't exist. Both branches here use ``...vision_gemini``
    (one extra dot) so they resolve to ``chat.vision_gemini``.
    """
    global _VISION_PROVIDER_SINGLETON
    if _VISION_PROVIDER_SINGLETON is not None:
        return _VISION_PROVIDER_SINGLETON

    import os as _os
    policy = (_os.environ.get("IA_VISION_PROVIDER") or "auto").strip().lower()

    # Local SAM+CLIP — try when policy allows AND weights are on disk.
    if policy in ("sam_clip", "samclip", "local"):
        try:
            from ....multimodal.vision_sam_clip import SamClipVisionProvider
            _VISION_PROVIDER_SINGLETON = SamClipVisionProvider()
            return _VISION_PROVIDER_SINGLETON
        except Exception as _e:  # noqa: BLE001
            # Forced-local but module/weights missing — return a permissive
            # error provider rather than silently dropping back to Gemini.
            import logging as _lg
            _lg.getLogger(__name__).error(
                "IA_VISION_PROVIDER=sam_clip but SAM+CLIP init failed: %s — "
                "falling back to Gemini", _e,
            )

    if policy == "auto":
        try:
            from ....multimodal.vision_sam_clip import (
                SAM_CHECKPOINT, SamClipVisionProvider,
            )
            if SAM_CHECKPOINT.exists():
                _VISION_PROVIDER_SINGLETON = SamClipVisionProvider()
                return _VISION_PROVIDER_SINGLETON
        except Exception:  # noqa: BLE001
            pass  # Fall through to Gemini

    # Default / explicit Gemini path.
    from ...vision_gemini import GeminiVisionProvider
    _VISION_PROVIDER_SINGLETON = GeminiVisionProvider()
    return _VISION_PROVIDER_SINGLETON

def _safe_robot_name(articulation_path: str) -> str:
    """Derive a filesystem-safe slug from a USD path, e.g. '/World/Franka' -> 'franka'."""
    name = articulation_path.rstrip("/").split("/")[-1] or "robot"
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name).lower()

def _check_real_data_path(path: str) -> Optional[str]:
    """Return an error string if the real_data_path is unusable, else None."""
    if not path:
        return "real_data_path is required"
    p = Path(path)
    if not p.exists():
        return f"real_data_path not found: {path}"
    if p.suffix.lower() not in (".h5", ".hdf5"):
        return f"real_data_path must be HDF5 (.h5/.hdf5), got {p.suffix}"
    return None

def _wf_now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string with trailing Z."""
    return _wf_dt.now(_wf_tz.utc).isoformat() + "Z"

def _resolve_run_id(run_id: Optional[str]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Resolve a run_id (or None → most-recent active run) to its registry entry.

    Returns (run_id, entry) or (None, None) if no matching run exists.
    """
    if not _RUN_REGISTRY:
        return None, None
    if run_id is None:
        # Pick the most-recently-launched RUNNING (or PAUSED) run.
        candidates = [
            (rid, e) for rid, e in _RUN_REGISTRY.items()
            if e.get("state") in ("running", "paused")
        ]
        if not candidates:
            return None, None
        # Newest by launch_time
        candidates.sort(key=lambda kv: kv[1].get("launch_time", 0.0), reverse=True)
        return candidates[0]
    entry = _RUN_REGISTRY.get(run_id)
    return (run_id, entry) if entry else (None, None)

async def _query_run_ipc(entry: Dict[str, Any], request: Dict[str, Any]) -> Dict[str, Any]:
    """Send an IPC request to a running launch_training subprocess.

    Override in tests via monkeypatch. The real implementation talks to the
    subprocess over its Unix socket (entry['ipc_socket']).
    """
    handler = entry.get("ipc_handler")
    if handler is None:
        raise RuntimeError(
            "No IPC handler registered for this run — was it launched via launch_training?"
        )
    return await handler(request)

def _validate_env_id(env_id: Any, num_envs: int) -> Optional[str]:
    """Return an error message if env_id is invalid, else None."""
    if not isinstance(env_id, int) or isinstance(env_id, bool):
        return f"env_id must be an integer, got {type(env_id).__name__}"
    if env_id < 0 or env_id >= num_envs:
        return f"env_id {env_id} out of range [0, {num_envs})"
    return None

def __getattr__(name: str):  # PEP 562 module-level __getattr__
    """Lazy re-export for legacy-named utilities.

    Phase 3-7 will replace this with direct function definitions in
    this module body. Until then, `from ._shared import <name>` for any
    name in `_LEGACY_REEXPORT_NAMES` resolves to the corresponding
    function in `tool_executor.py`.
    """
    if name in _LEGACY_REEXPORT_NAMES:
        return _resolve_from_legacy(name)
    raise AttributeError(
        f"module 'service.isaac_assist_service.chat.tools.handlers._shared' "
        f"has no attribute {name!r}. If this is a future-Phase-3-7 utility "
        f"that should be re-exported, add it to _LEGACY_REEXPORT_NAMES."
    )


__all__ = [
    "CONSTANTS",
    "_SAFE_XFORM_SNIPPET",
    "_OG_NODE_TYPE_MAP",
    "_open_hdf5_safely",
    "_ROBOT_WIZARD_REGISTRY",
    "_resolve_robot_asset",
    "_probe_gpu_capability",
    "_probe_scipy",
    "_probe_curobo",
    "_probe_isaac_lab",
    "_detect_local_vram_gb",
    # Plus the lazy-imported names; importers see them via __getattr__.
    *_LEGACY_REEXPORT_NAMES,
]
