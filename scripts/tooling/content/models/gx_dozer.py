"""Modern armoured bulldozer that replaces the USA Dozer's art.

GeneralsX @feature Claude 15/10/2026 Tracked, D9-class proportions: low engine hood, armoured cab
with slit windows, curved blade on push arms and a rear ripper. Bones EXHAUSTFX01 and DIRTFX01
match the particle bones the retail Dozer Draw module uses.
GeneralsX @feature Claude 16/10/2026 The blade sits on its own BLADE bone and the model carries a dig
cycle (lift, drop below grade, push, settle) that the ArtRemap plays where the retail digging animation
ran; DIRTFX01 rides on the cutting edge so the dirt spray follows it.
"""

from geometry import Builder, Region, ShadeFn
from w3d import Material, Mesh, Model

CAMO = Region(0.0, 0.25, 1.0, 1.0, world_size=32.0)
DARK = Region(0.0, 0.0, 1.0, 0.25, world_size=12.0)
TEAM = Region(0, 0, 1, 1, world_size=8.0)


def build(name, body_texture, team_texture):
    model = Model(name)
    model.add_bone("EXHAUSTFX01", "ROOTTRANSFORM", (3.0, 2.4, 11.8))
    # The push arms hinge on the track frames; the blade, arms and tilt rams turn about that axis.
    model.add_bone("BLADE", "ROOTTRANSFORM", (4.0, 0.0, 2.0))
    model.add_bone("DIRTFX01", "BLADE", (13.8, 0.0, 0.6))

    body = Material("GXBody", body_texture, specular=(50, 50, 45), shininess=10.0)
    team = Material("GXTeam", team_texture)

    hull = Mesh("HULL", body)
    b = Builder(hull, ShadeFn(height=9.0))
    # Tracks with the raised rear sprocket.
    for y0, y1 in ((-7.6, -4.4), (4.4, 7.6)):
        b.extrude_y([(-10.5, 0.0), (8.8, 0.0), (10.8, 2.0), (9.6, 3.8), (-6.0, 3.8), (-9.0, 6.4), (-12.4, 4.6), (-12.0, 1.6)],
                    y0, y1, DARK)
        for x in (-7.5, -4.5, -1.5, 1.5, 4.5, 7.5):
            b.cylinder_y(x, y1 if y0 > 0 else y0 - 0.1, y1 + 0.1 if y0 > 0 else y0, 1.1, 0.9, sides=10, region=DARK)
    # Track guards.
    for y0, y1 in ((-7.8, -4.2), (4.2, 7.8)):
        b.box((-8.0, y0, 3.8), (10.4, y1, 4.2), CAMO)
    # Engine hood with a sloped radiator guard.
    b.extrude_y([(-3.0, 3.0), (9.6, 3.0), (10.4, 5.0), (9.4, 8.6), (-3.0, 8.6)], -4.1, 4.1, CAMO)
    b.box((9.5, -3.4, 4.6), (10.3, 3.4, 8.0), DARK)
    # Rear body and fuel tank.
    b.box((-12.0, -4.6, 3.0), (-3.0, 4.6, 7.4), CAMO)
    # Armoured cab: sloped sides, slit windows.
    b.loft([(-10.0, -4.6, 7.4), (-1.6, -4.6, 7.4), (-1.6, 4.6, 7.4), (-10.0, 4.6, 7.4)],
           [(-9.2, -3.8, 13.4), (-2.6, -3.8, 13.4), (-2.6, 3.8, 13.4), (-9.2, 3.8, 13.4)], CAMO)
    for y0, y1 in ((-4.45, -4.3), (4.3, 4.45)):
        b.box((-8.6, y0, 10.4), (-3.0, y1, 11.4), DARK)
    b.box((-1.95, -3.0, 10.2), (-1.75, 3.0, 11.2), DARK)
    # Roof armour, lights and antenna.
    b.box((-9.6, -4.2, 13.4), (-2.2, 4.2, 13.9), CAMO)
    for y in (-3.4, 3.4):
        b.box((-2.6, y - 0.4, 13.9), (-1.8, y + 0.4, 14.4), DARK)
    b.cylinder_z(-8.6, -3.4, 13.9, 17.4, 0.08, 0.04, sides=4, region=DARK)
    # Exhaust stack and air intake.
    b.cylinder_z(3.0, 2.4, 8.6, 11.6, 0.45, 0.4, sides=10, region=DARK)
    b.cylinder_z(3.0, -2.4, 8.6, 10.2, 0.7, 0.7, sides=10, region=CAMO)
    # Rear ripper.
    b.box((-14.6, -3.6, 4.0), (-12.0, 3.6, 5.0), DARK)
    b.extrude_y([(-14.6, 0.0), (-13.8, 0.0), (-13.4, 4.0), (-14.6, 4.0)], -0.6, 0.6, DARK)
    model.attach("ROOTTRANSFORM", hull)

    blade = Mesh("BLADE", body)
    b = Builder(blade, ShadeFn(height=9.0))
    # Blade on push arms: a curved moldboard made of tilted strips, with end bits.
    for y0, y1 in ((-7.4, -6.2), (6.2, 7.4)):
        b.box((4.0, y0, 1.4), (12.6, y1, 2.6), DARK)
    strips = [(13.0, 0.2, 13.4, 2.0), (12.8, 2.0, 12.6, 3.8), (12.6, 3.8, 12.6, 5.6), (12.6, 5.6, 13.2, 7.2)]
    for xa, za, xb, zb in strips:
        b.extrude_y([(xa, za), (xa + 0.7, za), (xb + 0.7, zb), (xb, zb)], -9.2, 9.2, CAMO)
    for y0, y1 in ((-9.8, -9.2), (9.2, 9.8)):
        b.extrude_y([(12.4, 0.2), (14.2, 0.2), (13.9, 7.2), (12.6, 7.2)], y0, y1, CAMO)
    b.box((13.4, -9.2, 0.0), (14.4, 9.2, 0.35), DARK)
    # Hydraulic tilt cylinders.
    for y in (-3.0, 3.0):
        b.cylinder_x(9.6, 12.6, y, 5.6, 0.35, sides=8, region=DARK)
    model.attach("BLADE", blade)


    stripes = Mesh("HOUSECOLOR01", team)
    s = Builder(stripes, ShadeFn(height=9.0, floor=0.8))
    for y0, y1 in ((-4.75, -4.62), (4.62, 4.75)):
        s.box((-9.6, y0, 8.4), (-2.0, y1, 9.2), TEAM)
    model.attach("ROOTTRANSFORM", stripes)
    blade_stripe = Mesh("HOUSECOLOR02", team)
    Builder(blade_stripe, ShadeFn(height=9.0, floor=0.8)).box((12.6, -6.0, 6.6), (13.25, 6.0, 7.0), TEAM)
    model.attach("BLADE", blade_stripe)

    # Dig cycle, played once per PREATTACK_A: lift the blade, drop the edge below grade, push, settle.
    # Turning about +Y lowers the front; keys are (frame, degrees) joined linearly.
    keys = [(0, 0.0), (8, -7.0), (14, 3.0), (24, 3.0), (32, 0.0)]

    def blade_angle(f):
        for (fa, a), (fb, b2) in zip(keys, keys[1:]):
            if f <= fb:
                t = (f - fa) / (fb - fa)
                t = t * t * (3 - 2 * t)
                return ("y", a + (b2 - a) * t)
        return ("y", keys[-1][1])
    model.add_motion("BLADE", keys[-1][0] + 1, turn=blade_angle)
    return model
