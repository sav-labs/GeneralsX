"""Modern main battle tank (Abrams-class look) that replaces the USA Crusader's art.

GeneralsX @feature Claude 15/10/2026 Low, wide turret with flat armour faces, long smoothbore
gun with a thermal sleeve, side skirts, remote weapon station and bustle rack. Bones match what
the Crusader's Draw module needs: TURRET, BARREL (recoil), TURRETMS (shell launch, fire FX) and
TURRETFX (muzzle flash mesh). Treads are TREADSL/TREADSR so W3DTankDraw scrolls them.
"""

from geometry import Builder, Region, ShadeFn
from w3d import ADDITIVE, MESH_FLAG_HIDDEN, MESH_FLAG_TWO_SIDED, Material, Mesh, Model

# Body atlas rows (V measured from the bottom of the image): camouflage on top, running gear below.
CAMO = Region(0.0, 0.25, 1.0, 1.0, world_size=32.0)
DARK = Region(0.0, 0.0, 1.0, 0.25, world_size=12.0)

TURRET_X = -1.0
TURRET_Z = 5.6
GUN_Z = 7.1


def turret_ring(points, z):
    return [(x + TURRET_X, y, z) for x, y in points]


def build(name, body_texture, tread_texture, team_texture, flash_texture):
    model = Model(name)
    model.add_bone("TURRET", "ROOTTRANSFORM", (TURRET_X, 0, TURRET_Z))
    model.add_bone("BARREL", "TURRET", (TURRET_X + 9.8, 0, GUN_Z))
    model.add_bone("TURRETMS", "BARREL", (TURRET_X + 30.4, 0, GUN_Z))
    model.add_bone("TURRETFX", "BARREL", (TURRET_X + 30.4, 0, GUN_Z))

    body = Material("GXBody", body_texture, specular=(60, 60, 55), shininess=12.0)
    team = Material("GXTeam", team_texture)
    tread = Material("GXTread", tread_texture, scroll_mapper=True)
    flash = Material("GXFlash", flash_texture, shader=ADDITIVE, emissive=(255, 255, 255))

    # --- Hull -------------------------------------------------------------------------------
    hull = Mesh("HULL", body)
    b = Builder(hull, ShadeFn(height=7.0))
    # Lower hull between the tracks.
    b.extrude_y([(-14.4, 1.7), (13.4, 1.7), (14.8, 3.3), (-14.8, 3.3)], -4.6, 4.6, CAMO)
    # Upper hull over the tracks: long, shallow glacis and a vertical rear plate.
    b.extrude_y([(-15.0, 3.3), (14.8, 3.3), (15.6, 4.0), (8.6, 5.6), (-15.2, 5.6), (-15.4, 4.3)],
                -7.0, 7.0, CAMO)
    # Engine deck grilles and rear stowage.
    b.box((-14.6, -4.8, 5.6), (-8.8, 4.8, 5.85), DARK)
    b.box((-15.9, -6.2, 3.6), (-15.2, 6.2, 5.2), DARK)
    # Driver's periscopes.
    b.box((9.4, -1.4, 5.3), (10.6, 1.4, 5.85), DARK)
    # Headlight clusters and tow points.
    for y in (-5.8, 5.8):
        b.box((14.6, y - 0.7, 4.0), (15.4, y + 0.7, 4.6), DARK)
    # Side skirts with an angled front panel.
    for y0, y1 in ((-7.4, -7.0), (7.0, 7.4)):
        b.extrude_y([(-14.6, 1.8), (12.4, 1.8), (14.4, 3.3), (14.4, 4.7), (-14.9, 4.7)], y0, y1, CAMO)
    # Road wheels showing under the skirts, and the drive sprocket / idler.
    for side in (-1, 1):
        y_in, y_out = (7.0, 7.12) if side > 0 else (-7.12, -7.0)
        for k in range(7):
            x = -10.8 + k * 3.5
            b.cylinder_y(x, y_in, y_out, 1.2, 1.05, sides=12, region=DARK)
        b.cylinder_y(-13.6, y_in, y_out, 2.0, 1.15, sides=12, region=DARK)
        b.cylinder_y(13.1, y_in, y_out, 2.2, 1.2, sides=12, region=DARK)
    model.attach("ROOTTRANSFORM", hull)

    # --- Treads ------------------------------------------------------------------------------
    track_profile = [(-12.2, 0.0), (11.4, 0.0), (14.2, 2.2), (13.4, 3.2), (-14.0, 3.2), (-14.8, 2.0)]
    for mesh_name, y0, y1, direction in (("TREADSL", 4.6, 6.98, -1.0), ("TREADSR", -6.98, -4.6, 1.0)):
        mesh = Mesh(mesh_name, tread)
        tb = Builder(mesh, ShadeFn(height=4.0, floor=0.55),
                     uv_fn=lambda p, d=direction: (d * p[0] / 6.0, (p[1] - 4.6 if p[1] > 0 else p[1] + 6.98) / 2.4))
        tb.extrude_y(track_profile, y0, y1)
        model.attach("ROOTTRANSFORM", mesh)

    # --- Turret ------------------------------------------------------------------------------
    turret = Mesh("TURRETBODY", body)
    t = Builder(turret, ShadeFn(ground=2.0, height=7.0, floor=0.7))
    base = [(8.8, -2.2), (8.8, 2.2), (6.4, 6.7), (-6.6, 6.7), (-11.0, 5.9), (-11.0, -5.9), (-6.6, -6.7), (6.4, -6.7)]
    top = [(7.6, -2.0), (7.6, 2.0), (5.5, 6.0), (-6.2, 6.0), (-10.6, 5.3), (-10.6, -5.3), (-6.2, -6.0), (5.5, -6.0)]
    t.loft(turret_ring(base, TURRET_Z), turret_ring(top, TURRET_Z + 3.0), CAMO)
    tx = TURRET_X
    # Gun mantlet.
    t.box((tx + 8.6, -1.7, 6.2), (tx + 9.9, 1.7, 8.0), CAMO)
    # Bustle rack.
    t.box((tx - 13.4, -5.4, 6.1), (tx - 10.9, 5.4, 6.3), DARK)
    for y in (-5.3, 0.0, 5.3):
        t.box((tx - 13.4, y - 0.12, 6.3), (tx - 13.2, y + 0.12, 7.9), DARK)
    t.box((tx - 13.4, -5.4, 7.8), (tx - 13.2, 5.4, 7.95), DARK)
    t.box((tx - 13.1, -4.8, 6.3), (tx - 11.0, -1.0, 7.4), CAMO)
    t.box((tx - 13.1, 0.8, 6.3), (tx - 11.0, 4.4, 7.1), CAMO)
    # Gunner's primary sight and the commander's independent thermal viewer.
    t.box((tx + 4.2, 2.6, 8.6), (tx + 6.0, 4.4, 9.5), CAMO)
    t.box((tx + 4.45, 2.8, 8.9), (tx + 6.05, 4.2, 9.35), DARK)
    t.box((tx - 0.6, -5.0, 8.6), (tx + 0.6, -3.8, 9.1), CAMO)
    t.box((tx - 0.5, -4.9, 9.1), (tx + 0.9, -3.9, 10.2), CAMO)
    t.box((tx + 0.85, -4.75, 9.3), (tx + 0.95, -4.05, 9.9), DARK)
    # Commander's cupola with a remote weapon station, loader's hatch with a machine gun.
    t.cylinder_z(tx - 3.0, -3.0, 8.6, 9.3, 1.5, 1.4, sides=10, region=CAMO)
    t.box((tx - 3.8, -3.6, 9.3), (tx - 1.8, -2.2, 10.2), CAMO)
    t.box((tx - 1.8, -3.25, 9.55), (tx - 1.3, -2.55, 10.0), DARK)
    t.cylinder_x(tx - 1.3, tx + 1.9, -2.9, 9.8, 0.12, sides=6, region=DARK)
    t.cylinder_z(tx - 3.0, 3.2, 8.6, 9.1, 1.2, 1.15, sides=10, region=CAMO)
    t.box((tx - 2.2, 3.0, 9.1), (tx - 1.6, 3.4, 9.6), DARK)
    t.cylinder_x(tx - 1.6, tx + 1.2, 3.2, 9.45, 0.1, sides=6, region=DARK)
    # Smoke grenade dischargers on both cheeks.
    for side in (-1, 1):
        for k in range(3):
            t.cylinder_x(tx + 6.0, tx + 7.0, side * (5.6 - k * 0.45), 8.9, 0.2, sides=6, region=DARK)
    # Antennas.
    for y in (-4.6, 4.6):
        t.cylinder_z(tx - 9.5, y, 8.6, 13.0, 0.08, 0.04, sides=4, region=DARK)
    model.attach("TURRET", turret)

    team_turret = Mesh("HOUSECOLOR01", team)
    tt = Builder(team_turret, ShadeFn(ground=2.0, height=7.0, floor=0.75))
    # Identification panels on the turret roof and bustle sides.
    tt.box((tx - 9.6, -2.2, 8.6), (tx - 6.4, 2.2, 8.66), Region(0, 0, 1, 1, world_size=8.0))
    for y0, y1 in ((-4.85, -4.8), (4.4, 4.45)):
        tt.box((tx - 12.9, y0, 6.5), (tx - 11.2, y1, 7.0), Region(0, 0, 1, 1, world_size=8.0))
    model.attach("TURRET", team_turret)

    team_hull = Mesh("HOUSECOLOR02", team)
    th = Builder(team_hull, ShadeFn(height=7.0, floor=0.75))
    for y0, y1 in ((-7.48, -7.4), (7.4, 7.48)):
        th.box((-12.0, y0, 3.7), (8.0, y1, 4.25), Region(0, 0, 1, 1, world_size=8.0))
    model.attach("ROOTTRANSFORM", team_hull)

    # --- Gun ---------------------------------------------------------------------------------
    gun = Mesh("GUN", body)
    g = Builder(gun, ShadeFn(ground=2.0, height=7.0, floor=0.8))
    g.cylinder_x(tx + 9.8, tx + 12.2, 0, GUN_Z, 0.78, 0.66, sides=14, region=DARK)
    sections = [(12.2, 17.0, 0.5), (17.0, 17.4, 0.56), (17.4, 22.6, 0.47), (22.6, 23.0, 0.53), (23.0, 29.6, 0.44)]
    for x0, x1, r in sections:
        g.cylinder_x(tx + x0, tx + x1, 0, GUN_Z, r, sides=14, region=CAMO, caps=False)
    g.cylinder_x(tx + 29.6, tx + 30.4, 0, GUN_Z, 0.5, sides=14, region=DARK)
    # Muzzle reference sensor.
    g.box((tx + 29.3, -0.18, GUN_Z + 0.5), (tx + 29.9, 0.18, GUN_Z + 0.75), DARK)
    model.attach("BARREL", gun)

    # --- Muzzle flash (hidden until the weapon fires) ----------------------------------------
    fx = Mesh("TURRETFX", flash, attributes=MESH_FLAG_HIDDEN | MESH_FLAG_TWO_SIDED)
    m = Builder(fx, shade=lambda p, n: (255, 255, 255, 255))
    x0 = tx + 30.4
    full = Region(0, 0, 1, 1, world_size=1.0)
    m.uv_fn = lambda p: ((p[0] - x0) / 7.0, (p[1] + 2.4) / 4.8)
    m.polygon([(x0, -2.4, GUN_Z), (x0 + 7.0, -2.4, GUN_Z), (x0 + 7.0, 2.4, GUN_Z), (x0, 2.4, GUN_Z)], full)
    m.uv_fn = lambda p: ((p[0] - x0) / 7.0, (p[2] - GUN_Z + 2.4) / 4.8)
    m.polygon([(x0, 0, GUN_Z - 2.4), (x0 + 7.0, 0, GUN_Z - 2.4), (x0 + 7.0, 0, GUN_Z + 2.4), (x0, 0, GUN_Z + 2.4)], full)
    model.attach("TURRETFX", fx)

    return model
