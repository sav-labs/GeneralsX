"""Modern USA infantry that replaces the art of the retail Ranger, Pathfinder, Colonel Burton and Pilot.

GeneralsX @feature Claude 16/10/2026 Rigid soldiers (one mesh per body part, each on its own bone) with
their own skeleton and a set of procedural clips: stand, look around, run, aim, fire, death falls,
flailing, cheering, free fall, parachute hang, landing, rappelling, kneeling work and climbing. Arms
reach for the weapon and feet stay planted through two-bone IK, so one pose description drives every
clip. The retail skeleton and its animations stay untouched: ArtRemap maps each retail animation name
to the clip that matches the condition state it plays in (see AmericaInfantryArt.ini), and logic keeps
the retail bones (Muzzle and the rest) as it does for vehicles.

Rest pose: standing, facing +X, arms hanging. Units: about 10.5 tall, the size of the retail soldiers.
"""

import math

import numpy as np

from geometry import Builder, Region, ShadeFn
from w3d import ANIM_CHANNEL_Q, ANIM_CHANNEL_X, ANIM_CHANNEL_Y, ANIM_CHANNEL_Z, Material, Mesh, Model

UNIFORM = Region(0.0, 0.5, 1.0, 1.0, world_size=6.0)
GEAR = Region(0.0, 0.25, 1.0, 0.5, world_size=4.0)
SKIN = Region(0.0, 0.125, 1.0, 0.25, world_size=4.0)
DARK = Region(0.0, 0.0, 1.0, 0.125, world_size=4.0)
TEAM = Region(0, 0, 1, 1, world_size=4.0)

RATE = 30

# Rest skeleton: name -> (parent, world position).
SKELETON = [
    ("PELVIS", "ROOTTRANSFORM", (0.0, 0.0, 5.4)),
    ("SPINE", "PELVIS", (0.0, 0.0, 6.1)),
    ("HEAD", "SPINE", (0.0, 0.0, 9.0)),
    ("RUPPERARM", "SPINE", (0.0, -1.3, 8.55)),
    ("RFOREARM", "RUPPERARM", (0.0, -1.3, 6.95)),
    ("LUPPERARM", "SPINE", (0.0, 1.3, 8.55)),
    ("LFOREARM", "LUPPERARM", (0.0, 1.3, 6.95)),
    ("RTHIGH", "PELVIS", (0.0, -0.6, 5.2)),
    ("RCALF", "RTHIGH", (0.0, -0.6, 2.85)),
    ("RFOOT", "RCALF", (0.0, -0.6, 0.55)),
    ("LTHIGH", "PELVIS", (0.0, 0.6, 5.2)),
    ("LCALF", "LTHIGH", (0.0, 0.6, 2.85)),
    ("LFOOT", "LCALF", (0.0, 0.6, 0.55)),
    ("WEAPON", "SPINE", (1.0, -0.8, 6.6)),
]
UPPER_ARM, FOREARM = 1.6, 1.6  # shoulder to elbow, elbow to the middle of the hand
THIGH, CALF = 2.35, 2.3
ANKLE_Z = 0.55
SUPPORT = 2.0  # how far along the weapon the support hand holds the handguard


# --- rotations -----------------------------------------------------------------------------------
def rot(axis, degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def euler(e):
    """(yaw about Z, pitch about Y, roll about X) in degrees. Positive pitch tips the top towards +X."""
    yaw, pitch, roll = e
    return rot("z", yaw) @ rot("y", pitch) @ rot("x", roll)


def arc(a, b):
    """Shortest rotation taking direction a onto direction b."""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if c < -0.9999:
        return rot("x", 180.0)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1 + c)


