"""Detailed modern main battle tank (Abrams-class) for the USA Crusader, built with blend.kit.

GeneralsX @feature Claude 16/10/2026 Replaces the box-built gx_mbt look: bevelled armour, seven road
wheels with rims and hubs per side, a real track loop around sprocket, idler and return rollers, side
skirt panels, engine deck louvres, a remote weapon station, sights, smoke dischargers, bustle rack with
stowage, and a gun with thermal sleeve and muzzle reference sensor. Bones the Crusader's Draw module
needs keep their names and places (TURRET, BARREL, TURRETMS, TURRETFX, TREADSL/TREADSR). Extra bones
carry moving parts (WHEELL01.., SPROCKETL, IDLERL, RWS, CITV, HATCH01/02, ANTENNA01/02) and damage
effects (SMOKE01.., FIRE01..). The damaged model loses skirt panels, stowage and an antenna.
"""

import math

from mathutils import Matrix, Vector

TURRET_X = -1.0
TURRET_Z = 5.6
GUN_Z = 7.1

ROAD_X = [-10.8 + k * 3.5 for k in range(7)]
ROAD_R = 1.05
TRACK_T = 0.42
ROAD_Z = TRACK_T + ROAD_R
SPROCKET = (-13.5, 2.45, 1.12)
IDLER = (12.9, 2.35, 1.0)
ROLLERS = [(-6.0, 3.35, 0.32), (1.6, 3.4, 0.32), (7.6, 3.35, 0.32)]
TRACK_Y = (4.62, 6.95)


def track_path():
    """Outline the track's inner face wraps: convex hull of the wheels, clockwise seen from the left."""
    pts = []
    circles = [(x, ROAD_Z, ROAD_R) for x in ROAD_X] + [SPROCKET, IDLER] + list(ROLLERS)
    for cx, cz, r in circles:
        for k in range(48):
            a = 2 * math.pi * k / 48
            pts.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    pts = sorted(set((round(x, 4), round(z, 4)) for x, z in pts))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]  # counter-clockwise
    hull.reverse()  # clockwise: the top run goes forward, the bottom run back, as W3DTankDraw scrolls
    # Resample so long straight runs still bend smoothly and links stay even.
    out = []
    for i, a in enumerate(hull):
        b = hull[(i + 1) % len(hull)]
        d = math.dist(a, b)
        steps = max(1, int(d / 0.8))
        for s in range(steps):
            t = s / steps
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    # The top run sags between its supports (sprocket, return rollers, idler).
    supports = sorted([SPROCKET[0]] + [r[0] for r in ROLLERS] + [IDLER[0]])
    sagged = []
    for x, z in out:
        if z > 3.0:
            for x0, x1 in zip(supports, supports[1:]):
                if x0 < x < x1:
                    t = (x - x0) / (x1 - x0)
                    z -= 0.035 * (x1 - x0) * 4 * t * (1 - t)
                    break
        sagged.append((x, z))
    return sagged


def running_gear(k, side, thrown=False):
    s = 1 if side > 0 else -1
    tag = "L" if side > 0 else "R"
    y_mid = s * (TRACK_Y[0] + TRACK_Y[1]) / 2
    k.at(group="HULL", finish="paint")
    for i, x in enumerate(ROAD_X):
        bone = f"WHEEL{tag}{i + 1:02d}"
        k.add_bone(bone, "ROOTTRANSFORM", (x, y_mid, ROAD_Z))
        k.at(bone=bone, group=bone)
        # Dual road wheel: two tyres with the guide horns running between them.
        k.wheel((x, y_mid + s * 0.62, ROAD_Z), ROAD_R, 0.9, spokes=6, side=s)
        k.wheel((x, y_mid - s * 0.62, ROAD_Z), ROAD_R, 0.9, side=s, detail=False)
        k.cyl((x, y_mid, ROAD_Z), "y", ROAD_R * 0.55, 0.4, sides=12, bevel=0, finish="metal")
    # Drive sprocket: two toothed rings and a hub.
    bone = f"SPROCKET{tag}"
    sx, sz, sr = SPROCKET
    k.add_bone(bone, "ROOTTRANSFORM", (sx, y_mid, sz))
    k.at(bone=bone, group=bone)
    for off in (-0.7, 0.7):
        k.cyl((sx, y_mid + off, sz), "y", sr * 0.9, 0.35, sides=22, bevel=0, finish="metal")
        for t in range(11):
            a = 2 * math.pi * t / 11
            k.box((sx + math.cos(a) * sr - 0.16, y_mid + off - 0.15, sz + math.sin(a) * sr - 0.16),
                  (sx + math.cos(a) * sr + 0.16, y_mid + off + 0.15, sz + math.sin(a) * sr + 0.16), bevel=0,
                  finish="steel")
    k.cyl((sx, y_mid + s * 1.0, sz), "y", sr * 0.5, 0.5, sides=14, finish="paint")
    k.bolts([(sx + math.cos(a) * sr * 0.32, y_mid + s * 1.27, sz + math.sin(a) * sr * 0.32)
             for a in [2 * math.pi * t / 8 for t in range(8)]], "y", radius=0.07, finish="steel")
    # Idler.
    bone = f"IDLER{tag}"
    ix, iz, ir = IDLER
    k.add_bone(bone, "ROOTTRANSFORM", (ix, y_mid, iz))
    k.at(bone=bone, group=bone)
    k.wheel((ix, y_mid + s * 0.62, iz), ir, 0.9, spokes=5, finish_tyre="metal", side=s)
    k.wheel((ix, y_mid - s * 0.62, iz), ir, 0.9, finish_tyre="metal", side=s, detail=False)
    # Return rollers on stub axles.
    k.at(bone="ROOTTRANSFORM", group="HULL")
    for rx, rz, rr in ROLLERS:
        k.cyl((rx, y_mid, rz), "y", rr, 1.5, sides=14, finish="rubber")
        k.cyl((rx, s * 4.4, rz), "y", 0.12, 0.6, sides=8, finish="metal")
    # Suspension arms and bump stops behind each road wheel.
    for x in ROAD_X:
        k.prism([(x - 0.15, ROAD_Z - 0.2), (x + 1.5, ROAD_Z + 0.5), (x + 1.5, ROAD_Z + 0.9), (x - 0.15, ROAD_Z + 0.25)],
                s * 4.3, s * 4.62, bevel=0.06, finish="metal")
        k.box((x + 1.4, s * 4.2 - 0.3, ROAD_Z + 1.0), (x + 2.0, s * 4.2 + 0.3, ROAD_Z + 1.3), bevel=0.05, finish="metal")
    # Track loop.
    y0, y1 = (TRACK_Y[0], TRACK_Y[1]) if side > 0 else (-TRACK_Y[1], -TRACK_Y[0])
    if thrown:
        k.track_loop(f"TREADS{tag}", "ROOTTRANSFORM", thrown_track_path(), y0, y1, thickness=TRACK_T, links=3.0,
                     closed=False)
    else:
        k.track_loop(f"TREADS{tag}", "ROOTTRANSFORM", track_path(), y0, y1, thickness=TRACK_T, links=3.0)


