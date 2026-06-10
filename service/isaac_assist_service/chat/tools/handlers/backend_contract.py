"""backend_contract — machine-readable controller-backend contract [P2-13].

The additive step CONTROLLER_BACKEND_CONTRACT.md recommends instead of an ABC:
one declarative row per ``target_source`` selector, consumed by
``motion_controllers`` honesty tagging, retrieval surfaces, and (after
UR10-track coordination — pick_place.py is their file) the dispatcher's C4
reroute/raise decisions.

The rows DECLARE; they never measure. Verified-status lives in the
verification ledger and the per-template ``motion_controllers`` records —
a backend is honest-verified only when measured rows exist (today: curobo,
direct_joint). ``sim2real`` values:

- ``honest``           target derivation declared + no simulation shortcuts
- ``honest-cheat-grip``FixedJoint transport (declared simulation shortcut)
- ``omniscient``       reads live ground-truth poses (demo/ML-gen only)
- ``external``         logic outside Isaac (honesty delegated)
- ``experimental``     not expected to deliver; in the matrix for coverage
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

BACKEND_CONTRACT: Dict[str, Dict[str, Any]] = {
    "curobo": {
        "families": ["franka", "ur10", "g1_arm"],
        "grip": {"franka": "parallel", "ur10": "suction_cup_frame",
                 # g1 dex hand V0 = surface-gripper FJ-attach (no finger
                 # joints) — QA-audit 2026-06-10 vs pick_place.py ~4084
                 "g1_arm": "surface_fj_attach"},
        "world_model": "manual_obstacles+ur10_multicube_auto",
        "multi_item": True,
        # "targets" är simulate-GATENS vokabulär, inte controllerns
        "routing": ["drop_targets", "color_routing"],
        "sim2real": "honest",
        "ctrl_records": True,
        "never_auto": False,
    },
    "spline": {
        "families": ["franka"],
        # fixedjoint half was never emitted (QA-audit vs source 3061-3864)
        "grip": {"franka": "friction"},
        "world_model": None,
        "multi_item": False,
        "routing": ["color_routing"],
        "sim2real": "honest",
        "ctrl_records": False,   # C5-audit 2026-06-10: 0 ctrl:* refs in source
        "never_auto": False,
    },
    "native": {
        "families": ["franka"],          # non-Franka REROUTES to builtin (C4)
        "grip": {"franka": "parallel"},
        "world_model": None,
        "multi_item": False,
        "routing": [],
        "sim2real": "honest",
        "ctrl_records": False,
        "never_auto": False,
    },
    "builtin": {
        "families": ["franka", "ur10", "ur10e", "cobotta_pro_900"],
        "grip": {"franka": "parallel", "ur10": "surface", "ur10e": "surface",
                 "cobotta_pro_900": "parallel"},
        "world_model": None,
        "multi_item": False,
        "routing": [],
        "sim2real": "honest",
        "ctrl_records": False,
        "never_auto": True,   # only reachable via native's non-Franka reroute
    },
    "diffik": {
        "families": ["franka"],
        "grip": {"franka": "parallel"},
        "world_model": None,
        "multi_item": False,
        "routing": [],
        "sim2real": "honest",
        "ctrl_records": False,
        "never_auto": False,
    },
    "osc": {
        "families": ["franka"],
        "grip": {"franka": "effort_mode"},
        "world_model": None,
        "multi_item": False,
        "routing": [],
        "sim2real": "experimental",   # 0-2/4 expected; teardown gap (drives)
        "ctrl_records": False,
        "never_auto": True,
    },
    "sensor_gated": {
        "families": ["*taught_poses"],
        # "Grip is ALWAYS friction — no EE<->cube FixedJoint (Anton's
        # rule)" (pick_place.py ~2276) — the FJ accusation was WRONG
        # (QA-audit 2026-06-10); grip_style="fixed_joint" is dead arg surface
        "grip": {"*": "friction"},
        "world_model": None,
        "multi_item": False,
        "routing": [],
        "sim2real": "honest",
        "ctrl_records": True,   # C5-audit 2026-06-10: 15 ctrl:* refs in source
        "never_auto": True,   # mandatory sensor_path / taught poses
    },
    "fixed_poses": {
        "families": ["*dof_remap"],
        "grip": {},               # no grasp logic — pose replay only
        "world_model": None,
        "multi_item": False,
        "routing": [],
        "sim2real": "honest",
        "ctrl_records": False,
        "never_auto": True,   # mandatory pose_sequence
    },
    "cube_tracking": {
        "families": ["franka"],
        # FRICTION-FIX: no FJ created (pick_place.py ~710) — omniscience
        # is in the TARGETING (live pose polling), not the grip
        "grip": {"franka": "friction"},
        "world_model": None,
        "multi_item": False,
        "routing": [],
        "sim2real": "omniscient",   # live ground-truth pose polling, declared
        "ctrl_records": False,
        "never_auto": True,
    },
    "ros2_cmd": {
        "families": ["*"],
        "grip": {"*": "external"},
        "world_model": None,
        "multi_item": False,
        "routing": [],
        "sim2real": "external",   # loop not yet closed (X-08b)
        "ctrl_records": False,
        "never_auto": True,
    },
}

#: selectors the auto-resolver may return, in priority order (contract §3)
AUTO_PRIORITY: List[str] = ["curobo", "spline", "native", "diffik"]


def contract_for(selector: str) -> Optional[Dict[str, Any]]:
    """The declared contract row for a ``target_source`` selector, or None
    for unknown selectors ('auto' resolves before contract lookup;
    'cortex' is retired and intentionally absent)."""
    return BACKEND_CONTRACT.get(selector)


def supports_family(selector: str, family: str) -> bool:
    """Does *selector* DECLARE support for *family*? Wildcard families
    (``*``-prefixed) mean any articulation meeting the stated condition."""
    row = BACKEND_CONTRACT.get(selector)
    if not row:
        return False
    fams = row["families"]
    return family in fams or any(f.startswith("*") for f in fams)
