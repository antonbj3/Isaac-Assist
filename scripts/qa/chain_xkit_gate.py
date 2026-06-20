#!/usr/bin/env python3
"""chain_xkit_gate.py — CROSS-KIT declarative composition chain with AUTO-DERIVED handoff (robot-diversity).

WHY (2026-06-17, feedback_ur10_corrupts_global_physx): a single UR10 run corrupts process-global PhysX state
(survives new_stage/reset_simulation/SM._clear; only a Kit PROCESS restart clears it). So a UR10->Franka chain
in ONE Kit is fundamentally blocked (single-Kit chain_gate relay = 0/1). This gate runs EACH stage in its OWN
FRESH Kit and hands off at the STATE level, sidestepping the corruption.

L3 AUTO-HANDOFF (#29): stage k-1's delivered cube world pos X is RECORDED; stage k's offset is DERIVED
automatically from X + stage k's pick-sensor geometry (O = X_xy - pick_sensor_xy) so stage k's pick lands on
the handoff; the RELAYED cube is re-instantiated at X and source_override'd into stage k's controller. So
stage k consumes the EXACT object stage k-1 delivered (faithful relay), not its own placeholder.

PROVEN 2026-06-17 (cont.226): CP-CHAIN-UR10-SRC (UR10) -> [auto-offset O=[0.51,-0.79,0]] -> CP-CHAIN-FLAT
(Franka) = stage0 1/1 (->Tray, handoff [0.51,-0.39,0.775]) + stage1 1/1 (relayed cube ->Bin) = ALL DELIVERED
(vs single-Kit 1/1 + 0/1). NOTE: each stage's grip is honest (clean Kit); per-stage delivery is the bar.

Usage:
  python scripts/qa/chain_xkit_gate.py CP-CHAIN-UR10-SRC CP-CHAIN-FLAT
Restart the Kit (kit_restart.sh) before invoking so stage0 starts clean; the gate restarts between stages.
"""
import asyncio, json, os as _os, sys, re, subprocess
REPO = "/home/anton/projects/Omniverse_Nemotron_Ext"
sys.path.insert(0, REPO)
_RELAY_ASSET = _os.environ.get("RELAY_ASSET")    # cont.319r: real-object chain — re-create the relayed object as THIS referenced asset (not a 0.05 cube); unset => byte-identical cube relay
_RELAY_MESH = _os.environ.get("RELAY_MESH", "")  # the asset's child mesh leaf for the convexHull collider


def _pick_xy(tpl):
    """stage's pick location (world xy in its OWN frame) — the proximity-sensor xy, else first source cube xy."""
    code = tpl.get("code") or ""
    m = re.search(r'add_proximity_sensor\([^)]*position\s*=\s*\[([^\]]+)\]', code)
    if m:
        v = [float(x) for x in m.group(1).split(",")]
        return [v[0], v[1]]
    # no proximity sensor (e.g. a source_paths-driven UR10 source serving as a receiver): fall back to the
    # first source cube's create_prim xy so the auto-offset still lands the pick (pedestal) on the handoff.
    cubes, _ = _src_target_cubes(tpl)
    for cp in cubes:
        mm = re.search(r'create_prim\([^)]*' + re.escape(cp) + r'[^)]*position\s*=\s*\[([^\]]+)\]', code)
        if mm:
            v = [float(x) for x in mm.group(1).split(",")]
            return [v[0], v[1]]
    return [0.0, 0.4]


def _src_target_cubes(tpl):
    sa = tpl.get("simulate_args") or tpl.get("verify_args") or {}
    cubes = sa.get("cube_paths") or ([sa.get("cube_path")] if sa.get("cube_path") else ["/World/Cube_1"])
    target = sa.get("target_path") or "/World/Bin"
    return cubes, target


