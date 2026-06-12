"""HONEST GRADED TIME-SERIES assessment — maximum RESOLUTION, no binary gate.
Builds a template, plays it, logs per-item pos/orient/vel + contacts every 0.1s,
SAVES the raw time-series JSON, then reports CONTINUOUS quality dimensions per item
(placement error m, containment depth m signed, tilt deg, impact vel m/s, residual
speed, post-settle drift m, neighbor disturbance m caused) + the trajectory profile.
Usage: scene_timeseries.py <TEMPLATE> [duration_s]"""
import asyncio, json, sys, math
sys.path.insert(0, "/home/anton/projects/Omniverse_Nemotron_Ext")

async def main():
    name = sys.argv[1]
    from service.isaac_assist_service.chat.tools import kit_tools
    from service.isaac_assist_service.chat.canonical_instantiator import (
        execute_template_canonical, settle_after_canonical)
    tpl = json.load(open(f"/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates/{name}.json"))
    sa = tpl.get("simulate_args", {}) or {}
    # WINDOW from the template's declared duration_s (conveyor/multi-cube need 180-360s; a hardcoded 55s cuts
    # them off -> cubes never get picked -> falsely ON_BELT). Explicit argv[2] still overrides (surveys cap at 55).
    dur = float(sys.argv[2]) if len(sys.argv) > 2 else float(sa.get("duration_s") or 55.0)
    items = [i for i in (sa.get("cube_paths") or ([sa.get("cube_path")] if sa.get("cube_path") else [])) if i]
    # role_defaults.workpieces[] is the AUTHORITATIVE cube set for code_template tpls — cube_paths can list FAR fewer
    # than the scene spawns (CP-25 lists 1 but spawns 16; CP-19 lists 1 spawns 6). Union them so the eyes are NOT blind
    # to spawned cubes (reporting 1/1 while 15 go unseen is a false success — the "du kan inte vara blind" mandate).
    for _w in ((tpl.get("role_defaults") or {}).get("workpieces") or []):
        _p = _w.get("path") if isinstance(_w, dict) else None
        if _p and _p not in items:
            items.append(_p)
    # CLASS GATE: ~277 of the templates are RL/SDG/ROS2/train with NO placement items. Running a full single-tenant
    # Kit sim + emitting an authoritative-looking empty GRADED header is misleading + wasteful. Items-driven (never
    # false-skips a real placement run, even if pattern_hint mislabels it).
    if not items:
        _h = (tpl.get("intent", {}) or {}).get("pattern_hint") or (tpl.get("intent", {}) or {}).get("task_type") or "?"
        if _h == "pick_place":
            print(f"=== SUSPECT: {name} hint=pick_place but ZERO items (authoring bug) — not gradable ===")
        else:
            print(f"=== NOT GRADABLE BY THIS TOOL: {name} (class={_h}; no placement items) — needs artifact/topic/policy verifier ===")
        return
    target = sa.get("target_path") or (tpl.get("role_defaults", {}).get("primary_destination", {}) or {}).get("path", "/World/Bin")
    # Multi-destination (sort/route templates): role_defaults.destinations is a list of bins.
    # Collect ALL so each cube can be graded vs its NEAREST valid bin (no single-target blindness).
    _dl = tpl.get("role_defaults", {}).get("destinations")
    dests = [d["path"] for d in _dl if isinstance(d, dict) and d.get("path")] if isinstance(_dl, list) else []
    if target and target not in dests: dests = [target] + dests
    if not dests: dests = [target]
    # Bin discovery from color_routing values: sorters with role_defaults.destinations=null keep their bins ONLY here,
    # so without this a correctly-routed cube is graded vs the wrong/only bin (false error).
    _cr = sa.get("color_routing") or {}
    for _bp in (_cr.values() if isinstance(_cr, dict) else []):
        if isinstance(_bp, str) and _bp not in dests: dests.append(_bp)
    # Sorters that store bins as role_defaults.*_destination dicts (CP-47: red_destination/blue_destination)
    # or only reference them inside a code destination_map={...}: discover ALL so a correctly-routed cube
    # isn't graded vs the only-discovered bin (false MISROUTE/xy-miss — caught CP-47 blue->BlueBin false-neg).
    _rd_all = tpl.get("role_defaults", {}) or {}
    for _k, _v in _rd_all.items():
        if isinstance(_v, dict) and isinstance(_v.get("path"), str) and \
           any(_tok in _k.lower() for _tok in ("destination", "bin", "tray", "pallet")):
            if _v["path"] not in dests: dests.append(_v["path"])
    import re as _re2
    _blob = (tpl.get("code_template") or "") + "\n" + (tpl.get("code") or "")
    _dm = _re2.search(r'destination_map\s*=\s*\{([^}]*)\}', _blob)
    if _dm:
        for _ref in _re2.finditer(r'\{\{(\w+)(?:\[(\d+)\])?\.path\}\}', _dm.group(1)):
            _node = _rd_all.get(_ref.group(1))
            if _ref.group(2) is not None and isinstance(_node, list):
                _idx = int(_ref.group(2)); _node = _node[_idx] if _idx < len(_node) else None
            if isinstance(_node, dict) and isinstance(_node.get("path"), str) and _node["path"] not in dests:
                dests.append(_node["path"])
        for _lit in _re2.finditer(r'/World/[A-Za-z0-9_]+', _dm.group(1)):
            if _lit.group(0) not in dests: dests.append(_lit.group(0))
    # Conveyor/belt detection: a cube still on the belt is a moving-pick in progress, NOT a static placement failure.
    _rdd = tpl.get("role_defaults", {}) or {}
    belts = [v["path"] for k, v in _rdd.items() if isinstance(v, dict) and v.get("path")
             and ("conveyor" in k.lower() or "belt" in k.lower() or isinstance(v.get("surface_velocity"), list))]
    robot = (tpl.get("role_defaults", {}).get("primary_robot", {}) or {}).get("path", "/World/Franka")
    await kit_tools.exec_sync("import omni.usd\nomni.usd.get_context().new_stage()\nfrom pxr import UsdGeom\nUsdGeom.Xform.Define(omni.usd.get_context().get_stage(),'/World')\n", timeout=20)
    b = await asyncio.wait_for(execute_template_canonical(tpl), timeout=600)
    if not b.get("instantiated"):
        print("BUILD_FAIL", str(b.get("errors"))[:300]); return
    try: await asyncio.wait_for(settle_after_canonical(tpl), timeout=30)
    except Exception: pass

    RAW = f'''
import omni.usd, omni.kit.app, omni.timeline, json
from pxr import UsdGeom, Sdf, Gf
stage=omni.usd.get_context().get_stage()
ITEMS={json.dumps(items)}; TARGET={json.dumps(target)}; ROBOT={json.dumps(robot)}; DESTS={json.dumps(dests)}; BELTS={json.dumps(belts)}
def wp(p):
    if not p: return None
    pr=stage.GetPrimAtPath(Sdf.Path(p))
    if not (pr and pr.IsValid()): return None
    m=UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(0); t=m.ExtractTranslation(); r=m.ExtractRotationMatrix()
    uz=r.GetRow(2); n=(float(uz[0])**2+float(uz[1])**2+float(uz[2])**2)**0.5 or 1.0
    return [round(float(t[0]),4),round(float(t[1]),4),round(float(t[2]),4), round(float(uz[2])/n,4)]
def bbox(p):
    if not p: return None
    pr=stage.GetPrimAtPath(Sdf.Path(p))
    if not (pr and pr.IsValid()): return None
    r=UsdGeom.Imageable(pr).ComputeWorldBound(0, UsdGeom.Tokens.default_).ComputeAlignedRange()
    mn,mx=r.GetMin(),r.GetMax()
    return [[round(float(mn[i]),4) for i in range(3)],[round(float(mx[i]),4) for i in range(3)]]
# 2026-06-04 robustness: declared ROBOT (role_defaults.primary_robot, default /World/Franka) may not
# exist — many templates omit primary_robot. Fall back to the actual ArticulationRoot prim so the grader
# is never blind on a valid scene (was: EE=None -> Sdf.Path(None) crash on CP-80/84/85 w/ primary_robot unset).
if not stage.GetPrimAtPath(Sdf.Path(ROBOT)).IsValid():
    from pxr import UsdPhysics as _UPg
    for _arp in stage.Traverse():
        if _arp.HasAPI(_UPg.ArticulationRootAPI): ROBOT=str(_arp.GetPath()); break
EE=None
for cand in (ROBOT+"_SGCone", ROBOT+"/ee_link", ROBOT+"/panda_hand", ROBOT+"/wrist_3_link", ROBOT+"/tool0"):
    if stage.GetPrimAtPath(Sdf.Path(cand)).IsValid(): EE=cand; break
if EE is None: EE=ROBOT
tb=bbox(TARGET); dest_bb={{p:bbox(p) for p in DESTS}}; belt_bb={{p:bbox(p) for p in BELTS}}
init={{p:wp(p) for p in ITEMS}}; ibb={{p:bbox(p) for p in ITEMS}}
# grip-integrity: detect a FixedJoint EE<->item weld (the FORBIDDEN grip) or a kinematic-held item. The grip FJ can
# be created DURING carry (handler physics callback) so re-scan periodically. A SurfaceGripper D6 suction attachment
# is NOT a FixedJoint -> correctly NOT flagged. A real friction/suction grasp leaves grip_audit clean.
from pxr import UsdPhysics, Usd
ROBOT_PRIMS=set()
_rrp=stage.GetPrimAtPath(Sdf.Path(ROBOT))
if _rrp and _rrp.IsValid():
    for _d in Usd.PrimRange(_rrp): ROBOT_PRIMS.add(str(_d.GetPath()))
def _ee_side(t): return (t in ROBOT_PRIMS) or any(k in t.lower() for k in ("suctioncone","/cone","follower","gripper","panda_hand","ee_link","finger"))
ITEMSET=set(ITEMS)
grip_audit={{p.split("/")[-1]:{{"fj_ee_item":False,"kinematic":False}} for p in ITEMS}}
def _semclass(p):  # mirror handler _cube_semantic_class: USD Semantics color/class for routing-correctness
    try:
        from pxr import Semantics
        pr=stage.GetPrimAtPath(Sdf.Path(p))
        if not (pr and pr.IsValid()): return None
        for sn in ("Semantics_color","Semantics_colour","Semantics_class"):
            sem=Semantics.SemanticsAPI.Get(pr,sn)
            if not sem: continue
            da=sem.GetSemanticDataAttr()
            if da and da.IsValid():
                v=da.Get()
                if v: return str(v).lower()
    except Exception: pass
    return None
cube_class={{p.split("/")[-1]:_semclass(p) for p in ITEMS}}
contacts=set()
try:
    from pxr import PhysxSchema, PhysicsSchemaTools
    from omni.physx import get_physx_simulation_interface
    _crp=list(ITEMS)
    for base in (ROBOT, TARGET):  # robot links + bin/edge so we see gripper-vs-edge + arm-vs-anything
        bp=stage.GetPrimAtPath(Sdf.Path(base))
        if bp and bp.IsValid():
            for d in [bp]+list(bp.GetChildren()):
                for dd in [d]+list(d.GetChildren()): _crp.append(str(dd.GetPath()))
    for p in set(_crp):
        pr=stage.GetPrimAtPath(Sdf.Path(p))
        if pr and pr.IsValid():
            try: PhysxSchema.PhysxContactReportAPI.Apply(pr)
            except Exception: pass
    def _oc(h,d):
        for ch in h:
            try: contacts.add((str(PhysicsSchemaTools.intToSdfPath(ch.actor0)).split("/")[-1], str(PhysicsSchemaTools.intToSdfPath(ch.actor1)).split("/")[-1]))
            except Exception: pass
    _sub=get_physx_simulation_interface().subscribe_contact_report_events(_oc)
except Exception: _sub=None
app=omni.kit.app.get_app(); tl=omni.timeline.get_timeline_interface()
if not tl.is_playing(): tl.play()
prev={{p:wp(p) for p in ITEMS}}; rows=[]
N=int({dur}*60)
for i in range(N):
    app.update()
    if i%60==0:  # grip-integrity scan ~1Hz (a carry FJ persists for seconds)
        try:
            for _jp in stage.Traverse():
                if _jp.IsA(UsdPhysics.FixedJoint):
                    _j=UsdPhysics.FixedJoint(_jp); _b0=_j.GetBody0Rel().GetTargets(); _b1=_j.GetBody1Rel().GetTargets()
                    _t0=str(_b0[0]) if _b0 else ""; _t1=str(_b1[0]) if _b1 else ""
                    for _it in ITEMSET:
                        if (_t0==_it and _ee_side(_t1)) or (_t1==_it and _ee_side(_t0)): grip_audit[_it.split("/")[-1]]["fj_ee_item"]=True
            for _it in ITEMS:
                _kp=stage.GetPrimAtPath(Sdf.Path(_it)); _ka=_kp.GetAttribute("physics:kinematicEnabled") if (_kp and _kp.IsValid()) else None
                if _ka and _ka.Get(): grip_audit[_it.split("/")[-1]]["kinematic"]=True
        except Exception: pass
    if i%6==0:
        snap={{}}
        for p in ITEMS:
            c=wp(p); pv=prev.get(p); vz=0.0; spd=0.0
            if c and pv:
                spd=((c[0]-pv[0])**2+(c[1]-pv[1])**2+(c[2]-pv[2])**2)**0.5/0.1; vz=(c[2]-pv[2])/0.1
            snap[p.split("/")[-1]]={{"p":(c[:3] if c else None),"up":(c[3] if c else None),"spd":round(spd,3),"vz":round(vz,3)}}
            prev[p]=c
        ee=wp(EE)
        rows.append({{"t":round(i/60.0,1),"ee":(ee[:3] if ee else None),"items":snap,"contacts":sorted(["%s|%s"%(a,c) for (a,c) in contacts])}})
        contacts.clear()
print("META="+json.dumps({{"target_bbox":tb,"dest_bbox":dest_bb,"belt_bbox":belt_bb,"grip_audit":grip_audit,"cube_class":cube_class,"init":{{k.split("/")[-1]:v for k,v in init.items()}},"item_bbox":{{k.split("/")[-1]:v for k,v in ibb.items()}},"ee":EE}}))
print("TS_BEGIN"+json.dumps(rows)+"TS_END")
'''
    r = await asyncio.wait_for(kit_tools.exec_sync(RAW, timeout=int(dur) + 130), timeout=int(dur) + 150)
    o = r.get("output") or ""
    meta = {}
    for l in o.splitlines():
        if l.startswith("META="): meta = json.loads(l[5:])
    a = o.find("TS_BEGIN"); z = o.find("TS_END")
    if a < 0: print("TS_PARSE_FAIL", o[-500:]); return
    rows = json.loads(o[a+8:z])
    raw = {"template": name, "meta": meta, "rows": rows, "provenance": _provenance()}
    rawpath = f"{_OUTDIR}/ts_{name}.json"
    json.dump(raw, open(rawpath, "w"))
    print(f"RAW saved -> {rawpath} ({len(rows)} samples)")
    # pandas-style tidy table: index=t, cols=per-item x/y/z/tilt/spd/vz + ee + contacts
    try:
        import pandas as pd
        recs = []
        for rw in rows:
            d = {"t": rw["t"], "ee_x": (rw["ee"][0] if rw["ee"] else None), "ee_y": (rw["ee"][1] if rw["ee"] else None),
                 "ee_z": (rw["ee"][2] if rw["ee"] else None), "contacts": ";".join(c for c in rw.get("contacts", []) if "ConveyorBelt" not in c)}
            for nm, s in rw["items"].items():
                p = s.get("p")
                d[f"{nm}_x"] = (p[0] if p else None); d[f"{nm}_y"] = (p[1] if p else None); d[f"{nm}_z"] = (p[2] if p else None)
                d[f"{nm}_tilt"] = (round(math.degrees(math.acos(max(-1, min(1, s["up"])))), 2) if s.get("up") is not None else None)
                d[f"{nm}_spd"] = s.get("spd"); d[f"{nm}_vz"] = s.get("vz")
            recs.append(d)
        df = pd.DataFrame(recs).set_index("t")
        df.to_csv(f"{_OUTDIR}/ts_{name}.csv")
        try: df.to_parquet(f"{_OUTDIR}/ts_{name}.parquet")
        except Exception: pass
        print(f"PANDAS table -> {_OUTDIR}/ts_{name}.csv (shape {df.shape})")
    except Exception as _pe:
        print("pandas save skipped:", _pe)
    _report(raw)

