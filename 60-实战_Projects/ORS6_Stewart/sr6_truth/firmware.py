# -*- coding: utf-8 -*-
"""Faithful 1:1 port of the SR6-Alpha4_ESP32.ino kinematics.
Every constant and formula is copied from the firmware source so that the
Python/JS model is provably identical to what the real ESP32 runs.
Source lines referenced in comments (SR6-Alpha4_ESP32.ino).
"""
import math

MS_PER_RAD = 637          # #define ms_per_rad 637  (us/rad)
PI = 3.14159              # firmware uses literal 3.14159

def _map(x, in_min, in_max, out_min, out_max):
    # Arduino map(): integer-style linear interpolation (no clamping)
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

def constrain(x, lo, hi):
    return lo if x < lo else hi if x > hi else x

# --- exact arm-angle functions -------------------------------------------------
def SetMainServo(x, y):
    """firmware SetMainServo(float x,float y); x,y in 1/100 mm. returns us-from-neutral."""
    x /= 100.0; y /= 100.0
    gamma = math.atan2(x, y)
    csq = x*x + y*y
    c = math.sqrt(csq)
    beta = math.acos((csq - 28125) / (100*c))      # arm=50, rod=175 -> 175^2-50^2=28125
    return MS_PER_RAD * (gamma + beta - PI)

def SetPitchServo(x, y, z, pitch):
    """firmware SetPitchServo(float x,y,z,pitch); x,y,z in 1/100mm, pitch in 1/100 deg."""
    pitch *= 0.0001745
    x += 5500*math.sin(0.2618 + pitch)             # 55mm lever, 15deg home offset
    y -= 5500*math.cos(0.2618 + pitch)
    x /= 100.0; y /= 100.0; z /= 100.0
    bsq = 36250 - (75 + z)**2                       # equivalent arm length (rod=175 @ z=0)
    gamma = math.atan2(x, y)
    csq = x*x + y*y
    c = math.sqrt(csq)
    beta = math.acos((csq + 5625 - bsq) / (150*c))  # pitch arm=75 -> 2*75=150, 75^2=5625
    return MS_PER_RAD * (gamma + beta - PI)

# --- T-code axis mapping (SR6 mode, from the main loop) -------------------------
# Inputs are TCode channel values 0..9999 (neutral = 5000).
def tcode_to_servo_us(xLin=5000, yLin=5000, zLin=5000, xRot=5000, yRot=5000, zRot=5000):
    roll   = _map(yRot,0,9999,-3000,3000)
    pitch  = _map(zRot,0,9999,-2500,2500)
    fwd    = _map(yLin,0,9999,-3000,3000)
    thrust = _map(xLin,0,9999,-6000,6000)
    side   = _map(zLin,0,9999,-3000,3000)
    out1 = SetMainServo(16248 - fwd, 1500 + thrust + roll)   # Lower left
    out2 = SetMainServo(16248 - fwd, 1500 - thrust - roll)   # Upper left
    out5 = SetMainServo(16248 - fwd, 1500 - thrust + roll)   # Upper right
    out6 = SetMainServo(16248 - fwd, 1500 + thrust - roll)   # Lower right
    out3 = SetPitchServo(16248 - fwd, 4500 - thrust,  side - 1.5*roll, -pitch)  # Left pitch
    out4 = SetPitchServo(16248 - fwd, 4500 - thrust, -side + 1.5*roll, -pitch)  # Right pitch
    # firmware sign convention applied at ledcWrite (ZERO -/+ out). We return the
    # signed delta each arm physically rotates (matching ledcWrite signs):
    return {
        "LL": -out1, "UL": +out2, "LR": +out6, "UR": -out5,
        "PL": constrain(-out3, -600, 1000),   # ledcWrite uses (ZERO - out3) clamped to [ZERO-600, ZERO+1000]
        "PR": constrain(+out4, -1000, 600),   # ledcWrite uses (ZERO + out4) clamped to [ZERO-1000, ZERO+600]
    }

if __name__ == "__main__":
    h = tcode_to_servo_us()
    print("home servo us-from-neutral:", {k: round(v,2) for k,v in h.items()})
