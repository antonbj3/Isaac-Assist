"""Test cuRobo vhold variants — for each mode, run 3 iter via observe_one + read scene data.
Captures: delivered (cube_M support), L shift, R shift, drop_xy.
"""
import asyncio, sys, os, json
from pathlib import Path
REPO = Path("/home/anton/projects/Omniverse_Nemotron_Ext")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/"scripts"))
from review.sweep_all_rewritten import observe_one

INIT_L = (-0.3505, 0.30); INIT_R = (-0.2495, 0.30)
BIN_C = (0.2675, -0.3325)

async def run_n_iters(label, n=10):
    rows = []
    for i in range(n):
        rec = await observe_one("CP-PRECISION-3CUBE")
        if rec.get("exception"):
            rows.append({"i": i+1, "exc": rec["exception"]})
            continue
        cs = rec.get("cube_supports", {})
        fM = cs.get('/World/Cube_M', {}).get('final_pos', [0,0,0])
        fL = cs.get('/World/Cube_L', {}).get('final_pos', [0,0,0])
        fR = cs.get('/World/Cube_R', {}).get('final_pos', [0,0,0])
        sup = cs.get('/World/Cube_M', {}).get('support', '?')
        delivered = 'Bin/Floor' in str(sup) or cs.get('/World/Cube_M', {}).get('under_target', False)
        L_shift = ((fL[0]-INIT_L[0])**2 + (fL[1]-INIT_L[1])**2)**0.5 * 1000
        R_shift = ((fR[0]-INIT_R[0])**2 + (fR[1]-INIT_R[1])**2)**0.5 * 1000
        drop_xy = ((fM[0]-BIN_C[0])**2 + (fM[1]-BIN_C[1])**2)**0.5 * 1000
        rows.append({"i": i+1, "deliv": int(delivered), "L_mm": round(L_shift,1), "R_mm": round(R_shift,1), "drop_mm": round(drop_xy,1), "sup": sup.split('/')[-1] if sup else '?'})
    print(f"\n=== {label} ===")
    for r in rows: print(f"  iter {r['i']}: deliv={r.get('deliv','-')} L={r.get('L_mm','-')}mm R={r.get('R_mm','-')}mm drop={r.get('drop_mm','-')}mm sup={r.get('sup','-')}{'  EXC:'+r.get('exc','') if 'exc' in r else ''}")
    deliv_count = sum(r.get('deliv',0) for r in rows if 'deliv' in r)
    avg_L = sum(r.get('L_mm',0) for r in rows if 'L_mm' in r) / max(1,len([r for r in rows if 'L_mm' in r]))
    avg_R = sum(r.get('R_mm',0) for r in rows if 'R_mm' in r) / max(1,len([r for r in rows if 'R_mm' in r]))
    print(f"  AGG: {deliv_count}/{n} delivered, avg L={avg_L:.1f}mm R={avg_R:.1f}mm")
    return {"label": label, "rows": rows, "delivered": deliv_count, "avg_L_mm": avg_L, "avg_R_mm": avg_R}

async def set_vhold_mode_in_kit(mode):
    """Set builtins._vhold_mode_test in Kit subprocess so handler reads it."""
    from service.isaac_assist_service.chat.tools import kit_tools
    code = f"import builtins; builtins._vhold_mode_test = {mode}; print('VHOLD_MODE_SET={mode}')"
    r = await kit_tools.exec_sync(code, timeout=5)
    print(r.get("output","").strip())

async def main():
    mode = int(os.environ.get('VHOLD_MODE', '0'))
    label = {0:'BASELINE', 1:'PCM-hold-base', 2:'PCM-hold-goal', 3:'PCM-hold-w0.1', 4:'PCM-reach-w1', 5:'PCM-reach-w10', 6:'PCM-reach-w100', 7:'PCM-hold+reach-w100', 8:'PCM-hold-w100'}.get(mode, f'mode{mode}')
    await set_vhold_mode_in_kit(mode)
    result = await run_n_iters(label, n=10)
    print(f"\nJSON: {json.dumps(result)}")

if __name__ == "__main__":
    asyncio.run(main())
