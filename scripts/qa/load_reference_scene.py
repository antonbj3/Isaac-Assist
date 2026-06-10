#!/usr/bin/env python3
"""Open a NVIDIA Isaac reference scene in the running Kit (RPC :8001) for inspection/time-series.
Usage: load_reference_scene.py <usd_path_or_name>
  - absolute path, OR a name that's searched under reference_scenes/ + the Isaac asset root.
Then use scripts/qa/scene_eyes.py-style probes, or just inspect the prim tree (printed)."""
import asyncio, sys, os, glob
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")
from service.isaac_assist_service.chat.tools import kit_tools
ROOTS = ["/home/anton/projects/Omniverse_Nemotron_Ext/reference_scenes",
         "/mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac"]
def resolve(q):
    if os.path.isfile(q): return q
    for r in ROOTS:
        hits = glob.glob(f"{r}/**/{q}", recursive=True) or glob.glob(f"{r}/**/*{q}*.usd", recursive=True)
        hits = [h for h in hits if ".thumbs" not in h and h.endswith(".usd")]
        if hits: return sorted(hits, key=len)[0]
    return None
async def main():
    p = resolve(sys.argv[1] if len(sys.argv) > 1 else "ur10_bin_stacking_short_suction.usd")
    if not p: print("NOT FOUND"); return
    print("OPENING", p)
    code = ('import omni.usd\nctx=omni.usd.get_context()\nctx.open_stage(%r)\nst=ctx.get_stage()\n'
            'print("OPENED", st.GetRootLayer().identifier.split("/")[-1])\n'
            'n=0\n'
            'for pr in st.Traverse():\n n+=1\nprint("prims", n, "default", st.GetDefaultPrim().GetPath() if st.GetDefaultPrim() else None)\n') % p
    r = await kit_tools.exec_sync(code, timeout=120)
    print((r.get("output") or str(r))[:1500])
asyncio.run(main())
