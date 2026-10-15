"""Modern light tactical vehicle (JLTV-class look) that replaces the USA Humvee's art.

GeneralsX @feature Claude 15/10/2026 V-hull armoured cab, steep hood, rear cargo bay and a remote
weapon station. Sub-objects and bones follow the Humvee Draw module: TURRET (machine gun station)
or TURRETUP01 with a missile launcher and HOUSECOLOR03 after the TOW upgrade, MUZZLE01/MUZZLEFX01
and MUZZLEUP01/MUZZLEFXUP01 for the two guns, WEAPONB01 for missiles, TIRE01-04 for the wheels
(left front, right front, left rear, right rear).
"""

from geometry import Builder, Region, ShadeFn
from w3d import ADDITIVE, MESH_FLAG_HIDDEN, MESH_FLAG_TWO_SIDED, Material, Mesh, Model

CAMO = Region(0.0, 0.25, 1.0, 1.0, world_size=24.0)
DARK = Region(0.0, 0.0, 1.0, 0.25, world_size=10.0)
GLASS = Region(0, 0, 1, 1, world_size=6.0)
TEAM = Region(0, 0, 1, 1, world_size=8.0)

WHEEL_R = 1.65
WHEELS = {"TIRE01": (6.0, 3.55), "TIRE02": (6.0, -3.55), "TIRE03": (-5.6, 3.55), "TIRE04": (-5.6, -3.55)}
RING = (-1.4, 0.0, 7.9)


def muzzle_flash(model, bone, material, origin, length=3.0, size=1.0):
    fx = Mesh(bone, material, attributes=MESH_FLAG_HIDDEN | MESH_FLAG_TWO_SIDED)
    x, y, z = origin
    m = Builder(fx, shade=lambda q, n: (255, 255, 255, 255), uv_fn=lambda q: ((q[0] - x) / length, (q[1] - y + size) / (2 * size)))
    m.polygon([(x, y - size, z), (x + length, y - size, z), (x + length, y + size, z), (x, y + size, z)])
    m.uv_fn = lambda q: ((q[0] - x) / length, (q[2] - z + size) / (2 * size))
    m.polygon([(x, y, z - size), (x + length, y, z - size), (x + length, y, z + size), (x, y, z + size)])
    model.attach(bone, fx)


