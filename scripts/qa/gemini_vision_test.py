"""Feasibility: does Gemini-VISION via Vertex work (image POST)? Generates a 3-colour
test image and asks Gemini to read the colours. Reuses GeminiProvider's Vertex base_url +
ADC bearer. If it reads them, the LLM-vision-pick path (render -> Gemini sees -> select) is feasible."""
import os, sys, json, base64, urllib.request
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
os.environ["GEMINI_PROVIDER_VERTEX"] = "1"
import numpy as np
from service.isaac_assist_service.chat.llm_gemini import GeminiProvider

# 3 colour bands left->right: red, green, blue
img = np.zeros((120, 360, 3), dtype=np.uint8)
img[:, 0:120] = (220, 20, 20); img[:, 120:240] = (20, 200, 20); img[:, 240:360] = (20, 20, 220)
try:
    from PIL import Image
    import io
    buf = io.BytesIO(); Image.fromarray(img).save(buf, format="PNG"); png = buf.getvalue()
except Exception:
    # minimal PNG fallback via imageio if PIL missing
    import imageio.v2 as iio, io
    buf = io.BytesIO(); iio.imwrite(buf, img, format="png"); png = buf.getvalue()

p = GeminiProvider(api_key="vertex-adc", model="gemini-2.5-flash")
body = {"contents": [{"role": "user", "parts": [
    {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png).decode()}},
    {"text": "This image has three vertical colour bands. List the three colours from LEFT to RIGHT, comma-separated, lowercase, nothing else."},
]}]}
req = urllib.request.Request(p.base_url, data=json.dumps(body).encode(),
                            headers={"Content-Type": "application/json", "Authorization": "Bearer " + p._vertex_bearer()})
try:
    resp = json.load(urllib.request.urlopen(req, timeout=60))
    txt = resp["candidates"][0]["content"]["parts"][0]["text"].strip()
    print("GEMINI-VISION reply:", repr(txt))
    ok = all(c in txt.lower() for c in ("red", "green", "blue"))
    print("VISION-FEASIBLE:", ok, "(reads all 3 colours)")
except Exception as e:
    err = e
    try: err = e.read().decode()[:300]
    except Exception: pass
    print("VISION CALL FAILED:", err)
