"""Modern directed-energy tank that replaces the art of the USA Microwave Tank.

GeneralsX @feature Claude 16/10/2026 The main battle tank's hull with a low turret carrying a
phased-array emitter panel on an elevating cradle, cooling radiators and a sensor mast. Bones
follow the Microwave Tank's Draw module: TURRET, WEAPON01/WEAPON02 (beam origin) and
PROJECTORGLOW09 for the emitter glow; treads are TREADSL/TREADSR from the shared hull.
"""

from geometry import Builder, Region, ShadeFn
from gx_mbt import TURRET_X, TURRET_Z, hull, turret_ring
from w3d import Material, Mesh, Model

CAMO = Region(0.0, 0.25, 1.0, 1.0, world_size=32.0)
DARK = Region(0.0, 0.0, 1.0, 0.25, world_size=12.0)
TEAM = Region(0, 0, 1, 1, world_size=8.0)

EMITTER_X = TURRET_X + 6.4
EMITTER_Z = TURRET_Z + 5.4


def build(name, body_texture, tread_texture, team_texture, glass_texture):
    model = Model(name)
    model.add_bone("TURRET", "ROOTTRANSFORM", (TURRET_X, 0, TURRET_Z))
    for bone in ("WEAPON01", "WEAPON02", "PROJECTORGLOW09"):
        model.add_bone(bone, "TURRET", (EMITTER_X + 0.6, 0, EMITTER_Z))

    body = Material("GXBody", body_texture, specular=(60, 60, 55), shininess=12.0)
    team = Material("GXTeam", team_texture)
    tread = Material("GXTread", tread_texture, scroll_mapper=True)
    glass = Material("GXGlass", glass_texture, specular=(200, 220, 255), shininess=50.0)
    hull(model, body, tread, team)

    turret = Mesh("TURRETBODY", body)
    t = Builder(turret, ShadeFn(ground=2.0, height=9.0, floor=0.7))
    tx = TURRET_X
    base = [(6.0, -4.0), (6.0, 4.0), (3.6, 6.0), (-8.6, 6.0), (-10.0, 4.6), (-10.0, -4.6), (-8.6, -6.0), (3.6, -6.0)]
    top = [(5.0, -3.6), (5.0, 3.6), (3.0, 5.2), (-8.0, 5.2), (-9.4, 4.0), (-9.4, -4.0), (-8.0, -5.2), (3.0, -5.2)]
    t.loft(turret_ring(base, TURRET_Z), turret_ring(top, TURRET_Z + 2.4), CAMO)
    # Elevating cradle arms either side of the emitter.
    for y0, y1 in ((-4.6, -3.8), (3.8, 4.6)):
        t.extrude_y([(tx + 1.0, TURRET_Z + 2.4), (tx + 5.0, TURRET_Z + 2.4), (EMITTER_X + 0.4, EMITTER_Z + 0.6),
                     (EMITTER_X - 1.6, EMITTER_Z + 1.4), (tx + 1.0, TURRET_Z + 4.4)], y0, y1, CAMO)
    # Emitter panel: a thick tilted slab, front face is the array (glass), back carries a power box.
    ex, ez = EMITTER_X, EMITTER_Z
    t.loft([(ex - 1.2, -3.7, ez - 3.0), (ex + 0.2, -3.7, ez - 3.0), (ex + 0.2, 3.7, ez - 3.0), (ex - 1.2, 3.7, ez - 3.0)],
           [(ex - 2.0, -3.7, ez + 3.0), (ex - 0.6, -3.7, ez + 3.0), (ex - 0.6, 3.7, ez + 3.0), (ex - 2.0, 3.7, ez + 3.0)], CAMO)
    t.box((ex - 4.0, -2.2, ez - 1.4), (ex - 1.4, 2.2, ez + 1.6), DARK)
    # Cooling radiators on the turret rear and a sensor mast.
    for y in (-3.2, 0.0, 3.2):
        t.box((tx - 9.2, y - 1.3, TURRET_Z + 2.4), (tx - 6.4, y + 1.3, TURRET_Z + 3.2), DARK)
    t.cylinder_z(tx - 4.0, -3.4, TURRET_Z + 2.4, TURRET_Z + 6.4, 0.25, 0.2, sides=6, region=DARK)
    t.box((tx - 4.8, -4.2, TURRET_Z + 6.4), (tx - 3.2, -2.6, TURRET_Z + 7.4), CAMO)
    model.attach("TURRET", turret)

    array = Mesh("EMITTER", glass)
    a = Builder(array, ShadeFn(ground=2.0, height=9.0, floor=0.95))
    a.polygon([(ex + 0.25, -3.4, ez - 2.7), (ex + 0.25, 3.4, ez - 2.7), (ex - 0.55, 3.4, ez + 2.7), (ex - 0.55, -3.4, ez + 2.7)],
              Region(0, 0, 1, 1, world_size=2.0), outward_from=(ex - 3.0, 0, ez))
    model.attach("TURRET", array)

    team_turret = Mesh("HOUSECOLOR01", team)
    tt = Builder(team_turret, ShadeFn(ground=2.0, height=9.0, floor=0.75))
    for y0, y1 in ((-5.25, -5.2), (5.2, 5.25)):
        tt.box((tx - 7.0, y0, TURRET_Z + 0.8), (tx + 1.0, y1, TURRET_Z + 1.6), TEAM)
    model.attach("TURRET", team_turret)
    return model
