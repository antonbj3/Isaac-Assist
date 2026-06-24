"""LLM-VISION-pick (cont.319, Anton CV direction): Gemini SEES the rendered scene image
and identifies the object VISUALLY (prims named neutrally A/B/C so it can't cheat from the
name — it must read colour from the IMAGE). Builds 3 display-coloured cubes, captures the
viewport RGB, asks Gemini-vision (Vertex) which prim is the target colour, writes CP-LLM-VISION
with source_paths=[that prim]. Then scene_eyes verifies the right cube is delivered.
Run: python scripts/qa/llm_vision_pick.py "red" """
import os, sys, json, base64, urllib.request, asyncio
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
from service.isaac_assist_service.chat.tools import kit_tools
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

TARGET = sys.argv[1] if len(sys.argv) > 1 else "red"
# neutral prim names -> Gemini must read colour from the IMAGE, not the name
LAYOUT = [("/World/Cube_A", (1.0, 0.0, 0.0), [0.30, 0.16]),   # red,   left
          ("/World/Cube_B", (0.0, 1.0, 0.0), [0.42, 0.16]),   # green, middle
          ("/World/Cube_C", (0.0, 0.0, 1.0), [0.54, 0.16])]   # blue,  right
PNG = "/tmp/llm_vision_scene.png"

KIT = "import omni.usd, omni.kit.app, omni.kit.viewport.utility as vpu\n" \
      "from pxr import UsdGeom, Gf, UsdLux\n" \
      "omni.usd.get_context().new_stage(); st=omni.usd.get_context().get_stage()\n" \
      "UsdGeom.Xform.Define(st,'/World')\n" \
      "UsdLux.DistantLight.Define(st,'/World/L').CreateIntensityAttr(600)\n" \
      "UsdLux.DomeLight.Define(st,'/World/Dome').CreateIntensityAttr(1500)\n" \
      "g=UsdGeom.Cube.Define(st,'/World/Ground'); g.GetSizeAttr().Set(1.0)\n" \
      "gx=UsdGeom.Xformable(g); gx.AddTranslateOp().Set((0.42,0.16,-0.5)); gx.AddScaleOp().Set((4,4,0.5))\n" \
      "g.GetDisplayColorAttr().Set([(0.5,0.5,0.5)])\n"
for path, col, pos in LAYOUT:
    KIT += (f"c=UsdGeom.Cube.Define(st,'{path}'); c.GetSizeAttr().Set(0.05)\n"
            f"UsdGeom.Xformable(c).AddTranslateOp().Set(({pos[0]},{pos[1]},0.03))\n"
            f"c.GetDisplayColorAttr().Set([{col}])\n")
KIT += ("cam=UsdGeom.Camera.Define(st,'/World/Cam')\n"
        "cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.01,100))\n"
        "cam.GetHorizontalApertureAttr().Set(20.955); cam.GetVerticalApertureAttr().Set(20.955)\n"
        "cam.GetFocalLengthAttr().Set(16.0)\n"
        "_cx=UsdGeom.Xformable(cam); _cx.AddTranslateOp().Set((0.42,-0.05,0.70)); _cx.AddRotateXYZOp().Set((20.0,0.0,0.0))\n"
        "vp=vpu.get_active_viewport(); vp.camera_path='/World/Cam'\n"
        "app=omni.kit.app.get_app()\n"
        "for _ in range(40): app.update()\n"
        f"vpu.capture_viewport_to_file(vp, file_path='{PNG}')\n"
        "for _ in range(40): app.update()\n"
        "print('CAPTURED')\n")


async def render():
    r = await kit_tools.exec_sync(KIT, timeout=180)
    print("KIT:", (r.get("output", "") if isinstance(r, dict) else str(r))[-200:])


asyncio.run(render())
if not os.path.exists(PNG):
    print("NO PNG CAPTURED — abort"); sys.exit(1)
png = open(PNG, "rb").read()
print("PNG bytes:", len(png))

p = GeminiProvider(api_key="vertex-adc", model="gemini-2.5-flash")
prims = "\n".join(f"- {path} at x={pos[0]} (so {'left' if pos[0]<0.38 else 'right' if pos[0]>0.46 else 'middle'} in the image)" for path, _, pos in LAYOUT)
prompt = (f"The image shows 3 cubes left-to-right. The prims are:\n{prims}\n\n"
          f"Based ONLY on the colours you SEE in the image, which prim is the {TARGET.upper()} cube? "
          f"Reply with only the prim path (e.g. /World/Cube_A).")
body = {"contents": [{"role": "user", "parts": [
    {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png).decode()}}, {"text": prompt}]}]}
req = urllib.request.Request(p.base_url, data=json.dumps(body).encode(),
                            headers={"Content-Type": "application/json", "Authorization": "Bearer " + p._vertex_bearer()})
resp = json.load(urllib.request.urlopen(req, timeout=60))
ans = resp["candidates"][0]["content"]["parts"][0]["text"].strip()
pick = next((path for path, _, _ in LAYOUT if path in ans), None)
truth = {"red": "/World/Cube_A", "green": "/World/Cube_B", "blue": "/World/Cube_C"}.get(TARGET.lower())
print(f"TARGET={TARGET!r}  GEMINI-VISION-RAW={ans!r}  -> PICK={pick}  (truth={truth})  {'CORRECT' if pick==truth else 'WRONG'}")