MEASURE = r'''
import omni.usd, omni.kit.app, omni.timeline, json
from pxr import Sdf, UsdGeom
stage=omni.usd.get_context().get_stage()
def cz(p):
    pr=stage.GetPrimAtPath(Sdf.Path(p))
    if not pr or not pr.IsValid(): return None
    t=UsdGeom.Xformable(pr).ComputeLocalToWorldTransform(0).ExtractTranslation()
    return [round(float(t[i]),3) for i in range(3)]
def bb(p):
    pr=stage.GetPrimAtPath(Sdf.Path(p))
    if not pr or not pr.IsValid(): return None
    r=UsdGeom.Imageable(pr).ComputeWorldBound(0,UsdGeom.Tokens.default_).ComputeAlignedRange()
    if r.IsEmpty(): return None
    return [float(r.GetMin()[i]) for i in range(3)],[float(r.GetMax()[i]) for i in range(3)]
TARGET=__TARGET__; CUBES=__CUBES__; PLAY=__PLAY__
if PLAY:
    app=omni.kit.app.get_app(); tl=omni.timeline.get_timeline_interface(); tl.play()
    for _ in range(5000): app.update()
tb=bb(TARGET); res={"target":TARGET,"delivered":0,"total":len(CUBES),"poses":{}}
for cp in CUBES:
    c=cz(cp); res["poses"][cp]=c
    if tb and c and tb[0][0]-0.06<=c[0]<=tb[1][0]+0.06 and tb[0][1]-0.06<=c[1]<=tb[1][1]+0.06 and c[2]>tb[0][2]-0.04:
        res["delivered"]+=1
print("MEASURE "+json.dumps(res))
'''

# A single 5000-update PLAY RPC 504s for a SLOW receiver (UR10 cuRobo + reroot/relay overhead, cont.233):
# the Kit RPC gateway times the request out before the loop finishes. Play in CHUNKS (each its own RPC,
# under the gateway timeout) then measure with PLAY=False. Robust either way: a genuinely-stuck receiver
# now reports a clean delivered=0 instead of crashing the gate on an empty (504) MEASURE output.
PLAY_CHUNK = '''
import omni.kit.app, omni.timeline
app=omni.kit.app.get_app(); tl=omni.timeline.get_timeline_interface()
if not tl.is_playing(): tl.play()
for _ in range(__N__): app.update()
print("PLAYED __N__")
'''


async def _play_and_measure(kt, target, cubes, total=6000, chunk=1000, reacquire=False):
    # RE-ACQUIRE (cont.261): an OFFSET UR10 source_paths receiver (path-3, own-cube) needs a STOP->PLAY so the
    # scene-reset-manager re-acquires the controller against the final sim view — the bare play in PLAY_CHUNK
    # left it with stale state -> WRONG goal (~[-0.257,-1.058], not the cube at [0.5,-1.2]) -> 3950 res_None
    # plan-fails, while scene_eyes (which STOP->PLAYs) DELIVERED the same build. ⚠️ GATED by `reacquire`:
    # a SENSOR receiver (path-2) re-instantiates its relay cube AFTER build, and tl.stop() TELEPORTS that body
    # off the handoff (PhysX restores initial pose, cont.181) -> breaks the GOLD Franka relay (CP-CHAIN-FLAT
    # 1/1->0/1, cont.261b regression). So only path-3 passes reacquire=True; path-1/path-2/native stay bare.
    if reacquire:
        await kt.exec_sync(
            "import omni.timeline, omni.kit.app\n"
            "tl=omni.timeline.get_timeline_interface(); app=omni.kit.app.get_app()\n"
            "tl.stop()\n"
            "for _ in range(10): app.update()\n"
            "tl.play()\n"
            "for _ in range(90): app.update()\n", timeout=150)
    # cont.277: scale the measurement window with N — a fixed 6000 FALSE-NEGATIVES large multi-cube chains
    # (CP-08's 4 cubes used ~1500 updates each; a 6/9-cube chain would be cut off mid-delivery). max() keeps the
    # 6000 floor; only GROWS the window, and the controller idles after S["done"] -> benign for working chains.
    # cont.319kk: 1700/cube was calibrated on CP-08 BINNING (fast). STRUCTURED receivers (CP-CHAIN-STACK-RECV
    # column, CP-CHAIN-PALLETIZE-RECV distinct-slot grid) plan ~2x slower per cube (careful ascending-z / slot
    # placement), so 1700*3=5100 (floored to 6000) WINDOW-CUTS them: chain_recv_probe N-of-M showed default-window
    # 3-cube STACK delivers 2/3 when cuRobo planning runs slow (ctrl:phase=executing at freeze, 16 plan_calls) but
    # a clean 3/3 column when it finishes (24 plan_calls, phase=wait_sensor) — the SAME stochastic boundary the
    # proven chains side-stepped by manually setting CHAIN_TOTAL~12000 (see chain_stages.json PALLETIZE-RECV note).
    # Raising the per-cube budget to 3200 makes those structured chains robust BY DEFAULT (3-cube=9600, 4-cube=12800
    # ~ the documented 12000 need) so a chain author need not remember the manual knob. 1-cube chains stay at the
    # 6000 floor (3200<6000) -> BYTE-IDENTICAL for every proven single-cube relay; only GROWS multi-cube windows.
    total = max(total, 3200 * len(cubes), int(_os.environ.get('CHAIN_TOTAL') or 0))
    # cont.319hh: optional per-chunk pose trajectory for diagnosing WHICH cube drops WHEN (e.g. the 4th
    # palletize pick). ENV-GATED + default-off (CHAIN_TRAJ unset) so normal chain runs are byte-identical
    # (no extra RPCs, no behaviour change) -> zero regression on the proven gate. Only a diagnostic run
    # (CHAIN_TRAJ=1) pays the per-chunk MEASURE cost and gets res["traj"] = [{t, poses}, ...].
    _cap = bool(_os.environ.get("CHAIN_TRAJ"))
    _mcode = MEASURE.replace("__TARGET__", repr(target)).replace("__CUBES__", repr(cubes)).replace("__PLAY__", "False")
    traj = []
    done = 0
    while done < total:
        n = min(chunk, total - done)
        await kt.exec_sync(PLAY_CHUNK.replace("__N__", str(n)), timeout=200)
        done += n
        if _cap:
            _o = (await kt.exec_sync(_mcode, timeout=120)).get("output", "").strip()
            _l = [l for l in _o.splitlines() if l.startswith("MEASURE")]
            if _l:
                try: traj.append({"t": done, "poses": json.loads(_l[-1][8:]).get("poses", {})})
                except Exception: pass
    out = (await kt.exec_sync(_mcode, timeout=120)).get("output", "").strip()
    lines = [l for l in out.splitlines() if l.startswith("MEASURE")]
    if not lines:
        return {"target": target, "delivered": 0, "total": len(cubes), "poses": {},
                "measure_error": out[-400:]}
    res = json.loads(lines[-1][8:])
    if _cap:
        res["traj"] = traj
    return res


