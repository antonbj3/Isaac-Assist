#!/usr/bin/env python3
"""real_asset_spawn.py — DIMENSION-HANDLING for real assets (Anton rescope 2026-06-19, cont.319e).

Real assets (YCB props, etc.) have arbitrary real-world dimensions vs our generated parametric primitives.
Picking a real object with the Franka jaw requires per-asset reasoning I'd been doing BY HAND 4x (measure the
USD bbox -> base-z so it rests ON the surface, orient the narrowest horizontal axis along the jaw close-axis
(world-Y, q=[0,1,0,0]), object-aware drop_height, flag tall/topple-risk, find the child Mesh for the collider).
This encapsulates that as a first-class helper so ANY real asset is auto-spawnable into a pick-place template.

compute_spawn_recipe(usd_path, surface_z=0.805) -> dict:
  extent_cm, base_offset_cm, mesh_leaf, spawn_z, rotation_euler, graspable, min_horiz_cm,
  drop_height, tall (topple-risk -> needs descend-to-place), collider_approx, note.

GROUNDED + VERIFIED against the 3 hand-tuned cont.319 templates (foam_brick native, gelatin_box native,
tomato_soup_can stood upright). Run `python real_asset_spawn.py <usd>` for a recipe, or `--selftest`.
"""
import sys, os, json

JAW_MAX = 0.075          # Franka parallel jaw usable opening (~8cm, keep margin)
TALL_THRESH = 0.09       # standing height above which a narrow object topples on a drop -> descend-to-place
ROUND_HINT = ("can", "bottle", "ball", "cylinder", "mug", "bowl", "cup", "pitcher")


def _bbox(usd_path):
    from pxr import Usd, UsdGeom
    s = Usd.Stage.Open(usd_path)
    dp = s.GetDefaultPrim()
    bb = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_])
    rng = bb.ComputeWorldBound(dp).ComputeAlignedRange()
    mn, mx = rng.GetMin(), rng.GetMax()
    ext = [mx[i] - mn[i] for i in range(3)]
    leaf = None
    for p in s.Traverse():
        if p.GetTypeName() == "Mesh":
            leaf = p.GetName(); break
    return ext, mn[2], leaf


