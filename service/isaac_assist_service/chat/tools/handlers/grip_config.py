"""Grip-stiffness configuration for friction-grip pick-place.

For real-robot-realistic friction grip, finger drive stiffness must be tuned
to cube mass and surface friction (mu). Too low → cube slips. Too high →
adjacent objects get nudged on close + impulse-spike at contact.

The analytical formula (compute_optimal_grip) approximates required finger
stiffness via:
    grip_force_N = (mass * g * safety) / mu
    stiffness    = grip_force_N / finger_displacement
    damping      = 2 * sqrt(stiffness * mass)  (critical damping)

Calibration against empirical failure-thresholds (see
scripts/friction_paradigm/find_grip_threshold.py) keeps the SAFETY_FACTOR
and DEFAULT_DISPLACEMENT constants honest.
"""
from __future__ import annotations
from typing import Dict, Optional


# Tuned constants — adjust based on empirical bisection-test results.
DEFAULT_SAFETY_FACTOR: float = 3.0     # hold against gravity + dynamic margin
DEFAULT_DISPLACEMENT_M: float = 0.02   # finger position-error during static hold
DEFAULT_G: float = 9.81

# Production default when no mass/mu known (current pick_place.py value).
DEFAULT_STIFFNESS: float = 10000.0
DEFAULT_DAMPING: float = 200.0


def compute_optimal_grip(
    mass_kg: float,
    mu: float,
    safety: float = DEFAULT_SAFETY_FACTOR,
    displacement_m: float = DEFAULT_DISPLACEMENT_M,
    g: float = DEFAULT_G,
    real_franka_max_force_N: float = 70.0,
) -> Dict[str, float]:
    """Compute optimal finger drive stiffness, damping, AND maxForce for friction grip.

    IMPORTANT: Isaac panda's default finger drive has maxForce ≈ 7.2 N — caps grip
    regardless of stiffness setting. Without raising maxForce, stiff tuning is futile
    for any cube mass > ~0.15 kg. Real Franka max grip force = 70 N (datasheet).

    Args:
        mass_kg: cube mass in kilograms
        mu: friction coefficient between finger pad and cube surface (Coulomb)
        safety: multiplier on gravity force (default 3× = handle accelerations)
        displacement_m: assumed finger position-error during hold (Franka ~0.02m)
        g: gravitational acceleration
        real_franka_max_force_N: hard cap on grip force (datasheet limit)

    Returns:
        dict with grip_force_N (required), max_force (cap to set on drive),
        stiffness (N/m), damping (N·s/m).
    """
    if mass_kg <= 0:
        raise ValueError(f"mass_kg must be > 0, got {mass_kg}")
    if mu <= 0:
        raise ValueError(f"mu must be > 0, got {mu}")

    required_friction_N = mass_kg * g * safety
    required_grip_N = required_friction_N / max(mu, 0.05)  # mu floor 0.05

    # Cap at real Franka max — warn (via return field) if cube unholdable
    actual_grip_N = min(required_grip_N, real_franka_max_force_N)
    # maxForce: set with small headroom above expected grip
    max_force = min(actual_grip_N * 1.2, real_franka_max_force_N)
    # Stiffness sized so we reach max_force at expected displacement
    stiffness = max_force / displacement_m
    damping = 2.0 * (stiffness * mass_kg) ** 0.5
    return {
        "grip_force_N": round(required_grip_N, 3),
        "max_force": round(max_force, 2),
        "stiffness": round(stiffness, 1),
        "damping": round(damping, 2),
        "force_capped": required_grip_N > real_franka_max_force_N,
    }


def resolve_grip_config(
    grip_config: Optional[dict] = None,
    mass_kg: Optional[float] = None,
    mu: Optional[float] = None,
) -> Dict[str, float]:
    """Resolve final stiffness/damping from user input.

    Precedence:
      1. Explicit grip_config={"stiffness": ..., "damping": ...} → use as-is
      2. mass_kg + mu provided → compute_optimal_grip
      3. Fallback → DEFAULT_STIFFNESS / DEFAULT_DAMPING
    """
    if grip_config and "stiffness" in grip_config:
        return {
            "stiffness": float(grip_config["stiffness"]),
            "damping": float(grip_config.get("damping", DEFAULT_DAMPING)),
            "max_force": float(grip_config.get("max_force", 70.0)),
            "source": "explicit",
        }
    if mass_kg is not None and mu is not None:
        cfg = compute_optimal_grip(mass_kg=mass_kg, mu=mu)
        cfg["source"] = f"computed(mass={mass_kg}, mu={mu})"
        return cfg
    return {
        "stiffness": DEFAULT_STIFFNESS,
        "damping": DEFAULT_DAMPING,
        "source": "default",
    }


# Kit-side snippet — embed in generated handler code via .format()
# Reads cube mass + cube material mu, computes stiffness, applies to finger drives.
KIT_SIDE_AUTODETECT_SNIPPET = '''
# --- grip_config auto-detect (runtime) ---
def _detect_cube_mass(stage, cube_path):
    p = stage.GetPrimAtPath(cube_path)
    if not (p and p.IsValid()): return None
    a = p.GetAttribute("physics:mass")
    if a and a.HasAuthoredValue():
        return float(a.Get())
    return None

def _detect_cube_mu(stage, cube_path):
    p = stage.GetPrimAtPath(cube_path)
    if not (p and p.IsValid()): return None
    rel = p.GetRelationship("material:binding:physics")
    if not rel: return None
    for mp in rel.GetTargets():
        m = stage.GetPrimAtPath(mp)
        if not (m and m.IsValid()): continue
        pm = UsdPhysics.MaterialAPI(m)
        a = pm.GetStaticFrictionAttr()
        if a and a.HasAuthoredValue():
            return float(a.Get())
    return None
'''
