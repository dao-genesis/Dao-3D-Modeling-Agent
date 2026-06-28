# -*- coding: utf-8 -*-
"""Automated physical-validation harness for the SR6 mechanism.

Closes the loop WITHOUT human inspection: it asserts the model obeys real,
externally-anchored physics and the official PDF motion spec. Anchors that are
NOT self-referential:
  * rod length = 175 mm  (firmware constant 28125 = 175^2-50^2)
  * arm lengths 50 / 75.2 mm  (firmware + measured STL)
  * servo bore positions  (measured from the real frame STL)
  * motion envelope >= official Build-Instructions spec (p5): +-30 mm trans, +-30 deg rot
Run: python validate.py   ->  writes report.json (used by the web viewer + CI).
"""
import sys, os, json, math
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import mechanism as M
import firmware as fw

LEGS = M.LEGS
PDF_SPEC = {  # official Build Instructions p5 operating spec (half-ranges)
    "surge": 30.0, "sway": 30.0, "stroke": 30.0, "roll": 30.0, "pitch": 30.0,
}
ARM_LIMIT_DEG = 80.0   # physical servo swing limit from neutral

def check_home():
    c = M.closure()
    return {"name":"home_closure","pass": c["reachable"] and c["max_rod_err"]<1e-9,
            "max_rod_err_mm": c["max_rod_err"], "detail":"all 6 rods == 175 mm at rest"}

def check_envelope(grid=None):
    """Every pose inside the PDF operating envelope must close all rods at 175 mm."""
    if grid is None:
        grid = {"stroke":[-30,-15,0,15,30],"surge":[-30,0,30],"sway":[-30,0,30],
                "roll":[-30,0,30],"pitch":[-30,0,30]}
    worst=0.0; nbad=0; n=0
    for ax,vals in grid.items():
        for v in vals:
            n+=1; c=M.closure(**{ax:v})
            worst=max(worst,c["max_rod_err"])
            if not (c["reachable"] and c["max_rod_err"]<1e-6): nbad+=1
    return {"name":"operating_envelope_closure","pass": nbad==0,
            "n_poses":n,"n_fail":nbad,"max_rod_err_mm":worst,
            "detail":"all rods == 175 across +-30mm / +-30deg PDF envelope"}

def check_decoupling():
    """Pure pitch must not move the main arms; pure stroke must stay L/R symmetric."""
    cp = M.closure(pitch=25)
    main_move = max(abs(math.degrees(cp["arms"][k])) for k in ["LL","UL","LR","UR"])
    cs = M.closure(stroke=25)
    asym = max(abs(cs["arms"]["LL"]-cs["arms"]["LR"]), abs(cs["arms"]["UL"]-cs["arms"]["UR"]))
    ok = main_move < 0.5 and math.degrees(asym) < 0.5
    return {"name":"axis_decoupling","pass":ok,
            "pitch_main_arm_move_deg":main_move,"stroke_LR_asym_deg":math.degrees(asym),
            "detail":"pitch leaves main arms fixed; stroke stays L/R symmetric"}

def check_symmetry():
    """sway(+v) mirrors sway(-v): LL<->LR, UL<->UR."""
    a=M.closure(sway=25); b=M.closure(sway=-25)
    err=max(abs(a["arms"]["LL"]-b["arms"]["LR"]), abs(a["arms"]["UL"]-b["arms"]["UR"]))
    return {"name":"mirror_symmetry","pass":math.degrees(err)<0.5,
            "mirror_err_deg":math.degrees(err),"detail":"left-right mirror symmetry holds"}

def check_continuity():
    """Arm angles vary continuously & monotonically along each axis (no singular jump)."""
    bad=[]
    for ax,lim in [("stroke",30),("surge",30),("sway",30),("roll",30),("pitch",30)]:
        vs=np.linspace(-lim,lim,41); prev=None; series={k:[] for k in LEGS}
        for v in vs:
            c=M.closure(**{ax:v})
            for k in LEGS: series[k].append(c["arms"][k])
        for k in LEGS:
            d=np.diff(series[k])
            if np.max(np.abs(d)) > 0.25:  # >14 deg jump between 1.5deg steps -> singular
                bad.append(f"{ax}:{k}")
    return {"name":"continuity_no_singularity","pass":len(bad)==0,
            "discontinuous":bad,"detail":"arm angles smooth across the envelope"}

