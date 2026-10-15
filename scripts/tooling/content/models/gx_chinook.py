"""Modern tandem-rotor transport helicopter (CH-47F-class look) that replaces the USA Chinook's art.

GeneralsX @feature Claude 15/10/2026 Long box fuselage with side fuel sponsons, glazed cockpit, rear
loading ramp and two three-blade rotors that spin in opposite directions. Bones and sub-objects
follow the Chinook Draw module and death behaviour: PROPELLER01/PROPELLER02 rotor heads, PROPS01
and PROPS02 rotor meshes (hidden when the wreck lands), ROPESTART/ROPEEND for the combat drop rope
and SMOKE01 for damage smoke. The retail cargo net module keeps working because it is a separate
model attached at the object's origin.
"""

import math

from geometry import Builder, Region, ShadeFn
from gx_apache import loft_x
from w3d import ALPHA_BLEND, MESH_FLAG_TWO_SIDED, Material, Mesh, Model

CAMO = Region(0.0, 0.25, 1.0, 1.0, world_size=28.0)
DARK = Region(0.0, 0.0, 1.0, 0.25, world_size=10.0)
GLASS = Region(0, 0, 1, 1, world_size=6.0)
TEAM = Region(0, 0, 1, 1, world_size=8.0)

FRONT_HUB = (14.0, 0.0, 12.6)
REAR_HUB = (-17.0, 0.0, 15.4)
ROTOR_R = 16.0


def rotor(model, bone, hub, material, disc_material, blades=3, phase=0.0):
    hx, hy, hz = hub
    mesh = Mesh(f"PROPS0{bone[-1]}", material)
    r = Builder(mesh, ShadeFn(ground=2.0, height=12.0, floor=0.85))
    for k in range(blades):
        a = phase + k * 2 * math.pi / blades
        ca, sa = math.cos(a), math.sin(a)
        pts = [(hx + along * ca - across * sa, hy + along * sa + across * ca)
               for along, across in ((0.9, -0.5), (ROTOR_R, -0.5), (ROTOR_R, 0.5), (0.9, 0.5))]
        r.loft([(x, y, hz - 0.08) for x, y in pts], [(x, y, hz + 0.08) for x, y in pts], DARK)
    r.cylinder_z(hx, hy, hz - 0.35, hz + 0.35, 1.1, 1.1, sides=10, region=DARK)
    model.attach(bone, mesh)

    disc = Mesh(f"DISC0{bone[-1]}", disc_material, attributes=MESH_FLAG_TWO_SIDED)
    d = Builder(disc, shade=lambda q, n: (255, 255, 255, 255),
                uv_fn=lambda q: ((q[0] - hx) / (2 * ROTOR_R) + 0.5, (q[1] - hy) / (2 * ROTOR_R) + 0.5))
    d.polygon([(hx + ROTOR_R * math.cos(t), hy + ROTOR_R * math.sin(t), hz) for t in (2 * math.pi * k / 24 for k in range(24))])
    model.attach(bone, disc)