TPL_DIR = "/home/anton/projects/Omniverse_Nemotron_Ext/workspace/templates"
_REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
_HANDLER = _REPO + "/service/isaac_assist_service/chat/tools/handlers/pick_place.py"
# Output directory for ts_*.json/.csv/.parquet artifacts.  Override via env var TS_OUTDIR.
import os as _os
_OUTDIR = _os.environ.get("TS_OUTDIR", "/home/anton/.isaac_qa/run")

def _provenance():
    """Code-state stamp on every result (Anton: no precision without code-state + timestamp)."""
    import hashlib, subprocess, datetime
    def _sha(p):
        try: return hashlib.sha256(open(p, "rb").read()).hexdigest()[:12]
        except Exception: return "?"
    try:
        rev = subprocess.run(["git", "-C", _REPO, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception: rev = "?"
    return {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "handler_sha": _sha(_HANDLER), "eyes_sha": _sha(__file__), "git_rev": rev}

def _tpl_meta(name):
    """Kit-free: re-read the template for placement INTENT so _report grades correctly on ANY saved
    ts_*.json (no re-sim needed): per-cube drop_targets, has_stacking, declared bin cavity depths."""
    out = {"drop_targets": {}, "has_stacking": False, "dest_depth": {}, "primary_depth": None, "color_routing": {}, "tpl_class": {}}
    try:
        tpl = json.load(open(f"{TPL_DIR}/{name}.json"))
    except Exception:
        return out
    rd = tpl.get("role_defaults", {}) or {}
    sf = (tpl.get("intent", {}) or {}).get("structural_features", {}) or {}
    out["has_stacking"] = bool(sf.get("has_stacking"))
    out["color_routing"] = (tpl.get("simulate_args", {}) or {}).get("color_routing") or {}
    # circulation templates: a moving cube at end is the SUCCESS condition
    out["circulating"] = bool((tpl.get("simulate_args", {}) or {}).get("min_laps_per_cube"))
    # Cleanest source: role_defaults.destinations[].routing_key -> path (the explicit color->bin map).
    # ARMS the misroute guard (_expected_short) — without this it falls back to nearest-bin and a misroute reads OK.
    if not out["color_routing"]:
        for _n in (rd.get("destinations") or []):
            if isinstance(_n, dict) and _n.get("routing_key") and _n.get("path"):
                out["color_routing"][str(_n["routing_key"]).lower()] = _n["path"]
    # Fallback: parse the code's destination_map={"<class>": <bin>, ...} into color_routing so _expected_short
    # grades each cube vs its COLOR's required bin (CP-47/CP-03 color-sort; resolves {{X.path}}/{{X[i].path}}).
    if not out["color_routing"]:
        import re as _re3
        _blob = (tpl.get("code_template") or "") + "\n" + (tpl.get("code") or "")
        _dm = _re3.search(r'destination_map\s*=\s*\{([^}]*)\}', _blob)
        if _dm:
            _crm = {}
            for _kv in _re3.finditer(r'["\'](\w[\w ]*)["\']\s*:\s*([^,}]+)', _dm.group(1)):
                _key = _kv.group(1).strip().lower(); _val = _kv.group(2).strip()
                _ref = _re3.match(r'\{\{(\w+)(?:\[(\d+)\])?\.path\}\}', _val)
                if _ref:
                    _node = rd.get(_ref.group(1))
                    if _ref.group(2) is not None and isinstance(_node, list):
                        _i = int(_ref.group(2)); _node = _node[_i] if _i < len(_node) else None
                    if isinstance(_node, dict) and _node.get("path"): _crm[_key] = _node["path"]
                else:
                    _lit = _re3.search(r'/World/[A-Za-z0-9_]+', _val)
                    if _lit: _crm[_key] = _lit.group(0)
            if _crm: out["color_routing"] = _crm
    wps = rd.get("workpieces", [])
    if isinstance(wps, list):
        for w in wps:
            if isinstance(w, dict) and w.get("path"):
                sn = w["path"].split("/")[-1]
                if w.get("drop_target"): out["drop_targets"][sn] = w["drop_target"]
                _c = w.get("semantic_class") or w.get("color") or w.get("class_name")
                if _c: out["tpl_class"][sn] = str(_c).lower()
    def _dep(node):
        sz = node.get("size") if isinstance(node, dict) else None
        return float(sz[2]) if isinstance(sz, list) and len(sz) > 2 else None
    pdn = rd.get("primary_destination")
    if isinstance(pdn, dict):
        out["primary_depth"] = _dep(pdn)
        if pdn.get("path"):
            dpt = _dep(pdn)
            if dpt is not None: out["dest_depth"][pdn["path"].split("/")[-1]] = dpt
    dl = rd.get("destinations")
    if isinstance(dl, list):
        for n in dl:
            if isinstance(n, dict) and n.get("path"):
                dpt = _dep(n)
                if dpt is not None: out["dest_depth"][n["path"].split("/")[-1]] = dpt
    return out

def _report(raw):
    rows = raw["rows"]; meta = raw["meta"]; tb = meta.get("target_bbox")
    names = sorted({n for rw in rows for n in rw["items"]})
    tm = _tpl_meta(raw.get("template", ""))
    drop_targets = tm["drop_targets"]; has_stacking = tm["has_stacking"]
    dest_depth = tm["dest_depth"]; primary_depth = tm["primary_depth"]
    init = meta.get("init", {}) or {}
    # destinations carry FULL bbox corners: (short, cx,cy,rim_z,floor_z, b0x,b0y,b1x,b1y, mdz)
    dbb = meta.get("dest_bbox") or ({"target": tb} if tb else {})
    dests = []
    for p, b in dbb.items():
        if b:
            dests.append((p.split("/")[-1], (b[0][0]+b[1][0])/2, (b[0][1]+b[1][1])/2, b[1][2], b[0][2],
                          b[0][0], b[0][1], b[1][0], b[1][1], b[1][2]-b[0][2]))
    def _nearest(fp):
        return min(dests, key=lambda d: (fp[0]-d[1])**2 + (fp[1]-d[2])**2) if dests else None
    floor_ref = min((dd[4] for dd in dests), default=0.0)
    belt_bb = [b for b in (meta.get("belt_bbox") or {}).values() if b]
    # routing-correctness: grade each cube vs its REQUIRED bin (class -> color_routing), not just the geometrically nearest
    # (a wrong-but-nearest bin would otherwise read err~0 + seated = a perfect score for a SORT FAILURE).
    tm_cr = tm.get("color_routing") or {}; tm_tc = tm.get("tpl_class") or {}; cube_class_meta = meta.get("cube_class") or {}
    dest_by_short = {d[0]: d for d in dests}
    fpos = {}  # final position per cube (for the supported-by-a-cube-below check)
    for _n in names:
        _sq = [rw["items"][_n]["p"] for rw in rows if rw["items"].get(_n) and rw["items"][_n].get("p")]
        if _sq: fpos[_n] = _sq[-1]
    # grip_gap precondition: does the EE actually move? (UR10 ee_link is a static frame -> gap is meaningless, don't flag)
    _ee_xyz = [rw["ee"] for rw in rows if rw.get("ee")]; ee_moves = False
    if len(_ee_xyz) >= 3:
        def _stdev(vals):
            _mn = sum(vals) / len(vals)
            return (sum((v - _mn)**2 for v in vals) / len(vals)) ** 0.5
        _sx = _stdev([e[0] for e in _ee_xyz]); _sy = _stdev([e[1] for e in _ee_xyz]); _sz = _stdev([e[2] for e in _ee_xyz])
        ee_moves = (max(_sx, _sy, _sz) > 0.02)
    def _expected_short(nm):
        cls = cube_class_meta.get(nm) or tm_tc.get(nm)
        if not cls or not tm_cr: return None
        for k, bp in tm_cr.items():   # exact then substring both ways ('red' vs 'red cube')
            kl = str(k).lower()
            if kl == cls or cls in kl or kl in cls: return str(bp).split("/")[-1]
        return None
    _ds = ", ".join("%s(%.2f,%.2f)" % (d[0], d[1], d[2]) for d in dests) if dests else "?"
    print(f"\n=== GRADED ASSESSMENT: {raw['template']} | dests=[{_ds}] (each cube vs nearest; per-cube drop_target if known) ===")
    _pv = raw.get("provenance") or _provenance()
    print(f"  [provenance] ts={_pv.get('ts','re-grade')} eyes={_pv.get('eyes_sha')} handler={_pv.get('handler_sha')} git={_pv.get('git_rev')}")
    print("  per item — bin | err_xy(m) | containment(m,+seated/-miss)[kind] | settled_tilt°(transit°) | impact_vz(peak_spd) | drift | STATE")
    def _tilt(s): return math.degrees(math.acos(max(-1, min(1, s["up"]))))
    def _r(x, n=3): return round(x, n) if isinstance(x, (int, float)) else x
    # physics-observed cavity: a dest where a cube's BOTTOM descended below the rim => it has a real cavity (no threshold)
    _ib = meta.get("item_bbox", {})
    descended = set()
    for dd in dests:
        hit = False
        for rw in rows:
            for _n, _s in rw["items"].items():
                _p = _s.get("p")
                if _p and dd[5] <= _p[0] <= dd[7] and dd[6] <= _p[1] <= dd[8]:
                    _bb = _ib.get(_n) or [[0, 0, 0], [0, 0, 0.05]]; _hz = (_bb[1][2]-_bb[0][2])/2 or 0.025
                    if (_p[2]-_hz) < dd[3] - 0.015: descended.add(dd[0]); hit = True; break
            if hit: break
    for nm in names:
        seq = [(rw["t"], rw["items"][nm]) for rw in rows if rw["items"].get(nm) and rw["items"][nm].get("p")]
        if not seq: print(f"  {nm}: NO_DATA"); continue
        ft, fin = seq[-1]
        fp = fin["p"]; fup = fin["up"]
        ib = meta.get("item_bbox", {}).get(nm) or [[0, 0, 0], [0, 0, 0.05]]
        half_z = (ib[1][2] - ib[0][2]) / 2 or 0.025
        # supported = resting on a cube DIRECTLY below (physics-grounded "stacked", robust vs the cavity/surface threshold)
        supported = any(o != nm and fpos.get(o) and abs(fpos[o][0]-fp[0]) < 0.05 and abs(fpos[o][1]-fp[1]) < 0.05
                        and abs((fp[2]-half_z)-(fpos[o][2]+half_z)) < 0.03 for o in names)
        # --- stack_align: lateral offset of a stacked cube vs the cube below + vs the tower axis (additive scoring) ---
        align_score = None; off_xy = None
        if supported:
            _base = next((o for o in names if o != nm and fpos.get(o)
                          and abs(fpos[o][0]-fp[0]) < 0.05 and abs(fpos[o][1]-fp[1]) < 0.05
                          and abs((fp[2]-half_z)-(fpos[o][2]+half_z)) < 0.03), None)
            if _base is not None:
                off_xy = ((fp[0]-fpos[_base][0])**2 + (fp[1]-fpos[_base][1])**2) ** 0.5
                w = (ib[1][0] - ib[0][0]) or 0.05
                # tower axis: all cubes whose final xy sit within 0.5*w of nm's xy -> their mean (cx,cy)
                _grp = [o for o in names if fpos.get(o)
                        and ((fpos[o][0]-fp[0])**2 + (fpos[o][1]-fp[1])**2) ** 0.5 < 0.5 * w]
                if _grp:
                    _cx = sum(fpos[o][0] for o in _grp) / len(_grp)
                    _cy = sum(fpos[o][1] for o in _grp) / len(_grp)
                    tower_off = ((fp[0]-_cx)**2 + (fp[1]-_cy)**2) ** 0.5
                else:
                    tower_off = off_xy
                off_eff = max(off_xy, tower_off)
                align_score = max(0.0, min(1.0, 1 - off_eff / (0.5 * w)))
        d = _nearest(fp)
        landed_short = d[0] if d else None
        # actually INSIDE the nearest bin footprint? MISROUTED only applies to a cube SEATED in the WRONG bin —
        # not one on-belt / off-target / not-delivered (those are their own states).
        landed_in = bool(d) and (d[5]-0.02 <= fp[0] <= d[7]+0.02) and (d[6]-0.02 <= fp[1] <= d[8]+0.02)
        exp_short = _expected_short(nm); routed = None; route_blind = False
        if exp_short:
            routed = (landed_short == exp_short)
            ed = dest_by_short.get(exp_short)
            if ed is not None:
                d = ed  # grade vs the REQUIRED bin (color_routing class->bin)
            else:
                route_blind = True  # required bin known but bbox missing -> don't silently grade vs nearest
        dt = drop_targets.get(nm)
        # --- err_xy: per-cube drop_target xy if known, else nearest-bin center (Rank 4) ---
        if dt: err_xy = ((fp[0]-dt[0])**2 + (fp[1]-dt[1])**2) ** 0.5
        elif d: err_xy = ((fp[0]-d[1])**2 + (fp[1]-d[2])**2) ** 0.5
        else: err_xy = None
        # --- containment: xy-gate + cavity/surface/stack classify (Rank 1) ---
        containment = None; kind = "?"
        if d is not None:
            cx, cy, rim_z, floor_z = d[1], d[2], d[3], d[4]
            b0x, b0y, b1x, b1y, mdz = d[5], d[6], d[7], d[8], d[9]
            m = 0.02
            xy_inside = (b0x - m <= fp[0] <= b1x + m) and (b0y - m <= fp[1] <= b1y + m)
            decl = dest_depth.get(d[0])
            if decl is None and len(dests) == 1: decl = primary_depth
            observed = d[0] in descended  # physics: a cube descended below this dest's rim
            decl_cav = decl is not None and decl >= 2 * half_z  # cavity only if the cube FITS INSIDE (depth >= cube height);
            # a thin marker/plate (e.g. CP-28's 2.5cm marker vs a 5cm cube) is a SURFACE the cube rests ON, not a cavity
            is_cavity = decl_cav or (mdz >= 0.07) or observed
            bottom = fp[2] - half_z
            # GROUNDING HIERARCHY (most-grounded first; basis is LABELED so any heuristic call is visible):
            # dt_near = ended within 6cm of its OWN declared drop_target xy. A cube delivered to a 2nd pallet/tier that
            # the single dest-bbox scan missed ("single-dest blindness") must NOT read xy-miss/FLUNG. Uses the per-cube
            # drop_target only -> RE-GRADES from saved data (fixed CP-19 Cube_4/5/6 on PalletB, false-FLUNG @0.011m err).
            dt_near = bool(dt) and len(dt) >= 3 and ((fp[0]-dt[0])**2 + (fp[1]-dt[1])**2) ** 0.5 <= 0.06
            if not xy_inside and not dt_near:
                containment = -(((fp[0]-cx)**2 + (fp[1]-cy)**2) ** 0.5); kind = "xy-miss"
            elif supported:                          # physics: resting on a cube below -> seated-as-stacked (robust)
                containment = half_z; kind = "stacked"
            elif dt and len(dt) >= 3:                # template-declared intended rest; cube should end at/below it
                containment = half_z - max(0.0, fp[2] - dt[2]); kind = "drop_target"
            elif is_cavity:                          # cube should reach the cavity floor
                containment = half_z - max(0.0, bottom - floor_z)
                kind = "cavity-obs" if observed else ("cavity-decl" if decl_cav else "cavity-dz")
            else:                                    # flat surface / pallet: seated when bottom ~ surface top
                containment = half_z - max(0.0, bottom - rim_z); kind = "surface"
        # --- tilt localized: settled (spd<0.05) vs transit carry-swing (Rank 5) ---
        settled_tilt = max((_tilt(s) for _, s in seq if s.get("spd") is not None and s["spd"] < 0.05 and s.get("up") is not None),
                           default=(_tilt(fin) if fup is not None else None))
        transit_tilt = max((_tilt(s) for _, s in seq if s.get("spd") is not None and s["spd"] >= 0.05 and s.get("up") is not None), default=0.0)
        # --- impact_vz localized to touchdown near final rest z; peak_spd surfaces hidden flings (Rank 5) ---
        win = max(0.15, 3 * half_z)
        impact_vz = min((s["vz"] for _, s in seq if s.get("vz") is not None and s["vz"] < 0 and abs(s["p"][2]-fp[2]) < win), default=0.0)
        peak_spd = max((s["spd"] for _, s in seq if s.get("spd") is not None), default=0.0)
        ip = init.get(nm)  # initial pos (also used by the terminal-state max_disp block below)
        # --- carry_jerk: rigid-grip signature during the in-air carry (high accel/reversals => non-rigid grasp) ---
        acc_max = None; rev = None; rigid_score = None
        carry = [s["p"] for (t, s) in seq if s.get("p") and ip and s["p"][2] > ip[2] + 0.06]
        if len(carry) >= 4:
            acc = [(sum((carry[i+1][k] - 2*carry[i][k] + carry[i-1][k])**2 for k in range(3)) ** 0.5) / (0.1 * 0.1)
                   for i in range(1, len(carry)-1)]
            acc_max = max(acc) if acc else 0.0
            rev = sum(1 for i in range(1, len(carry)-1)
                      if sum((carry[i][k]-carry[i-1][k]) * (carry[i+1][k]-carry[i][k]) for k in range(3)) < 0)
            rigid_score = max(0.0, min(1.0, 1 - (acc_max - 12) / (60 - 12))) * max(0.0, min(1.0, 1 - max(0, rev - 1) / 4))
        # --- grip_gap: cube<->EE distance during the in-air carry; a rigid grasp holds it ~constant (low std) ---
        gap_mean = None; gap_std = None
        if ee_moves:
            gaps = []
            for rw in rows:
                _it = rw["items"].get(nm); _cp = _it.get("p") if _it else None; _ep = rw.get("ee")
                if _cp and _ep and ip and _cp[2] > ip[2] + 0.06:
                    _g = sum((_cp[k] - _ep[k])**2 for k in range(3)) ** 0.5
                    # only HELD samples: post-release the cube sits while the EE retracts -> gap grows to 0.5-0.8m,
                    # which falsely inflated gap_std (false LOOSE_GRIP on delivering shelf/pile templates). A genuinely
                    # held cube hangs within ~0.25m of the tool, so cap the window to that.
                    if _g < 0.25:
                        gaps.append(_g)
            if gaps:
                gap_mean = sum(gaps) / len(gaps)
                _gm = gap_mean
                gap_std = (sum((g - _gm)**2 for g in gaps) / len(gaps)) ** 0.5
        # --- post-settle drift (N/A if never settled) ---
        last_moving = max((t for t, s in seq if s.get("spd") and s["spd"] > 0.1), default=None)
        after = [s["p"] for _, s in seq] if last_moving is None else [s["p"] for t, s in seq if t > last_moving + 0.2]
        drift = (max((sum((q[k]-after[0][k])**2 for k in range(3))**0.5 for q in after), default=0.0)) if after else None
        # --- terminal-state flags (Rank 3A settle + Rank 7 position) ---
        plateau = 0
        for _, s in reversed(seq):
            if s.get("spd") is not None and s["spd"] < 0.05: plateau += 1
            else: break
        spd_f = fin.get("spd")
        aloft = d is not None and (fp[2] - half_z) > d[3] + 2 * half_z
        max_disp = 0.0
        if ip:
            for _, s in seq:
                if s.get("p"): max_disp = max(max_disp, sum((s["p"][k]-ip[k])**2 for k in range(3))**0.5)
        state = []
        _circ = tm.get("circulating")
        if spd_f is not None and spd_f > 0.05:
            # lap-aware (2026-06-13): recirculation templates DECLARE that
            # cubes keep moving (min_laps_per_cube) — flagging IN_FLIGHT
            # made every successful circulation read as a faithfulness issue
            state.append("CIRCULATING" if _circ else "IN_FLIGHT")
        elif plateau < 5 and not _circ: state.append("UNSETTLED")
        if aloft and not supported and not dt_near: state.append("ALOFT")  # supported=on a cube below; dt_near=at its own
        # declared drop_target (e.g. a 2nd/upper shelf tier the nearest-dest doesn't know about) -> not actually floating
        if d is not None and (fp[2]-half_z) < floor_ref - 0.05: state.append("ON_FLOOR")
        if kind == "xy-miss": state.append("FLUNG" if max_disp > 0.5 else "OFF_TARGET")
        # ON_BELT: cube still on a conveyor (moving-pick in progress) — NOT a static placement failure, just not-yet-handled
        if belt_bb and any((b[0][0]-0.05 <= fp[0] <= b[1][0]+0.05) and (b[0][1]-0.1 <= fp[1] <= b[1][1]+0.1) and (fp[2]-half_z) < b[1][2]+0.06 for b in belt_bb):
            state.append("ON_BELT")
        # orientation: a cube at the right position but on its side is NOT correctly placed (containment alone misses this).
        # SKIP for round items (sphere/ball): they roll, have no meaningful "up" -> tilt is noise, not a topple.
        _round = any(k in nm.lower() for k in ("sphere", "ball", "round"))
        if not _round and settled_tilt is not None and settled_tilt > 60: state.append("TOPPLED")
        elif not _round and settled_tilt is not None and settled_tilt > 30: state.append("TILTED")
        # stack alignment (additive — only for cubes resting on a cube below)
        if align_score is not None and align_score < 0.5: state.append("MISALIGNED")
        elif align_score is not None and align_score < 0.85: state.append("STACK_DRIFT")
        # grip integrity: a FixedJoint EE<->item weld or kinematic-held cube makes a CHEAT read as a perfect grasp
        ga = (meta.get("grip_audit") or {}).get(nm, {})
        if ga.get("fj_ee_item"): state.append("FORBIDDEN_FJ_GRIP")
        if ga.get("kinematic"): state.append("KINEMATIC_HELD")
        if acc_max is not None and (acc_max > 40 or rev >= 3): state.append("NON_RIGID_GRIP")
        # gap_std flags only EGREGIOUS slip (>20mm). A faithfully-held cube still pendulum-swings a few mm during
        # accel/decel (CP-13 rigid=0.04mm, but normal sort/stack carries run 3-10mm) -> 3mm false-fired on delivering
        # templates. carry_jerk (NON_RIGID_GRIP, validated CP-13/CP-70) is the primary grip-faithfulness verdict.
        if gap_std is not None and gap_std > 0.020 and rigid_score is not None and rigid_score < 0.5: state.append("LOOSE_GRIP")
        if routed is False and landed_in: state.append("MISROUTED(in %s,need %s)" % (landed_short, exp_short))
        if route_blind: state.append("UNROUTABLE_NO_BIN(need %s)" % exp_short)
        # NOT_SEATED: at the dest xy but resting too high (on-rim/above intent) and NOT supported by a cube below (= legit stack)
        if (containment is not None and containment < -0.015 and landed_in and not supported
                and kind in ("cavity-obs", "cavity-decl", "cavity-dz", "surface", "drop_target")):
            state.append("NOT_SEATED")
        st = ",".join(state) if state else "OK"
        _xtra = ""
        if align_score is not None: _xtra += " align=%.1fmm(%.2f)" % (off_xy * 1000, align_score)
        if acc_max is not None: _xtra += " jerk=%.0f(%d)" % (acc_max, rev)
        if gap_mean is not None: _xtra += " gap=%.1fmm(std%.2f)" % (gap_mean * 1000, gap_std * 1000)
        print(f"  {nm}: bin={d[0] if d else '?'} | err_xy={_r(err_xy)} | contain={_r(containment)}[{kind}] | "
              f"tilt={_r(settled_tilt,1)}°(tr {_r(transit_tilt,1)}°) | impact_vz={_r(impact_vz,2)}(pk {_r(peak_spd,2)}) | "
              f"drift={_r(drift)} | {st} | final={[_r(v) for v in fp]}{_xtra}")
    # contact timeline (grip + knocks); belts kept out of the contact log
    print("  contact events (item handled / item-vs-item / arm-vs-item):")
    seen = set()
    for rw in rows:
        for c in rw.get("contacts", []):
            if "|" in c and c not in seen and "ConveyorBelt" not in c and "Belt" not in c:
                seen.add(c); print(f"    t={rw['t']}s {c}")

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1].endswith(".json"):
    _report(json.load(open(sys.argv[1])))
else:
    asyncio.run(main())
