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
guessing. CONFOUNDED (cont.200) when the SCENE has colors NOT in color_routing (e.g. CP-35 has a 5th 'd'
color / 10 cubes vs the routed 8) — the bin-containment read mis-flags; cross-check with scene_eyes for
such. A NOT-IN-ANY-BIN / undelivered flag is AMBIGUOUS (real scatter vs still-feeding vs tool-confound) —
always disambiguate against scene_eyes before trusting it. One local Kit (restart before run).
Usage: routing_validate.py CP-16 [CP-17 ...]
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
    # cont.200: run the FULL authored duration (multi-cube sorters are throughput-paced) — the old
    # min(...,5000)-step cap UNDER-RAN long sorters (CP-35 read 3/8 at ~150s but 9/10 at 175s = the
    # cont.188 under-duration trap reproduced in this tool). Scale to dur, generous cap.
    steps = min(max(int(dur * 40), 3000), 8000)

    await kit_tools.exec_sync("import omni.usd; omni.usd.get_context().new_stage()", timeout=25)
    b = await asyncio.wait_for(etc(tpl), timeout=600)
    if not b.get("instantiated"):
        return {"template": name, "status": "BUILD_FAIL", "errors": str(b.get("errors"))[:200]}
    # capture START positions (pre-play) so a cube still near its start = NEVER-PICKED/STILL-FEEDING
    # (under-duration), distinct from a scattered/dropped cube — the cont.188 still-feeding discriminator.
    start_q = "import omni.usd,json as _j\nfrom pxr import UsdGeom,Sdf\ns=omni.usd.get_context().get_stage()\no={}\n" \
              + f"for p in {json.dumps(srcs)}:\n" \
              + "    pr=s.GetPrimAtPath(Sdf.Path(p))\n    \n    if pr and pr.IsValid():\n" \
              + "        t=UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(0).ExtractTranslation()\n" \
              + "        o[p]=[float(t[0]),float(t[1]),float(t[2])]\nprint('START '+_j.dumps(o))"
    rs = await kit_tools.exec_sync(start_q, timeout=25)
    starts = {}
    for l in (rs.get("output") or "").splitlines():
        if l.startswith("START "): starts = json.loads(l[6:])
    await kit_tools.exec_sync(
        "import omni.timeline,omni.kit.app; omni.timeline.get_timeline_interface().play()\n"
        f"_a=omni.kit.app.get_app()\nfor _ in range({steps}): _a.update()", timeout=int(steps/25)+120)

    spec = json.dumps({"routing": routing, "srcs": srcs, "starts": starts})
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
    # first-char fallback (r1->red) — only when UNAMBIGUOUS (routing keys have distinct first chars).
    if color not in bins:
        _cand=[c for c in bins if c and color and c[0]==color[0]]
        if len(_cand)==1: color=_cand[0]
    row={{"cube":sp,"color":color}}
    if cc is None: row["verdict"]="MISSING"; res.append(row); continue
    cpos=cc[0]; row["pos"]=[round(x,3) for x in cpos]
    if color not in bins: row["verdict"]="UNMAPPED(cube color not in routing)"; res.append(row); continue
    # STILL-FEEDING (under-duration): cube barely moved from its t=0 start = never picked yet, NOT a
    # routing failure -> the cont.188 still-feeding discriminator (don't read under-duration as scatter).
    _st=D.get("starts",{{}}).get(sp)
    if _st is not None:
        _d=((cpos[0]-_st[0])**2+(cpos[1]-_st[1])**2)**0.5
        if _d<0.15: row["verdict"]="STILL-FEEDING(near start, under-duration)"; res.append(row); continue
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
    # Verdict logic (cont.199 fix — the CP-17 control showed UNMAPPED must NOT collapse to ROUTING-FALSE:
    # a size-named/attr-routed sorter the tool can't map is UNASSESSABLE here, not a mis-route). Priority:
    # real mis-route > unassessable-by-tool > incomplete-delivery > all-correct.
    n_ok = sum(1 for r in rows if r.get("verdict") == "CORRECT")
    has_misroute = any(("MIS-ROUTED" in r.get("verdict", "")) or r.get("verdict") == "NOT-IN-ANY-BIN" for r in rows)
    has_unmapped = any(r.get("verdict", "").startswith("UNMAPPED") or r.get("verdict") == "MISSING" for r in rows)
    has_undeliv = any("UNDELIVERED" in r.get("verdict", "") for r in rows)
    has_feeding = any("STILL-FEEDING" in r.get("verdict", "") for r in rows)
    if not rows:
        verdict = "NO_DATA"
    elif has_misroute:
        verdict = "ROUTING-FALSE"                # cube MOVED but landed in wrong/no bin = real mis-route
    elif has_unmapped:
        verdict = "UNASSESSABLE(non-color-named/attr-routed — out of this tool's scope)"
    elif has_undeliv:
        verdict = "ROUTING-FALSE(picked-then-dropped to floor)"   # genuine delivery fail, not under-duration
    elif has_feeding:
        verdict = "INCOMPLETE(some still feeding — re-run at longer duration; NOT a routing fail)"
    elif n_ok == len(rows):
        verdict = "ROUTED-OK"
    else:
        verdict = "REVIEW"
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
