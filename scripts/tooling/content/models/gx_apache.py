"""Modern attack helicopter (Apache-class look) that replaces the USA Comanche's art.

GeneralsX @feature Claude 15/10/2026 Tandem cockpit, nose sensor turret, chin gun, stub wings with
missile rails, mast radar and a four-blade rotor with a blur disc. Bones match the Comanche Draw
module and death behaviour: PROPELLER01 (main rotor, flies off on death), PROPELLER02 (tail rotor),
MUZZLE and TURRETFX (chin gun), WEAPONA01/02 (missile rails), WEAPONB01/02 (rocket pods, mesh
MISSILEUPGRADE shown with the upgrade), FLARE01-03 and SMOKE01. The rotors spin in the model's
own looping animation AVGXAPACHE.AVGXAPACHE.
"""

import math

from geometry import Builder, Region, ShadeFn, centroid
from w3d import ADDITIVE, ALPHA_BLEND, MESH_FLAG_HIDDEN, MESH_FLAG_TWO_SIDED, Material, Mesh, Model

CAMO = Region(0.0, 0.25, 1.0, 1.0, world_size=24.0)
DARK = Region(0.0, 0.0, 1.0, 0.25, world_size=10.0)
GLASS = Region(0, 0, 1, 1, world_size=6.0)
TEAM = Region(0, 0, 1, 1, world_size=8.0)

ROTOR_HUB = (1.0, 0.0, 12.2)
TAIL_HUB = (-22.6, 1.1, 10.6)
GUN = (13.6, 0.0, 2.9)


def ring(x, half_width, z0, z1, chamfer=0.35):
    """Octagonal fuselage cross-section at station x."""
    c = min(chamfer * half_width, chamfer * (z1 - z0) / 2)
    w = half_width
    return [(x, -w + c, z0), (x, w - c, z0), (x, w, z0 + c), (x, w, z1 - c),
            (x, w - c, z1), (x, -w + c, z1), (x, -w, z1 - c), (x, -w, z0 + c)]


def loft_x(builder, stations, region):
    """Fuselage from consecutive rings; each segment is convex so faces orient outward."""
    rings = [ring(*s) for s in stations]
    for a, b in zip(rings, rings[1:]):
        c = centroid(a + b)
        n = len(a)
        for i in range(n):
            j = (i + 1) % n
            builder.polygon([a[i], a[j], b[j], b[i]], region, outward_from=c)
    builder.polygon(rings[0], region, outward_from=centroid(rings[0] + rings[1]))
    builder.polygon(rings[-1], region, outward_from=centroid(rings[-1] + rings[-2]))