def quaternion(m):
    """Rotation matrix -> (x, y, z, w), the order W3D animation channels store."""
    t = m[0, 0] + m[1, 1] + m[2, 2]
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = ((m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s)
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = (0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s)
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = ((m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s)
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = ((m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s)
    return tuple(float(c) for c in q)


def two_bone(root, target, a, b, pole):
    """Joint position of a two-bone chain from root reaching for target, bending towards pole."""
    d = target - root
    dist = float(np.linalg.norm(d))
    dist = min(max(dist, abs(a - b) + 1e-3), a + b - 1e-3)
    d = d / (np.linalg.norm(d) or 1.0)
    cos_a = (a * a + dist * dist - b * b) / (2 * a * dist)
    side = pole - np.dot(pole, d) * d
    side = side / (np.linalg.norm(side) or 1.0)
    return root + d * a * cos_a + side * a * math.sqrt(max(0.0, 1 - cos_a * cos_a))


# --- poses -----------------------------------------------------------------------------------------
def pose(**kw):
    """A pose: pelvis offset and turn, spine and head turns, legs (feet planted at a spot by IK, or
    joint angles), the weapon's grip position and aim in world space, and arms (on the weapon by IK,
    or joint angles)."""
    p = {
        "pelvis": (0.0, 0.0, 0.0), "hips": (0.0, 0.0, 0.0), "spine": (0.0, 0.0, 0.0), "head": (0.0, 0.0, 0.0),
        "lfoot": (0.15, 0.6, ANKLE_Z), "rfoot": (-0.15, -0.6, ANKLE_Z), "lfoot_pitch": 0.0, "rfoot_pitch": 0.0,
        "lleg": None, "rleg": None,  # (thigh euler, calf euler) instead of IK
        "grip": (1.2, -0.75, 6.4), "aim": (25.0, 30.0, 0.0),  # weapon (yaw, pitch down, roll)
        "larm": None, "rarm": None,  # (upper euler, fore euler) instead of holding the weapon
    }
    p.update(kw)
    return p


def blend(a, b, t):
    """Mix two poses of the same shape; t eases in and out."""
    t = t * t * (3 - 2 * t)
    out = {}
    for k, va in a.items():
        vb = b[k]
        if va is None or vb is None:
            out[k] = vb if t >= 0.5 else va
        elif isinstance(va, tuple) and va and isinstance(va[0], tuple):
            out[k] = tuple(tuple(x + (y - x) * t for x, y in zip(pa, pb)) for pa, pb in zip(va, vb))
        elif isinstance(va, tuple):
            out[k] = tuple(x + (y - x) * t for x, y in zip(va, vb))
        else:
            out[k] = va + (vb - va) * t
    return out


def solve(p, has_weapon):
    """World rotation and position of every bone for a pose."""
    world = {"ROOTTRANSFORM": (np.eye(3), np.zeros(3))}
    rest = {name: np.array(pos, float) for name, _, pos in SKELETON}
    rest["ROOTTRANSFORM"] = np.zeros(3)
    parent = {name: par for name, par, _ in SKELETON}

    def place(name, r):
        pr, pt = world[parent[name]]
        local = rest[name] - rest[parent[name]]
        world[name] = (r, pt + pr @ local)

    place("PELVIS", euler(p["hips"]))
    world["PELVIS"] = (world["PELVIS"][0], world["PELVIS"][1] + np.array(p["pelvis"]))
    place("SPINE", world["PELVIS"][0] @ euler(p["spine"]))
    place("HEAD", world["SPINE"][0] @ euler(p["head"]))

    # Weapon: grip position and aim in world space; it hangs off the spine.
    yaw, pitch, roll = p["aim"]
    w_rot = rot("z", yaw) @ rot("y", pitch) @ rot("x", roll)
    world["WEAPON"] = (w_rot, np.array(p["grip"], float))

    hip_yaw = rot("z", p["hips"][0])
    for side, sign in (("L", 1.0), ("R", -1.0)):
        # Arms.
        upper, fore = side + "UPPERARM", side + "FOREARM"
        spine_r = world["SPINE"][0]
        place(upper, spine_r)
        shoulder = world[upper][1]
        arm = p[side.lower() + "arm"]
        if arm is None and has_weapon:
            hand = world["WEAPON"][1] if side == "R" else world["WEAPON"][1] + w_rot @ np.array([SUPPORT, 0.0, 0.25])
            pole = spine_r @ np.array([-0.4, sign * 1.0, -1.0])
            elbow = two_bone(shoulder, hand, UPPER_ARM, FOREARM, pole)
            ur = arc(np.array([0, 0, -1.0]), elbow - shoulder)
            world[upper] = (ur, shoulder)
            world[fore] = (arc(np.array([0, 0, -1.0]), hand - elbow), elbow)
        else:
            ue, fe = arm if arm is not None else ((0.0, 0.0, sign * 8.0), (0.0, -15.0, 0.0))
            ur = spine_r @ euler(ue)
            world[upper] = (ur, shoulder)
            world[fore] = (ur @ euler(fe), shoulder + ur @ np.array([0, 0, -UPPER_ARM]))
        # Legs.
        thigh, calf, foot = side + "THIGH", side + "CALF", side + "FOOT"
        place(thigh, world["PELVIS"][0])
        hip = world[thigh][1]
        leg = p[side.lower() + "leg"]
        if leg is None:
            ankle = np.array(p[side.lower() + "foot"], float)
            knee = two_bone(hip, ankle, THIGH, CALF, hip_yaw @ np.array([1.0, sign * 0.15, 0.0]))
            world[thigh] = (arc(np.array([0, 0, -1.0]), knee - hip), hip)
            world[calf] = (arc(np.array([0, 0, -1.0]), ankle - knee), knee)
            world[foot] = (hip_yaw @ rot("y", p[side.lower() + "foot_pitch"]), knee + world[calf][0] @ np.array([0, 0, -CALF]))
        else:
            te, ce = leg
            tr = world["PELVIS"][0] @ euler(te)
            cr = tr @ euler(ce)
            knee = hip + tr @ np.array([0, 0, -THIGH])
            world[thigh] = (tr, hip)
            world[calf] = (cr, knee)
            world[foot] = (cr @ rot("y", p[side.lower() + "foot_pitch"]), knee + cr @ np.array([0, 0, -CALF]))
    return world


def local_tracks(model, frames_world):
    """Per-bone animation tracks from world transforms per frame: a rotation for every bone and an
    offset for the bones that move away from their rest pivot (pelvis, weapon)."""
    rest = {name: np.array(pos, float) for name, _, pos in SKELETON}
    rest["ROOTTRANSFORM"] = np.zeros(3)
    parent = {name: par for name, par, _ in SKELETON}
    tracks = []
    for name, par, _ in SKELETON:
        index = model.bone_index(name)
        quats, offsets = [], []
        for world in frames_world:
            pr, pt = world[par]
            r, t = world[name]
            quats.append(quaternion(pr.T @ r))
            offsets.append(pr.T @ (t - pt) - (rest[name] - rest[par]))
        tracks.append((index, ANIM_CHANNEL_Q, quats))
        offsets = np.array(offsets)
        for axis, channel in enumerate((ANIM_CHANNEL_X, ANIM_CHANNEL_Y, ANIM_CHANNEL_Z)):
            if np.abs(offsets[:, axis]).max() > 1e-4:
                tracks.append((index, channel, [(float(v),) for v in offsets[:, axis]]))
    return tracks


# --- clips -----------------------------------------------------------------------------------------
def low_ready(**kw):
    return pose(**kw)


def aiming(**kw):
    base = dict(grip=(1.75, -0.7, 7.75), aim=(0.0, 0.0, 0.0), spine=(-6.0, 2.0, 0.0), head=(6.0, 6.0, 4.0),
                lfoot=(0.9, 0.75, ANKLE_Z), rfoot=(-0.7, -0.75, ANKLE_Z), hips=(-12.0, 0.0, 0.0))
    base.update(kw)
    return pose(**base)


def unarmed(**kw):
    base = dict(larm=((0.0, 4.0, 8.0), (0.0, -12.0, 0.0)), rarm=((0.0, 4.0, -8.0), (0.0, -12.0, 0.0)))
    base.update(kw)
    return pose(**base)


def lying(back=True, **kw):
    s = -1.0 if back else 1.0
    base = dict(pelvis=(s * 1.0, 0.0, -4.55), hips=(0.0, s * 88.0, 0.0), spine=(0.0, s * 2.0, 0.0),
                head=(15.0, -s * 10.0, 0.0), lleg=((0.0, -8.0, 6.0), (0.0, 10.0, 0.0)),
                rleg=((0.0, 4.0, -4.0), (0.0, 22.0, 0.0)), grip=(-s * 2.5, -3.2, 0.35), aim=(70.0, 0.0, 90.0),
                larm=((0.0, -s * 30.0, 50.0), (0.0, -30.0, 0.0)), rarm=((0.0, -s * 10.0, -40.0), (0.0, -50.0, 0.0)))
    base.update(kw)
    return pose(**base)


def clip_frames(frames, fn):
    return [fn(f / (frames - 1) if frames > 1 else 0.0, f) for f in range(frames)]


def clips(armed):
    """name -> list of poses, one per frame (30 per second)."""
    rest = low_ready() if armed else unarmed()
    aim = aiming() if armed else unarmed(spine=(0.0, 4.0, 0.0))
    out = {}

    def breathe(t, f, base):
        k = math.sin(2 * math.pi * t)
        return blend(base, base, 0.0) | {"spine": tuple(np.array(base["spine"]) + np.array([0.0, 1.2 * k, 0.0])),
                                         "pelvis": (0.0, 0.0, -0.04 * (1 - k))}

    out["STAND"] = clip_frames(40, lambda t, f: breathe(t, f, rest))

    def look(t, f):
        yaw = 40 * math.sin(2 * math.pi * t) if t < 0.5 else -30 * math.sin(2 * math.pi * (t - 0.5))
        p = dict(rest)
        p["head"] = (yaw, 4.0 * math.sin(4 * math.pi * t), 0.0)
        p["spine"] = (yaw * 0.25, 0.0, 0.0)
        p["hips"] = (0.0, 0.0, 2.5 * math.sin(2 * math.pi * t))
        return p
    out["IDLE"] = clip_frames(60, look)

    def run(t, f):
        # Three strides per loop: about 31 units, the distance the retail Draw modules give a run loop.
        ph = 6 * math.pi * t
        p = dict(rest)
        stride = 2.6
        for side, sign, off in (("l", 1.0, 0.0), ("r", -1.0, math.pi)):
            a = ph + off
            x = stride * math.cos(a)
            lift = max(0.0, math.sin(a)) * 1.6
            p[side + "foot"] = (x + 0.6, sign * 0.55, ANKLE_Z + lift)
            p[side + "foot_pitch"] = -25.0 * math.sin(a)
        bob = 0.35 * abs(math.cos(ph))
        p["pelvis"] = (0.6, 0.0, -0.55 - bob)
        p["hips"] = (8.0 * math.cos(ph), 8.0, 0.0)
        p["spine"] = (-8.0 * math.cos(ph), 10.0, 0.0)
        if armed:
            p["grip"] = (1.6, -0.6, 6.9 - bob * 0.5)
            p["aim"] = (35.0, 18.0, 0.0)
        else:
            swing = 40.0 * math.cos(ph)
            p["larm"] = ((0.0, swing, 10.0), (0.0, -60.0, 0.0))
            p["rarm"] = ((0.0, -swing, -10.0), (0.0, -60.0, 0.0))
        return p
    out["RUN"] = clip_frames(61, run)

    out["AIM"] = clip_frames(30, lambda t, f: aim | {"spine": tuple(np.array(aim["spine"]) + np.array([0.0, 0.6 * math.sin(2 * math.pi * t), 0.0]))})

    def fire(t, f):
        k = max(0.0, 1.0 - f / 4.0)
        p = dict(aim)
        g = np.array(aim["grip"]) + np.array([-0.35 * k, 0.0, 0.08 * k])
        p["grip"] = tuple(g)
        p["aim"] = (aim["aim"][0], aim["aim"][1] - 5.0 * k, aim["aim"][2])
        p["spine"] = (aim["spine"][0], aim["spine"][1] - 2.0 * k, aim["spine"][2])
        return p
    out["FIRE"] = clip_frames(8, fire)
    out["AIMIN"] = clip_frames(10, lambda t, f: blend(rest, aim, t))
    out["AIMOUT"] = clip_frames(10, lambda t, f: blend(aim, rest, t))
    dip = dict(rest, pelvis=(0.0, 0.0, -0.5))
    out["SHIFT"] = clip_frames(12, lambda t, f: blend(rest, dip, t * 2) if t < 0.5 else blend(dip, rest, t * 2 - 1))

    def fall(back):
        down = lying(back) if armed else lying(back, larm=((0.0, -60.0, 60.0), (0.0, -20.0, 0.0)))
        hit = dict(rest, spine=(0.0, -12.0 if back else 14.0, 0.0), head=(0.0, -20.0 if back else 20.0, 0.0),
                   pelvis=(0.0, 0.0, -0.3))
        knees = dict(down, pelvis=(-0.4 if back else 0.4, 0.0, -2.8), hips=(0.0, -40.0 if back else 40.0, 0.0),
                     lleg=((0.0, -50.0, 0.0), (0.0, 80.0, 0.0)), rleg=((0.0, -40.0, 0.0), (0.0, 70.0, 0.0)))

        def fn(t, f):
            if t < 0.2:
                return blend(rest, hit, t / 0.2)
            if t < 0.55:
                return blend(hit, knees, (t - 0.2) / 0.35)
            return blend(knees, down, (t - 0.55) / 0.45)
        return fn
    out["DIEBACK"] = clip_frames(36, fall(True))
    out["DIEFWD"] = clip_frames(36, fall(False))

    def flail(t, f):
        ph = 2 * math.pi * t
        p = unarmed(grip=(-1.0, -2.5, 9.5), aim=(0.0, -60.0, 30.0))
        p["larm"] = ((20.0 * math.sin(ph), -120.0 + 50.0 * math.sin(ph), 40.0), (0.0, -40.0 - 30.0 * math.cos(ph), 0.0))
        p["rarm"] = ((-20.0 * math.sin(ph), -120.0 - 50.0 * math.sin(ph), -40.0), (0.0, -40.0 + 30.0 * math.cos(ph), 0.0))
        p["lleg"] = ((0.0, -30.0 + 35.0 * math.sin(ph), 20.0), (0.0, 40.0 + 30.0 * math.cos(ph), 0.0))
        p["rleg"] = ((0.0, -30.0 - 35.0 * math.sin(ph), -20.0), (0.0, 40.0 - 30.0 * math.cos(ph), 0.0))
        p["spine"] = (0.0, -15.0 * math.sin(ph), 10.0 * math.cos(ph))
        p["head"] = (0.0, 20.0 * math.cos(ph), 0.0)
        return p
    out["FLAIL"] = clip_frames(20, flail)
    land = lying(True) if armed else lying(True, larm=((0.0, -60.0, 60.0), (0.0, -20.0, 0.0)))
    out["TUMBLE"] = clip_frames(24, lambda t, f: blend(flail(0.0, 0), land, t))

    def cheer(t, f):
        up = math.sin(4 * math.pi * t)
        if armed:
            p = dict(rest, grip=(0.5, -1.4, 10.9 + 0.5 * up), aim=(80.0, -10.0, 0.0))
        else:
            p = unarmed(larm=((0.0, -160.0 - 10.0 * up, 10.0), (0.0, -15.0, 0.0)),
                        rarm=((0.0, -160.0 - 10.0 * up, -10.0), (0.0, -15.0, 0.0)))
        p["head"] = (0.0, -15.0, 0.0)
        p["pelvis"] = (0.0, 0.0, -0.25 * (1 - abs(up)))
        return p
    out["CHEER"] = clip_frames(30, cheer)

    def freefall(t, f):
        w = math.sin(2 * math.pi * t)
        p = dict(rest) if armed else unarmed()
        p["larm"] = ((0.0, -100.0 + 6.0 * w, 50.0), (0.0, -30.0, 0.0))
        p["rarm"] = ((0.0, -100.0 - 6.0 * w, -50.0), (0.0, -30.0, 0.0))
        p["lleg"] = ((0.0, -10.0 + 5.0 * w, 15.0), (0.0, 30.0, 0.0))
        p["rleg"] = ((0.0, -10.0 - 5.0 * w, -15.0), (0.0, 30.0, 0.0))
        p["grip"] = (1.1, -0.2, 7.0)
        p["aim"] = (90.0, 10.0, 0.0)
        return p
    out["FREEFALL"] = clip_frames(20, freefall)

    def hang(t, f):
        w = math.sin(2 * math.pi * t)
        p = dict(rest) if armed else unarmed()
        p["larm"] = ((0.0, -165.0, 12.0), (0.0, -10.0, 0.0))
        p["rarm"] = ((0.0, -165.0, -12.0), (0.0, -10.0, 0.0))
        p["lleg"] = ((0.0, -6.0 + 6.0 * w, 3.0), (0.0, 8.0, 0.0))
        p["rleg"] = ((0.0, -6.0 - 6.0 * w, -3.0), (0.0, 12.0, 0.0))
        p["grip"] = (1.1, -0.2, 7.0)
        p["aim"] = (90.0, 10.0, 0.0)
        p["head"] = (0.0, 10.0, 0.0)
        return p
    out["HANG"] = clip_frames(40, hang)
    out["CHUTEOPN"] = clip_frames(10, lambda t, f: blend(freefall(0.0, 0), hang(0.0, 0), t))
    crouch = dict(rest, pelvis=(0.0, 0.0, -2.0), spine=(0.0, 20.0, 0.0),
                  lfoot=(0.6, 0.6, ANKLE_Z), rfoot=(-0.4, -0.6, ANKLE_Z))
    out["LAND"] = clip_frames(16, lambda t, f: blend(crouch, rest, t))

    def rappel(t, f):
        w = math.sin(2 * math.pi * t)
        p = dict(rest)
        p["larm"] = ((0.0, -160.0, 5.0), (0.0, -15.0, 0.0))
        p["rarm"] = ((0.0, -20.0, -10.0), (0.0, -70.0, 0.0))
        p["lleg"] = ((0.0, -40.0 + 6.0 * w, 8.0), (0.0, 50.0, 0.0))
        p["rleg"] = ((0.0, -30.0 - 6.0 * w, -8.0), (0.0, 40.0, 0.0))
        p["grip"] = (-0.9, -0.3, 7.6)
        p["aim"] = (90.0, -55.0, 0.0)
        p["spine"] = (0.0, -8.0, 0.0)
        return p
    out["RAPPEL"] = clip_frames(20, rappel)

    def work(t, f):
        k = math.sin(6 * math.pi * t)
        p = dict(rest)
        p["pelvis"] = (-0.4, 0.0, -2.6)
        p["lfoot"] = (1.4, 0.6, ANKLE_Z)
        p["rleg"] = ((0.0, -10.0, 0.0), (0.0, 95.0, 0.0))
        p["rfoot_pitch"] = 60.0
        p["spine"] = (0.0, 28.0, 0.0)
        p["head"] = (0.0, 20.0, 0.0)
        p["larm"] = ((0.0, -60.0 + 8.0 * k, 10.0), (0.0, -50.0, 0.0))
        p["rarm"] = ((0.0, -55.0 - 8.0 * k, -10.0), (0.0, -55.0, 0.0))
        p["grip"] = (-1.0, -1.2, 7.5)
        p["aim"] = (90.0, -60.0, 0.0)
        return p
    out["WORK"] = clip_frames(40, work)

    def climb(t, f):
        ph = 2 * math.pi * t
        p = dict(rest)
        p["larm"] = ((0.0, -150.0 + 20.0 * math.sin(ph), 10.0), (0.0, -30.0, 0.0))
        p["rarm"] = ((0.0, -150.0 - 20.0 * math.sin(ph), -10.0), (0.0, -30.0, 0.0))
        p["lleg"] = ((0.0, -40.0 - 25.0 * math.sin(ph), 5.0), (0.0, 60.0, 0.0))
        p["rleg"] = ((0.0, -40.0 + 25.0 * math.sin(ph), -5.0), (0.0, 60.0, 0.0))
        p["grip"] = (-0.9, -0.3, 7.6)
        p["aim"] = (90.0, -55.0, 0.0)
        p["head"] = (0.0, -20.0, 0.0)
        return p
    out["CLIMB"] = clip_frames(20, climb)
    return out


# --- geometry --------------------------------------------------------------------------------------
class Parts:
    """Meshes per bone and material, authored in the rest pose in model space."""

    def __init__(self, model, body, team):
        self.model = model
        self.materials = {"body": body, "team": team}
        self.meshes = {}

    def b(self, bone, kind="body"):
        key = (bone, kind)
        if key not in self.meshes:
            name = f"{bone}{'' if kind == 'body' else '_TEAM'}"
            if kind == "team":
                name = f"HOUSECOLOR{len([k for k in self.meshes if k[1] == 'team']) + 1:02d}"
            mesh = Mesh(name, self.materials[kind])
            floor = 0.82 if kind == "team" else 0.7
            self.meshes[key] = (mesh, Builder(mesh, ShadeFn(ground=0.0, height=10.0, floor=floor)))
        return self.meshes[key][1]

    def finish(self):
        for (bone, _kind), (mesh, _b) in self.meshes.items():
            if mesh.triangles:
                self.model.attach(bone, mesh)


def ring(cx, cy, z, rx, ry, n=8):
    return [(cx + rx * math.cos(2 * math.pi * k / n), cy + ry * math.sin(2 * math.pi * k / n), z) for k in range(n)]


def body(parts, kit):
    p = parts
    # Legs: thighs, calves with knee pads, boots.
    for side, y in (("L", 0.6), ("R", -0.6)):
        t = p.b(side + "THIGH")
        t.loft(ring(0.0, y, 3.0, 0.42, 0.42), ring(0.0, y, 5.4, 0.55, 0.52), UNIFORM)
        t.box((0.1, y - 0.3, 3.6), (0.5, y + 0.3, 4.4), GEAR)  # cargo pocket
        c = p.b(side + "CALF")
        c.loft(ring(0.0, y, 0.75, 0.33, 0.33), ring(0.0, y, 2.95, 0.44, 0.42), UNIFORM)
        c.box((0.3, y - 0.36, 2.4), (0.62, y + 0.36, 3.3), DARK if kit.get("kneepads", True) else UNIFORM)
        f = p.b(side + "FOOT")
        f.box((-0.42, y - 0.34, 0.0), (0.85, y + 0.34, 0.55), DARK)
        f.loft(ring(0.0, y, 0.55, 0.36, 0.36), ring(0.0, y, 0.95, 0.34, 0.34), DARK, cap_bottom=False)
    # Hips and belt.
    h = p.b("PELVIS")
    h.loft(ring(0.0, 0.0, 4.9, 0.62, 1.0), ring(0.0, 0.0, 6.2, 0.62, 0.95), UNIFORM)
    h.loft(ring(0.0, 0.0, 5.75, 0.68, 1.05), ring(0.0, 0.0, 6.15, 0.68, 1.05), GEAR)
    if kit.get("holster", True):
        h.box((-0.3, -1.25, 4.9), (0.35, -1.0, 5.9), DARK)
    # Torso: waist to shoulders.
    s = p.b("SPINE")
    s.loft(ring(0.0, 0.0, 6.1, 0.6, 0.95), ring(0.05, 0.0, 7.9, 0.72, 1.2), UNIFORM)
    s.loft(ring(0.05, 0.0, 7.9, 0.72, 1.2), ring(0.0, 0.0, 8.95, 0.55, 0.85), UNIFORM)
    s.cylinder_z(0.05, 0.0, 8.9, 9.25, 0.3, 0.28, sides=8, region=SKIN)
    vest = kit.get("vest", "plate")
    if vest == "plate":
        s.box((-0.82, -0.92, 6.5), (0.86, 0.92, 8.6), GEAR)
        for y in (-0.55, 0.0, 0.55):
            s.box((0.86, y - 0.22, 6.7), (1.12, y + 0.22, 7.35), GEAR)  # magazine pouches
        s.box((0.86, -0.7, 7.55), (1.0, 0.7, 8.2), GEAR)  # admin pouch
        p.b("SPINE", "team").box((0.86, -0.92, 8.3), (0.9, 0.92, 8.5), TEAM)
    elif vest == "flight":
        s.box((-0.75, -0.95, 6.5), (0.8, 0.95, 8.4), GEAR)
        s.box((0.8, -0.6, 6.8), (0.98, -0.1, 7.5), GEAR)
        s.box((0.8, 0.1, 6.8), (0.98, 0.6, 7.5), GEAR)
    elif vest == "chest_rig":
        s.box((0.62, -0.9, 6.6), (0.95, 0.9, 7.6), GEAR)
        s.box((-0.7, -0.4, 6.8), (-0.6, 0.4, 8.2), GEAR)
        s.box((0.7, 0.55, 7.7), (0.9, 0.75, 8.6), DARK)  # knife on the chest
    pack = kit.get("pack")
    if pack == "assault":
        s.box((-1.55, -0.7, 6.6), (-0.8, 0.7, 8.5), GEAR)
        s.cylinder_z(-1.0, 0.55, 8.5, 10.4, 0.06, 0.04, sides=4, region=DARK)  # radio antenna
    elif pack == "ghillie":
        s.box((-1.3, -0.8, 6.8), (-0.75, 0.8, 8.3), GEAR)
        for k in range(10):
            a = 2 * math.pi * k / 10
            s.box((-0.4 + 0.5 * math.cos(a), 0.9 * math.sin(a) - 0.12, 8.5), (-0.2 + 0.5 * math.cos(a), 0.9 * math.sin(a) + 0.12, 9.1), GEAR)
    # Arms: sleeves, team patch on the shoulder, gloves.
    for side, y, sign in (("L", 1.3, 1.0), ("R", -1.3, -1.0)):
        u = p.b(side + "UPPERARM")
        u.loft(ring(0.0, y, 6.95, 0.32, 0.32), ring(0.0, y, 8.75, 0.42, 0.42), UNIFORM)
        p.b(side + "UPPERARM", "team").box((-0.25, y + sign * 0.38, 7.9), (0.25, y + sign * 0.46, 8.4), TEAM)
        fo = p.b(side + "FOREARM")
        fo.loft(ring(0.0, y, 5.6, 0.26, 0.26), ring(0.0, y, 6.95, 0.32, 0.32), UNIFORM)
        fo.box((-0.2, y - 0.22, 5.05), (0.24, y + 0.22, 5.6), DARK if kit.get("gloves", True) else SKIN)
    # Head and headgear.
    hd = p.b("HEAD")
    hd.loft(ring(0.05, 0.0, 9.2, 0.42, 0.4), ring(0.08, 0.0, 9.9, 0.5, 0.46), SKIN)
    hd.loft(ring(0.08, 0.0, 9.9, 0.5, 0.46), ring(0.04, 0.0, 10.35, 0.42, 0.4), SKIN)
    hat = kit.get("hat", "helmet")
    if hat == "helmet":
        hd.loft(ring(0.0, 0.0, 9.85, 0.6, 0.56, 10), ring(0.0, 0.0, 10.4, 0.58, 0.54, 10), GEAR, cap_bottom=False)
        hd.loft(ring(0.0, 0.0, 10.4, 0.58, 0.54, 10), ring(-0.02, 0.0, 10.75, 0.36, 0.34, 10), GEAR, cap_bottom=False)
        hd.box((0.5, -0.12, 10.15), (0.68, 0.12, 10.5), DARK)  # night-vision mount
        hd.box((0.42, -0.3, 9.7), (0.58, 0.3, 9.85), DARK)  # eye protection
        p.b("HEAD", "team").box((-0.5, -0.6, 10.2), (-0.1, 0.6, 10.32), TEAM)
    elif hat == "boonie":
        hd.cylinder_z(0.0, 0.0, 10.05, 10.12, 0.95, 0.95, sides=12, region=GEAR)
        hd.loft(ring(0.0, 0.0, 10.12, 0.52, 0.5, 10), ring(0.0, 0.0, 10.6, 0.44, 0.42, 10), GEAR)
        hd.box((0.44, -0.32, 9.65), (0.53, 0.32, 9.8), DARK)  # face paint band
    elif hat == "flight":
        hd.loft(ring(0.0, 0.0, 9.5, 0.62, 0.58, 10), ring(0.0, 0.0, 10.3, 0.62, 0.58, 10), GEAR, cap_bottom=False)
        hd.loft(ring(0.0, 0.0, 10.3, 0.62, 0.58, 10), ring(0.0, 0.0, 10.8, 0.35, 0.33, 10), GEAR, cap_bottom=False)
        hd.box((0.46, -0.42, 9.65), (0.66, 0.42, 10.1), DARK)  # visor
        p.b("HEAD", "team").box((-0.62, -0.06, 9.9), (0.2, 0.06, 10.82), TEAM)
    elif hat == "ghillie":
        hd.loft(ring(0.0, 0.0, 9.9, 0.62, 0.58, 10), ring(0.0, 0.0, 10.7, 0.4, 0.38, 10), GEAR, cap_bottom=False)
        for k in range(8):
            a = 2 * math.pi * k / 8
            hd.box((0.55 * math.cos(a) - 0.1, 0.55 * math.sin(a) - 0.1, 9.4), (0.55 * math.cos(a) + 0.1, 0.55 * math.sin(a) + 0.1, 10.2), GEAR)
        hd.box((0.44, -0.32, 9.65), (0.53, 0.32, 9.8), DARK)


def weapon(parts, kind):
    """Weapon on the WEAPON bone, authored with the pistol grip at the bone and the bore along +X.
    Returns the muzzle position relative to the grip."""
    g = np.array(dict(SKELETON_POS)["WEAPON"])
    w = parts.b("WEAPON")

    def box(lo, hi, region=DARK):
        w.box(tuple(g + np.array(lo)), tuple(g + np.array(hi)), region)

    def tube(x0, x1, z, r0, r1=None, region=DARK):
        w.cylinder_x(g[0] + x0, g[0] + x1, g[1], g[2] + z, r0, r1, sides=8, region=region)

    box((-0.12, -0.1, -0.55), (0.12, 0.1, 0.05))  # pistol grip
    if kind == "rifle":
        box((-1.55, -0.13, 0.0), (-0.35, 0.13, 0.45), GEAR)  # stock
        box((-0.35, -0.14, 0.05), (1.0, 0.14, 0.5))  # receiver
        box((0.25, -0.11, -0.65), (0.6, 0.11, 0.05))  # magazine
        box((1.0, -0.16, 0.08), (2.6, 0.16, 0.42), GEAR)  # handguard
        tube(2.6, 3.4, 0.25, 0.07)
        box((0.05, -0.1, 0.5), (0.65, 0.1, 0.72))  # optic
        return (3.4, 0.0, 0.25)
    if kind == "carbine":
        box((-1.35, -0.13, 0.0), (-0.35, 0.13, 0.45))
        box((-0.35, -0.14, 0.05), (0.9, 0.14, 0.5))
        box((0.2, -0.11, -0.6), (0.55, 0.11, 0.05))
        box((0.9, -0.15, 0.08), (2.3, 0.15, 0.42))
        tube(2.3, 3.6, 0.25, 0.14)  # suppressor
        box((0.1, -0.09, 0.5), (0.5, 0.09, 0.66))
        return (3.6, 0.0, 0.25)
    # Precision rifle with a long barrel, scope and bipod.
    box((-1.7, -0.14, -0.1), (-0.3, 0.14, 0.45), GEAR)
    box((-0.3, -0.14, 0.05), (1.2, 0.14, 0.48))
    box((0.3, -0.1, -0.45), (0.6, 0.1, 0.05))
    box((1.2, -0.16, 0.06), (3.0, 0.16, 0.4), GEAR)
    tube(3.0, 5.0, 0.25, 0.08)
    tube(4.6, 5.0, 0.25, 0.12)  # muzzle brake
    tube(-0.2, 1.4, 0.82, 0.16, 0.2)  # scope
    box((0.25, -0.06, 0.48), (0.4, 0.06, 0.7))
    box((0.9, -0.06, 0.48), (1.05, 0.06, 0.7))
    box((2.7, -0.3, -0.55), (2.8, -0.24, 0.1))  # bipod legs
    box((2.7, 0.24, -0.55), (2.8, 0.3, 0.1))
    return (5.0, 0.0, 0.25)


SKELETON_POS = [(name, pos) for name, _, pos in SKELETON]


def build(name, body_texture, team_texture, kit):
    """A soldier model and its clips: returns (model, {clip name: tracks and frame count})."""
    model = Model(name)
    for bone, parent, pos in SKELETON:
        model.add_bone(bone, parent, pos)
    body_mat = Material("GXInfantry", body_texture, specular=(30, 30, 30), shininess=6.0)
    team_mat = Material("GXTeam", team_texture)
    parts = Parts(model, body_mat, team_mat)
    body(parts, kit)
    armed = kit.get("weapon") is not None
    if armed:
        muzzle = weapon(parts, kit["weapon"])
        g = np.array(dict(SKELETON_POS)["WEAPON"])
        model.add_bone("MUZZLE", "WEAPON", tuple(g + np.array(muzzle)))
    parts.finish()

    anims = {}
    for clip, poses in clips(armed).items():
        frames_world = [solve(p, armed) for p in poses]
        anims[clip] = (len(poses), local_tracks(model, frames_world))
    return model, anims


KITS = {
    # Ranger: plate carrier, assault pack, helmet with night-vision mount, rifle with optic.
    "GXIRNG": dict(weapon="rifle", vest="plate", pack="assault", hat="helmet"),
    # Pathfinder: ghillie hood and shoulder strips, precision rifle.
    "GXISNP": dict(weapon="sniper", vest="chest_rig", pack="ghillie", hat="ghillie", kneepads=False),
    # Colonel Burton: boonie hat and face paint, chest rig with knife, suppressed carbine.
    "GXIBRT": dict(weapon="carbine", vest="chest_rig", hat="boonie", kneepads=False),
    # Pilot: flight suit, survival vest and helmet with visor; unarmed like the retail pilot.
    "GXIPLT": dict(weapon=None, vest="flight", hat="flight", kneepads=False, holster=True, gloves=True),
}