def compute_spawn_recipe(usd_path, surface_z=0.805, clearance=0.005):
    ext, min_z, leaf = _bbox(usd_path)
    ex, ey, ez = ext
    name = os.path.basename(usd_path)[:-4].lower()
    is_roundish = any(k in name for k in ROUND_HINT)

    rotation = None
    # A clearly-elongated round/long object (a can/bottle lying down) is NOT graspable across its length AND
    # rolls -> stand it upright (long axis -> Z) so the jaw grips the now-vertical barrel.
    longest = max(ext); li = ext.index(longest)
    others = [e for i, e in enumerate(ext) if i != li]
    elongated = longest > 1.4 * max(others)
    if li in (0, 1) and (elongated and (is_roundish or min(others) >= JAW_MAX)):
        # rotate the horizontal long axis up to Z: long on X -> rot about Y(+90); long on Y -> rot about X(+90)
        rotation = [90, 0, 0] if li == 1 else [0, 90, 0]
        # recompute extents after standing: the long axis becomes vertical
        if li == 1:   # y<->z
            ex, ey, ez = ext[0], ext[2], ext[1]
        else:         # x<->z
            ex, ey, ez = ext[2], ext[1], ext[0]

    # after orientation: ensure the NARROWER horizontal axis is along Y (the jaw close-axis). If x is narrower
    # than y, add a 90-about-Z so the narrow side faces the jaw.
    rot_z_for_jaw = ex < ey - 1e-4
    if rot_z_for_jaw:
        if rotation is None:
            rotation = [0, 0, 90]
        else:
            rotation = [rotation[0], rotation[1], rotation[2] + 90]
        ex, ey = ey, ex

    min_horiz = min(ex, ey)
    max_horiz = max(ex, ey)
    jaw_fits = min_horiz < JAW_MAX
    horiz_aspect = max_horiz / max(min_horiz, 1e-6)
    z_ratio = ez / max(min_horiz, 1e-6)
    height = ez
    tall = height > TALL_THRESH
    # The bbox-CENTER grasp is RELIABLE only for COMPACT BOX-LIKE objects. ELONGATED (high horizontal aspect) or
    # CURVED/HOLLOW (tall bbox vs grip width) objects put the body OFF the bbox center -> the grasp slips/never
    # seats. PROVEN by the CP-YCB-BANANA adversarial audit (cont.319g): banana jaw_fits (3.9cm) but the grasp
    # NEVER seated (curved body off the bbox center, toppled, not delivered). So graspable = jaw_fits AND box-like.
    box_like = horiz_aspect < 2.0 and z_ratio < 1.8
    graspable = jaw_fits and box_like
    # base sits on the surface: spawn the wrapping Xform so the asset's lowest point clears the surface.
    # (min_z is the asset's base relative to its origin in the NATIVE frame; for a standing rotation the half
    # height is ez/2, origin-centered, so base offset = -ez/2.)
    base_off = (-ez / 2.0) if rotation else min_z
    spawn_z = surface_z + (-base_off) + clearance
    # object-aware drop: release just enough to clear a typical bin rim; tall objects can't be made upright by
    # drop_height alone (need descend-to-place) -> flag.
    drop_height = round(0.10 + height, 3) if not tall else round(0.10 + height, 3)
    approx = "convexDecomposition" if is_roundish and ("bowl" in name or "mug" in name) else "convexHull"

    note = []
    if not jaw_fits:
        note.append("min horiz %.1fcm EXCEEDS jaw — scale down or different grasp" % (min_horiz * 100))
    elif not box_like:
        note.append("jaw-fits but NOT box-like (aspect %.1f, z/grip %.1f) — bbox-center grasp UNRELIABLE "
                    "(elongated/curved/hollow); needs a Kit grasp-test or complex-mesh grasp" % (horiz_aspect, z_ratio))
    if tall:
        note.append("TALL (%.1fcm) — topples on drop into a bin; needs DESCEND-TO-PLACE for upright" % (height * 100))
    if rotation:
        note.append("reoriented to stand/face the jaw")
    return {
        "asset": os.path.basename(usd_path),
        "mesh_leaf": leaf,
        "extent_cm": [round(e * 100, 1) for e in ext],
        "oriented_hwd_cm": [round(ex * 100, 1), round(ey * 100, 1), round(ez * 100, 1)],
        "rotation_euler": rotation,
        "spawn_z": round(spawn_z, 3),
        "graspable": graspable,
        "jaw_fits": jaw_fits,
        "horiz_aspect": round(horiz_aspect, 2),
        "z_grip_ratio": round(z_ratio, 2),
        "min_horiz_cm": round(min_horiz * 100, 1),
        "tall_needs_descend_place": tall,
        "drop_height": drop_height,
        "collider_approx": approx,
        "note": "; ".join(note) or "graspable in computed orientation",
    }


YCB = "/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Props/YCB/Axis_Aligned"
import os as _os
REPO = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))


