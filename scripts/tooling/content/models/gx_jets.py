"""Modern USA combat aircraft that replace the art of the retail USA jets.

GeneralsX @feature Claude 16/10/2026 Three airframes from one set of parts:
- "f35": single-engine stealth multirole fighter with canted twin tails, in place of the Raptor.
- "wing": tailless flying-wing strike aircraft, in place of the Stealth Fighter.
- "hyper": long arrowhead hypersonic bomber with twin tails, in place of the Aurora.
Bones follow the retail jet Draw modules: ENGINE01/02 (exhaust, lens flare and damage smoke),
WINGTIP01/02 (contrails), SMOKE01, WEAPONA01-04 (launch points) and the afterburner sub-objects
(BURNERFX01/02 or BURNERFX03/04) that the JETAFTERBURNER states show and hide.
"""

from geometry import Builder, Region, ShadeFn, centroid
from gx_apache import loft_x
from w3d import ADDITIVE, MESH_FLAG_TWO_SIDED, Material, Mesh, Model

CAMO = Region(0.0, 0.25, 1.0, 1.0, world_size=30.0)
DARK = Region(0.0, 0.0, 1.0, 0.25, world_size=10.0)
GLASS = Region(0, 0, 1, 1, world_size=6.0)
TEAM = Region(0, 0, 1, 1, world_size=8.0)


def plate(builder, outline, z0, z1, region):
    """Convex planform outline (x, y) given a thickness from z0 to z1 (wings, tails, stabilisers)."""
    builder.loft([(x, y, z0) for x, y in outline], [(x, y, z1) for x, y in outline], region)


def fin(builder, root, tip, thickness, region):
    """Tail fin: root and tip are (x_front, x_back, y, z) chords; the fin may lean sideways."""
    rf, rb, ry, rz = root
    tf, tb, ty, tz = tip
    t = thickness / 2
    a = [(rf, ry - t, rz), (rb, ry - t, rz), (tb, ty - t, tz), (tf, ty - t, tz)]
    b = [(rf, ry + t, rz), (rb, ry + t, rz), (tb, ty + t, tz), (tf, ty + t, tz)]
    c = centroid(a + b)
    builder.polygon(a, region, outward_from=c)
    builder.polygon(b, region, outward_from=c)
    for i in range(4):
        j = (i + 1) % 4
        builder.polygon([a[i], a[j], b[j], b[i]], region, outward_from=c)


def burner(model, bone, material, origin, length, radius):
    """Afterburner plume: additive cone behind a nozzle, on its own bone so states can show/hide it."""
    mesh = Mesh(bone, material, attributes=MESH_FLAG_TWO_SIDED)
    x, y, z = origin
    b = Builder(mesh, shade=lambda q, n: (255, 255, 255, 255),
                uv_fn=lambda q: (min(1.0, max(0.0, (x - q[0]) / length)), 0.5 + (q[1] - y + q[2] - z) / (4 * radius)))
    b.cylinder_x(x - length, x, y, z, 0.05, radius, sides=10, caps=False)
    model.attach(bone, mesh)


