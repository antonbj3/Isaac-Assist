#!/usr/bin/env python3
"""routing_validate.py — first-class COLOR-SORT ROUTING detector (task #36).

The delivery/position gate counts "cubes in bins" but is BLIND to MIS-ROUTING: a cube that lands in
the WRONG-color bin still passes a delivered-count gate. This validator closes that hole for the
color-sort class — it checks each cube ended in its COLOR-ASSIGNED bin (xy-containment vs the ASSIGNED
bin, not any bin), the exact gap #36 names.

Method (hand-derived + proven on CP-16, cont.198 — eyes-first, RAW final positions):
  1. Parse `color_routing={color: bin_path}` from the template code (a clean dict literal).
  2. Map each source cube to a color (by name suffix `Cube_<color>` — the corpus convention; if a
     template doesn't name cubes by color, the cube is reported UNMAPPED, never silently passed).
  3. Build + run the template; read bin world-positions from the LIVE scene (robust — no parsing of
     create_bin/bin_specs literals, which vary: some templates use a loop).
  4. For each cube: CORRECT iff its final xy is within the ASSIGNED bin's footprint (+margin) and it is
     in-bin (not on the floor); else MIS-ROUTED (names the bin it actually landed in) / UNDELIVERED.

Honest scope: covers color-named-cube sorters (the common case). Mixed-SKU / bbox-less zone routing
(the cont.21 exception) needs the bbox compose_and_verify gate, not this. Reports UNMAPPED rather than
guessing. One local Kit (restart before run). Usage: routing_validate.py CP-16 [CP-17 ...]
"""
import asyncio, json, re, sys
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)


def _parse_color_routing(code):
    """Extract {color: bin_path} from a `color_routing={...}` dict literal in the template code."""
    m = re.search(r"color_routing\s*=\s*\{(.*?)\}", code, re.S)
    if not m:
        return {}
    out = {}
    for km, vm in re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', m.group(1)):
        out[km.lower()] = vm
    return out


def _source_paths(tpl):
    sa = tpl.get("simulate_args") or {}
    return list(sa.get("cube_paths") or ([sa["cube_path"]] if sa.get("cube_path") else []))


async def _validate_one(kit_tools, etc, name):
    tpl = json.load(open(f"{REPO}/workspace/templates/{name}.json"))
    code = tpl.get("code", "")
    routing = _parse_color_routing(code)
    if not routing:
        return {"template": name, "status": "NOT_A_COLOR_SORT (no color_routing dict)"}
    srcs = _source_paths(tpl)
    sa = tpl.get("simulate_args") or {}
    dur = int(sa.get("duration_s") or 120)
    steps = min(max(int(dur * 25), 2500), 5000)

    await kit_tools.exec_sync("import omni.usd; omni.usd.get_context().new_stage()", timeout=25)
    b = await asyncio.wait_for(etc(tpl), timeout=600)
    if not b.get("instantiated"):
        return {"template": name, "status": "BUILD_FAIL", "errors": str(b.get("errors"))[:200]}
    await kit_tools.exec_sync(
        "import omni.timeline,omni.kit.app; omni.timeline.get_timeline_interface().play()\n"
        f"_a=omni.kit.app.get_app()\nfor _ in range({steps}): _a.update()", timeout=int(steps/25)+90)

    spec = json.dumps({"routing": routing, "srcs": srcs})
    code_q = f'''
import omni.usd, json as _j
from pxr import UsdGeom, Sdf
stage=omni.usd.get_context().get_stage()
D=_j.loads({spec!r})
def ctr(p):
    pr=stage.GetPrimAtPath(Sdf.Path(p))
    if not pr or not pr.IsValid(): return None
    r=UsdGeom.Imageable(pr).ComputeWorldBound(0,UsdGeom.Tokens.default_).ComputeAlignedRange()
    if r.IsEmpty(): return None
    mn,mx=r.GetMin(),r.GetMax()
    return [(float(mn[i])+float(mx[i]))/2 for i in range(3)], [float(mx[i]-mn[i]) for i in range(3)]
bins={{}}
for color,bp in D["routing"].items():
    c=ctr(bp)
    if c: bins[color]={{"path":bp,"c":c[0],"half":[c[1][0]/2,c[1][1]/2]}}
res=[]
for sp in D["srcs"]:
    cc=ctr(sp)
    color=sp.rsplit("_",1)[-1].lower()
    row={{"cube":sp,"color":color}}
    if cc is None: row["verdict"]="MISSING"; res.append(row); continue
    cpos=cc[0]; row["pos"]=[round(x,3) for x in cpos]
    if color not in bins: row["verdict"]="UNMAPPED(cube color not in routing)"; res.append(row); continue
    if cpos[2]<0.6: row["verdict"]="UNDELIVERED(floor)"; res.append(row); continue
    # which bin footprint contains it (xy)?
    landed=[col for col,bn in bins.items()
            if abs(cpos[0]-bn["c"][0])<=bn["half"][0]+0.06 and abs(cpos[1]-bn["c"][1])<=bn["half"][1]+0.06]
    assigned=color
    if assigned in landed: row["verdict"]="CORRECT"
    elif landed: row["verdict"]="MIS-ROUTED->"+",".join(landed)
    else: row["verdict"]="NOT-IN-ANY-BIN"
    res.append(row)
print("ROUTING_RESULT "+_j.dumps(res))
'''
    rr = await kit_tools.exec_sync(code_q, timeout=60)
    out = (rr.get("output") or rr.get("error") or "")
    line = [l for l in out.splitlines() if l.startswith("ROUTING_RESULT")]
    rows = json.loads(line[-1].replace("ROUTING_RESULT ", "")) if line else []
    n_ok = sum(1 for r in rows if r.get("verdict") == "CORRECT")
    verdict = "ROUTED-OK" if (rows and n_ok == len(rows)) else ("ROUTING-FALSE" if rows else "NO_DATA")
    return {"template": name, "status": "OK", "verdict": verdict,
            "n_correct": n_ok, "n_cubes": len(rows), "rows": rows}


async def main():
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not names:
        print("usage: routing_validate.py <TEMPLATE> [TEMPLATE ...]", file=sys.stderr); return
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical
    for nm in names:
        r = await _validate_one(kit_tools, execute_template_canonical, nm)
        print(f"=== {nm}: {r.get('verdict', r.get('status'))} "
              f"({r.get('n_correct','?')}/{r.get('n_cubes','?')}) ===")
        for row in r.get("rows", []):
            print(f"    {row.get('cube'):26s} {row.get('verdict')}")

if __name__ == "__main__":
    asyncio.run(main())
