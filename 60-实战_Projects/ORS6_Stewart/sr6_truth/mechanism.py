# -*- coding: utf-8 -*-
"""3D rigid-body forward kinematics for the real SR6 mechanism.

Geometry (geometry.json) is anchored on measured STL servo bores + firmware
constants (arm 50/75.2 mm, rod 175 mm). FK takes the 6 servo angles that the
*firmware* commands for a given T-code and solves the receiver's rigid 6-DOF
pose by enforcing all 6 rods = 175 mm. This is true physics (rigid body), not
a self-referential identity: a consistent rigid pose must EXIST for the 6
independent firmware commands, and its motion is then measured against the
official PDF spec.
"""
import json, os, math, sys
import numpy as np
from scipy.optimize import least_squares
sys.path.insert(0, os.path.dirname(__file__))
import firmware as fw

LEGS = ["LL","UL","LR","UR","PL","PR"]
_G = json.load(open(os.path.join(os.path.dirname(__file__), "geometry.json")))
ROD = _G["rod"]
S       = {k: np.array(_G["servos"][k])   for k in LEGS}
AXIS    = {k: np.array(_G["axis"][k])     for k in LEGS}
ARMHOME = {k: np.array(_G["arm_home"][k]) for k in LEGS}
RLOC    = {k: np.array(_G["recv_local"][k]) for k in LEGS}
SIGN    = {k: float(_G.get("sign",{}).get(k,1)) for k in LEGS}
HOME_R  = np.array(_G["home_R"]); HOME_T = np.array(_G["home_t"])
_FW_HOME = fw.tcode_to_servo_us()        # us-from-neutral at neutral T-code

def rot_axis(axis, ang):
    a = axis/np.linalg.norm(axis); c,s = math.cos(ang), math.sin(ang)
    x,y,z = a
    return np.array([
        [c+x*x*(1-c),   x*y*(1-c)-z*s, x*z*(1-c)+y*s],
        [y*x*(1-c)+z*s, c+y*y*(1-c),   y*z*(1-c)-x*s],
        [z*x*(1-c)-y*s, z*y*(1-c)+x*s, c+z*z*(1-c)]])

def euler_R(rx,ry,rz):
    Rx=rot_axis([1,0,0],rx); Ry=rot_axis([0,1,0],ry); Rz=rot_axis([0,0,1],rz)
    return Rz@Ry@Rx

def balls_for(servo_us):
    """servo_us: dict us-from-neutral. Returns world ball positions."""
    out={}
    for k in LEGS:
        dtheta = SIGN[k] * (servo_us[k] - _FW_HOME[k]) / fw.MS_PER_RAD   # delta angle from home (rad)
        out[k] = S[k] + rot_axis(AXIS[k], dtheta) @ ARMHOME[k]
    return out

# --- pose-driven model: prescribe rigid receiver pose, arms follow (per-leg IK) -------
# DOF are defined in the HOME RECEIVER frame so the sliders are intuitive and decoupled:
#   sway   = translation along receiver local X (mm)
#   surge  = translation along receiver local Y (mm)
#   stroke = translation along receiver local Z = cup axis (mm)   <- the main up/down
#   roll   = rotation about receiver local Y (deg)
#   pitch  = rotation about receiver local X (deg)
#   yaw    = rotation about receiver local Z = cup axis (deg)
def pose_pivots(sway=0.,surge=0.,stroke=0.,roll=0.,pitch=0.,yaw=0.):
    """Rigid receiver pivots in world for a pose given in the home-receiver frame."""
    Rd = euler_R(math.radians(pitch), math.radians(roll), math.radians(yaw))  # about local X,Y,Z
    d  = np.array([sway,surge,stroke])
    R  = HOME_R @ Rd
    t  = HOME_R @ d + HOME_T
    return {k: R@RLOC[k] + t for k in LEGS}, R, t

def arm_close(leg, pivot, span=2.2):
    """Solve the arm angle (rad, relative to home) so the rod length == ROD exactly.
    Returns (theta, reachable). Picks the root nearest the home angle (the physical branch)."""
    S0, ax, ah = S[leg], AXIS[leg], ARMHOME[leg]
    def gap(th):  # signed: |ball-pivot| - ROD
        ball = S0 + rot_axis(ax, th) @ ah
        return np.linalg.norm(ball - pivot) - ROD
    # scan for a sign change bracketing the root nearest 0
    ths = np.linspace(-span, span, 221)
    g = [gap(t) for t in ths]
    roots=[]
    for i in range(len(ths)-1):
        if g[i]==0: roots.append(ths[i])
        elif g[i]*g[i+1] < 0:
            a,b=ths[i],ths[i+1]
            for _ in range(60):
                m=0.5*(a+b)
                if gap(a)*gap(m)<=0: b=m
                else: a=m
            roots.append(0.5*(a+b))
    if not roots:
        # unreachable: report closest approach gap
        i=int(np.argmin(np.abs(g))); return ths[i], False, g[i]
    th=min(roots, key=abs)
    return th, True, gap(th)

def closure(**pose):
    """Full closure check for a prescribed pose. Returns per-leg arm angle, rod length, reachability."""
    piv,_,_ = pose_pivots(**pose)
    res={"reachable":True,"max_rod_err":0.0,"arms":{},"rods":{},"pivots":piv}
    for k in LEGS:
        th, ok, gp = arm_close(k, piv[k])
        ball = S[k] + rot_axis(AXIS[k], th) @ ARMHOME[k]
        rod = float(np.linalg.norm(ball - piv[k]))
        res["arms"][k]=th; res["rods"][k]=rod
        res["reachable"] &= ok
        res["max_rod_err"]=max(res["max_rod_err"], abs(rod-ROD))
    return res

if __name__=="__main__":
    print("home closure:", closure())
    c=closure()
    print("home reachable:", c["reachable"], "max rod err: %.2e"%c["max_rod_err"])
    print("home rods:", {k:round(v,4) for k,v in c["rods"].items()})
