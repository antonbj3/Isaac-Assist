"""RIGOROUS vision SORT (cont.319, Anton: handle complex setups). The layout-crutch sort (left-to-right
mapping) MIS-MAPS a 2-row / checkerboard scene. The seg-based sort ENUMERATES every prim from instance
segmentation (no layout), reads each prim's colour from the RGB at its segmentation region (vision-derived,
not the prim name), and routes each to its colour bin. Neutral prim names (Cube_a/b/c/d) -> routing comes
from VISION + segmentation, not position or name. scene_eyes + routing_validate verify each in its colour bin.
Run: python scripts/qa/vision_seg_sort.py"""
import os, sys, json, asyncio
import numpy as np
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext/scripts/qa")
from service.isaac_assist_service.chat.tools import kit_tools
from seg_localize import capture_rgb_seg_kit_code

# 2x2 CHECKERBOARD (left-to-right ordering is ambiguous + mis-maps): a=red, b=blue, c=blue, d=red
CUBES = {"Cube_a": ((1.0, 0.0, 0.0), [0.35, 0.14]), "Cube_b": ((0.0, 0.0, 1.0), [0.53, 0.14]),
         "Cube_c": ((0.0, 0.0, 1.0), [0.35, 0.22]), "Cube_d": ((1.0, 0.0, 0.0), [0.53, 0.22])}
TRUTH = {"Cube_a": "red", "Cube_b": "blue", "Cube_c": "blue", "Cube_d": "red"}
BINS = {"red": "/World/Bin_red", "blue": "/World/Bin_blue"}
PNG = "/tmp/vss_rgb.png"; SEG = "/tmp/vss_seg.npy"; IDS = "/tmp/vss_ids.json"
W, H = 640, 480

build = ("import omni.usd, omni.timeline\nfrom pxr import UsdGeom, UsdPhysics, Gf, UsdLux\n"
         "omni.usd.get_context().new_stage(); st=omni.usd.get_context().get_stage()\n"
         "UsdPhysics.Scene.Define(st,'/World/PhysicsScene')\n"
         "UsdLux.DistantLight.Define(st,'/World/L').CreateIntensityAttr(800); UsdLux.DomeLight.Define(st,'/World/Dome').CreateIntensityAttr(1200)\n")
for p, (rgb, (x, y)) in CUBES.items():
    pp = "/World/" + p
    build += (f"c=UsdGeom.Cube.Define(st,'{pp}'); c.GetSizeAttr().Set(0.05)\n"
              f"UsdGeom.Xformable(c).AddTranslateOp().Set(({x},{y},0.83)); c.GetDisplayColorAttr().Set([{rgb}])\n"
              f"UsdPhysics.CollisionAPI.Apply(st.GetPrimAtPath('{pp}'))\n"
              f"try:\n    from semantics.schema.editor import PrimSemanticData\n    PrimSemanticData(st.GetPrimAtPath('{pp}')).add_entry('class','{p}')\nexcept Exception: pass\n")
build += capture_rgb_seg_kit_code((0.45, 0.20, 1.6), W, H, PNG, SEG, IDS, settle=50)


async def run():
    r = await kit_tools.exec_sync(build, timeout=200)
    return (r.get("output", "") if isinstance(r, dict) else str(r))

print("P1:", [l for l in asyncio.run(run()).splitlines() if "SEG_CAPTURE_DONE" in l or "Error" in l][:2])
if not (os.path.exists(SEG) and os.path.exists(PNG)):
    print("capture failed"); sys.exit(1)

# RIGOROUS: enumerate prims from seg, read each prim's colour from RGB at its seg region (vision-derived)
from PIL import Image
rgb = np.array(Image.open(PNG).convert("RGB"))
seg = np.load(SEG); ids = json.load(open(IDS))
prim_color = {}
for k, lbl in ids.items():
    if not lbl.startswith("/World/Cube_"): continue
    ys, xs = np.where(seg == int(k))
    if len(xs) == 0: continue
    mr, mg, mb = rgb[ys, xs, 0].mean(), rgb[ys, xs, 1].mean(), rgb[ys, xs, 2].mean()
    col = "red" if mr > mg and mr > mb else ("blue" if mb > mr and mb > mg else "green")
    prim_color[lbl.split("/")[-1]] = col
ok = all(prim_color.get(p) == TRUTH[p] for p in TRUTH)
print("VISION-derived colours:", prim_color, "vs truth", TRUTH, "->", "ALL CORRECT" if ok else "MISCLASSIFIED")

# build the sort template: labels from VISION (not name/position), color_routing
lines = ['create_scene_baseline(include_ground=False, table_size=[2.0, 1.0])', '',
         'robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0, 0, 0.75], orientation=[0.7071068, 0, 0, 0.7071068])', '']
for p, (rgb_c, (x, y)) in CUBES.items():
    col = prim_color.get(p, "red")
    pp = "/World/" + p
    lines += [f'create_prim(prim_path="{pp}", prim_type="Cube", position=[{x}, {y}, 0.83], size=0.05)',
              'for _api in ("PhysicsRigidBodyAPI","PhysicsCollisionAPI","PhysicsMassAPI"):',
              f'    apply_api_schema(prim_path="{pp}", schema_name=_api)',
              f'set_semantic_label(prim_path="{pp}", class_name="{col}", semantic_type="color")']
cr = ", ".join(f'"{c}": "{BINS[c]}"' for c in BINS)
srcs = ",".join(f'"/World/{p}"' for p in CUBES)
lines += ['', 'create_bin(prim_path="/World/Bin_red", position=[-0.15, -0.45, 0.75], size=[0.22, 0.22, 0.12])',
          'create_bin(prim_path="/World/Bin_blue", position=[0.18, -0.45, 0.75], size=[0.22, 0.22, 0.12])', '',
          'setup_pick_place_controller(', '    robot_path="/World/Franka",', '    robot_family="franka",', '    target_source="curobo",',
          f'    source_paths=[{srcs}],', '    destination_path="/World/Bin_red",', '    color_routing={' + cr + '},',
          '    planning_obstacles=["/World/Table"],', ')']
code = "\n".join(lines) + "\n"
routing = {p: BINS[prim_color.get(p, "red")] for p in CUBES}
tpl = {"task_id": "CP-VISION-SORT-SEG", "code": code, "code_template": code,
       "goal": f"Rigorous vision sort: segmentation enumerated the prims + read each colour from RGB {prim_color} (NO layout/name); Franka routes each to its colour bin.",
       "role_defaults": {"primary_robot": {"path": "/World/Franka", "class": "franka_panda", "position": [0, 0, 0.75], "orientation": [0.7071068, 0, 0, 0.7071068]},
                         "primary_destination": {"path": "/World/Bin_red", "position": [-0.15, -0.45, 0.75], "size": [0.22, 0.22, 0.12]}},
       "_vision_sort_seg": {"prim_color": prim_color, "routing": routing},
       "verified_status": f"VISION-SORT-SEG (cont.319): colours from segmentation+RGB {prim_color}. UNVERIFIED."}
json.dump(tpl, open("/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-VISION-SORT-SEG.json", "w"), indent=2)
print("WROTE CP-VISION-SORT-SEG.json routing=%s" % routing)