def build(name, body_texture, team_texture, glass_texture, flash_texture, disc_texture):
    model = Model(name)
    model.add_bone("PROPELLER01", "ROOTTRANSFORM", ROTOR_HUB)
    model.add_bone("PROPELLER02", "ROOTTRANSFORM", TAIL_HUB)
    model.add_bone("MUZZLE", "ROOTTRANSFORM", GUN)
    model.add_bone("TURRETFX", "ROOTTRANSFORM", GUN)
    for i, y in enumerate((-6.6, 6.6), 1):
        model.add_bone(f"WEAPONA{i:02d}", "ROOTTRANSFORM", (3.0, y, 4.9))
    for i, y in enumerate((-4.3, 4.3), 1):
        model.add_bone(f"WEAPONB{i:02d}", "ROOTTRANSFORM", (3.2, y, 5.1))
    for i, (x, y) in enumerate(((-8.0, -1.4), (-8.0, 1.4), (-12.0, 0.0)), 1):
        model.add_bone(f"FLARE{i:02d}", "ROOTTRANSFORM", (x, y, 5.2))
    model.add_bone("SMOKE01", "ROOTTRANSFORM", (-2.0, 2.8, 9.0))

    body = Material("GXBody", body_texture, specular=(70, 70, 70), shininess=16.0)
    glass = Material("GXGlass", glass_texture, specular=(200, 200, 200), shininess=40.0)
    team = Material("GXTeam", team_texture)
    flash = Material("GXFlash", flash_texture, shader=ADDITIVE, emissive=(255, 255, 255))
    disc = Material("GXDisc", disc_texture, shader=ALPHA_BLEND)

    hull = Mesh("FUSELAGE", body)
    b = Builder(hull, ShadeFn(ground=2.0, height=9.0, floor=0.7))
    loft_x(b, [(16.6, 0.5, 4.6, 5.6), (14.6, 1.5, 3.7, 6.6), (11.2, 1.9, 3.5, 7.2), (5.0, 2.1, 3.5, 7.8),
               (1.0, 2.6, 3.6, 8.6), (-5.0, 2.4, 4.0, 8.4), (-9.0, 1.3, 5.2, 8.0), (-21.0, 0.55, 6.6, 7.6)], CAMO)
    # Canopy frames over the tandem seats (glass is a separate mesh).
    b.box((10.9, -1.95, 7.1), (11.3, 1.95, 8.1), DARK)
    b.box((5.0, -2.0, 7.7), (5.4, 2.0, 9.2), DARK)
    # Engine nacelles with exhaust deflectors.
    for y in (-3.1, 3.1):
        b.cylinder_x(-5.0, 3.2, y, 8.2, 1.3, 1.25, sides=10, region=CAMO)
        b.cylinder_x(-6.4, -5.0, y * 1.1, 8.4, 0.9, 1.15, sides=10, region=DARK)
        b.cylinder_x(3.2, 3.6, y, 8.2, 1.0, sides=10, region=DARK)
    # Stub wings, pylons and missile rails.
    for side in (-1, 1):
        y0, y1 = sorted((side * 2.0, side * 7.4))
        b.extrude_y([(0.6, 6.0), (3.4, 6.0), (3.0, 6.5), (0.8, 6.5)], y0, y1, CAMO)
        for yy in (side * 4.3, side * 6.6):
            b.box((1.4, yy - 0.2, 5.3), (2.8, yy + 0.2, 6.0), DARK)
        for dy in (-0.45, 0.45):
            for dz in (-0.4, 0.4):
                b.cylinder_x(0.4, 3.4, side * 6.6 + dy, 4.9 + dz, 0.28, sides=8, region=CAMO)
    # Nose sensor turret, chin gun and its mount.
    b.cylinder_x(16.0, 17.6, 0.0, 4.4, 0.95, 0.8, sides=12, region=DARK)
    b.cylinder_z(9.4, 0.0, 2.9, 3.6, 0.9, 0.7, sides=10, region=DARK)
    b.cylinder_x(9.4, GUN[0], 0.0, GUN[2], 0.18, sides=8, region=DARK)
    # Landing gear.
    for y in (-2.7, 2.7):
        b.box((7.6, y - 0.2, 1.4), (8.0, y + 0.2, 3.7), DARK)
        b.cylinder_y(8.0, y - 0.35, y + 0.35, 1.0, 0.95, sides=10, region=DARK)
    b.box((-19.4, -0.15, 3.0), (-19.0, 0.15, 6.8), DARK)
    b.cylinder_y(-19.2, -0.25, 0.25, 2.8, 0.5, sides=8, region=DARK)
    # Tail fin with the tail rotor gearbox, horizontal stabilator.
    b.extrude_y([(-23.6, 6.6), (-19.6, 6.6), (-21.0, 12.6), (-23.4, 12.6)], -0.25, 0.25, CAMO)
    b.cylinder_y(TAIL_HUB[0], 0.2, 0.9, TAIL_HUB[2], 0.5, sides=8, region=DARK)
    b.extrude_y([(-23.2, 7.0), (-20.4, 7.0), (-20.6, 7.3), (-23.0, 7.3)], -3.6, 3.6, CAMO)
    # Rotor mast, hub and mast-mounted radar dome.
    b.cylinder_z(ROTOR_HUB[0], 0.0, 8.6, ROTOR_HUB[2] - 0.4, 0.55, 0.45, sides=10, region=DARK)
    b.cylinder_z(ROTOR_HUB[0], 0.0, ROTOR_HUB[2] + 0.5, ROTOR_HUB[2] + 1.2, 0.5, 0.5, sides=10, region=DARK)
    b.cylinder_z(ROTOR_HUB[0], 0.0, ROTOR_HUB[2] + 1.2, ROTOR_HUB[2] + 2.2, 1.3, 1.0, sides=14, region=CAMO)
    model.attach("ROOTTRANSFORM", hull)

    canopy = Mesh("CANOPY", glass)
    g = Builder(canopy, ShadeFn(ground=2.0, height=9.0, floor=0.9))
    g.loft([(11.0, -1.85, 7.1), (14.4, -1.4, 6.5), (14.4, 1.4, 6.5), (11.0, 1.85, 7.1)],
           [(11.0, -1.4, 8.2), (12.8, -1.0, 7.9), (12.8, 1.0, 7.9), (11.0, 1.4, 8.2)], GLASS, cap_bottom=False)
    g.loft([(5.2, -1.95, 7.7), (10.9, -1.85, 7.2), (10.9, 1.85, 7.2), (5.2, 1.95, 7.7)],
           [(5.2, -1.5, 9.3), (10.9, -1.3, 8.3), (10.9, 1.3, 8.3), (5.2, 1.5, 9.3)], GLASS, cap_bottom=False)
    model.attach("ROOTTRANSFORM", canopy)

    pods = Mesh("MISSILEUPGRADE", body)
    p = Builder(pods, ShadeFn(ground=2.0, height=9.0, floor=0.7))
    for y in (-4.3, 4.3):
        p.cylinder_x(0.0, 3.4, y, 5.1, 0.85, 0.85, sides=12, region=DARK)
        p.cylinder_x(3.4, 3.8, y, 5.1, 0.85, 0.5, sides=12, region=DARK)
    model.attach("ROOTTRANSFORM", pods)

    stripes = Mesh("HOUSECOLOR01", team)
    s = Builder(stripes, ShadeFn(ground=2.0, height=9.0, floor=0.8))
    s.extrude_y([(-16.0, 6.6), (-11.0, 6.0), (-11.0, 6.9), (-16.0, 7.4)], -1.12, 1.12, TEAM)
    s.extrude_y([(-23.3, 11.0), (-21.4, 11.0), (-21.1, 12.0), (-23.3, 12.0)], -0.3, 0.3, TEAM)
    model.attach("ROOTTRANSFORM", stripes)

    # Main rotor: four blades plus a faint blur disc, all turning with PROPELLER01.
    blades = Mesh("BLADES", body)
    r = Builder(blades, ShadeFn(ground=2.0, height=9.0, floor=0.85))
    hx, hy, hz = ROTOR_HUB
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        ca, sa = math.cos(a), math.sin(a)
        pts = []
        for along, across in ((0.8, -0.45), (14.6, -0.45), (14.6, 0.45), (0.8, 0.45)):
            pts.append((hx + along * ca - across * sa, hy + along * sa + across * ca))
        r.loft([(x, y, hz - 0.08) for x, y in pts], [(x, y, hz + 0.08) for x, y in pts], DARK)
    r.cylinder_z(hx, hy, hz - 0.3, hz + 0.3, 1.0, 1.0, sides=10, region=DARK)
    model.attach("PROPELLER01", blades)

    blur = Mesh("ROTORDISC", disc, attributes=MESH_FLAG_TWO_SIDED)
    d = Builder(blur, shade=lambda q, n: (255, 255, 255, 255),
                uv_fn=lambda q: ((q[0] - hx) / 30.0 + 0.5, (q[1] - hy) / 30.0 + 0.5))
    d.polygon([(hx + 15 * math.cos(t), hy + 15 * math.sin(t), hz) for t in (2 * math.pi * k / 24 for k in range(24))])
    model.attach("PROPELLER01", blur)

    tail = Mesh("TAILROTOR", body)
    tr = Builder(tail, ShadeFn(ground=2.0, height=9.0, floor=0.85))
    tx, ty, tz = TAIL_HUB
    for k in range(4):
        a = k * math.pi / 2 + math.pi / 4
        ca, sa = math.cos(a), math.sin(a)
        pts = [(tx + along * ca - across * sa, tz + along * sa + across * ca)
               for along, across in ((0.3, -0.25), (3.2, -0.25), (3.2, 0.25), (0.3, 0.25))]
        tr.extrude_y([(x, z) for x, z in pts], ty + 0.85, ty + 1.0, DARK)
    model.attach("PROPELLER02", tail)

    fx = Mesh("TURRETFX", flash, attributes=MESH_FLAG_HIDDEN | MESH_FLAG_TWO_SIDED)
    gx, gy, gz = GUN
    m = Builder(fx, shade=lambda q, n: (255, 255, 255, 255),
                uv_fn=lambda q: ((q[0] - gx) / 3.0, (q[1] - gy + 1.0) / 2.0))
    m.polygon([(gx, gy - 1.0, gz), (gx + 3.0, gy - 1.0, gz), (gx + 3.0, gy + 1.0, gz), (gx, gy + 1.0, gz)])
    m.uv_fn = lambda q: ((q[0] - gx) / 3.0, (q[2] - gz + 1.0) / 2.0)
    m.polygon([(gx, gy, gz - 1.0), (gx + 3.0, gy, gz - 1.0), (gx + 3.0, gy, gz + 1.0), (gx, gy, gz + 1.0)])
    model.attach("TURRETFX", fx)

    model.add_spin("PROPELLER01", "z", revolutions=1.0)
    model.add_spin("PROPELLER02", "y", revolutions=2.0)
    return model