def build(name, body_texture, team_texture, glass_texture, disc_texture):
    model = Model(name)
    model.add_bone("PROPELLER01", "ROOTTRANSFORM", FRONT_HUB)
    model.add_bone("PROPELLER02", "ROOTTRANSFORM", REAR_HUB)
    model.add_bone("ROPESTART", "ROOTTRANSFORM", (-4.0, 0.0, 2.6))
    model.add_bone("ROPEEND", "ROOTTRANSFORM", (-4.0, 0.0, -10.0))
    model.add_bone("SMOKE01", "ROOTTRANSFORM", (-14.0, 2.5, 11.0))

    body = Material("GXBody", body_texture, specular=(60, 60, 60), shininess=14.0)
    glass = Material("GXGlass", glass_texture, specular=(200, 200, 200), shininess=40.0)
    team = Material("GXTeam", team_texture)
    disc = Material("GXDisc", disc_texture, shader=ALPHA_BLEND)

    hull = Mesh("FUSELAGE", body)
    b = Builder(hull, ShadeFn(ground=2.0, height=11.0, floor=0.7))
    loft_x(b, [(19.6, 1.2, 4.0, 6.4), (17.2, 3.0, 3.0, 8.8), (12.0, 3.6, 2.8, 9.6), (-13.0, 3.6, 2.8, 9.6),
               (-19.0, 3.2, 4.6, 9.6), (-21.4, 2.6, 6.4, 9.2)], CAMO)
    # Rear pylon carrying the aft rotor, front rotor tower.
    b.loft([(-21.6, -2.2, 9.4), (-10.0, -2.2, 9.4), (-10.0, 2.2, 9.4), (-21.6, 2.2, 9.4)],
           [(-20.0, -1.6, 14.4), (-14.6, -1.6, 14.4), (-14.6, 1.6, 14.4), (-20.0, 1.6, 14.4)], CAMO)
    b.loft([(11.0, -2.0, 9.4), (16.4, -2.0, 9.4), (16.4, 2.0, 9.4), (11.0, 2.0, 9.4)],
           [(12.6, -1.4, 11.8), (15.6, -1.4, 11.8), (15.6, 1.4, 11.8), (12.6, 1.4, 11.8)], CAMO)
    for hub in (FRONT_HUB, REAR_HUB):
        b.cylinder_z(hub[0], 0.0, hub[2] - 1.0, hub[2] - 0.3, 0.6, 0.5, sides=10, region=DARK)
    # Engines on the rear pylon.
    for y in (-3.0, 3.0):
        b.cylinder_x(-21.0, -12.0, y, 11.2, 1.25, 1.2, sides=12, region=CAMO)
        b.cylinder_x(-22.0, -21.0, y, 11.2, 0.9, 1.25, sides=12, region=DARK)
    # Side fuel sponsons.
    for y0, y1 in ((-5.0, -3.5), (3.5, 5.0)):
        b.extrude_y([(-9.0, 2.6), (8.0, 2.6), (9.4, 3.8), (8.4, 5.4), (-9.0, 5.4), (-10.2, 4.0)], y0, y1, CAMO)
    # Landing gear.
    for x, y in ((9.0, -3.6), (9.0, 3.6), (-9.6, -4.4), (-9.6, 4.4)):
        b.box((x - 0.25, y - 0.25, 1.0), (x + 0.25, y + 0.25, 3.0), DARK)
        b.cylinder_y(x, y - 0.4, y + 0.4, 0.9, 0.85, sides=10, region=DARK)
    # Rear ramp outline, door and a refuelling probe.
    b.box((-21.6, -2.6, 4.6), (-21.3, 2.6, 4.8), DARK)
    b.box((8.6, 3.62, 3.4), (11.4, 3.7, 7.6), DARK)
    b.cylinder_x(19.0, 25.0, 2.6, 6.2, 0.16, sides=8, region=DARK)
    model.attach("ROOTTRANSFORM", hull)

    windows = Mesh("WINDOWS", glass)
    g = Builder(windows, ShadeFn(ground=2.0, height=11.0, floor=0.9))
    g.loft([(17.3, -3.05, 6.0), (19.7, -1.25, 5.6), (19.7, 1.25, 5.6), (17.3, 3.05, 6.0)],
           [(17.3, -2.7, 8.6), (18.6, -1.6, 7.8), (18.6, 1.6, 7.8), (17.3, 2.7, 8.6)], GLASS, cap_bottom=False)
    for side in (-1, 1):
        for k in range(5):
            x = 6.0 - k * 4.0
            y = side * 3.63
            g.polygon([(x, y, 6.6), (x + 1.4, y, 6.6), (x + 1.4, y, 7.8), (x, y, 7.8)], GLASS, outward_from=(x, 0, 7))
    model.attach("ROOTTRANSFORM", windows)

    stripes = Mesh("HOUSECOLOR01", team)
    s = Builder(stripes, ShadeFn(ground=2.0, height=11.0, floor=0.8))
    for y0, y1 in ((-3.7, -3.62), (3.62, 3.7)):
        s.box((-12.0, y0, 8.2), (6.0, y1, 8.8), TEAM)
    s.box((-19.6, -1.65, 14.4), (-15.0, 1.65, 14.46), TEAM)
    model.attach("ROOTTRANSFORM", stripes)

    rotor(model, "PROPELLER01", FRONT_HUB, body, disc, phase=0.0)
    rotor(model, "PROPELLER02", REAR_HUB, body, disc, phase=math.pi / 3)
    model.add_spin("PROPELLER01", "z", revolutions=1.0)
    model.add_spin("PROPELLER02", "z", revolutions=-1.0)
    return model
