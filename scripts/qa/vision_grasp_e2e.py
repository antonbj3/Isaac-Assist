"""CV-grasp END-TO-END (cont.319, Anton CV direction): camera-perception-driven grasp,
NO ground-truth for selection/localisation. Flow:
 1. Kit: build 3 colour collision-cubes + offset-overhead camera, capture RGB.
 2. SAM2: segment the TARGET colour -> mask centroid pixel.
 3. Kit: camera-ray for that pixel -> physx-raycast -> 3D hit + HIT PRIM (collision name).
 4. Write CP-VISION-GRASP (Franka + same cubes + bin + controller source_paths=[hit prim]).
 5. scene_eyes verifies the hit (=target colour) cube is delivered + others untouched.
Run: python scripts/qa/vision_grasp_e2e.py red"""
import os, sys, json, asyncio
import numpy as np
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
from service.isaac_assist_service.chat.tools import kit_tools

TARGET = sys.argv[1] if len(sys.argv) > 1 else "red"
CUBES = {"red": ((1.0, 0.0, 0.0), [0.32, 0.16]),
         "green": ((0.0, 1.0, 0.0), [0.42, 0.16]),
         "blue": ((0.0, 0.0, 1.0), [0.52, 0.16])}
Z = 0.80
PNG = "/tmp/vision_grasp_scene.png"
W, H = 1280, 720
CAM = (0.42, -0.10, 1.55)   # offset in -y + high -> cubes at +y are off-axis (no directly-below specular)

# --- scene-build code shared by perception (collision-only) ---
build = ("import omni.usd, omni.kit.app, omni.kit.viewport.utility as vpu, omni.timeline\n"
         "from pxr import UsdGeom, UsdPhysics, Gf, UsdLux\n"
         "omni.usd.get_context().new_stage(); st=omni.usd.get_context().get_stage()\n"
         "UsdPhysics.Scene.Define(st,'/World/PhysicsScene')\n"
         "UsdLux.DistantLight.Define(st,'/World/L').CreateIntensityAttr(600)\n"
         "UsdLux.DomeLight.Define(st,'/World/Dome').CreateIntensityAttr(1500)\n")
for name, (col, pos) in CUBES.items():
    p = f"/World/Cube_{name}"
    build += (f"c=UsdGeom.Cube.Define(st,'{p}'); c.GetSizeAttr().Set(0.05)\n"
              f"UsdGeom.Xformable(c).AddTranslateOp().Set(({pos[0]},{pos[1]},{Z}))\n"
              f"c.GetDisplayColorAttr().Set([{col}])\n"
              f"UsdPhysics.CollisionAPI.Apply(st.GetPrimAtPath('{p}'))\n")
build += (f"cam=UsdGeom.Camera.Define(st,'/World/Cam'); cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.01,100))\n"
          "cam.GetHorizontalApertureAttr().Set(20.955); cam.GetVerticalApertureAttr().Set(20.955); cam.GetFocalLengthAttr().Set(14.0)\n"
          f"UsdGeom.Xformable(cam).AddTranslateOp().Set({CAM})\n"
          "vp=vpu.get_active_viewport(); vp.camera_path='/World/Cam'\n"
          "app=omni.kit.app.get_app(); omni.timeline.get_timeline_interface().play()\n"
          "for _ in range(50): app.update()\n"
          f"vpu.capture_viewport_to_file(vp, file_path='{PNG}')\n"
          "for _ in range(40): app.update()\n"
          "print('SCENE_BUILT')\n")


async def phase1():
    r = await kit_tools.exec_sync(build, timeout=180)
    print("P1:", (r.get("output", "") if isinstance(r, dict) else str(r))[-120:])


asyncio.run(phase1())
if not os.path.exists(PNG):
    print("NO PNG"); sys.exit(1)

# --- phase 2: SAM2 on the target colour ---
from PIL import Image
from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor
img = np.array(Image.open(PNG).convert("RGB"))
pred = SAM2ImagePredictor(build_sam2("configs/sam2.1/sam2.1_hiera_s.yaml",
       "/home/anton/projects/Omniverse_Nemotron_Ext/vision_models/sam2.1_hiera_small.pt", device="cuda"))
pred.set_image(img)
r, g, b = img[..., 0].astype(int), img[..., 1].astype(int), img[..., 2].astype(int)
seed = {"red": (r > 110) & (g < 90) & (b < 90), "green": (g > 110) & (r < 90) & (b < 90),
        "blue": (b > 110) & (r < 90) & (g < 90)}[TARGET]
ys, xs = np.where(seed)
if len(xs) == 0:
    print("TARGET colour %s not visible in render" % TARGET); sys.exit(1)
px, py = int(np.median(xs)), int(np.median(ys))
masks, scores, _ = pred.predict(point_coords=np.array([[px, py]]), point_labels=np.array([1]), multimask_output=False)
mys, mxs = np.where(masks[0].astype(bool))
cpx, cpy = int(mxs.mean()), int(mys.mean())
print("SAM2 target=%s mask centroid pixel=(%d,%d) score=%.3f" % (TARGET, cpx, cpy, scores[0]))