def thrown_track_path():
    """The damaged model's left track, broken under the front road wheel: it still wraps the rear of the
    running gear, then runs off the idler and lies flat on the ground ahead of the tank."""
    path = track_path()
    # Start just behind the break on the bottom run, then follow the band round to the idler's top.
    start = next(i for i, (x, z) in enumerate(path) if z < 1.0 and x < 8.4)
    path = path[start:] + path[:start]
    top = max(i for i, (x, z) in enumerate(path) if z > 3.0 and x < IDLER[0])
    tail = [(13.6, 3.05), (14.5, 2.2), (15.3, 1.1), (16.3, 0.5), (17.6, 0.43), (19.4, 0.48), (21.0, 0.42),
            (22.4, 0.5)]
    return path[:top + 1] + tail


def hull(k, damaged_parts=True):
    k.at(bone="ROOTTRANSFORM", group="HULL", finish="paint", damaged=None)
    # Lower hull tub between the tracks.
    k.prism([(-14.3, 1.6), (12.8, 1.6), (14.6, 3.2), (15.0, 3.6), (-14.9, 3.6), (-15.0, 2.4)], -4.6, 4.6, bevel=0.07)
    # Upper hull and sponsons: shallow glacis, flat deck, vertical rear.
    k.prism([(-15.2, 3.5), (14.9, 3.5), (15.7, 4.05), (8.7, 5.55), (-15.0, 5.55), (-15.4, 5.2), (-15.4, 3.7)],
            -7.0, 7.0, bevel=0.07, segments=2)
    # Weld beads where the glacis meets the nose and the deck, and along the sponson edges.
    k.weld([(8.7, -6.95, 5.56), (8.7, 6.95, 5.56)])
    k.weld([(15.7, -6.95, 4.06), (15.7, 6.95, 4.06)])
    for s in (-1, 1):
        k.weld([(-15.0, s * 7.0, 5.56), (8.7, s * 7.0, 5.56), (15.7, s * 7.0, 4.06)], radius=0.055)

    # Add-on glacis armour either side of the driver, bolted round the edges.
    def glacis_z(x):
        return 5.55 - (x - 8.7) * (1.5 / 7.0)
    for y0, y1 in ((1.6, 6.4), (-6.4, -1.6)):
        k.prism([(9.4, glacis_z(9.4)), (14.8, glacis_z(14.8)), (14.8, glacis_z(14.8) + 0.16), (9.4, glacis_z(9.4) + 0.16)],
                y0, y1, bevel=0.04, segments=1)
        for x in (9.8, 11.1, 12.4, 13.7):
            k.bolts([(x, y, glacis_z(x) + 0.2) for y in (y0 + 0.3, y1 - 0.3)], "z")
    # Driver's hatch with three periscopes.
    k.cyl((10.4, 0.0, 5.5), "z", 1.15, 0.2, sides=24, finish="paint", bevel=0.06)
    k.box((10.6, -1.0, 5.55), (11.5, 1.0, 5.85), bevel=0.08)
    for y in (-0.75, 0.0, 0.75):
        k.box((11.0, y - 0.28, 5.7), (11.45, y + 0.28, 6.0), bevel=0.04, finish="dark")
        k.box((11.44, y - 0.24, 5.74), (11.48, y + 0.24, 5.96), bevel=0.0, finish="glass")
    # Headlight clusters with guards, tow eyes, front fenders and mud flaps.
    for s in (-1, 1):
        y = s * 5.7
        k.box((14.4, y - 0.75, 4.0), (15.25, y + 0.75, 4.75), bevel=0.1, finish="dark")
        for dy in (-0.35, 0.35):
            k.cyl((15.28, y + dy, 4.38), "x", 0.22, 0.08, sides=14, finish="light", bevel=0.02)
        k.tube([(15.2, y - 0.85, 4.0), (15.6, y - 0.85, 4.1), (15.6, y + 0.85, 4.1), (15.2, y + 0.85, 4.0)], 0.06,
               finish="metal")
        k.tube([(15.2, y - 0.85, 4.8), (15.6, y - 0.85, 4.75), (15.6, y + 0.85, 4.75), (15.2, y + 0.85, 4.8)], 0.06,
               finish="metal")
        k.tube([(14.9, s * 2.0 - 0.4, 3.2), (15.4, s * 2.0, 2.9), (14.9, s * 2.0 + 0.4, 3.2)], 0.14, finish="metal")
        k.box((13.4, s * 4.62, 3.9), (15.5, s * 7.0, 4.05), bevel=0.05)
        k.box((15.3, s * 4.8, 2.6), (15.42, s * 6.9, 3.95), bevel=0.03, finish="rubber")
    # Engine deck: two louvred grilles, access doors with hinges and handles, fuel caps.
    k.grille(-14.4, -9.4, -3.6, -0.4, 5.55, 12, axis="x")
    k.grille(-14.4, -9.4, 0.4, 3.6, 5.55, 12, axis="x")
    for y0, y1 in ((-6.6, -4.1), (4.1, 6.6)):
        k.box((-13.8, y0, 5.55), (-6.8, y1, 5.68), bevel=0.05)
        for x in (-13.0, -10.0, -7.6):
            k.cyl((x, (y0 + y1) / 2, 5.72), "y", 0.1, 2.2, sides=8, finish="metal")
        k.tube([(-12.0, y0 + 0.4, 5.68), (-12.0, y0 + 0.4, 5.9), (-11.2, y0 + 0.4, 5.9), (-11.2, y0 + 0.4, 5.68)],
               0.04, finish="steel")
    for y in (-5.9, 5.9):
        k.cyl((-5.6, y, 5.6), "z", 0.35, 0.18, sides=14, finish="metal")
    # Rear: exhaust grille, tail lights, tow pintle, telephone box, rear fenders.
    k.box((-15.6, -4.2, 3.9), (-15.3, 4.2, 5.25), bevel=0.06, finish="dark")
    for j in range(7):
        z = 4.0 + j * 0.18
        k.box((-15.75, -4.1, z), (-15.45, 4.1, z + 0.08), bevel=0.02, finish="metal")
    for s in (-1, 1):
        k.box((-15.6, s * 6.1 - 0.45, 4.3), (-15.35, s * 6.1 + 0.45, 4.85), bevel=0.06, finish="dark")
        k.cyl((-15.62, s * 6.1, 4.58), "x", 0.15, 0.06, sides=12, finish="light")
        k.box((-15.2, s * 4.62, 3.9), (-14.6, s * 7.0, 4.05), bevel=0.04)
        k.box((-15.25, s * 4.8, 2.5), (-15.14, s * 6.9, 3.9), bevel=0.03, finish="rubber")
        k.tube([(-15.2, s * 3.0 - 0.4, 3.0), (-15.7, s * 3.0, 2.7), (-15.2, s * 3.0 + 0.4, 3.0)], 0.14, finish="metal")
    k.box((-15.8, -0.5, 2.6), (-15.3, 0.5, 3.1), bevel=0.08, finish="metal")
    k.box((-15.5, 3.4, 4.25), (-15.1, 4.1, 4.95), bevel=0.06)
    # Tow cable along the right deck edge.
    k.tube([(-12.0, -6.75, 5.62), (6.0, -6.75, 5.62), (6.4, -6.5, 5.62), (6.0, -6.25, 5.62), (-11.6, -6.25, 5.62)],
           0.1, finish="steel")
    # Side skirts: two thick armoured panels at the front, five thinner ones behind, bolted along the top.
    k.skirts = {}
    k.tiles = []
    panels = [(9.9, 13.6, 0.5), (6.3, 9.8, 0.5)] + [(x, x + 3.45, 0.3) for x in (2.75, -0.8, -4.35, -7.9, -11.45)]
    for s in (-1, 1):
        for n, (x0, x1, t) in enumerate(panels):
            lose = damaged_parts and n in (2, 5) and s > 0
            k.at(damaged=False if lose else None)
            y_in = s * 7.0
            y_out = s * (7.0 + t)
            ya, yb = sorted((y_in, y_out))
            bottom = 2.55 if n > 1 else 2.35
            if n == 0:
                k.skirts[(s, n)] = k.prism([(x0, bottom), (x1 - 1.3, bottom), (x1, 3.4), (x1, 4.75), (x0, 4.75)], ya,
                                           yb, bevel=0.1)
            else:
                k.skirts[(s, n)] = k.prism([(x0, bottom), (x1, bottom), (x1, 4.75), (x0, 4.75)], ya, yb, bevel=0.08)
            k.bolts([((x0 + 0.35 + j * (x1 - x0 - 0.7) / 3), y_out + s * 0.02, 4.45) for j in range(4)], "y",
                    radius=0.08)
            k.box((x0 + 0.3, y_out - 0.05 if s > 0 else y_out - 0.09, bottom + 0.1),
                  (x1 - 0.3, y_out + 0.09 if s > 0 else y_out + 0.05, bottom + 0.22), bevel=0.02)
        k.at(damaged=None)
        # Reactive armour tiles over the rear skirt panels, two rows; the damaged hull has lost some.
        y_face = s * 7.3
        for i in range(15):
            x0 = -11.3 + i * 1.18
            for j, z0 in enumerate((2.68, 3.72)):
                lost = (i * 7 + j * 3 + (s > 0)) % 5 == 0
                # Tiles on the skirt panels the damaged hull has lost go with them.
                lost = lost or (damaged_parts and s > 0 and any(
                    x0 + 0.55 > a and x0 + 0.55 < b for n, (a, b, _) in enumerate(panels) if n in (2, 5)))
                k.at(damaged=False if lost else None)
                ya, yb = sorted((y_face, y_face + s * 0.38))
                tile = k.box((x0, ya, z0), (x0 + 1.1, yb, z0 + 0.98), bevel=0.04, segments=1)
                if not lost:
                    k.tiles.append((s, x0, z0, tile))
                k.bolts([(x0 + 0.55, yb + 0.03 if s > 0 else ya - 0.03, z0 + 0.49)], "y", radius=0.11, height=0.07,
                        finish="metal")
        k.at(damaged=None)
        # Team colour: a small panel on the nose of the front skirt.
        k.at(group="HOUSECOLOR02", finish="team")
        ya, yb = sorted((s * 7.5, s * 7.55))
        k.box((11.4, ya, 3.75), (13.0, yb, 4.35), bevel=0.01)
        k.at(group="HULL", finish="paint")