def build(name, body_texture, team_texture, glass_texture, flash_texture, variant="f35"):
    model = Model(name)
    body = Material("GXBody", body_texture, specular=(90, 90, 90), shininess=20.0)
    glass = Material("GXGlass", glass_texture, specular=(220, 200, 120), shininess=50.0)
    team = Material("GXTeam", team_texture)
    flame = Material("GXFlash", flash_texture, shader=ADDITIVE, emissive=(255, 255, 255))

    hull = Mesh("FUSELAGE", body)
    b = Builder(hull, ShadeFn(ground=-3.0, height=6.0, floor=0.75))
    canopy = Mesh("CANOPY", glass)
    g = Builder(canopy, ShadeFn(ground=-3.0, height=6.0, floor=0.95))
    stripes = Mesh("HOUSECOLOR01", team)
    s = Builder(stripes, ShadeFn(ground=-3.0, height=6.0, floor=0.85))

    if variant == "f35":
        loft_x(b, [(18.0, 0.2, 0.9, 1.3), (15.0, 1.1, 0.4, 2.2), (10.0, 2.0, 0.0, 2.8), (4.0, 3.4, -0.2, 2.6),
                   (-6.0, 3.6, -0.2, 2.4), (-12.0, 2.6, 0.0, 2.2), (-15.0, 1.5, 0.4, 1.9)], CAMO)
        b.cylinder_x(-17.0, -15.0, 0.0, 1.15, 1.25, 1.05, sides=12, region=DARK)
        g.loft([(13.0, -0.9, 2.3), (7.0, -1.3, 2.5), (7.0, 1.3, 2.5), (13.0, 0.9, 2.3)],
               [(12.0, -0.4, 3.0), (7.5, -0.6, 3.5), (7.5, 0.6, 3.5), (12.0, 0.4, 3.0)], GLASS, cap_bottom=False)
        for side in (-1, 1):
            plate(b, [(4.0, side * 3.4), (-7.0, side * 13.0), (-10.0, side * 13.0), (-9.0, side * 3.4)], 0.9, 1.3, CAMO)
            plate(b, [(-11.0, side * 2.4), (-15.0, side * 7.2), (-17.0, side * 7.2), (-16.0, side * 2.0)], 1.0, 1.3, CAMO)
            fin(b, (-9.0, -14.5, side * 2.2, 2.2), (-13.0, -16.0, side * 3.6, 7.0), 0.3, CAMO)
            s.loft([(-1.0, side * 7.0, 1.31), (-3.0, side * 10.0, 1.31), (-4.6, side * 10.0, 1.31), (-3.2, side * 7.0, 1.31)],
                   [(-1.0, side * 7.0, 1.36), (-3.0, side * 10.0, 1.36), (-4.6, side * 10.0, 1.36), (-3.2, side * 7.0, 1.36)], TEAM)
        nozzles = [(-17.0, -0.45, 1.15), (-17.0, 0.45, 1.15)]
        wingtips = [(-9.0, -13.0, 1.1), (-9.0, 13.0, 1.1)]
        burners = ("BURNERFX01", "BURNERFX02")
        weapons = [(-1.0, -6.0, 0.4), (-1.0, 6.0, 0.4), (0.0, -2.0, -0.4), (0.0, 2.0, -0.4)]
        smoke = (-6.0, 0.0, 2.6)
    elif variant == "wing":
        # Flying wing: a lifting centre body and two swept outer panels, all low and flat.
        plate(b, [(14.0, 0.0), (2.0, 7.0), (-6.0, 6.0), (-8.0, 0.0), (-6.0, -6.0), (2.0, -7.0)], 0.0, 1.0, CAMO)
        loft_x(b, [(12.0, 0.6, 0.6, 1.4), (8.0, 2.4, 0.4, 2.4), (0.0, 3.6, 0.3, 2.6), (-6.0, 2.6, 0.4, 1.8)], CAMO)
        for side in (-1, 1):
            plate(b, [(2.0, side * 7.0), (-12.0, side * 21.0), (-14.0, side * 19.5), (-6.0, side * 6.0)], 0.35, 0.85, CAMO)
            plate(b, [(-6.0, side * 6.0), (-14.0, side * 19.5), (-11.0, side * 10.0), (-10.0, side * 6.0)], 0.35, 0.8, CAMO)
            b.loft([(-1.0, side * 2.0, 1.8), (-6.0, side * 1.6, 1.6), (-6.0, side * 3.6, 1.4), (-1.0, side * 3.2, 1.6)],
                   [(-2.0, side * 2.2, 2.4), (-6.0, side * 2.0, 2.0), (-6.0, side * 3.2, 1.8), (-2.0, side * 3.0, 2.0)], DARK)
            s.loft([(0.0, side * 9.0, 0.86), (-6.0, side * 15.0, 0.86), (-7.6, side * 14.0, 0.86), (-2.0, side * 8.4, 0.86)],
                   [(0.0, side * 9.0, 0.9), (-6.0, side * 15.0, 0.9), (-7.6, side * 14.0, 0.9), (-2.0, side * 8.4, 0.9)], TEAM)
        g.loft([(10.0, -0.9, 2.0), (6.0, -1.4, 2.4), (6.0, 1.4, 2.4), (10.0, 0.9, 2.0)],
               [(9.4, -0.5, 2.4), (6.4, -0.8, 2.8), (6.4, 0.8, 2.8), (9.4, 0.5, 2.4)], GLASS, cap_bottom=False)
        nozzles = [(-8.6, -2.6, 1.0), (-8.6, 2.6, 1.0)]
        wingtips = [(-13.0, -20.5, 0.6), (-13.0, 20.5, 0.6)]
        burners = ("BURNERFX03", "BURNERFX04")
        weapons = [(-1.0, -1.5, -0.2), (-1.0, 1.5, -0.2), (-2.0, -4.0, -0.2), (-2.0, 4.0, -0.2)]
        smoke = (-4.0, 0.0, 2.2)
    else:
        # Hypersonic arrowhead: long chined forebody, cropped delta, twin tails and big engine bays.
        loft_x(b, [(26.0, 0.2, 1.0, 1.3), (20.0, 1.4, 0.4, 2.2), (12.0, 2.6, 0.0, 2.8), (0.0, 3.6, -0.4, 2.8),
                   (-14.0, 3.8, -0.4, 2.6), (-20.0, 3.2, 0.0, 2.2)], CAMO)
        for side in (-1, 1):
            plate(b, [(10.0, side * 3.0), (-14.0, side * 15.0), (-20.0, side * 15.0), (-20.0, side * 3.0)], 0.6, 1.2, CAMO)
            fin(b, (-12.0, -19.5, side * 5.0, 1.2), (-17.5, -21.0, side * 6.5, 7.5), 0.35, CAMO)
            b.cylinder_x(-21.0, -6.0, side * 2.6, -0.2, 1.4, 1.2, sides=10, region=DARK)
            s.loft([(-4.0, side * 8.0, 1.21), (-10.0, side * 12.6, 1.21), (-14.0, side * 12.6, 1.21), (-10.0, side * 8.0, 1.21)],
                   [(-4.0, side * 8.0, 1.26), (-10.0, side * 12.6, 1.26), (-14.0, side * 12.6, 1.26), (-10.0, side * 8.0, 1.26)], TEAM)
        g.loft([(19.0, -0.9, 2.3), (14.0, -1.3, 2.7), (14.0, 1.3, 2.7), (19.0, 0.9, 2.3)],
               [(18.2, -0.4, 2.8), (14.5, -0.6, 3.2), (14.5, 0.6, 3.2), (18.2, 0.4, 2.8)], GLASS, cap_bottom=False)
        nozzles = [(-21.0, -2.6, -0.2), (-21.0, 2.6, -0.2)]
        wingtips = [(-20.0, -15.0, 0.9), (-20.0, 15.0, 0.9)]
        burners = ("BURNERFX03", "BURNERFX04")
        weapons = [(-4.0, -1.2, -0.5), (-4.0, 1.2, -0.5), (-6.0, -1.2, -0.5), (-6.0, 1.2, -0.5)]
        smoke = (-10.0, 0.0, 2.6)

    for i, pos in enumerate(nozzles, 1):
        model.add_bone(f"ENGINE{i:02d}", "ROOTTRANSFORM", pos)
    for i, pos in enumerate(wingtips, 1):
        model.add_bone(f"WINGTIP{i:02d}", "ROOTTRANSFORM", pos)
    for i, pos in enumerate(weapons, 1):
        model.add_bone(f"WEAPONA{i:02d}", "ROOTTRANSFORM", pos)
    model.add_bone("SMOKE01", "ROOTTRANSFORM", smoke)
    for bone, pos in zip(burners, nozzles):
        model.add_bone(bone, "ROOTTRANSFORM", pos)

    model.attach("ROOTTRANSFORM", hull)
    model.attach("ROOTTRANSFORM", canopy)
    model.attach("ROOTTRANSFORM", stripes)
    for bone, pos in zip(burners, nozzles):
        burner(model, bone, flame, pos, length=7.0 if variant == "hyper" else 5.0, radius=0.9)
    return model