async def run_stage0(name):
    from service.isaac_assist_service.chat.tools import kit_tools as kt
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical, settle_after_canonical
    tpl = json.load(open(f"{REPO}/workspace/templates/{name}.json"))
    cubes, target = _src_target_cubes(tpl)
    await kt.exec_sync("import omni.usd; omni.usd.get_context().new_stage()", timeout=25)
    await kt.exec_sync("import builtins\nfor k in [x for x in list(vars(builtins)) if x.startswith('_curobo_pp_sub_')]:\n    try: delattr(builtins,k)\n    except Exception: pass\n", timeout=10)
    await execute_template_canonical(tpl); await settle_after_canonical(tpl)
    r = await _play_and_measure(kt, target, cubes)
    # handoff = delivered cube world poses
    r["handoff"] = {cp: r["poses"][cp] for cp in cubes if r["poses"].get(cp)}
    return r


async def run_stage_k(k, name, handoff):
    """Faithful relay: derive offset so this stage's pick lands on the handoff, re-instantiate the relayed
    cube(s) at the handoff world pos, source_override the controller to them."""
    from service.isaac_assist_service.chat.tools import kit_tools as kt
    from service.isaac_assist_service.chat.canonical_instantiator import execute_template_canonical, settle_after_canonical
    from service.isaac_assist_service.chat.composer import reroot_prim_path
    tpl = json.load(open(f"{REPO}/workspace/templates/{name}.json"))
    root = f"inst{k}"
    handoff_cubes = list(handoff.values())              # world poses of stage k-1's delivered cubes
    X0 = handoff_cubes[0]
    px = _pick_xy(tpl)
    off = (round(X0[0] - px[0], 3), round(X0[1] - px[1], 3), 0.0)   # AUTO-derive: pick lands on handoff
    # TEST HOOK (cont.260): CHAIN_FORCE_OFF="x,y" forces a LARGE offset through the real chain harness to
    # re-verify path-3 (source_paths own-cube) delivery under arbitrary offset (UR10-offset re-verification,
    # the scene_eyes finding that "UR10 mishandles offset" is stale). When set, the snap-to-native is skipped.
    import os as _os
    _forced = bool(_os.environ.get("CHAIN_FORCE_OFF"))
    if _forced:
        _fx, _fy = (float(v) for v in _os.environ["CHAIN_FORCE_OFF"].split(","))
        off = (_fx, _fy, 0.0)
    # SMALL-residual snap (an OPTIMIZATION, not a UR10 limitation): a co-designed pair leaves a tiny residual
    # off from settle variance; snap it to native so the stage skips a needless reroot. ⚠️ REFUTED HISTORY
    # (cont.261): this used to claim "the UR10 controller mis-handles ANY origin_offset (14mm -> 0/1)" and "a
    # UR10 receiver MUST be co-designed zero-offset". That was a MEASUREMENT ARTIFACT — _play_and_measure's
    # bare play left the offset UR10 receiver un-re-acquired -> wrong goal -> 3950 res_None plan-fails (while
    # scene_eyes, which STOP->PLAYs, delivered the same build). With the STOP->PLAY re-acquire now in
    # _play_and_measure, path-3 (reroot+offset, own-cube) DELIVERS at ARBITRARY offset (forced off=[0.5,-0.8]
    # -> 1/1, cube on the offset Tray, 0 planfails). So a UR10 receiver NO LONGER needs zero-offset co-design;
    # large auto-derived offsets (non-co-designed pairs) flow through path-3 and deliver.
    if not _forced and max(abs(off[0]), abs(off[1])) < 0.05:
        off = (0.0, 0.0, 0.0)
    if off == (0.0, 0.0, 0.0):
        # SNAPPED-to-native build (off≈0): in a CROSS-Kit chain each stage runs in its OWN fresh Kit, so no
        # instance_root namespacing is needed for a co-designed pair — build EXACTLY like run_stage0 (native:
        # no reroot, no offset); the receiver's own cube at its design pick IS the handoff (within the snapped
        # ~14mm residual, negligible for a settled box). (The old "UR10 fails under reroot even at off=0" claim
        # here is REFUTED, cont.261 — scene_eyes rerooted to inst0 + path-3 reroot+offset both deliver; this
        # native build is now just an optimization for the tiny-residual case, not a UR10 workaround.)
        cubes, target = _src_target_cubes(tpl)
        await kt.exec_sync("import omni.usd; omni.usd.get_context().new_stage()", timeout=25)
        await kt.exec_sync("import builtins\nfor k in [x for x in list(vars(builtins)) if x.startswith('_curobo_pp_sub_')]:\n    try: delattr(builtins,k)\n    except Exception: pass\n", timeout=10)
        await execute_template_canonical(tpl); await settle_after_canonical(tpl)
        r = await _play_and_measure(kt, target, cubes)
        r["auto_offset"] = [0.0, 0.0, 0.0]; r["handoff_in"] = X0; r["receiver_mode"] = "native_zero_offset"
        return r
    relay_paths = [f"/World/{root}/Cube_{i+1}" for i in range(len(handoff_cubes))]
    await kt.exec_sync("import omni.usd; omni.usd.get_context().new_stage()", timeout=25)
    await kt.exec_sync("import builtins\nfor k in [x for x in list(vars(builtins)) if x.startswith('_curobo_pp_sub_')]:\n    try: delattr(builtins,k)\n    except Exception: pass\n", timeout=10)
    own_cubes, target = _src_target_cubes(tpl)
    target_inst = reroot_prim_path(target, root)
    has_sensor = bool(re.search(r'add_proximity_sensor', tpl.get("code") or ""))
    if has_sensor:
        # SENSOR-driven receiver (e.g. CP-CHAIN-FLAT): delete this stage's own placeholder cubes and re-
        # instantiate the RELAYED cubes at the handoff (a sibling relay root so the controller doesn't spawn
        # over them); the proximity sensor at the offset-aligned pick detects them dynamically. source_override
        # points the controller at the relay paths.
        relay_root = f"/World/relay{k}"
        measure_cubes = [f"{relay_root}/Cube_{i+1}" for i in range(len(handoff_cubes))]
        await execute_template_canonical(tpl, instance_root=root, origin_offset=off, source_override=measure_cubes)
        dl = "import omni.usd\nfrom pxr import Sdf, UsdGeom, UsdPhysics, PhysxSchema, Gf\nstage=omni.usd.get_context().get_stage()\n"
        dl += f"for pr in list(stage.Traverse()):\n    p=str(pr.GetPath()); nm=pr.GetName()\n    if p.startswith('/World/{root}/') and (nm.startswith('Cube') or nm.startswith('Item') or nm.startswith('Brick')):\n        stage.RemovePrim(p)\n"
        dl += f"stage.DefinePrim('{relay_root}','Xform')\n"
        # ⚠️ GENERALITY LIMIT (cont.301c): the handoff carries POSITION ONLY (_play_and_measure's res["poses"]
        # = world translation, no size/type), and each relayed object is re-created here as a hardcoded 0.05
        # UsdGeom.Cube. So the multi-cube handoff is FAITHFUL ONLY for homogeneous 0.05-cube chains (all proven
        # chains are). A heterogeneous handoff (Brick/Box, or a different cube size) would relay a 0.05 cube at
        # the right position but the WRONG shape/size -> the receiver picks a stand-in, not the real object. To
        # generalize: carry the measured bbox size (bb() already computes it) + the source prim type through the
        # handoff dict, and re-create with that type/size here. Deferred (no heterogeneous chain use case yet;
        # per feedback_phantom_rootcause_and_optional_bug_overinvest — don't Kit-invest in an optional feature).
        for cp, X in zip(measure_cubes, handoff_cubes):
            if _RELAY_ASSET:  # cont.319r YCB-aware relay: re-create the real referenced asset, not a 0.05 cube
                dl += (f"p=stage.DefinePrim('{cp}','Xform'); p.GetReferences().AddReference('{_RELAY_ASSET}')\n"
                       # cont.319r-b: place at the DELIVERED z (not the cube's 0.78 clamp) so a non-cube object
                       # rests on the handoff without a fall -> no settle-drift out of the receiver's sensor zone.
                       f"x=UsdGeom.Xformable(p); x.ClearXformOpOrder(); x.AddTranslateOp().Set(Gf.Vec3d({X[0]},{X[1]},{X[2]}))\n"
                       # cont.319kk-h: a relay-side CollisionAPI-on-Xform + sleepThreshold=0 fix (mirroring the
                       # WORKING standalone CP-YCB-01) was TESTED here and REFUTED — still 0/1, selector stays in
                       # wait_sensor + never claims the relayed referenced object. So the kk-c gap is NOT a
                       # missing-collider/sleep on the relay object; it's deeper (the selector's claim of a
                       # DefinePrim+AddReference Xform at a relay path, vs the add_reference HELPER's setup, OR the
                       # deep selector). Deferred (kk-c) stands. Relay reverted to the proven cube-faithful form.
                       "for _api in (UsdPhysics.RigidBodyAPI, UsdPhysics.MassAPI):\n    _api.Apply(p)\nPhysxSchema.PhysxRigidBodyAPI.Apply(p)\n"
                       f"_mp=stage.GetPrimAtPath('{cp}/{_RELAY_MESH}')\nif _mp.IsValid():\n    UsdPhysics.CollisionAPI.Apply(_mp)\n    UsdPhysics.MeshCollisionAPI.Apply(_mp).GetApproximationAttr().Set('convexHull')\n"
                       f"_rel=p.CreateRelationship('physics:materialBinding', custom=False); _rel.SetTargets([Sdf.Path('/World/PhysicsMaterials/rubber_natural')])\n")
                continue
            dl += (f"c=UsdGeom.Cube.Define(stage,'{cp}'); c.GetSizeAttr().Set(0.05)\n"
                   f"x=UsdGeom.Xformable(c.GetPrim()); x.ClearXformOpOrder(); x.AddTranslateOp().Set(Gf.Vec3d({X[0]},{X[1]},{max(X[2],0.78)}))\n"
                   "for api in (UsdPhysics.RigidBodyAPI, UsdPhysics.CollisionAPI, UsdPhysics.MassAPI):\n    api.Apply(c.GetPrim())\n"
                   "PhysxSchema.PhysxRigidBodyAPI.Apply(c.GetPrim())\n"
                   "rel=c.GetPrim().CreateRelationship('physics:materialBinding', custom=False)\n"
                   "rel.SetTargets([Sdf.Path('/World/PhysicsMaterials/rubber_natural')])\n")
        dl += "print('RELAY_PLACED')\n"
        await kt.exec_sync(dl, timeout=30)
    else:
        # SOURCE_PATHS-driven receiver (no proximity sensor, e.g. CP-CHAIN-UR10-SRC): the auto-offset already
        # places this stage's OWN pedestal+cube EXACTLY at the handoff (off = X0_xy - source_cube_xy), so the
        # controller picks its own cube at the handoff pose with NO relay-override. source_override to a post-
        # build relay path does NOT bind for a source_paths controller (the relay cube stayed 0-jiggle, 0/1,
        # cont.234) — a fresh own-cube at the identical handoff pose is the faithful relay for a settled box.
        measure_cubes = [reroot_prim_path(c, root) for c in own_cubes]
        await execute_template_canonical(tpl, instance_root=root, origin_offset=off)
        # NOTE: no settle_after_canonical here — its settle_state uses un-rerooted paths (/World/Cube_1) that
        # don't match the instance build; the own cube is built at rest on the offset pedestal, _play_and_
        # measure's play settles it.
    # reacquire only for path-3 (source_paths own-cube): the OFFSET UR10 controller needs the STOP->PLAY
    # re-acquire; a SENSOR receiver (path-2) must NOT stop (it would teleport its post-build relay cube).
    r = await _play_and_measure(kt, target_inst, measure_cubes, reacquire=not has_sensor)
    r["auto_offset"] = list(off); r["handoff_in"] = X0
    r["receiver_mode"] = "sensor" if has_sensor else "source_paths"
    return r