def turret(k, damaged=False):
    tx = TURRET_X
    k.add_bone("TURRET", "ROOTTRANSFORM", (tx, 0, TURRET_Z))
    k.add_bone("BARREL", "TURRET", (tx + 9.8, 0, GUN_Z))
    k.add_bone("TURRETMS", "BARREL", (tx + 30.4, 0, GUN_Z))
    k.add_bone("TURRETFX", "BARREL", (tx + 30.4, 0, GUN_Z))
    k.at(bone="TURRET", group="TURRETBODY", finish="paint", damaged=None)
    # Turret ring skirt and the faceted turret: wedge front, flat cheeks, long bustle.
    k.cyl((tx, 0, TURRET_Z + 0.1), "z", 5.4, 0.3, sides=40, finish="metal")
    base = [(8.9, -2.3), (8.9, 2.3), (6.4, 6.75), (-6.6, 6.75), (-11.2, 5.95), (-11.2, -5.95), (-6.6, -6.75), (6.4, -6.75)]
    top = [(7.8, -2.1), (7.8, 2.1), (5.6, 6.1), (-6.2, 6.1), (-10.8, 5.4), (-10.8, -5.4), (-6.2, -6.1), (5.6, -6.1)]
    k.loft([(x + tx, y, TURRET_Z + 0.25) for x, y in base], [(x + tx, y, TURRET_Z + 3.0) for x, y in top], bevel=0.07,
           segments=2)
    # Weld beads round the roof and down the corners.
    roof = [(x + tx, y, TURRET_Z + 3.0) for x, y in top]
    k.weld(roof + [roof[0]], radius=0.06)
    for (bx, by), (ux, uy) in zip(base, top):
        k.weld([(bx + tx, by, TURRET_Z + 0.3), (ux + tx, uy, TURRET_Z + 2.98)], radius=0.05)

    # Add-on side armour: three bolted plates a side, following the lean of the turret wall.
    def wall_y(z):
        return 6.75 - (z - TURRET_Z - 0.25) / 2.75 * 0.65
    k.side_plates = []
    for s in (-1, 1):
        for x0, x1 in ((tx + 1.8, tx + 5.6), (tx - 2.2, tx + 1.65), (tx - 6.2, tx - 2.35)):
            z0, z1 = 6.05, 8.35
            lo = [(x0, s * (wall_y(z0) - 0.05), z0), (x1, s * (wall_y(z0) - 0.05), z0), (x1, s * (wall_y(z0) + 0.24), z0),
                  (x0, s * (wall_y(z0) + 0.24), z0)]
            hi = [(x0, s * (wall_y(z1) - 0.05), z1), (x1, s * (wall_y(z1) - 0.05), z1), (x1, s * (wall_y(z1) + 0.24), z1),
                  (x0, s * (wall_y(z1) + 0.24), z1)]
            k.side_plates.append(k.loft(lo, hi, bevel=0.05, segments=1))
            for z in (z0 + 0.3, z1 - 0.3):
                k.bolts([(x, s * (wall_y(z) + 0.27), z) for x in (x0 + 0.3, x1 - 0.3)], "y")
    # Cheek armour seams: raised plates on the front faces.
    for s in (-1, 1):
        k.loft([(tx + 8.75, s * 2.35, 6.2), (tx + 6.55, s * 6.55, 6.2), (tx + 6.3, s * 6.55, 6.2), (tx + 8.5, s * 2.35, 6.2)],
               [(tx + 7.95, s * 2.2, 8.35), (tx + 5.85, s * 6.0, 8.35), (tx + 5.6, s * 6.0, 8.35), (tx + 7.7, s * 2.2, 8.35)],
               bevel=0.04)
    # Roof: blow-out panels over the ammunition, lifting eyes, wind sensor mast.
    for y0, y1 in ((-5.2, -2.6), (2.6, 5.2)):
        k.box((tx - 10.2, y0, 8.6), (tx - 6.4, y1, 8.72), bevel=0.04)
        k.bolts([(tx - 10.0 + j * 1.2, y, 8.76) for j in range(4) for y in (y0 + 0.2, y1 - 0.2)], "z")
    for x, y in ((tx + 4.0, -5.4), (tx + 4.0, 5.4), (tx - 9.6, -4.6), (tx - 9.6, 4.6)):
        k.tube([(x - 0.3, y, 8.6), (x - 0.25, y, 8.95), (x + 0.25, y, 8.95), (x + 0.3, y, 8.6)], 0.07, finish="metal")
    k.cyl((tx - 9.0, 0.0, 9.3), "z", 0.06, 1.4, sides=6, finish="metal")
    k.cyl((tx - 9.0, 0.0, 10.05), "y", 0.08, 0.9, sides=6, finish="metal")
    # Gun mantlet with its canvas cover.
    k.box((tx + 8.5, -1.75, 6.15), (tx + 9.9, 1.75, 8.1), bevel=0.1, segments=2)
    k.box((tx + 9.7, -1.25, 6.45), (tx + 10.6, 1.25, 7.75), bevel=0.35, segments=3, finish="canvas")
    # Coaxial machine gun port.
    k.cyl((tx + 9.95, 1.2, 6.65), "x", 0.12, 0.3, sides=8, finish="dark")
    # Gunner's primary sight "doghouse" with armoured doors.
    k.box((tx + 4.0, -4.6, 8.55), (tx + 6.3, -2.4, 9.75), bevel=0.15, segments=2)
    k.box((tx + 6.25, -4.3, 8.8), (tx + 6.35, -2.7, 9.5), bevel=0.0, finish="glass")
    for y0, y1 in ((-4.65, -3.55), (-3.45, -2.35)):
        k.box((tx + 6.32, y0, 8.6), (tx + 6.5, y1, 9.72), bevel=0.04)
    # Commander's independent thermal viewer on its own bone (it scans).
    k.add_bone("CITV", "TURRET", (tx + 0.8, 2.0, 8.6))
    k.at(bone="CITV", group="CITV")
    k.cyl((tx + 0.8, 2.0, 8.8), "z", 0.55, 0.4, sides=16)
    k.box((tx + 0.2, 1.5, 9.0), (tx + 1.6, 2.5, 9.9), bevel=0.12)
    k.box((tx + 1.55, 1.65, 9.2), (tx + 1.65, 2.35, 9.7), bevel=0.0, finish="lens")
    k.at(bone="TURRET", group="TURRETBODY")
    # Commander's cupola with the remote weapon station on its own bone.
    k.cyl((tx - 3.0, -3.0, 8.75), "z", 1.55, 0.35, sides=24, finish="paint")
    for a in range(8):
        ang = 2 * math.pi * a / 8
        k.box((tx - 3.0 + math.cos(ang) * 1.35 - 0.15, -3.0 + math.sin(ang) * 1.35 - 0.15, 8.9),
              (tx - 3.0 + math.cos(ang) * 1.35 + 0.15, -3.0 + math.sin(ang) * 1.35 + 0.15, 9.15), bevel=0.03,
              finish="glass")
    k.add_bone("HATCH01", "TURRET", (tx - 4.2, -3.0, 9.0))
    k.at(bone="HATCH01", group="HATCH01")
    k.cyl((tx - 3.0, -3.0, 9.05), "z", 1.05, 0.18, sides=20)
    k.tube([(tx - 3.5, -3.4, 9.15), (tx - 3.5, -3.4, 9.35), (tx - 2.5, -3.4, 9.35), (tx - 2.5, -3.4, 9.15)], 0.04,
           finish="steel")
    k.add_bone("RWS", "TURRET", (tx - 3.0, -1.3, 9.0))
    k.at(bone="RWS", group="RWS")
    k.box((tx - 3.6, -1.9, 8.8), (tx - 2.1, -0.7, 9.6), bevel=0.1)  # pedestal
    k.box((tx - 3.4, -2.05, 9.6), (tx - 1.6, -0.55, 10.2), bevel=0.12)  # cradle
    k.box((tx - 3.2, -2.2, 9.7), (tx - 2.2, -2.05, 10.1), bevel=0.02, finish="dark")  # ammo box
    k.box((tx - 2.0, -0.6, 10.2), (tx - 1.2, -0.05, 10.8), bevel=0.08)  # sight
    k.box((tx - 1.22, -0.5, 10.3), (tx - 1.15, -0.15, 10.7), bevel=0.0, finish="lens")
    k.cyl((tx - 0.9, -1.3, 9.9), "x", 0.2, 1.0, sides=10, finish="metal")  # receiver
    k.cyl((tx + 0.85, -1.3, 9.9), "x", 0.08, 2.6, sides=8, finish="metal")  # barrel
    k.cyl((tx + 0.4, -1.3, 9.9), "x", 0.13, 1.0, sides=8, finish="metal")  # barrel jacket
    # Loader's hatch, machine gun on a skate mount with its shield.
    k.at(bone="TURRET", group="TURRETBODY")
    k.cyl((tx - 3.0, 3.2, 8.7), "z", 1.25, 0.25, sides=20)
    k.add_bone("HATCH02", "TURRET", (tx - 4.0, 3.2, 8.9))
    k.at(bone="HATCH02", group="HATCH02")
    k.cyl((tx - 3.0, 3.2, 8.92), "z", 0.95, 0.16, sides=20)
    k.at(bone="TURRET", group="TURRETBODY")
    # Armoured gun shield with a glass vision block, wrapping round the loader.
    k.box((tx - 1.9, 1.9, 8.8), (tx - 1.62, 4.5, 10.4), bevel=0.06)
    k.box((tx - 1.62, 2.75, 9.85), (tx - 1.56, 3.65, 10.25), bevel=0.0, finish="glass")
    for y0, y1 in ((4.45, 4.62), (1.78, 1.95)):
        k.box((tx - 3.6, y0, 8.8), (tx - 1.75, y1, 10.0), bevel=0.05)
    k.box((tx - 1.6, 3.05, 9.35), (tx - 1.1, 3.35, 9.65), bevel=0.04, finish="metal")
    k.cyl((tx - 0.2, 3.2, 9.5), "x", 0.06, 2.2, sides=8, finish="metal")
    k.box((tx - 1.4, 3.1, 9.1), (tx - 1.2, 3.3, 9.35), bevel=0.02, finish="dark")
    # Smoke grenade dischargers: two banks of six on the cheeks.
    for s in (-1, 1):
        k.box((tx + 5.4, s * 6.0 - 0.6, 8.35), (tx + 6.6, s * 6.0 + 0.6, 8.65), bevel=0.06, finish="metal")
        for row in range(2):
            for col in range(3):
                y = s * (5.6 + col * 0.38)
                k.cyl((tx + 6.1, y, 8.85 + row * 0.38), "x", 0.17, 0.9, sides=10, finish="metal", bevel=0.03)
                k.cyl((tx + 6.57, y, 8.85 + row * 0.38), "x", 0.12, 0.04, sides=10, finish="dark", bevel=0.0)
    # Grab handles on the side armour.
    for s in (-1, 1):
        k.tube([(tx + 2.4, s * 6.55, 7.7), (tx + 2.4, s * 6.85, 7.7), (tx + 4.6, s * 6.85, 7.7), (tx + 4.6, s * 6.55, 7.7)],
               0.05, finish="metal")
    # Bustle rack: tubular frame with jerrycans, ammunition cans and canvas bags.
    rack_x0, rack_x1 = tx - 13.6, tx - 10.9
    for z in (6.25, 7.9):
        if damaged and z > 7:
            # Top rail torn loose and bent down at the right rear corner.
            k.tube([(rack_x1, -5.5, z), (rack_x0, -5.5, z), (rack_x0, 0.0, z), (rack_x0 - 0.15, 2.0, z - 0.25),
                    (rack_x0 - 0.5, 3.6, z - 0.9), (rack_x0 - 0.9, 4.4, z - 1.6)], 0.07, finish="metal")
            k.tube([(rack_x1, 5.5, z), (rack_x1 - 0.7, 5.5, z - 0.1), (rack_x1 - 1.3, 5.9, z - 0.6)], 0.07,
                   finish="metal")
            continue
        k.tube([(rack_x1, -5.5, z), (rack_x0, -5.5, z), (rack_x0, 5.5, z), (rack_x1, 5.5, z)], 0.07, finish="metal")
    for y in (-5.5, -2.75, 0.0, 2.75, 5.5):
        if damaged and y > 2:
            k.tube([(rack_x0, y, 6.25), (rack_x0 - 0.2, y, 6.9), (rack_x0 - 0.7, y + 0.3, 7.3)], 0.06, finish="metal")
            continue
        k.tube([(rack_x0, y, 6.25), (rack_x0, y, 7.9)], 0.06, finish="metal")
    k.box((rack_x0, -5.5, 6.1), (rack_x1, 5.5, 6.25), bevel=0.03, finish="metal")
    k.at(damaged=False)
    for j, y in enumerate((-4.7, -3.7)):
        k.box((rack_x0 + 0.3, y - 0.42, 6.25), (rack_x0 + 1.9, y + 0.42, 7.75), bevel=0.12, finish="paint")
        k.tube([(rack_x0 + 0.6, y, 7.75), (rack_x0 + 0.6, y, 7.95), (rack_x0 + 1.1, y, 7.95)], 0.05, finish="metal")
    for y in (-2.2, -1.2):
        k.box((rack_x0 + 0.25, y - 0.4, 6.25), (rack_x0 + 1.4, y + 0.4, 7.0), bevel=0.06, finish="dark")
    k.box((rack_x0 + 0.2, -0.6, 6.25), (rack_x1 - 0.2, 2.4, 7.5), bevel=0.55, segments=4, finish="canvas")
    k.box((rack_x0 + 0.3, 2.6, 6.25), (rack_x1 - 0.3, 4.9, 7.25), bevel=0.45, segments=4, finish="canvas")
    k.cyl((rack_x0 + 1.3, 0.9, 7.75), "y", 0.42, 5.0, sides=16, bevel=0.2, finish="canvas")
    k.at(damaged=None)
    # Antennas on their own bones (they sway).
    for n, y in enumerate((-4.7, 4.7)):
        if damaged and n == 1:
            k.at(bone="TURRET", group="TURRETBODY")
            k.cyl((tx - 9.6, y, 8.9), "z", 0.14, 0.5, sides=8, finish="metal")
            k.cyl((tx - 9.6, y, 9.3), "z", 0.04, 0.4, sides=6, finish="metal")
            continue
        bone = f"ANTENNA{n + 1:02d}"
        k.add_bone(bone, "TURRET", (tx - 9.6, y, 8.6))
        k.at(bone=bone, group=bone)
        k.cyl((tx - 9.6, y, 8.85), "z", 0.16, 0.5, sides=10, finish="metal")
        k.cyl((tx - 9.6, y, 9.3), "z", 0.1, 0.4, sides=8, finish="rubber")
        k.cyl((tx - 9.6, y, 11.6), "z", 0.035, 4.2, radius2=0.02, sides=5, bevel=0.0, finish="dark")
    # Team colour: a chevron on the middle side plates and a band across the bustle rack.
    k.at(bone="TURRET", group="HOUSECOLOR01", finish="team")
    for s in (-1, 1):
        y = s * (wall_y(7.3) + 0.25)
        ya, yb = sorted((y, y + s * 0.06))
        for sign in (-1, 1):
            arm = [(tx - 0.25, 7.8), (tx - 0.25 + sign * 0.95, 6.9), (tx - 0.25 + sign * 1.25, 6.9), (tx - 0.25 + sign * 0.3, 7.8)]
            k.prism(arm if sign > 0 else arm[::-1], ya, yb, bevel=0.0)
    k.box((tx - 13.68, -5.0, 7.45), (tx - 13.62, 5.0, 7.7), bevel=0.0)
    # Gun: breech end, thermal sleeve in sections with clamps, fume extractor, muzzle reference sensor.
    k.at(bone="BARREL", group="GUN", finish="paint")
    k.cyl((tx + 11.2, 0, GUN_Z), "x", 0.72, 2.8, sides=24, radius2=0.62, bevel=0.06)
    sections = [(12.6, 16.6, 0.5), (16.9, 20.4, 0.48), (20.7, 24.2, 0.46), (24.5, 29.4, 0.44)]
    for x0, x1, r in sections:
        k.cyl((tx + (x0 + x1) / 2, 0, GUN_Z), "x", r, x1 - x0, sides=24, bevel=0.05)
    for x in (12.6, 16.75, 20.55, 24.35):
        k.cyl((tx + x, 0, GUN_Z), "x", 0.55, 0.3, sides=24, finish="metal", bevel=0.04)
    k.cyl((tx + 18.7, 0, GUN_Z), "x", 0.62, 1.6, sides=24, bevel=0.3, segments=3)
    k.cyl((tx + 29.9, 0, GUN_Z), "x", 0.46, 1.0, sides=24, finish="metal", bevel=0.05)
    k.cyl((tx + 30.42, 0, GUN_Z), "x", 0.3, 0.06, sides=24, finish="rubber", bevel=0.0)
    k.box((tx + 29.0, -0.22, GUN_Z + 0.42), (tx + 29.8, 0.22, GUN_Z + 0.78), bevel=0.06)
    k.at(bone="ROOTTRANSFORM", group="HULL", finish="paint")


