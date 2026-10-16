"""Modern armoured ambulance that replaces the art of the USA Ambulance (field medic vehicle).

GeneralsX @feature Claude 16/10/2026 Mine-protected cab and a tall medical module, with a roof
decontamination sprayer. Bones follow the Ambulance's Draw module: TURRET and TURRETEL (sprayer
traverse and elevation), WEAPONA (spray origin) and TIRE01-04 (left front, right front, left rear,
right rear).
"""

from geometry import Builder, Region, ShadeFn
from w3d import Material, Mesh, Model

CAMO = Region(0.0, 0.25, 1.0, 1.0, world_size=24.0)
DARK = Region(0.0, 0.0, 1.0, 0.25, world_size=10.0)
GLASS = Region(0, 0, 1, 1, world_size=6.0)
TEAM = Region(0, 0, 1, 1, world_size=8.0)

WHEEL_R = 1.9
WHEELS = {"TIRE01": (7.6, 4.0), "TIRE02": (7.6, -4.0), "TIRE03": (-6.8, 4.0), "TIRE04": (-6.8, -4.0)}
RING = (-2.0, 0.0, 11.0)


def build(name, body_texture, team_texture, glass_texture):
    model = Model(name)
    for bone, (x, y) in WHEELS.items():
        model.add_bone(bone, "ROOTTRANSFORM", (x, y, WHEEL_R))
    model.add_bone("TURRET", "ROOTTRANSFORM", RING)
    model.add_bone("TURRETEL", "TURRET", (RING[0], 0.0, RING[2] + 0.9))
    model.add_bone("WEAPONA", "TURRETEL", (RING[0] + 3.6, 0.0, RING[2] + 0.9))

    body = Material("GXBody", body_texture, specular=(60, 60, 55), shininess=12.0)
    glass = Material("GXGlass", glass_texture, specular=(200, 200, 200), shininess=40.0)
    team = Material("GXTeam", team_texture)

    hull = Mesh("HULL", body)
    b = Builder(hull, ShadeFn(height=11.0))
    # V-hull chassis.
    b.extrude_y([(-11.0, 2.2), (10.6, 2.2), (11.4, 3.0), (-11.4, 3.0)], -2.4, 2.4, DARK)
    b.box((-11.4, -3.7, 3.0), (11.4, 3.7, 4.4), CAMO)
    # Short sloped hood and heavy bumper.
    b.extrude_y([(6.0, 4.4), (11.4, 4.4), (11.6, 5.4), (10.6, 6.2), (6.0, 6.8)], -3.7, 3.7, CAMO)
    b.box((11.3, -3.4, 2.6), (12.2, 3.4, 3.8), DARK)
    b.box((11.6, -2.6, 4.6), (11.75, 2.6, 5.6), DARK)
    # Crew cab.
    b.loft([(1.0, -3.8, 4.4), (6.2, -3.8, 4.4), (6.2, 3.8, 4.4), (1.0, 3.8, 4.4)],
           [(1.0, -3.5, 8.6), (4.6, -3.5, 8.6), (4.6, 3.5, 8.6), (1.0, 3.5, 8.6)], CAMO)
    # Medical module: tall box with roof lockers, rear doors and steps.
    b.box((-11.6, -4.2, 4.4), (1.0, 4.2, 10.4), CAMO)
    b.box((-10.8, -3.6, 10.4), (-4.4, 3.6, 11.0), DARK)
    b.box((-11.75, -3.0, 4.8), (-11.6, -0.1, 9.6), DARK)
    b.box((-11.75, 0.1, 4.8), (-11.6, 3.0, 9.6), DARK)
    b.box((-12.6, -2.4, 3.2), (-11.4, 2.4, 3.5), DARK)
    # Wheel arches, mirrors, light bar.
    for x, _ in WHEELS.values():
        for y0, y1 in ((-4.4, -3.7), (3.7, 4.4)):
            b.box((x - 2.4, y0, 4.0), (x + 2.4, y1, 4.4), CAMO)
    for y in (-4.3, 4.3):
        b.box((5.6, y - 0.15, 6.4), (5.9, y + 0.15, 7.6), DARK)
    b.box((2.6, -2.6, 8.6), (3.4, 2.6, 9.0), DARK)
    b.cylinder_z(RING[0], RING[1], 10.4, RING[2], 1.2, 1.2, sides=10, region=DARK)
    model.attach("ROOTTRANSFORM", hull)

    windows = Mesh("WINDOWS", glass)
    g = Builder(windows, ShadeFn(height=11.0, floor=0.9))
    g.polygon([(6.26, -3.0, 5.2), (6.26, 3.0, 5.2), (4.7, 2.8, 8.2), (4.7, -2.8, 8.2)], GLASS, outward_from=(0, 0, 6))
    for side in (-1, 1):
        y = side * 3.82
        g.polygon([(1.4, y, 5.8), (5.2, y, 5.8), (4.4, y - side * 0.25, 8.0), (1.4, y - side * 0.25, 8.0)], GLASS,
                  outward_from=(3.0, 0, 6.5))
    model.attach("ROOTTRANSFORM", windows)

    # Team colour takes the place of the medical markings: side panels and roof cross.
    stripes = Mesh("HOUSECOLOR01", team)
    s = Builder(stripes, ShadeFn(height=11.0, floor=0.85))
    for y0, y1 in ((-4.28, -4.2), (4.2, 4.28)):
        s.box((-7.4, y0, 6.0), (-5.4, y1, 9.6), TEAM)
        s.box((-8.2, y0, 6.8), (-4.6, y1, 8.8), TEAM)
        s.box((-11.0, y0, 4.8), (0.4, y1, 5.3), TEAM)
    s.box((-9.6, -0.5, 11.0), (-5.6, 0.5, 11.06), TEAM)
    s.box((-8.1, -2.0, 11.0), (-7.1, 2.0, 11.06), TEAM)
    model.attach("ROOTTRANSFORM", stripes)

    for bone, (x, y) in WHEELS.items():
        wheel = Mesh(bone, body)
        w = Builder(wheel, ShadeFn(height=11.0, floor=0.7))
        y_in, y_out = sorted((y - 0.75, y + 0.75))
        w.cylinder_y(x, y_in, y_out, WHEEL_R, WHEEL_R, sides=14, region=DARK)
        hub_y = (y_out, y_out + 0.15) if y > 0 else (y_in - 0.15, y_in)
        w.cylinder_y(x, hub_y[0], hub_y[1], WHEEL_R, 0.9, sides=8, region=CAMO)
        model.attach(bone, wheel)

    rx, ry, rz = RING
    mount = Mesh("TURRET", body)
    m = Builder(mount, ShadeFn(ground=2.0, height=11.0, floor=0.8))
    m.box((rx - 1.0, -0.9, rz), (rx + 1.0, 0.9, rz + 0.6), CAMO)
    m.box((rx - 0.3, -0.7, rz + 0.6), (rx + 0.3, 0.7, rz + 1.3), DARK)
    model.attach("TURRET", mount)
    nozzle = Mesh("TURRETEL", body)
    n = Builder(nozzle, ShadeFn(ground=2.0, height=11.0, floor=0.8))
    n.box((rx - 1.2, -0.6, rz + 0.6), (rx + 0.8, 0.6, rz + 1.4), CAMO)
    n.cylinder_x(rx + 0.8, rx + 3.6, 0.0, rz + 0.9, 0.22, 0.16, sides=8, region=DARK)
    model.attach("TURRETEL", nozzle)
    return model