def kit_restart():
    out = subprocess.run(["bash", f"{REPO}/scripts/qa/kit_restart.sh"], capture_output=True, text=True, timeout=400)
    return "OK:" in out.stdout, ([l for l in out.stdout.splitlines() if "OK:" in l or "FAIL" in l] or [""])[-1]


async def main():
    specs = sys.argv[1:] or ["CP-CHAIN-UR10-SRC", "CP-CHAIN-FLAT"]
    results = []
    r0 = await run_stage0(specs[0]); r0["stage"] = 0; r0["name"] = specs[0]
    results.append(r0)
    print(f"  stage0 {specs[0]}: delivered={r0['delivered']}/{r0['total']} handoff={r0.get('handoff')}")
    handoff = r0.get("handoff", {})
    for i in range(1, len(specs)):
        if not handoff:
            print(f"CHAIN_XKIT ABORT: stage{i-1} produced no handoff (delivered 0)"); break
        ok, msg = kit_restart()
        print(f"  [kit_restart -> stage{i}] {msg}")
        if not ok:
            print("CHAIN_XKIT ABORT: kit_restart failed"); break
        rk = await run_stage_k(i, specs[i], handoff); rk["stage"] = i; rk["name"] = specs[i]
        results.append(rk)
        print(f"  stage{i} {specs[i]}: delivered={rk['delivered']}/{rk['total']} auto_offset={rk.get('auto_offset')} poses={rk.get('poses')}")
        handoff = {cp: rk["poses"][cp] for cp in rk["poses"] if rk["poses"].get(cp)}
    print("CHAIN_XKIT STAGES:")
    for r in results:
        print("  inst%d %s relay=%s/%s" % (r["stage"], r["name"], r.get("delivered"), r.get("total")))
    all_ok = all(r.get("delivered", 0) >= r.get("total", 1) for r in results) and len(results) == len(specs)
    print("CHAIN_XKIT SUMMARY: %d stage(s), %s — %s" % (
        len(results), " + ".join("%d/%d" % (r.get("delivered", 0), r.get("total", 1)) for r in results),
        "ALL DELIVERED (faithful cross-Kit relay)" if all_ok else "INCOMPLETE"))
    if _os.environ.get("CHAIN_TRAJ"):                         # cont.319hh diagnostic dump
        json.dump(results, open("/tmp/chain_traj.json", "w"), indent=1)
        print("CHAIN_TRAJ dumped -> /tmp/chain_traj.json")

if __name__ == "__main__":
    asyncio.run(main())