def damage_bones(k):
    """Points the damage effects use: smoke from the deck and turret, fire from the engine and hatches."""
    tx = TURRET_X
    for n, p in enumerate(((-12.0, -2.0, 5.8), (-10.0, 2.5, 5.8), (tx - 3.0, 3.2, 9.2))):
        k.add_bone(f"SMOKE{n + 1:02d}", "ROOTTRANSFORM", p)
    for n, p in enumerate(((-11.5, 0.0, 5.7), (-13.5, -4.5, 5.3), (tx - 3.0, -3.0, 9.3))):
        k.add_bone(f"FIRE{n + 1:02d}", "ROOTTRANSFORM", p)


def shadow_casters(k):
    """Closed low-poly shells just inside the visible hull, turret and gun: the only meshes that cast the
    stencil shadow (see W3DVolumetricShadow), named SHADOW*."""
    tx = TURRET_X
    k.at(bone="ROOTTRANSFORM", group="SHADOWHULL", finish="shadow", damaged=None)
    k.prism([(-15.0, 3.65), (14.7, 3.65), (15.45, 4.05), (8.75, 5.4), (-14.85, 5.4), (-15.2, 5.1)], -6.85, 6.85, bevel=0)
    for s in (-1, 1):
        ya, yb = sorted((s * 4.7, s * 6.85))
        k.prism([(-14.2, 1.3), (11.6, 0.6), (13.6, 2.4), (13.4, 3.66), (-14.4, 3.66), (-14.6, 2.4)], ya, yb, bevel=0)
    k.prism([(-14.1, 1.8), (12.7, 1.8), (14.4, 3.66), (-14.8, 3.66)], -4.55, 4.55, bevel=0)
    k.at(bone="TURRET", group="SHADOWTUR")
    base = [(8.7, -2.2), (8.7, 2.2), (6.3, 6.55), (-6.5, 6.55), (-10.9, 5.75), (-10.9, -5.75), (-6.5, -6.55), (6.3, -6.55)]
    top = [(7.7, -2.0), (7.7, 2.0), (5.5, 5.95), (-6.1, 5.95), (-10.6, 5.25), (-10.6, -5.25), (-6.1, -5.95), (5.5, -5.95)]
    k.loft([(x + tx, y, TURRET_Z + 0.35) for x, y in base], [(x + tx, y, TURRET_Z + 2.9) for x, y in top], bevel=0)
    k.at(bone="BARREL", group="SHADOWGUN")
    k.cyl((tx + 21.0, 0, GUN_Z), "x", 0.38, 17.6, sides=8, bevel=0)
    k.at(bone="ROOTTRANSFORM", group="HULL", finish="paint")


