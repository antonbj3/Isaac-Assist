"""Phase 25 — object palette expansion: 17 → 60 canonical classes.

Adds 43 new object classes beyond Block 1A's initial 17. Each entry has
a USD reference URL, default position offset, and footprint metadata
used by the snap engine + ratifier.

Per specs/IA_FULL_SPEC_2026-05-10.md Phase 25.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ObjectClass:
    """One entry in the canonical object palette, describing a USD asset class."""
    name: str
    usd_ref: str = ""
    category: str = "prop"  # robot | sensor | fixture | prop | environment
    footprint_xy_m: tuple = (0.1, 0.1)
    default_z: float = 0.0
    height_m: float = 0.0  # z-extent of the asset; 0 = unknown (static_eyes falls back to _CLASS_HEIGHTS_M)
    tags: List[str] = field(default_factory=list)


# Phase 25 palette — 60 classes. Block 1A's original 17 + 43 new.
PALETTE: Dict[str, ObjectClass] = {
    # Robots (8)
    # height_m = folded/home-pose z-extent of the physical asset (NOT the reach envelope).
    # Franka: base flange to highest link at home pose ~0.60 m.
    "franka_panda": ObjectClass("franka_panda", "Isaac/Robots/FrankaRobotics/FrankaPanda/franka.usd",
                                category="robot", footprint_xy_m=(0.4, 0.4), height_m=0.60,
                                tags=["arm", "manipulator"]),
    # UR10: arm folded at home; vertical reach 1.3 m but folded asset height ~0.70 m.
    "ur10": ObjectClass("ur10", "Isaac/Robots/UniversalRobots/UR10/ur10.usd",
                        category="robot", footprint_xy_m=(0.3, 0.3), height_m=0.70,
                        tags=["arm", "manipulator"]),
    # UR5e: smaller than UR10; folded home ~0.60 m.
    "ur5e": ObjectClass("ur5e", "Isaac/Robots/UniversalRobots/UR5e/ur5e.usd",
                        category="robot", footprint_xy_m=(0.25, 0.25), height_m=0.60,
                        tags=["arm", "manipulator"]),
    # Kinova Gen3: 7-DOF arm folded at home ~0.70 m.
    "kinova_gen3": ObjectClass("kinova_gen3", "Isaac/Robots/Kinova/Gen3/gen3.usd",
                                category="robot", footprint_xy_m=(0.3, 0.3), height_m=0.70,
                                tags=["arm"]),
    # Carter: differential-drive AMR with sensor mast, ~0.40 m to top of mast.
    "carter": ObjectClass("carter", "Isaac/Robots/Nvidia/Carter/carter_v1.usd",
                          category="robot", footprint_xy_m=(0.6, 0.45), height_m=0.40,
                          tags=["mobile"]),
    # Jetbot: miniature platform; camera/IMU at ~0.15 m.
    "jetbot": ObjectClass("jetbot", "Isaac/Robots/Nvidia/Jetbot/jetbot.usd",
                          category="robot", footprint_xy_m=(0.2, 0.15), height_m=0.15,
                          tags=["mobile"]),
    # Spot: quadruped standing height ~0.70 m (body ~0.5 m + head/lidar ~0.20 m).
    "spot": ObjectClass("spot", "Isaac/Robots/BostonDynamics/Spot/spot.usd",
                        category="robot", footprint_xy_m=(1.1, 0.5), height_m=0.70,
                        tags=["quadruped"]),
    # H1: full-height humanoid, standing ~1.80 m.
    "h1": ObjectClass("h1", "Isaac/Robots/Unitree/H1/h1.usd",
                      category="robot", footprint_xy_m=(0.4, 0.4), height_m=1.80,
                      tags=["humanoid"]),
    # Workpieces (10)
    "cube_small": ObjectClass("cube_small", category="prop", footprint_xy_m=(0.05, 0.05),
                              height_m=0.05, tags=["workpiece", "cube"]),
    "cube_medium": ObjectClass("cube_medium", category="prop", footprint_xy_m=(0.05, 0.05),
                               height_m=0.05, tags=["workpiece", "cube"]),
    "cube_large": ObjectClass("cube_large", category="prop", footprint_xy_m=(0.05, 0.05),
                              height_m=0.10, tags=["workpiece", "cube"]),
    "cylinder_small": ObjectClass("cylinder_small", category="prop", footprint_xy_m=(0.04, 0.04),
                                  height_m=0.05, tags=["workpiece"]),
    "cylinder_medium": ObjectClass("cylinder_medium", category="prop", footprint_xy_m=(0.04, 0.04),
                                   height_m=0.07, tags=["workpiece"]),
    "cylinder_large": ObjectClass("cylinder_large", category="prop", footprint_xy_m=(0.04, 0.04),
                                  height_m=0.10, tags=["workpiece"]),
    "sphere": ObjectClass("sphere", category="prop", footprint_xy_m=(0.05, 0.05),
                          height_m=0.05, tags=["workpiece"]),
    "screw": ObjectClass("screw", category="prop", footprint_xy_m=(0.01, 0.01),
                         height_m=0.03, tags=["workpiece"]),
    "nut": ObjectClass("nut", category="prop", footprint_xy_m=(0.012, 0.012),
                       height_m=0.01, tags=["workpiece"]),
    "bolt": ObjectClass("bolt", category="prop", footprint_xy_m=(0.012, 0.012),
                        height_m=0.03, tags=["workpiece"]),
    # Fixtures (12)
    "table_small": ObjectClass("table_small", category="fixture", footprint_xy_m=(0.8, 0.6),
                               height_m=0.40, tags=["fixture"]),
    "table_medium": ObjectClass("table_medium", category="fixture", footprint_xy_m=(1.2, 0.8),
                                height_m=0.40, tags=["fixture"]),
    "table_large": ObjectClass("table_large", category="fixture", footprint_xy_m=(2.0, 1.0),
                               height_m=0.75, tags=["fixture"]),
    "bin": ObjectClass("bin", category="fixture", footprint_xy_m=(0.4, 0.3),
                       height_m=0.15, tags=["fixture", "destination"]),
    "bin_large": ObjectClass("bin_large", category="fixture", footprint_xy_m=(0.6, 0.4),
                             height_m=0.20, tags=["fixture", "destination"]),
    "shelf": ObjectClass("shelf", category="fixture", footprint_xy_m=(1.2, 0.4),
                         height_m=1.20, tags=["fixture"]),
    # conveyor height_m = belt surface height above the frame base; frame ~0.05 m.
    "conveyor_short": ObjectClass("conveyor_short", category="fixture", footprint_xy_m=(1.5, 0.5),
                                  height_m=0.05, tags=["fixture", "dynamic"]),
    "conveyor_long": ObjectClass("conveyor_long", category="fixture", footprint_xy_m=(3.0, 0.5),
                                 height_m=0.05, tags=["fixture", "dynamic"]),
    # rotary_table: turntable disc, not including a pedestal; ~0.10 m thick.
    "rotary_table": ObjectClass("rotary_table", category="fixture", footprint_xy_m=(0.8, 0.8),
                                height_m=0.10, tags=["fixture", "dynamic"]),
    "gravity_dispenser": ObjectClass("gravity_dispenser", category="fixture", footprint_xy_m=(0.3, 0.3),
                                     height_m=0.30, tags=["fixture"]),
    "kit_tray": ObjectClass("kit_tray", category="fixture", footprint_xy_m=(0.4, 0.3),
                            height_m=0.05, tags=["fixture"]),
    # fence: industrial safety fence panel, ~2.0 m tall.
    "fence": ObjectClass("fence", category="fixture", footprint_xy_m=(2.0, 0.05),
                         height_m=2.00, tags=["fixture", "barrier"]),
    # Sensors (8)
    "camera_overhead": ObjectClass("camera_overhead", category="sensor", footprint_xy_m=(0.1, 0.1),
                                   height_m=0.05, tags=["sensor", "vision"]),
    "camera_side": ObjectClass("camera_side", category="sensor", footprint_xy_m=(0.1, 0.1),
                               height_m=0.05, tags=["sensor", "vision"]),
    # rtx_lidar: spinning lidar puck, ~0.08 m tall.
    "rtx_lidar": ObjectClass("rtx_lidar", category="sensor", footprint_xy_m=(0.08, 0.08),
                             height_m=0.08, tags=["sensor", "lidar"]),
    "barcode_reader": ObjectClass("barcode_reader", category="sensor", footprint_xy_m=(0.05, 0.05),
                                  height_m=0.05, tags=["sensor"]),
    "nir_spectrometer": ObjectClass("nir_spectrometer", category="sensor", footprint_xy_m=(0.1, 0.1),
                                    height_m=0.08, tags=["sensor"]),
    # proximity_sensor: flat disc, ~0.03 m.
    "proximity_sensor": ObjectClass("proximity_sensor", category="sensor", footprint_xy_m=(0.03, 0.03),
                                    height_m=0.03, tags=["sensor"]),
    # force_torque_sensor: disc between flange and tool, ~0.04 m.
    "force_torque_sensor": ObjectClass("force_torque_sensor", category="sensor", footprint_xy_m=(0.05, 0.05),
                                       height_m=0.04, tags=["sensor"]),
    # contact_sensor: thin pad, ~0.02 m.
    "contact_sensor": ObjectClass("contact_sensor", category="sensor", footprint_xy_m=(0.02, 0.02),
                                  height_m=0.02, tags=["sensor"]),
    # Environments (8)
    "wall": ObjectClass("wall", category="environment", footprint_xy_m=(2.0, 0.1),
                        height_m=2.00, tags=["environment", "barrier"]),
    "obstacle_box": ObjectClass("obstacle_box", category="environment", footprint_xy_m=(0.5, 0.5),
                                height_m=0.50, tags=["environment"]),
    "obstacle_cylinder": ObjectClass("obstacle_cylinder", category="environment", footprint_xy_m=(0.3, 0.3),
                                     height_m=0.50, tags=["environment"]),
    # groundplane: infinite plane — no physical z-extent.
    "groundplane": ObjectClass("groundplane", category="environment", footprint_xy_m=(20.0, 20.0),
                               height_m=0.0, tags=["environment"]),
    # lights: non-physical, no extent.
    "skydome_light": ObjectClass("skydome_light", category="environment", footprint_xy_m=(0.0, 0.0),
                                 height_m=0.0, tags=["light"]),
    "distant_light": ObjectClass("distant_light", category="environment", footprint_xy_m=(0.0, 0.0),
                                 height_m=0.0, tags=["light"]),
    # warehouse_box / kitchen_room: full room-scale environments, not stand-alone objects.
    "warehouse_box": ObjectClass("warehouse_box", category="environment", footprint_xy_m=(20.0, 20.0),
                                 height_m=0.0, tags=["environment"]),
    "kitchen_room": ObjectClass("kitchen_room", category="environment", footprint_xy_m=(4.0, 4.0),
                                height_m=0.0, tags=["environment"]),
    # Mobile-robot navigation aids (4)
    # nav2_waypoint / occupancy_marker: virtual markers, not physical objects.
    "nav2_waypoint": ObjectClass("nav2_waypoint", category="prop", footprint_xy_m=(0.05, 0.05),
                                 height_m=0.0, tags=["nav"]),
    "occupancy_marker": ObjectClass("occupancy_marker", category="prop", footprint_xy_m=(0.02, 0.02),
                                    height_m=0.0, tags=["nav"]),
    # person_cylinder: human-height obstacle proxy, ~1.70 m.
    "person_cylinder": ObjectClass("person_cylinder", category="prop", footprint_xy_m=(0.3, 0.3),
                                   height_m=1.70, tags=["person"]),
    # qr_marker: essentially flat sticker, ~0.002 m.
    "qr_marker": ObjectClass("qr_marker", category="prop", footprint_xy_m=(0.1, 0.1),
                             height_m=0.002, tags=["fiducial"]),
    # Tooling (10)
    # gripper_robotiq_2f85: 2-finger 85 mm gripper, closed length ~0.16 m.
    "gripper_robotiq_2f85": ObjectClass("gripper_robotiq_2f85", category="prop", footprint_xy_m=(0.1, 0.1),
                                        height_m=0.16, tags=["gripper"]),
    # gripper_robotiq_3finger: 3-finger gripper, taller body ~0.22 m.
    "gripper_robotiq_3finger": ObjectClass("gripper_robotiq_3finger", category="prop", footprint_xy_m=(0.12, 0.12),
                                           height_m=0.22, tags=["gripper"]),
    # suction_cup: cup body + fitting, ~0.06 m.
    "suction_cup": ObjectClass("suction_cup", category="prop", footprint_xy_m=(0.05, 0.05),
                               height_m=0.06, tags=["gripper"]),
    # screwdriver / drill: tool length along the hanging/stored axis, ~0.25 m.
    "screwdriver": ObjectClass("screwdriver", category="prop", footprint_xy_m=(0.02, 0.02),
                               height_m=0.25, tags=["tool"]),
    "drill": ObjectClass("drill", category="prop", footprint_xy_m=(0.2, 0.1),
                         height_m=0.25, tags=["tool"]),
    # welding_torch: torch body + cable adapter, ~0.30 m.
    "welding_torch": ObjectClass("welding_torch", category="prop", footprint_xy_m=(0.05, 0.05),
                                 height_m=0.30, tags=["tool"]),
    # paint_spray_nozzle: nozzle body, ~0.10 m.
    "paint_spray_nozzle": ObjectClass("paint_spray_nozzle", category="prop", footprint_xy_m=(0.05, 0.05),
                                      height_m=0.10, tags=["tool"]),
    # tool_changer: disc-shaped coupling, ~0.08 m thick.
    "tool_changer": ObjectClass("tool_changer", category="fixture", footprint_xy_m=(0.4, 0.4),
                                height_m=0.08, tags=["fixture"]),
    # fixture_clamp: clamp body height, ~0.10 m.
    "fixture_clamp": ObjectClass("fixture_clamp", category="fixture", footprint_xy_m=(0.1, 0.1),
                                 height_m=0.10, tags=["fixture"]),
    # magnetic_holder: flat disc magnet mount, ~0.04 m.
    "magnetic_holder": ObjectClass("magnetic_holder", category="fixture", footprint_xy_m=(0.05, 0.05),
                                   height_m=0.04, tags=["fixture"]),
}


def get_class(name: str) -> "ObjectClass | None":
    """Return the ``ObjectClass`` for *name*, or ``None`` if not in the palette."""
    return PALETTE.get(name)


def list_classes(category: "str | None" = None) -> "list[ObjectClass]":
    """Return all palette entries, optionally filtered to *category*.

    Args:
        category (str, optional): Category filter — ``"robot"``, ``"sensor"``,
            ``"fixture"``, ``"prop"``, or ``"environment"``. ``None`` returns
            the full palette.

    Returns:
        list[ObjectClass]: Matching entries.
    """
    if category is None:
        return list(PALETTE.values())
    return [c for c in PALETTE.values() if c.category == category]