# --- phase 3: camera-ray + physx raycast -> hit prim ---
ray = (f"import omni.usd\nfrom pxr import UsdGeom\nfrom omni.physx import get_physx_scene_query_interface\n"
       "import numpy as np\nst=omni.usd.get_context().get_stage()\n"
       "cam=st.GetPrimAtPath('/World/Cam'); cg=UsdGeom.Camera(cam)\n"
       f"foc=cg.GetFocalLengthAttr().Get(); hap=cg.GetHorizontalApertureAttr().Get()\n"
       f"W,H={W},{H}; fx=foc*W/hap; fy=fx; cx=W/2.0; cy=H/2.0\n"  # viewport CONFORMS vert-aperture -> square px -> fy=fx
       "m=UsdGeom.Xformable(cam).ComputeLocalToWorldTransform(0)\n"
       "t=np.array([m[3][0],m[3][1],m[3][2]]); R=np.array([[m[0][0],m[0][1],m[0][2]],[m[1][0],m[1][1],m[1][2]],[m[2][0],m[2][1],m[2][2]]])\n"
       f"px,py={cpx},{cpy}\n"
       "d=R@np.array([(px-cx)/fx,-(py-cy)/fy,-1.0]); d=d/np.linalg.norm(d)\n"
       "sqi=get_physx_scene_query_interface()\n"
       "hit=sqi.raycast_closest((float(t[0]),float(t[1]),float(t[2])),(float(d[0]),float(d[1]),float(d[2])),5.0)\n"
       "print('RAYHIT', hit.get('hit') if isinstance(hit,dict) else None, hit.get('collision') if isinstance(hit,dict) else None, hit.get('position') if isinstance(hit,dict) else None)\n")


async def phase3():
    r = await kit_tools.exec_sync(ray, timeout=120)
    return (r.get("output", "") if isinstance(r, dict) else str(r))

out = asyncio.run(phase3())
print("P3:", [l for l in out.splitlines() if "RAYHIT" in l][:1])
hitline = next((l for l in out.splitlines() if "RAYHIT" in l), "")
hit_prim = None
for name in CUBES:
    if f"/World/Cube_{name}" in hitline:
        hit_prim = f"/World/Cube_{name}"; break
print("CAMERA-PERCEIVED HIT PRIM:", hit_prim, "(target was", TARGET + ")",
      "CORRECT" if hit_prim == f"/World/Cube_{TARGET}" else "WRONG")
if hit_prim is None:
    print("no camera hit -> abort grasp"); sys.exit(1)

# --- phase 4: write CP-VISION-GRASP template, source_paths = the CAMERA-PERCEIVED prim ---
GZ = 0.79  # graspable band (settles on table); SAME x,y as perception cubes
GCUBES = {f"/World/Cube_{n}": (n.upper(), [p[0], p[1], GZ]) for n, (c, p) in CUBES.items()}
lines = ['create_scene_baseline(include_ground=False, table_size=[2.0, 1.0])', '',
         'robot_wizard(robot_name="franka_panda", dest_path="/World/Franka", position=[0, 0, 0.75], orientation=[0.7071068, 0, 0, 0.7071068])', '']
for p, (col, pos) in GCUBES.items():
    lines.append(f'create_prim(prim_path="{p}", prim_type="Cube", position={pos}, size=0.05)')
    lines.append('for _api in ("PhysicsRigidBodyAPI","PhysicsCollisionAPI","PhysicsMassAPI"):')
    lines.append(f'    apply_api_schema(prim_path="{p}", schema_name=_api)')
    lines.append(f'set_semantic_label(prim_path="{p}", semantic_type="color", class_name="{col.lower()}")')
lines += ['', 'create_bin(prim_path="/World/Bin", position=[0.0, -0.45, 0.75], size=[0.3, 0.3, 0.15])', '',
          'setup_pick_place_controller(',
          '    robot_path="/World/Franka",', '    robot_family="franka",', '    target_source="curobo",',
          f'    source_paths=["{hit_prim}"],',  # camera-perceived, NOT ground-truth
          '    destination_path="/World/Bin",', '    planning_obstacles=["/World/Table"],', ')']
body = "\n".join(lines) + "\n"
tpl = {"task_id": "CP-VISION-GRASP",
       "goal": f"CV-grasp: camera (SAM2+raycast) perceived {hit_prim} as the {TARGET} cube WITHOUT ground-truth; Franka picks ONLY it.",
       "code": body, "code_template": body,
       "role_defaults": {"primary_robot": {"path": "/World/Franka", "class": "franka_panda", "position": [0, 0, 0.75], "orientation": [0.7071068, 0, 0, 0.7071068]},
                         "primary_destination": {"path": "/World/Bin", "position": [0.0, -0.45, 0.75], "size": [0.3, 0.3, 0.15]}},
       "_vision_grasp": {"target_colour": TARGET, "perceived_prim": hit_prim, "sam2_pixel": [cpx, cpy], "raycast_from": "camera-ray+physx"},
       "verified_status": f"CV-GRASP (cont.319): source_paths from CAMERA perception ({hit_prim}), no ground-truth. UNVERIFIED."}
json.dump(tpl, open("/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/CP-VISION-GRASP.json", "w"), indent=2)
print("WROTE CP-VISION-GRASP.json source_paths=[%s]" % hit_prim)
print("NEXT: python scripts/qa/scene_eyes.py CP-VISION-GRASP 150  (verify %s delivered, others untouched)" % hit_prim)