def battle_damage(k):
    """The damaged model's wounds: penetrations through the turret's add-on plates and the skirts, gouges
    in the glacis, a skirt panel hanging from one bolt."""
    tx = TURRET_X
    k.at(bone="ROOTTRANSFORM", group="HULL", finish="paint", damaged=True)
    # Holes: (part, centre, radius).
    plates = k.side_plates  # right side first (y < 0), then left; front, middle, rear
    holes = [
        (plates[4], (tx - 0.4, 6.75 - 0.25, 7.25), 0.6),
        (plates[3], (tx + 3.2, 6.75 - 0.15, 6.7), 0.32),
        (plates[1], (tx + 0.6, -6.6, 7.6), 0.42),
        (k.skirts[(-1, 3)], (0.6, -7.15, 3.6), 0.62),
        (k.skirts[(1, 1)], (8.2, 7.25, 3.9), 0.45),
        (k.skirts[(-1, 0)], (11.0, -7.25, 3.4), 0.3),
        (k.skirts[(1, 4)], (-2.4, 7.15, 4.0), 0.35),
    ]
    # Burn marks for the bake: round every hole, over the engine deck and the turret bustle.
    k.burns = [(c, r * 4.5) for _, c, r in holes] + [((-11.5, 0.0, 5.6), 5.5), ((tx - 11.0, 2.5, 8.0), 3.5),
                                                      ((4.4, 7.2, 3.6), 2.5)]
    for part, centre, r in holes:
        k.cut(part, centre, "y", r, 2.0, sides=11, jag=0.35)
        # Reactive tiles in front of a holed skirt are holed (or gone) too.
        for s, x0, z0, tile in k.tiles:
            if s * centre[1] > 0 and x0 - r < centre[0] < x0 + 1.1 + r and z0 - r < centre[2] < z0 + 0.98 + r:
                k.cut(tile, centre, "y", r * 1.1, 2.0, sides=11, jag=0.35)
    # Skirt panel hanging from its rear top bolt.
    x0, x1 = 2.75, 6.2
    pivot = Vector((x1 - 0.35, 7.15, 4.45))
    panel = k.prism([(x0, 2.55), (x1, 2.55), (x1, 4.75), (x0, 4.75)], 7.0, 7.3, bevel=0.08)
    k.cut(panel, (x0 + 1.2, 7.15, 3.5), "y", 0.4, 2.0, sides=9, jag=0.4)
    rot = Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(-24), 4, "Y") @ Matrix.Translation(-pivot)
    tilt = Matrix.Rotation(math.radians(6), 4, "X")
    panel.obj.matrix_world = rot @ Matrix.Translation(pivot) @ tilt @ Matrix.Translation(-pivot)
    k.bolts([(x1 - 0.35, 7.33, 4.45)], "y", radius=0.08)
    k.at(damaged=None)


def build(k, damaged=False):
    running_gear(k, 1, thrown=damaged)
    running_gear(k, -1)
    hull(k)
    turret(k, damaged)
    if damaged:
        battle_damage(k)
    shadow_casters(k)
    damage_bones(k)