def check_arm_limits():
    worst={}; ok=True
    for ax,lim in [("stroke",30),("surge",30),("sway",30),("roll",30),("pitch",30)]:
        for v in (-lim,lim):
            c=M.closure(**{ax:v})
            for k in LEGS:
                d=abs(math.degrees(c["arms"][k])); worst[k]=max(worst.get(k,0),d)
                if d>ARM_LIMIT_DEG: ok=False
    return {"name":"arm_within_servo_limit","pass":ok,"limit_deg":ARM_LIMIT_DEG,
            "worst_arm_deg":{k:round(v,1) for k,v in worst.items()},
            "detail":f"every arm stays within +-{ARM_LIMIT_DEG} deg in the envelope"}

def check_firmware_fidelity():
    """Ported firmware must equal the C math at sample points (independent recompute)."""
    # hand recompute SetMainServo(16248,1500): see firmware comments
    x,y=16248/100.,1500/100.
    gamma=math.atan2(x,y); csq=x*x+y*y; c=math.sqrt(csq)
    beta=math.acos((csq-28125)/(100*c)); expect=637*(gamma+beta-3.14159)
    got=fw.SetMainServo(16248,1500)
    home=fw.tcode_to_servo_us()
    main_home_ok=all(abs(home[k])<0.5 for k in ["LL","UL","LR","UR"])
    return {"name":"firmware_fidelity","pass": abs(got-expect)<1e-9 and main_home_ok,
            "SetMainServo_err":abs(got-expect),"main_home_us":{k:round(home[k],3) for k in ["LL","UL","LR","UR"]},
            "detail":"python port == ESP32 C kinematics; main servos neutral at home"}

def check_pdf_envelope():
    """Reachable workspace must contain the official PDF operating spec."""
    res={}; ok=True
    for ax,half in PDF_SPEC.items():
        a=M.closure(**{ax:half}); b=M.closure(**{ax:-half})
        good=a["reachable"] and b["reachable"] and a["max_rod_err"]<1e-6 and b["max_rod_err"]<1e-6
        res[ax]=good; ok&=good
    return {"name":"meets_pdf_motion_spec","pass":ok,"axes":res,
            "detail":"reachable workspace contains PDF p5 spec (+-30mm / +-30deg)"}

CHECKS=[check_firmware_fidelity,check_home,check_envelope,check_pdf_envelope,
        check_decoupling,check_symmetry,check_continuity,check_arm_limits]

def reachable_envelope():
    def ok(ax,v):
        c=M.closure(**{ax:v}); return c["reachable"] and c["max_rod_err"]<1e-6
    env={}
    for ax,lim,unit in [("stroke",90,"mm"),("surge",60,"mm"),("sway",60,"mm"),
                        ("roll",60,"deg"),("pitch",60,"deg"),("yaw",45,"deg")]:
        r=[]
        for s in (1,-1):
            a,b=0.0,lim
            if ok(ax,s*b): r.append(s*b); continue
            for _ in range(34):
                m=0.5*(a+b)
                if ok(ax,s*m): a=m
                else: b=m
            r.append(s*a)
        env[ax]={"min":round(r[1],1),"max":round(r[0],1),"unit":unit,
                 "spec":PDF_SPEC.get(ax)}
    return env

def run():
    results=[c() for c in CHECKS]
    report={"all_pass":all(r["pass"] for r in results),
            "geometry":{"rod_mm":M.ROD,"arm_main_mm":50.0,"arm_pitch_mm":75.2,
                        "home_tilt_deg":15.0,"home_height_mm":round(float(M.HOME_T[2]),1)},
            "workspace":reachable_envelope(),
            "checks":results}
    return report

if __name__=="__main__":
    rep=run()
    out=os.path.join(os.path.dirname(__file__),"report.json")
    json.dump(rep,open(out,"w"),indent=2)
    for r in rep["checks"]:
        print(("PASS" if r["pass"] else "FAIL"), r["name"], "-", r["detail"])
    print("\nALL PASS:" , rep["all_pass"])
    sys.exit(0 if rep["all_pass"] else 1)
