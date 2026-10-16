"""Modern tracked rocket launcher (M270-class look) that replaces the USA Tomahawk's art.

GeneralsX @feature Claude 15/10/2026 Armoured three-seat cab, tracked carrier and a two-pod launcher
that traverses on TURRET and elevates on TURRETEL. WEAPONA01 is the launch point and MISSILE01 the
ready round the Draw module shows and hides as the launcher reloads.
"""

from geometry import Builder, Region, ShadeFn
from w3d import Material, Mesh, Model

CAMO = Region(0.0, 0.25, 1.0, 1.0, world_size=28.0)
DARK = Region(0.0, 0.0, 1.0, 0.25, world_size=12.0)
TEAM = Region(0, 0, 1, 1, world_size=8.0)

TURRET = (-4.0, 0.0, 5.4)
PIVOT = (-8.0, 0.0, 6.6)


def build(name, body_texture, tread_texture, team_texture):
    model = Model(name)
    model.add_bone("TURRET", "ROOTTRANSFORM", TURRET)
    model.add_bone("TURRETEL", "TURRET", PIVOT)
    model.add_bone("WEAPONA01", "TURRETEL", (PIVOT[0] + 14.2, 1.9, PIVOT[2] + 2.6))
    model.add_bone("MISSILE01", "TURRETEL", (PIVOT[0] + 14.2, 1.9, PIVOT[2] + 2.6))

    body = Material("GXBody", body_texture, specular=(60, 60, 55), shininess=12.0)
    tread = Material("GXTread", tread_texture, scroll_mapper=True)
    team = Material("GXTeam", team_texture)

    hull = Mesh("HULL", body)
    b = Builder(hull, ShadeFn(height=8.0))
    b.extrude_y([(-14.0, 1.6), (12.0, 1.6), (14.4, 3.2), (-14.2, 3.2)], -4.4, 4.4, CAMO)
    b.box((-14.2, -6.6, 3.2), (14.4, 6.6, 5.4), CAMO)
    # Armoured cab at the front with vision blocks.
    b.extrude_y([(6.4, 5.4), (14.4, 5.4), (14.6, 6.4), (12.6, 9.6), (6.4, 9.6)], -6.0, 6.0, CAMO)
    b.box((12.9, -5.0, 7.9), (13.5, 5.0, 8.6), DARK)
    for y0, y1 in ((-6.12, -6.0), (6.0, 6.12)):
        b.box((8.0, y0, 7.6), (11.6, y1, 8.6), DARK)
    # Side skirts and road wheels.
    for y0, y1 in ((-6.9, -6.6), (6.6, 6.9)):
        b.extrude_y([(-13.4, 1.8), (12.6, 1.8), (14.0, 3.0), (14.0, 4.6), (-13.8, 4.6)], y0, y1, CAMO)
    for side in (-1, 1):
        y_in, y_out = (6.6, 6.72) if side > 0 else (-6.72, -6.6)
        for k in range(6):
            b.cylinder_y(-10.0 + k * 4.0, y_in, y_out, 1.15, 1.0, sides=12, region=DARK)
    # Launcher cradle base.
    b.cylinder_z(TURRET[0], 0.0, 5.4, 6.0, 3.0, 3.0, sides=14, region=DARK)
    model.attach("ROOTTRANSFORM", hull)

    for mesh_name, y0, y1, direction in (("TREADSL", 4.4, 6.58, -1.0), ("TREADSR", -6.58, -4.4, 1.0)):
        mesh = Mesh(mesh_name, tread)
        tb = Builder(mesh, ShadeFn(height=4.0, floor=0.55),
                     uv_fn=lambda q, d=direction: (d * q[0] / 6.0, (abs(q[1]) - 4.4) / 2.2))
        tb.extrude_y([(-12.0, 0.0), (11.0, 0.0), (13.8, 2.0), (13.0, 3.2), (-13.4, 3.2), (-14.2, 2.0)], y0, y1)
        model.attach("ROOTTRANSFORM", mesh)

    turret = Mesh("LAUNCHERBASE", body)
    t = Builder(turret, ShadeFn(ground=2.0, height=8.0, floor=0.75))
    tx, _, tz = TURRET
    t.box((tx - 5.0, -4.6, tz + 0.6), (tx + 4.0, 4.6, tz + 1.4), CAMO)
    for y in (-4.2, 4.2):
        t.box((PIVOT[0] - 1.0, y - 0.4, tz + 1.4), (PIVOT[0] + 1.0, y + 0.4, PIVOT[2] + 0.6), DARK)
    model.attach("TURRET", turret)

    pods = Mesh("LAUNCHER", body)
    p = Builder(pods, ShadeFn(ground=2.0, height=10.0, floor=0.75))
    px, _, pz = PIVOT
    for y0, y1 in ((-3.9, -0.2), (0.2, 3.9)):
        p.box((px - 0.6, y0, pz + 0.4), (px + 14.0, y1, pz + 4.2), CAMO)
        # Six launch cells per pod on the front face.
        for row in range(2):
            for col in range(3):
                cy = y0 + 0.6 + col * 1.15
                cz = pz + 1.1 + row * 1.8
                p.box((px + 14.0, cy, cz), (px + 14.15, cy + 0.9, cz + 1.2), DARK)
    p.box((px - 0.8, -4.1, pz + 0.2), (px + 0.6, 4.1, pz + 0.6), DARK)
    model.attach("TURRETEL", pods)

    missile = Mesh("MISSILE01", body)
    m = Builder(missile, ShadeFn(ground=2.0, height=10.0, floor=0.85))
    wx, wy, wz = PIVOT[0] + 14.2, 1.9, PIVOT[2] + 2.6
    m.cylinder_x(wx - 1.0, wx + 0.4, wy, wz, 0.38, sides=10, region=CAMO)
    m.cylinder_x(wx + 0.4, wx + 1.2, wy, wz, 0.38, 0.05, sides=10, region=DARK)
    model.attach("MISSILE01", missile)

    stripes = Mesh("HOUSECOLOR01", team)
    s = Builder(stripes, ShadeFn(ground=2.0, height=10.0, floor=0.8))
    for y0, y1 in ((-3.98, -3.9), (3.9, 3.98)):
        s.box((px + 2.0, y0, pz + 3.2), (px + 12.0, y1, pz + 3.8), TEAM)
    model.attach("TURRETEL", stripes)
    return model