def emit_template(asset_usd, task_id, prim_name="Item_1", x=0.2, y=0.4,
                  base_template="CP-YCB-01", surface_z=0.805, write=True):
    """Generate a pick-place template JSON for ANY real asset, using compute_spawn_recipe for the
    dimension-handling (base-z, jaw-fit orientation, collider, mesh leaf). Returns (template_dict, recipe).
    This is the asset->working-template generator for real-asset scene-generation at scale."""
    import json
    r = compute_spawn_recipe(asset_usd, surface_z=surface_z)
    base = json.load(open(f"{REPO}/workspace/templates/{base_template}.json"))
    rot = r["rotation_euler"]; rl = f", rotation_euler={rot}" if rot else ""
    leaf = r["mesh_leaf"]; z = r["spawn_z"]
    b = "{{"; e = "}}"  # literal {{role}} placeholders survive into the saved template for the instantiator
    code = (
        f"# Auto-generated by real_asset_spawn.emit_template — real asset {_os.path.basename(asset_usd)}\n"
        f"# recipe: {r['note']}\n"
        f"create_scene_baseline(include_ground=False, table_size=[2.0, 1.0])\n"
        f"robot_wizard(robot_name={b}primary_robot.class{e}, dest_path={b}primary_robot.path{e}, position={b}primary_robot.position{e}, orientation={b}primary_robot.orientation{e})\n"
        f"create_conveyor(prim_path={b}input_conveyor.path{e}, position={b}input_conveyor.position{e}, size={b}input_conveyor.size{e}, surface_velocity={b}input_conveyor.surface_velocity{e})\n"
        f'create_prim(prim_path="/World/{prim_name}", prim_type="Xform", position=[{x}, {y}, {z}]{rl})\n'
        f'add_reference(prim_path="/World/{prim_name}", reference_path="{asset_usd}")\n'
        f'for api in ("PhysicsRigidBodyAPI", "PhysicsMassAPI", "PhysxRigidBodyAPI"):\n'
        f'    apply_api_schema(prim_path="/World/{prim_name}", schema_name=api)\n'
        f'apply_api_schema(prim_path="/World/{prim_name}/{leaf}", schema_name="PhysicsCollisionAPI")\n'
        f'simplify_collision(prim_path="/World/{prim_name}/{leaf}", approximation="{r["collider_approx"]}")\n'
        f'bulk_set_attribute(prim_paths=["/World/{prim_name}"], attr="physxRigidBody:sleepThreshold", value=0.0)\n'
        f'apply_physics_material(prim_path="/World/{prim_name}/{leaf}", material_name="rubber")\n'
        f"create_bin(prim_path={b}primary_destination.path{e}, position={b}primary_destination.position{e}, size={b}primary_destination.size{e})\n"
        f"add_proximity_sensor(sensor_path={b}pick_sensor.path{e}, position={b}pick_sensor.position{e}, size={b}pick_sensor.size{e})\n"
        f'setup_pick_place_controller(robot_path={b}primary_robot.path{e}, target_source="curobo", sensor_path={b}pick_sensor.path{e}, belt_path={b}input_conveyor.path{e}, source_paths=["/World/{prim_name}"], destination_path={b}primary_destination.path{e}, planning_obstacles=["/World/Table", {b}input_conveyor.path{e}, {b}primary_destination.path{e}])\n'
    )
    t = json.loads(json.dumps(base))
    t["task_id"] = task_id
    t["goal"] = f"Auto-generated real-asset pick-place: Franka picks {_os.path.basename(asset_usd)} into a bin. {r['note']}"
    t["code_template"] = code; t["code"] = code
    t["verified_status"] = "UNVERIFIED (auto-generated by real_asset_spawn.emit_template)"
    for k in ("simulate_args", "simulate_args_template"):
        if isinstance(t.get(k), dict):
            t[k]["cube_paths"] = [f"/World/{prim_name}"]; t[k]["cube_path"] = f"/World/{prim_name}"
            t[k]["target_path"] = "/World/Bin"; t[k]["duration_s"] = 40
    if write:
        json.dump(t, open(f"{REPO}/workspace/templates/{task_id}.json", "w"), indent=2)
    return t, r


