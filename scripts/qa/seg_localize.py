"""seg_localize — REUSABLE rigorous vision-localization (cont.319, Anton steer: layout-free, geometric).
Consolidates the proven camera-sensor + Gemini-point + instance-segmentation pipeline (CP-VISION-SEG/-YCB/
-CLUTTER/-DUP) into one importable block, so any vision task gets bild->fysisk-prim from GEOMETRY (per-pixel
instance segmentation), NOT a layout/horizontal-counting crutch — robust to clutter, duplicates, multi-row.

Key facts (proven): isaacsim.sensors.camera.Camera wrapped on a USD camera with the look-down transform
(AddTranslateOp only, NO rotation = down -Z) gives depth + instance_segmentation in our RPC Kit (the old
"RPC annotator limitation" was a camera-orientation misdiagnosis). Prims need a semantic label
(PrimSemanticData/set_semantic_label) to appear in instance-seg.

Usage:
    from seg_localize import capture_rgb_seg_kit_code, resolve_prim, gemini_point
    # 1. run capture_rgb_seg_kit_code(cam_pos, w, h, png, seg, ids) in Kit AFTER building your scene + labels
    # 2. (gx,gy) = gemini_point(png, "Point at the X")
    # 3. prim = resolve_prim(seg_path, ids_path, gx, gy)   # exact prim path, nearest-non-bg fallback
"""
import os, json, base64, urllib.request, re
import numpy as np


def capture_rgb_seg_kit_code(cam_pos, w, h, png, seg, ids, settle=60):
    """Return Kit-side python (str) that, run AFTER the scene + semantic labels exist, attaches the Camera
    sensor on a look-down USD camera and saves RGB (png), the instance-seg array (seg .npy) + idToLabels (ids)."""
    cx, cy, cz = cam_pos
    return (
        "import omni.usd, omni.kit.app, omni.timeline, numpy as _np, json as _json\n"
        "from pxr import UsdGeom as _UG, Gf as _Gf\n"
        "_st=omni.usd.get_context().get_stage()\n"
        f"_uc=_UG.Camera.Define(_st,'/World/SegCam'); _uc.GetClippingRangeAttr().Set(_Gf.Vec2f(0.01,100))\n"
        f"_UG.Xformable(_uc).AddTranslateOp().Set(({cx},{cy},{cz}))\n"  # translate-only -> looks straight down -Z
        "from isaacsim.sensors.camera import Camera as _Cam\n"
        f"_cam=_Cam(prim_path='/World/SegCam', frequency=20, resolution=({w},{h}))\n"
        "_cam.initialize(); _cam.add_instance_segmentation_to_frame()\n"
        "omni.timeline.get_timeline_interface().play()\n"
        f"_app=omni.kit.app.get_app()\nfor _ in range({settle}): _app.update()\n"
        "_fr=_cam.get_current_frame(); _rgba=_cam.get_rgba()\nfrom PIL import Image as _Img\n"
        f"_Img.fromarray(_rgba[:,:,:3].astype('uint8')).save('{png}')\n"
        "_seg=_fr['instance_segmentation']; _data=_np.asarray(_seg['data'])\n"
        f"_np.save('{seg}', _data); _json.dump(_seg.get('info',{{}}).get('idToLabels',{{}}), open('{ids}','w'))\n"
        "print('SEG_CAPTURE_DONE uniq='+str(len(_np.unique(_data))))\n")


def gemini_point(png, prompt, model="gemini-2.5-flash"):
    """Gemini-vision points at the target in the RGB image -> (x,y) pixel. Returns None if no point parsed."""
    os.environ.setdefault("GEMINI_PROVIDER_VERTEX", "1")
    import sys
    sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
    from service.isaac_assist_service.chat.llm_gemini import GeminiProvider
    gp = GeminiProvider(api_key="vertex-adc", model=model)
    body = {"contents": [{"role": "user", "parts": [
        {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(png, "rb").read()).decode()}},
        {"text": prompt}]}]}
    req = urllib.request.Request(gp.base_url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + gp._vertex_bearer()})
    ans = json.load(urllib.request.urlopen(req, timeout=60))["candidates"][0]["content"]["parts"][0]["text"]
    m = re.search(r'"x"\s*:\s*(\d+).*?"y"\s*:\s*(\d+)', ans, re.S)
    return (int(m.group(1)), int(m.group(2))) if m else None


def resolve_prim(seg_path, ids_path, gx, gy):
    """seg[pixel] -> exact prim path. Coarse Gemini points are absorbed: if (gx,gy) lands on
    background/unlabelled, snap to the NEAREST non-background pixel. Returns the prim path str (or None)."""
    seg = np.load(seg_path) if isinstance(seg_path, str) else np.asarray(seg_path)
    ids = json.load(open(ids_path)) if isinstance(ids_path, str) else dict(ids_path)
    h, w = seg.shape[:2]
    gx = min(max(int(gx), 0), w - 1); gy = min(max(int(gy), 0), h - 1)
    bg = [int(k) for k, v in ids.items() if v in ("BACKGROUND", "UNLABELLED")]
    pid = int(seg[gy, gx])
    if pid in bg:
        mask = ~np.isin(seg, bg); ys, xs = np.where(mask)
        if len(xs) == 0:
            return None
        i = int(np.argmin((xs - gx) ** 2 + (ys - gy) ** 2)); pid = int(seg[ys[i], xs[i]])
    lbl = ids.get(str(pid))
    return lbl if (lbl and lbl.startswith("/")) else None