def build(name, body_texture, team_texture, glass_texture, flash_texture):
    model = Model(name)
    for bone, (x, y) in WHEELS.items():
        model.add_bone(bone, "ROOTTRANSFORM", (x, y, WHEEL_R))
    model.add_bone("TURRET", "ROOTTRANSFORM", RING)
    model.add_bone("MUZZLE01", "TURRET", (RING[0] + 5.4, 0.0, RING[2] + 1.3))
    model.add_bone("MUZZLEFX01", "TURRET", (RING[0] + 5.4, 0.0, RING[2] + 1.3))
    model.add_bone("TURRETUP01", "ROOTTRANSFORM", RING)
    model.add_bone("MUZZLEUP01", "TURRETUP01", (RING[0] + 4.4, -0.6, RING[2] + 1.1))
    model.add_bone("MUZZLEFXUP01", "TURRETUP01", (RING[0] + 4.4, -0.6, RING[2] + 1.1))
    model.add_bone("WEAPONB01", "TURRETUP01", (RING[0] + 3.4, 1.2, RING[2] + 1.6))

    body = Material("GXBody", body_texture, specular=(60, 60, 55), shininess=12.0)
    glass = Material("GXGlass", glass_texture, specular=(200, 200, 200), shininess=40.0)
    team = Material("GXTeam", team_texture)
    flash = Material("GXFlash", flash_texture, shader=ADDITIVE, emissive=(255, 255, 255))

    hull = Mesh("HULL", body)
    b = Builder(hull, ShadeFn(height=8.0))
    # V-shaped belly and chassis.
    b.extrude_y([(-9.0, 1.9), (8.6, 1.9), (9.4, 2.6), (-9.4, 2.6)], -2.0, 2.0, DARK)
    b.box((-9.4, -3.3, 2.6), (9.4, 3.3, 3.9), CAMO)
    # Hood sloping down to a heavy grille and bumper.
    b.extrude_y([(3.2, 3.9), (9.4, 3.9), (9.7, 4.7), (9.0, 5.5), (3.2, 6.1)], -3.3, 3.3, CAMO)
    b.box((9.4, -3.0, 2.4), (10.2, 3.0, 3.4), DARK)
    b.box((9.6, -2.4, 4.0), (9.75, 2.4, 4.9), DARK)
    # Armoured crew cab with tapered sides.
    b.loft([(-4.6, -3.4, 3.9), (3.4, -3.4, 3.9), (3.4, 3.4, 3.9), (-4.6, 3.4, 3.9)],
           [(-4.4, -3.0, 7.8), (1.8, -3.0, 7.8), (1.8, 3.0, 7.8), (-4.4, 3.0, 7.8)], CAMO)
    # Cargo bay with a covered load.
    b.box((-9.4, -3.4, 3.9), (-4.6, 3.4, 5.4), CAMO)
    b.box((-9.0, -2.8, 5.4), (-5.0, 2.8, 6.6), DARK)
    # Wheel arches and mirrors.
    for x, _ in WHEELS.values():
        for y0, y1 in ((-3.9, -3.3), (3.3, 3.9)):
            b.box((x - 2.1, y0, 3.5), (x + 2.1, y1, 3.9), CAMO)
    for y in (-3.9, 3.9):
        b.box((2.8, y - 0.15, 5.6), (3.1, y + 0.15, 6.6), DARK)
    # Turret ring.
    b.cylinder_z(RING[0], RING[1], 7.8, RING[2], 1.6, 1.6, sides=12, region=DARK)
    model.attach("ROOTTRANSFORM", hull)

    windows = Mesh("WINDOWS", glass)
    g = Builder(windows, ShadeFn(height=8.0, floor=0.9))
    # Windscreen and side windows sit just proud of the cab faces.
    g.polygon([(3.46, -2.6, 4.6), (3.46, 2.6, 4.6), (1.9, 2.4, 7.4), (1.9, -2.4, 7.4)], GLASS, outward_from=(0, 0, 5))
    for side in (-1, 1):
        y = side * 3.42
        for x0, x1 in ((-3.8, -1.0), (-0.6, 2.4)):
            g.polygon([(x0, y, 5.2), (x1, y, 5.2), (x1, y - side * 0.3, 7.2), (x0, y - side * 0.3, 7.2)], GLASS,
                      outward_from=(x0, 0, 6))
    model.attach("ROOTTRANSFORM", windows)

    stripes = Mesh("HOUSECOLOR01", team)
    s = Builder(stripes, ShadeFn(height=8.0, floor=0.8))
    for y0, y1 in ((-3.48, -3.4), (3.4, 3.48)):
        s.box((-4.2, y0, 4.2), (3.0, y1, 4.8), TEAM)
    s.box((3.6, -1.4, 6.05), (6.0, 1.4, 6.1), TEAM)
    model.attach("ROOTTRANSFORM", stripes)

    for bone, (x, y) in WHEELS.items():
        wheel = Mesh(bone, body)
        w = Builder(wheel, ShadeFn(height=8.0, floor=0.7))
        y_in, y_out = sorted((y - 0.65, y + 0.65))
        w.cylinder_y(x, y_in, y_out, WHEEL_R, WHEEL_R, sides=14, region=DARK)
        hub_y = (y_out, y_out + 0.15) if y > 0 else (y_in - 0.15, y_in)
        w.cylinder_y(x, hub_y[0], hub_y[1], WHEEL_R, 0.8, sides=8, region=CAMO)
        model.attach(bone, wheel)

    rx, ry, rz = RING
    # Remote weapon station with a heavy machine gun.
    rws = Mesh("TURRET", body)
    r = Builder(rws, ShadeFn(ground=2.0, height=8.0, floor=0.8))
    r.box((rx - 1.4, -1.2, rz), (rx + 1.4, 1.2, rz + 0.5), CAMO)
    r.box((rx - 0.9, -0.9, rz + 0.5), (rx + 1.4, 0.9, rz + 1.8), CAMO)
    r.box((rx + 0.4, 0.95, rz + 1.0), (rx + 1.5, 1.5, rz + 1.8), DARK)
    r.cylinder_x(rx + 1.4, rx + 5.4, 0.0, rz + 1.3, 0.16, sides=8, region=DARK)
    r.cylinder_x(rx + 4.6, rx + 5.4, 0.0, rz + 1.3, 0.24, sides=8, region=DARK)
    model.attach("TURRET", rws)
    muzzle_flash(model, "MUZZLEFX01", flash, (rx + 5.4, 0.0, rz + 1.3), length=2.2, size=0.8)

    # Upgraded station: grenade launcher plus a twin missile box.
    up = Mesh("TURRETUP01", body)
    u = Builder(up, ShadeFn(ground=2.0, height=8.0, floor=0.8))
    u.box((rx - 1.4, -1.2, rz), (rx + 1.4, 1.2, rz + 0.5), CAMO)
    u.box((rx - 0.9, -1.0, rz + 0.5), (rx + 1.2, 0.6, rz + 1.7), CAMO)
    u.cylinder_x(rx + 1.2, rx + 4.4, -0.6, rz + 1.1, 0.22, sides=8, region=DARK)
    u.box((rx - 1.6, 0.6, rz + 0.9), (rx + 3.4, 1.8, rz + 2.3), CAMO)
    u.box((rx + 3.3, 0.75, rz + 1.05), (rx + 3.45, 1.65, rz + 2.15), DARK)
    model.attach("TURRETUP01", up)
    muzzle_flash(model, "MUZZLEFXUP01", flash, (rx + 4.4, -0.6, rz + 1.1), length=1.8, size=0.7)

    team_up = Mesh("HOUSECOLOR03", team)
    t = Builder(team_up, ShadeFn(ground=2.0, height=8.0, floor=0.8))
    t.box((rx - 1.2, 1.8, rz + 1.3), (rx + 2.8, 1.86, rz + 1.9), TEAM)
    model.attach("TURRETUP01", team_up)
    return model