def container_recipe(usd_path, surface_z=0.75, clearance=0.003):
    """DESTINATION recipe for a real-asset CONTAINER (tote/bin/crate) — the analog of compute_spawn_recipe for
    destinations (cont.319n: hand-found via the KLT tote, now first-class). Real containers ship with a SOLID
    collision approximation (boundingCube / convexHull) so a delivered object PERCHES on top instead of entering;
    to use one as a destination its collision mesh must be overridden to 'none' (triangle mesh = the actual HOLLOW
    interior). Returns the spawn pose (base on the surface) + the collision-mesh paths needing the hollow fix."""
    from pxr import Usd, UsdGeom, UsdPhysics
    s = Usd.Stage.Open(usd_path)
    dp = s.GetDefaultPrim()
    bb = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_])
    rng = bb.ComputeWorldBound(dp).ComputeAlignedRange()
    mn, mx = rng.GetMin(), rng.GetMax()
    ext = [mx[i] - mn[i] for i in range(3)]
    base_off = mn[2]                                  # asset base relative to origin (native)
    spawn_z = round(surface_z + (-base_off) + clearance, 3)   # so the container bottom rests on the surface
    SOLID = ("boundingCube", "boundingSphere", "convexHull", "convexDecomposition")
    col_meshes = []
    for p in s.Traverse():
        if p.HasAPI(UsdPhysics.MeshCollisionAPI):
            ap = UsdPhysics.MeshCollisionAPI(p).GetApproximationAttr().Get()
            rel = str(p.GetPath()).replace(str(dp.GetPath()), "").lstrip("/")
            col_meshes.append({"rel_path": rel, "approximation": ap, "needs_hollow_fix": ap in SOLID})
    needs_fix = any(m["needs_hollow_fix"] for m in col_meshes)
    return {
        "asset": os.path.basename(usd_path),
        "extent_cm": [round(e * 100, 1) for e in ext],
        "spawn_z": spawn_z,
        "interior_floor_z": round(surface_z + clearance, 3),
        "collision_meshes": col_meshes,
        "needs_hollow_collision_fix": needs_fix,
        "fix": ("for each collision mesh, simplify_collision(prim_path=<dest>/<rel_path>, approximation='none') "
                "so the container is HOLLOW and objects ENTER it") if needs_fix else "collision already non-solid",
    }


def _selftest():
    # reproduce the 3 hand-tuned cont.319 choices
    cases = {
        "061_foam_brick":      dict(rotation_euler=None,       graspable=True,  tall=False),  # native flat box -> delivered upright
        "009_gelatin_box":     dict(rotation_euler=None,       graspable=True,  tall=False),  # native thin box  -> delivered upright
        "005_tomato_soup_can": dict(rotation_euler=[90, 0, 0], graspable=True,  tall=True),   # stand upright    -> delivered (collection, topples)
        "011_banana":          dict(rotation_euler=None,       graspable=False, tall=False),  # CURVED -> grasp NEVER seated (CP-YCB-BANANA audit cont.319g); jaw_fits but not box-like
    }
    ok = True
    for obj, exp in cases.items():
        r = compute_spawn_recipe(f"{YCB}/{obj}.usd")
        got = dict(rotation_euler=r["rotation_euler"], graspable=r["graspable"], tall=r["tall_needs_descend_place"])
        match = got == exp
        ok &= match
        print(("OK  " if match else "FAIL") + f" {obj:22} got={got}  exp={exp}  spawn_z={r['spawn_z']}")
    # container_recipe regression: the KLT tote (cont.319n) must flag its SOLID boundingCube collision + find the /Visuals/ mesh path
    KLT = "/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/Props/KLT_Bin/small_KLT_visual_collision.usd"
    if os.path.exists(KLT):
        cr = container_recipe(KLT)
        cok = cr["needs_hollow_collision_fix"] and any(m["rel_path"] == "Visuals/FOF_Mesh_Magenta_Box" for m in cr["collision_meshes"])
        ok &= cok
        print(("OK   " if cok else "FAIL ") + "container KLT_tote      needs_hollow_fix=%s meshes=%s" % (cr["needs_hollow_collision_fix"], [m["rel_path"] for m in cr["collision_meshes"]]))
    print("SELFTEST", "PASS" if ok else "FAIL — recipe diverges from hand-tuned templates")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    elif len(sys.argv) > 1:
        print(json.dumps(compute_spawn_recipe(sys.argv[1]), indent=2))
    else:
        print("usage: real_asset_spawn.py <usd_path> | --selftest", file=sys.stderr); sys.exit(2)
