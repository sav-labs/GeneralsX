"""Modern USA base structures that replace the art of the retail USA buildings.

GeneralsX @feature Claude 16/10/2026 Power plant, barracks, war factory, supply center and command
center in a present-day US military look: precast concrete and ribbed metal halls, HESCO barriers,
solar panels, satellite dishes and team-colour bands. Each fits inside the retail footprint
(GeometryMajorRadius along +X, the front where units leave, GeometryMinorRadius along Y) so selection,
pathing and exits keep matching what is drawn.

Every model carries the particle bones the retail Draw modules name (SMOKE01, FIRE01, SPARKS01 ...) so
damage smoke, fire and sparks still appear. Logic bones (docks, exits) stay those of the retail model:
ArtRemap only changes what is drawn. Variants: "" intact, "D" scorched paint, "E" rubble (the same
building slumped to a fraction of its height, scorched, with debris around it).
"""

import math

from geometry import Builder, Region, ShadeFn
from w3d import ADDITIVE, MESH_FLAG_HIDDEN, MESH_FLAG_TWO_SIDED, Material, Mesh, Model

WALL = Region(0.0, 0.5, 1.0, 1.0, world_size=20.0)
ROOF = Region(0.0, 0.25, 1.0, 0.5, world_size=24.0)
METAL = Region(0.0, 0.0, 1.0, 0.25, world_size=10.0)
GLASS = Region(0, 0, 1, 1, world_size=8.0)
TEAM = Region(0, 0, 1, 1, world_size=8.0)

# Particle bones used by the retail USA building Draw modules (damage smoke, fire, sparks, steam).
FX_BONES = (
    [f"SMOKE{i:02d}" for i in range(1, 8)] + [f"FIRE{i:02d}" for i in range(1, 8)]
    + [f"SPARKS{i:02d}" for i in range(1, 12)] + [f"SPARK{i:02d}" for i in range(1, 8)]
    + [f"SMOKES{i:02d}" for i in range(1, 3)] + [f"SPARKSS{i:02d}" for i in range(1, 7)]
    + ["SMOKEM01", "SPARKSM01", "SPARKSM02", "STEAM01", "STEAM02", "STEAMM01", "STEAMS01", "DUST01",
       "FLAME01", "FLAME02", "PIT", "PIT01", "FXBONE01", "FXBONE02", "FXBONE03"]
)


class Kit:
    """Builders for the materials of one structure, plus the spots particle bones are spread over."""

    def __init__(self, name, wall_texture, team_texture, glass_texture, height):
        self.model = Model(name)
        shade = ShadeFn(ground=0.0, height=height, floor=0.72)
        self.body = Mesh("BODY", Material("GXBuilding", wall_texture, specular=(40, 40, 40), shininess=8.0))
        self.glass = Mesh("WINDOWS", Material("GXGlass", glass_texture, specular=(200, 200, 200), shininess=40.0))
        self.team = Mesh("HOUSECOLOR01", Material("GXTeam", team_texture))
        self.b = Builder(self.body, shade)
        self.g = Builder(self.glass, ShadeFn(ground=0.0, height=height, floor=0.9))
        self.t = Builder(self.team, ShadeFn(ground=0.0, height=height, floor=0.85))
        self.fx_spots = []

    # --- shapes -------------------------------------------------------------------------------
    def block(self, x0, y0, x1, y1, z0, z1, storey=10.0, region=WALL, roof=ROOF):
        """Walls in storey-high bands (each band restarts the wall texture, so tall walls keep their
        panel scale) and a flat roof."""
        c = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
        bands = max(1, round((z1 - z0) / storey))
        for k in range(bands):
            za = z0 + (z1 - z0) * k / bands
            zb = z0 + (z1 - z0) * (k + 1) / bands
            for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
                self.b.polygon([(a[0], a[1], za), (b[0], b[1], za), (b[0], b[1], zb), (a[0], a[1], zb)], region, outward_from=c)
        self.b.polygon([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], roof, outward_from=c)
        self.fx_spots.append((x0, y0, x1, y1, z1))

    def parapet(self, x0, y0, x1, y1, z, h=1.0, t=0.6):
        for lo, hi in (((x0, y0, z), (x1, y0 + t, z + h)), ((x0, y1 - t, z), (x1, y1, z + h)),
                       ((x0, y0 + t, z), (x0 + t, y1 - t, z + h)), ((x1 - t, y0 + t, z), (x1, y1 - t, z + h))):
            self.b.box(lo, hi, WALL)

    def pad(self, x0, y0, x1, y1, h=0.8):
        self.b.box((x0, y0, 0.0), (x1, y1, h), ROOF)

    def ac_unit(self, x, y, z):
        self.b.box((x - 1.6, y - 1.2, z), (x + 1.6, y + 1.2, z + 1.6), METAL)
        self.b.cylinder_z(x, y, z + 1.6, z + 1.8, 0.9, 0.9, sides=10, region=METAL)

    def antenna(self, x, y, z, h, r=0.18):
        self.b.cylinder_z(x, y, z, z + h, r * 1.6, r, sides=6, region=METAL)

    def dish(self, x, y, z, r, facing=0.0, tilt=35.0):
        """Satellite dish on a short post, opening towards `facing` degrees, tipped up by `tilt`."""
        self.b.cylinder_z(x, y, z, z + r * 0.9, 0.3, 0.3, sides=6, region=METAL)
        f, t = math.radians(facing), math.radians(tilt)
        axis = (math.cos(f) * math.cos(t), math.sin(f) * math.cos(t), math.sin(t))
        side = (-math.sin(f), math.cos(f), 0.0)
        up = (axis[1] * side[2] - axis[2] * side[1], axis[2] * side[0] - axis[0] * side[2], axis[0] * side[1] - axis[1] * side[0])
        cx, cy, cz = x, y, z + r * 0.9 + r * 0.4

        def ring(depth, radius, n=12):
            return [(cx + axis[0] * depth + (side[0] * math.cos(a) + up[0] * math.sin(a)) * radius,
                     cy + axis[1] * depth + (side[1] * math.cos(a) + up[1] * math.sin(a)) * radius,
                     cz + axis[2] * depth + (side[2] * math.cos(a) + up[2] * math.sin(a)) * radius)
                    for a in (2 * math.pi * k / n for k in range(n))]
        self.b.loft(ring(-r * 0.25, r * 0.35), ring(0.0, r), WALL, cap_bottom=True, cap_top=True)

    def hesco(self, x0, y0, x1, y1, h=2.6, cell=2.6):
        """A line of filled barrier cells from (x0, y0) to (x1, y1)."""
        length = math.hypot(x1 - x0, y1 - y0)
        n = max(1, round(length / cell))
        for k in range(n):
            cx = x0 + (x1 - x0) * (k + 0.5) / n
            cy = y0 + (y1 - y0) * (k + 0.5) / n
            s = cell * 0.48
            self.b.box((cx - s, cy - s, 0.0), (cx + s, cy + s, h), METAL)

    def solar_rows(self, x0, y0, x1, y1, z, rows, tilt_h=1.2):
        depth = (x1 - x0) / rows
        for k in range(rows):
            xa = x0 + k * depth + depth * 0.15
            xb = x0 + (k + 1) * depth - depth * 0.15
            self.g.extrude_y([(xa, z + 0.4), (xb, z + 0.4 + tilt_h), (xb, z + 0.7 + tilt_h), (xa, z + 0.7)], y0, y1, GLASS)
            self.b.box((xa + 0.2, y0 + 0.5, z), (xa + 0.6, y1 - 0.5, z + 0.5), METAL)

    def window_band(self, x0, y0, x1, y1, z0, z1, inset=0.12):
        """Glass on the outside of a wall plane (axis-aligned), slightly proud of it."""
        if abs(x1 - x0) < 1e-6:
            c = (x0 - (1 if x0 > 0 else -1), (y0 + y1) / 2, (z0 + z1) / 2)
            x = x0 + (inset if x0 > 0 else -inset)
            self.g.polygon([(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)], GLASS, outward_from=c)
        else:
            c = ((x0 + x1) / 2, y0 - (1 if y0 > 0 else -1), (z0 + z1) / 2)
            y = y0 + (inset if y0 > 0 else -inset)
            self.g.polygon([(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)], GLASS, outward_from=c)

    def team_band(self, x0, y0, x1, y1, z0, z1, proud=0.1):
        """Team-colour stripe just outside a wall plane (axis-aligned)."""
        if abs(x1 - x0) < 1e-6:
            x = x0 + (proud if x0 > 0 else -proud)
            self.t.box((min(x0, x), y0, z0), (max(x0, x), y1, z1), TEAM)
        else:
            y = y0 + (proud if y0 > 0 else -proud)
            self.t.box((x0, min(y0, y), z0), (x1, max(y0, y), z1), TEAM)

    def door(self, x, y0, y1, z1, depth=0.3):
        """Dark roller door on a +X or -X wall."""
        s = 1 if x > 0 else -1
        self.b.box((min(x, x + s * depth), y0, 0.0), (max(x, x + s * depth), y1, z1), METAL)

    # --- finishing ----------------------------------------------------------------------------
    def finish(self, variant, steam=None, sparks=None, height=20.0):
        if variant == "E":
            debris = []
            for mesh in (self.body, self.glass, self.team):
                slump(mesh, height)
            for k, (x0, y0, x1, y1, _z) in enumerate(self.fx_spots[:6]):
                for j in range(5):
                    u = 0.5 + 0.45 * math.sin(k * 7.1 + j * 3.3)
                    v = 0.5 + 0.45 * math.cos(k * 5.3 + j * 2.1)
                    debris.append((x0 + (x1 - x0) * u, y0 + (y1 - y0) * v, 1.0 + (j % 3)))
            for x, y, s in debris:
                self.b.box((x - s, y - s * 0.7, 0.0), (x + s, y + s * 0.7, s * 0.8), METAL)
            # Smoke and fire rise from the heap, not from where the roofs were.
            self.fx_spots = [(x0, y0, x1, y1, 1.5 + (z - 1.5) * 0.3) for x0, y0, x1, y1, z in self.fx_spots]
            steam = steam and (steam[0], steam[1], 1.5 + (steam[2] - 1.5) * 0.3)
            sparks = sparks and [(x, y, 1.5 + (z - 1.5) * 0.3) for x, y, z in sparks]
        add_fx_bones(self.model, self.fx_spots, steam=steam, sparks=sparks)
        for mesh in (self.body, self.glass, self.team):
            if mesh.triangles:
                self.model.attach("ROOTTRANSFORM", mesh)
        return self.model


def slump(mesh, height):
    """Rubble: everything above the ground floor sinks to a broken fraction of its height. The factor
    is a smooth function of position, so corners shared by faces stay together."""
    out = []
    for x, y, z in mesh.positions:
        if z <= 1.5:
            out.append((x, y, z))
            continue
        k = 0.22 + 0.16 * (math.sin(x * 0.31 + y * 0.17) * 0.5 + 0.5) + 0.08 * math.sin(y * 0.53 - x * 0.11)
        out.append((x, y, 1.5 + (z - 1.5) * k))
    mesh.positions = out


def add_fx_bones(model, spots, steam=None, sparks=None):
    """Spread the retail particle bones over the roofs. steam/sparks pin the bones the intact building
    uses all the time (steam vents, arcing wires) to a fixed point."""
    pinned = {}
    if steam:
        for name in ("SMOKE02", "STEAM01", "STEAMM01", "STEAMS01"):
            pinned[name] = steam
    if sparks:
        for i, name in enumerate([f"SPARK{n:02d}" for n in range(1, 8)] + [f"SPARKS{n:02d}" for n in range(1, 12)]):
            pinned[name] = sparks[i % len(sparks)]
    for i, name in enumerate(FX_BONES):
        if name in pinned:
            pos = pinned[name]
        else:
            x0, y0, x1, y1, z = spots[i % len(spots)]
            u = 0.5 + 0.38 * math.sin(i * 2.399)
            v = 0.5 + 0.38 * math.cos(i * 1.711)
            pos = (x0 + (x1 - x0) * u, y0 + (y1 - y0) * v, z + 0.5)
        model.add_bone(name, "ROOTTRANSFORM", pos)


# ------------------------------------------------------------------------------------------------
def power_plant(name, wall, team, glass, variant=""):
    """Compact gas-turbine plant: generator hall with solar roof, cooling tower, exhaust stack and a
    transformer yard. Retail footprint 44 x 60, height 46."""
    k = Kit(name, wall, team, glass, height=40.0)
    k.pad(-21.5, -29.5, 21.5, 29.5)
    # Generator hall along the back.
    k.block(-20.0, -27.0, 4.0, 6.0, 0.8, 17.0)
    k.parapet(-20.0, -27.0, 4.0, 6.0, 17.0)
    k.solar_rows(-18.5, -25.5, 2.5, 4.5, 17.0, rows=4)
    k.window_band(4.0, -24.0, 4.0, 3.0, 9.0, 12.0)
    k.team_band(4.0, -26.0, 4.0, 5.0, 14.0, 15.4)
    k.door(4.0, -9.0, -3.0, 8.0)
    # Cooling tower: hyperboloid shell.
    cx, cy = 8.0, 17.0
    rings = [(0.8, 10.5), (10.0, 8.6), (20.0, 7.0), (28.0, 7.2), (34.0, 7.8)]
    for (z0, r0), (z1, r1) in zip(rings, rings[1:]):
        ring0 = [(cx + r0 * math.cos(a), cy + r0 * math.sin(a), z0) for a in (2 * math.pi * i / 20 for i in range(20))]
        ring1 = [(cx + r1 * math.cos(a), cy + r1 * math.sin(a), z1) for a in (2 * math.pi * i / 20 for i in range(20))]
        k.b.loft(ring0, ring1, WALL, cap_bottom=False, cap_top=(z1 == 34.0))
    k.t.cylinder_z(cx, cy, 30.5, 32.0, 7.55, 7.7, sides=20, region=TEAM)
    k.fx_spots.append((cx - 5, cy - 5, cx + 5, cy + 5, 34.0))
    # Exhaust stack with a team band and a service ring.
    k.b.cylinder_z(-14.0, 16.0, 0.8, 44.0, 2.6, 2.1, sides=14, region=METAL)
    k.t.cylinder_z(-14.0, 16.0, 38.0, 40.0, 2.3, 2.25, sides=14, region=TEAM)
    k.b.cylinder_z(-14.0, 16.0, 30.0, 30.6, 3.4, 3.4, sides=14, region=METAL)
    # Pipes from the hall to the tower.
    for z in (6.0, 9.0):
        k.b.cylinder_x(4.0, cx - 8.0, 8.0 + (z - 6.0), z, 0.9, sides=10, region=METAL)
    # Transformer yard at the front left with insulators and a fence line.
    for y in (-24.0, -16.0):
        k.b.box((9.0, y - 3.0, 0.8), (17.0, y + 3.0, 7.0), METAL)
        for j in range(3):
            k.b.cylinder_z(11.0 + j * 2.6, y, 7.0, 10.0, 0.35, 0.25, sides=6, region=WALL)
        k.fx_spots.append((9.0, y - 3.0, 17.0, y + 3.0, 7.0))
    for y in (-28.0, -4.0):
        k.b.box((7.0, y - 0.15, 0.8), (21.0, y + 0.15, 4.0), METAL)
    k.b.box((20.8, -28.0, 0.8), (21.1, -4.0, 4.0), METAL)
    k.ac_unit(-6.0, 3.0, 17.0)
    sparks = [(11.0, -24.0, 10.0), (16.2, -16.0, 10.0), (13.6, -24.0, 10.0)]
    return k.finish(variant, steam=(cx, cy, 34.5), sparks=sparks, height=40.0)


def barracks(name, wall, team, glass, variant=""):
    """Two-storey troop building with an entrance canopy, HESCO line, roof plant and a mast.
    Retail footprint 110 x 90, height 20; soldiers leave through the +X face at Y 0 and -25."""
    k = Kit(name, wall, team, glass, height=20.0)
    k.pad(-52.0, -42.0, 52.0, 42.0)
    # Main wing across the back and a side wing towards the front.
    k.block(-48.0, -38.0, 6.0, 38.0, 0.8, 17.0, storey=8.0)
    k.parapet(-48.0, -38.0, 6.0, 38.0, 17.0)
    k.block(6.0, 10.0, 34.0, 38.0, 0.8, 13.0, storey=6.5)
    k.parapet(6.0, 10.0, 34.0, 38.0, 13.0)
    # Front glass bands and the entrance canopy over the exits.
    for z0, z1 in ((3.0, 6.0), (11.0, 14.0)):
        k.window_band(6.0, -36.0, 6.0, 8.0, z0, z1)
        k.window_band(-46.0, -38.0, 4.0, -38.0, z0, z1)
        k.window_band(-46.0, 38.0, 4.0, 38.0, z0, z1)
    k.window_band(34.0, 12.0, 34.0, 36.0, 4.0, 9.0)
    k.b.box((6.0, -32.0, 7.0), (16.0, 4.0, 7.8), METAL)
    for y in (-31.0, -14.0, 3.0):
        k.b.cylinder_z(15.2, y, 0.8, 7.0, 0.35, 0.35, sides=8, region=METAL)
    k.door(6.0, -29.0, -21.0, 6.0)
    k.door(6.0, -4.0, 4.0, 6.0)
    k.team_band(6.0, -37.0, 6.0, 9.0, 15.0, 16.2)
    k.team_band(34.0, 11.0, 34.0, 37.0, 10.6, 11.6)
    # Roof plant, mast and flag pole.
    for x, y in ((-40.0, -28.0), (-40.0, -20.0), (-12.0, 24.0), (-4.0, 24.0)):
        k.ac_unit(x, y, 17.0)
    k.antenna(-30.0, 30.0, 17.0, 14.0)
    k.dish(-20.0, -30.0, 17.0, 3.2, facing=200.0)
    k.b.cylinder_z(44.0, 32.0, 0.8, 18.0, 0.2, 0.15, sides=6, region=METAL)
    k.t.box((44.2, 32.0, 14.6), (44.3, 37.0, 17.6), TEAM)
    # Barrier line along the front, leaving the exit lane open.
    k.hesco(40.0, -41.0, 40.0, -36.0)
    k.hesco(40.0, 10.0, 40.0, 30.0)
    k.hesco(-50.0, -41.0, 30.0, -41.0)
    return k.finish(variant, height=17.0)


def war_factory(name, wall, team, glass, variant=""):
    """Vehicle assembly hall with a barrel-vault roof, a wide roller door on the +X face where vehicles
    leave (Y around -27), an office annex and a gantry crane. Retail footprint 106 x 120, height 40."""
    k = Kit(name, wall, team, glass, height=34.0)
    k.pad(-50.0, -57.0, 50.0, 57.0)
    # Main hall: walls plus a vaulted roof lofted in segments.
    x0, x1, y0, y1, wall_h, crown = -44.0, 34.0, -48.0, -4.0, 20.0, 31.0
    k.block(x0, y0, x1, y1, 0.8, wall_h, storey=10.0)
    segs = 8
    yc, half = (y0 + y1) / 2, (y1 - y0) / 2
    arc = [(yc + half * math.cos(math.pi * i / segs), wall_h + (crown - wall_h) * math.sin(math.pi * i / segs)) for i in range(segs + 1)]
    for (ya, za), (yb, zb) in zip(arc, arc[1:]):
        k.b.polygon([(x0, ya, za), (x1, ya, za), (x1, yb, zb), (x0, yb, zb)], ROOF, outward_from=(0.0, yc, wall_h))
    for x in (x0, x1):
        gable = [(x, y, z) for y, z in arc]
        k.b.polygon(gable, WALL, outward_from=(0.0 if x == x1 else 10.0, yc, wall_h + 2))
    k.fx_spots.append((x0, y0 + 8, x1, y1 - 8, crown - 1.0))
    # Roller door where vehicles exit, with a team band above.
    k.door(x1, -40.0, -14.0, 17.0, depth=0.4)
    k.team_band(x1, -42.0, x1, -12.0, 18.0, 19.4, proud=0.5)
    # Office annex and a second, lower bay along +Y.
    k.block(-44.0, 2.0, 10.0, 52.0, 0.8, 14.0, storey=7.0)
    k.parapet(-44.0, 2.0, 10.0, 52.0, 14.0)
    k.window_band(10.0, 4.0, 10.0, 50.0, 8.0, 11.0)
    k.window_band(-42.0, 52.0, 8.0, 52.0, 8.0, 11.0)
    k.block(10.0, 14.0, 40.0, 52.0, 0.8, 11.0, storey=11.0)
    k.door(40.0, 20.0, 46.0, 9.0)
    k.team_band(40.0, 15.0, 40.0, 51.0, 9.6, 10.4)
    k.solar_rows(-40.0, 6.0, 6.0, 48.0, 14.0, rows=5)
    # Link between hall and annex.
    k.block(-30.0, -4.0, -10.0, 2.0, 0.8, 12.0, storey=12.0)
    # Gantry crane over the hall's front apron.
    for y in (-50.0, -6.0):
        k.b.box((38.0, y - 0.6, 0.8), (39.2, y + 0.6, 22.0), METAL)
    k.b.box((37.6, -51.0, 22.0), (39.6, -5.0, 23.6), METAL)
    k.b.box((38.0, -30.0, 18.0), (39.2, -27.0, 22.0), METAL)
    # Roof vents along the vault.
    for x in (-36.0, -22.0, -8.0, 6.0, 20.0):
        k.b.box((x - 1.5, yc - 1.5, crown - 0.4), (x + 1.5, yc + 1.5, crown + 1.4), METAL)
    k.hesco(46.0, -56.0, 46.0, -44.0)
    k.hesco(46.0, 2.0, 46.0, 12.0)
    return k.finish(variant, steam=(-22.0, yc, crown + 1.6), height=30.0)


def supply_center(name, wall, team, glass, variant=""):
    """Logistics depot: sawtooth-roof warehouse, loading docks, container stacks and a helipad on the
    +X side where supply trucks and helicopters come in. Retail footprint 88 x 90, height 24."""
    k = Kit(name, wall, team, glass, height=22.0)
    k.pad(-42.0, -43.0, 42.0, 43.0)
    # Warehouse with sawtooth roof lights.
    x0, x1, y0, y1, h = -40.0, 6.0, -40.0, 8.0, 12.0
    k.block(x0, y0, x1, y1, 0.8, h, storey=12.0)
    teeth = 5
    step = (x1 - x0) / teeth
    for i in range(teeth):
        xa, xb = x0 + i * step, x0 + (i + 1) * step
        k.b.extrude_y([(xa, h), (xb, h), (xa + 0.3, h + 5.0)], y0, y1, ROOF)
        k.g.polygon([(xa - 0.05, y0 + 0.5, h + 4.6), (xa - 0.05, y1 - 0.5, h + 4.6), (xa - 0.05, y1 - 0.5, h + 0.4), (xa - 0.05, y0 + 0.5, h + 0.4)],
                    GLASS, outward_from=(xa + 3.0, (y0 + y1) / 2, h + 2.0))
    k.fx_spots.append((x0, y0, x1, y1, h + 2.0))
    # Loading docks on the front face.
    for y in (-34.0, -24.0, -14.0, -4.0):
        k.door(x1, y - 3.5, y + 3.5, 8.0)
    k.b.box((x1, -39.0, 0.8), (x1 + 4.0, 7.0, 3.2), WALL)
    k.team_band(x1, -39.0, x1, 7.0, 9.4, 10.6)
    # Office with glazing at the back corner.
    k.block(-40.0, 8.0, -16.0, 30.0, 0.8, 16.0, storey=8.0)
    k.parapet(-40.0, 8.0, -16.0, 30.0, 16.0)
    k.window_band(-16.0, 10.0, -16.0, 28.0, 10.0, 13.6)
    k.window_band(-38.0, 30.0, -18.0, 30.0, 10.0, 13.6)
    k.dish(-28.0, 20.0, 16.0, 3.0, facing=160.0)
    k.antenna(-36.0, 26.0, 16.0, 10.0)
    # Container stacks.
    for i, (x, y, z) in enumerate([(-10.0, 18.0, 0.8), (-10.0, 24.0, 0.8), (-10.0, 18.0, 6.2), (2.0, 18.0, 0.8), (2.0, 24.0, 0.8), (2.0, 30.0, 0.8),
                                   (-10.0, 36.0, 0.8), (2.0, 36.0, 0.8), (2.0, 24.0, 6.2)]):
        k.b.box((x - 5.8, y - 2.6, z), (x + 5.8, y + 2.6, z + 5.4), METAL)
        if i % 3 == 0:
            k.t.box((x - 5.9, y - 2.7, z + 4.2), (x + 5.9, y + 2.7, z + 4.9), TEAM)
        k.fx_spots.append((x - 5.0, y - 2.0, x + 5.0, y + 2.0, z + 5.4))
    # Helipad with a team ring and a light mast.
    hx, hy = 26.0, 22.0
    k.b.cylinder_z(hx, hy, 0.8, 1.6, 13.0, 13.0, sides=24, region=ROOF)
    k.t.cylinder_z(hx, hy, 1.6, 1.7, 9.0, 9.0, sides=24, region=TEAM)
    k.b.cylinder_z(hx, hy, 1.7, 1.8, 7.8, 7.8, sides=24, region=ROOF)
    k.b.cylinder_z(40.0, 40.0, 0.8, 14.0, 0.3, 0.2, sides=6, region=METAL)
    k.hesco(40.0, -42.0, 40.0, -10.0)
    return k.finish(variant, height=16.0)


def command_center(name, wall, team, glass, variant=""):
    """Headquarters: stepped command block with a glass operations floor, radar dome, antenna mast,
    satellite dishes and a rooftop helipad; vehicle bay on the +X face. Retail footprint 120 x 140,
    height 49."""
    k = Kit(name, wall, team, glass, height=42.0)
    k.pad(-57.0, -67.0, 57.0, 67.0)
    # Podium.
    k.block(-50.0, -60.0, 40.0, 60.0, 0.8, 12.0, storey=11.0)
    k.parapet(-50.0, -60.0, 40.0, 60.0, 12.0)
    k.window_band(40.0, -56.0, 40.0, -10.0, 5.0, 9.0)
    k.window_band(40.0, 10.0, 40.0, 56.0, 5.0, 9.0)
    k.door(40.0, -8.0, 8.0, 9.0)
    k.team_band(40.0, -58.0, 40.0, 58.0, 10.0, 11.2)
    # Command block with a glass operations floor.
    k.block(-42.0, -40.0, 20.0, 40.0, 12.0, 26.0, storey=14.0)
    k.window_band(20.0, -38.0, 20.0, 38.0, 18.0, 23.0)
    k.window_band(-40.0, -40.0, 18.0, -40.0, 18.0, 23.0)
    k.window_band(-40.0, 40.0, 18.0, 40.0, 18.0, 23.0)
    k.block(-42.0, -40.0, 20.0, 40.0, 26.0, 30.0, storey=4.0, region=WALL)
    k.parapet(-42.0, -40.0, 20.0, 40.0, 30.0)
    k.team_band(20.0, -39.0, 20.0, 39.0, 27.0, 28.4)
    # Top tower with the radar dome.
    k.block(-34.0, -14.0, -6.0, 14.0, 30.0, 38.0, storey=8.0)
    k.window_band(-6.0, -12.0, -6.0, 12.0, 33.0, 36.0)
    dome = [(-20.0 + 8.0 * math.cos(a) * math.cos(e), 8.0 * math.sin(a) * math.cos(e), 38.0 + 8.0 * math.sin(e))
            for e in (0.0, 0.5, 1.0, 1.35) for a in (2 * math.pi * i / 16 for i in range(16))]
    for r in range(3):
        k.b.loft(dome[r * 16:(r + 1) * 16], dome[(r + 1) * 16:(r + 2) * 16], WALL, cap_bottom=False, cap_top=(r == 2))
    k.fx_spots.append((-34.0, -14.0, -6.0, 14.0, 38.0))
    # Antenna mast, dishes, roof plant.
    k.antenna(-40.0, 36.0, 30.0, 18.0, r=0.3)
    k.antenna(-40.0, -36.0, 30.0, 12.0)
    k.dish(8.0, -30.0, 30.0, 4.0, facing=300.0)
    k.dish(8.0, 30.0, 30.0, 3.2, facing=60.0)
    for x, y in ((-30.0, -30.0), (-22.0, -30.0), (-30.0, 30.0)):
        k.ac_unit(x, y, 30.0)
    # Helipad on the podium in front of the command block.
    k.b.cylinder_z(30.0, 36.0, 12.0, 12.4, 8.0, 8.0, sides=20, region=ROOF)
    k.t.cylinder_z(30.0, 36.0, 12.4, 12.5, 5.6, 5.6, sides=20, region=TEAM)
    k.b.cylinder_z(30.0, 36.0, 12.5, 12.6, 4.8, 4.8, sides=20, region=ROOF)
    # Perimeter barriers at the front corners.
    k.hesco(52.0, -66.0, 52.0, -30.0)
    k.hesco(52.0, 30.0, 52.0, 66.0)
    return k.finish(variant, height=38.0)


def turret_mesh(k, bone, name):
    """A body-material mesh that turns with a turret bone (authored in model space)."""
    mesh = Mesh(name, k.body.material)
    return mesh, Builder(mesh, ShadeFn(ground=0.0, height=14.0, floor=0.75))


def patriot(name, wall, team, glass, variant=""):
    """Modern air-defence launcher: four sealed missile canisters on a turntable over a concrete pad, with
    a power unit and a fire-control cabin at the back. Retail footprint is a 12 radius cylinder, height
    14; the turret is TURRET01 with the canisters on TURRETEL and the missiles leaving from WEAPONA."""
    k = Kit(name, wall, team, glass, height=10.0)
    k.model.add_bone("TURRET01", "ROOTTRANSFORM", (0.0, 0.0, 1.2))
    k.model.add_bone("TURRETEL", "TURRET01", (0.0, 0.0, 4.2))
    k.model.add_bone("WEAPONA", "TURRETEL", (5.2, 0.0, 4.8))
    k.b.cylinder_z(0.0, 0.0, 0.0, 0.8, 11.0, 11.0, sides=16, region=ROOF)
    k.block(-10.0, -7.0, -6.6, -1.0, 0.8, 4.4, storey=4.0)
    k.block(-9.4, 1.0, -6.4, 6.0, 0.8, 3.2, storey=3.0, region=METAL)
    k.antenna(-8.2, -4.0, 4.4, 6.0)
    k.window_band(-6.6, -6.4, -6.6, -1.6, 2.4, 3.6)
    k.team_band(-10.0, -7.0, -6.6, -7.0, 3.4, 4.0)
    for a in range(0, 360, 90):
        r = math.radians(a + 45)
        k.hesco(10.0 * math.cos(r) - 2.0 * math.sin(r), 10.0 * math.sin(r) + 2.0 * math.cos(r),
                10.0 * math.cos(r) + 2.0 * math.sin(r), 10.0 * math.sin(r) - 2.0 * math.cos(r), h=1.8, cell=2.0)
    if variant != "E":
        base, b = turret_mesh(k, "TURRET01", "TURRET01")
        b.cylinder_z(0.0, 0.0, 0.8, 2.0, 3.4, 3.0, sides=14, region=METAL)
        for y0, y1 in ((-2.6, -2.0), (2.0, 2.6)):
            b.box((-1.2, y0, 2.0), (1.2, y1, 4.8), WALL)
        k.model.attach("TURRET01", base)
        pack, c = turret_mesh(k, "TURRETEL", "TURRETEL")
        for y in (-0.95, 0.95):
            for z in (3.4, 5.3):
                c.box((-4.8, y - 0.9, z), (5.0, y + 0.9, z + 1.8), WALL)
                c.box((5.0, y - 0.75, z + 0.15), (5.2, y + 0.75, z + 1.65), METAL)
        c.box((-5.2, -2.0, 3.2), (-4.8, 2.0, 7.4), METAL)
        k.model.attach("TURRETEL", pack)
        stripe = Mesh("HOUSECOLOR02", k.team.material)
        t = Builder(stripe, ShadeFn(ground=0.0, height=14.0, floor=0.85))
        for y0, y1 in ((-1.92, -1.86), (1.86, 1.92)):
            t.box((-3.0, y0, 5.1), (3.0, y1, 5.6), TEAM)
        k.model.attach("TURRETEL", stripe)
    return k.finish(variant, height=4.4)


def fire_base(name, wall, team, glass, variant=""):
    """Hardened fire base: a squat concrete bunker with firing slits for the garrison, ringed by HESCO,
    with a 155 mm howitzer turret on the roof. Retail footprint 52 x 52, height 15; the gun is TURRET01 >
    TURRETEL > BARREL (recoil) > MUZZLE01 and the MUZZLEFX flash; STATION01-04 are the garrison posts."""
    k = Kit(name, wall, team, glass, height=12.0)
    k.model.add_bone("TURRET01", "ROOTTRANSFORM", (0.0, 0.0, 7.2))
    k.model.add_bone("TURRETEL", "TURRET01", (2.4, 0.0, 9.4))
    k.model.add_bone("BARREL", "TURRETEL", (3.8, 0.0, 9.4))
    k.model.add_bone("MUZZLE01", "BARREL", (21.0, 0.0, 9.4))
    k.model.add_bone("MUZZLEFX", "BARREL", (21.0, 0.0, 9.4))
    for i, (x, y) in enumerate(((16.0, 16.0), (16.0, -16.0), (-16.0, -16.0), (-16.0, 16.0)), 1):
        k.model.add_bone(f"STATION{i:02d}", "ROOTTRANSFORM", (x, y, 7.6))
    k.pad(-25.0, -25.0, 25.0, 25.0)
    # Bunker with sloped earth-cover walls and a flat roof deck.
    k.b.loft([(-20.0, -20.0, 0.8), (20.0, -20.0, 0.8), (20.0, 20.0, 0.8), (-20.0, 20.0, 0.8)],
             [(-17.0, -17.0, 6.4), (17.0, -17.0, 6.4), (17.0, 17.0, 6.4), (-17.0, 17.0, 6.4)], WALL, cap_bottom=False)
    k.fx_spots.append((-17.0, -17.0, 17.0, 17.0, 6.4))
    k.parapet(-17.0, -17.0, 17.0, 17.0, 6.4, h=1.2, t=0.8)
    # Firing slits, one pair per side, and an entrance on the back.
    for a in range(4):
        r = math.radians(a * 90)
        ca, sa = round(math.cos(r)), round(math.sin(r))
        for off in (-8.0, 8.0):
            cx, cy = 18.4 * ca - off * sa, 18.4 * sa + off * ca
            px, py = -sa * 2.4, ca * 2.4
            k.g.polygon([(cx - px + ca * 0.05, cy - py + sa * 0.05, 3.6), (cx + px + ca * 0.05, cy + py + sa * 0.05, 3.6),
                         (cx + px - ca * 0.4, cy + py - sa * 0.4, 4.6), (cx - px - ca * 0.4, cy - py - sa * 0.4, 4.6)],
                        GLASS, outward_from=(0.0, 0.0, 3.0))
    k.door(-20.6, -3.0, 3.0, 3.6, depth=0.6)
    k.team_band(-17.0, -17.8, 17.0, -17.8, 7.0, 7.6, proud=0.0)
    k.team_band(-17.0, 17.8, 17.0, 17.8, 7.0, 7.6, proud=0.0)
    for x, y in ((-12.0, 12.0), (-12.0, -12.0)):
        k.ac_unit(x, y, 6.4)
    k.antenna(-14.0, 0.0, 6.4, 9.0)
    k.hesco(-24.0, -24.0, 24.0, -24.0)
    k.hesco(-24.0, 24.0, 24.0, 24.0)
    k.hesco(24.0, -21.4, 24.0, 21.4)
    k.hesco(-24.0, -21.4, -24.0, -6.0)
    k.hesco(-24.0, 6.0, -24.0, 21.4)
    if variant != "E":
        house, h = turret_mesh(k, "TURRET01", "TURRET01")
        h.cylinder_z(0.0, 0.0, 6.4, 7.4, 6.0, 6.0, sides=16, region=METAL)
        h.loft([(-6.0, -4.4, 7.4), (3.6, -4.4, 7.4), (3.6, 4.4, 7.4), (-6.0, 4.4, 7.4)],
               [(-5.6, -3.8, 11.2), (1.6, -3.8, 11.2), (1.6, 3.8, 11.2), (-5.6, 3.8, 11.2)], WALL)
        h.box((-7.4, -3.4, 7.8), (-6.0, 3.4, 10.4), METAL)
        k.model.attach("TURRET01", house)
        cradle, c = turret_mesh(k, "TURRETEL", "TURRETEL")
        c.box((1.6, -1.6, 8.2), (4.0, 1.6, 10.6), METAL)
        k.model.attach("TURRETEL", cradle)
        gun, g = turret_mesh(k, "BARREL", "BARREL")
        g.cylinder_x(3.8, 9.0, 0.0, 9.4, 0.85, 0.75, sides=12, region=METAL)
        g.cylinder_x(9.0, 20.0, 0.0, 9.4, 0.5, 0.42, sides=12, region=METAL, caps=False)
        g.cylinder_x(20.0, 21.0, 0.0, 9.4, 0.75, 0.75, sides=12, region=METAL)
        k.model.attach("BARREL", gun)
        stripe = Mesh("HOUSECOLOR02", k.team.material)
        t = Builder(stripe, ShadeFn(ground=0.0, height=14.0, floor=0.85))
        for y0, y1 in ((-4.5, -4.42), (4.42, 4.5)):
            t.box((-4.6, y0, 8.4), (2.4, y1, 9.2), TEAM)
        k.model.attach("TURRET01", stripe)
        flash = Mesh("MUZZLEFX", Material("GXFlash", "gxflash.tga", shader=ADDITIVE, emissive=(255, 255, 255)),
                     attributes=MESH_FLAG_HIDDEN | MESH_FLAG_TWO_SIDED)
        f = Builder(flash, shade=lambda q, n: (255, 255, 255, 255), uv_fn=lambda q: ((q[0] - 21.0) / 6.0, (q[1] + q[2] - 9.4 + 2.0) / 4.0))
        f.polygon([(21.0, -2.0, 9.4), (27.0, -2.0, 9.4), (27.0, 2.0, 9.4), (21.0, 2.0, 9.4)])
        f.polygon([(21.0, 0.0, 7.4), (27.0, 0.0, 7.4), (27.0, 0.0, 11.4), (21.0, 0.0, 11.4)])
        k.model.attach("MUZZLEFX", flash)
    return k.finish(variant, height=6.4)


def supply_drop_zone(name, wall, team, glass, variant=""):
    """Airdrop landing zone: a marked concrete pad with a team-colour drop cross, an operations
    container, stacks of netted cargo pallets, light masts and a smoke marker on FLARE01. Retail
    footprint 54 x 54, height 9."""
    k = Kit(name, wall, team, glass, height=9.0)
    k.model.add_bone("FLARE01", "ROOTTRANSFORM", (18.0, 18.0, 1.0))
    k.pad(-26.0, -26.0, 26.0, 26.0, h=0.5)
    k.fx_spots.append((-14.0, -14.0, 14.0, 14.0, 0.6))
    # Drop cross and corner markers in team colour.
    k.t.box((-14.0, -2.0, 0.5), (14.0, 2.0, 0.56), TEAM)
    k.t.box((-2.0, -14.0, 0.5), (2.0, 14.0, 0.56), TEAM)
    for x, y in ((-20.0, -20.0), (-20.0, 20.0), (20.0, -20.0), (20.0, 20.0)):
        k.t.box((x - 1.6, y - 1.6, 0.5), (x + 1.6, y + 1.6, 0.56), TEAM)
    # Operations container with a window and an air conditioner, and a fuel bladder.
    k.block(-24.0, -24.0, -12.0, -18.0, 0.5, 6.0, storey=6.0, region=METAL)
    k.window_band(-22.0, -18.0, -15.0, -18.0, 2.6, 4.4)
    k.ac_unit(-16.0, -21.0, 6.0)
    k.antenna(-22.5, -22.5, 6.0, 7.0)
    k.b.box((-24.0, 13.0, 0.5), (-14.0, 23.0, 2.2), METAL)
    # Netted pallets waiting for pickup.
    for i, (x, y) in enumerate(((8.0, -22.0), (12.5, -22.0), (17.0, -22.0), (21.5, -22.0), (21.5, -17.5), (21.5, -13.0))):
        h = 2.4 + 1.4 * (i % 2)
        k.b.box((x - 1.9, y - 1.9, 0.5), (x + 1.9, y + 1.9, 0.9), METAL)
        k.b.box((x - 1.7, y - 1.7, 0.9), (x + 1.7, y + 1.7, 0.9 + h), WALL)
        k.fx_spots.append((x - 1.7, y - 1.7, x + 1.7, y + 1.7, 0.9 + h))
    # Light masts on two corners and a windsock pole.
    for x, y in ((24.5, 24.5), (-24.5, 24.5), (24.5, -24.5)):
        k.b.cylinder_z(x, y, 0.5, 9.0, 0.3, 0.2, sides=6, region=METAL)
        k.b.box((x - 0.9, y - 0.4, 9.0), (x + 0.9, y + 0.4, 9.8), METAL)
    k.b.cylinder_z(-6.0, 24.5, 0.5, 7.0, 0.15, 0.12, sides=6, region=METAL)
    k.t.box((-6.0, 24.4, 6.0), (-2.8, 24.6, 6.8), TEAM)
    return k.finish(variant, height=6.0)


def strategy_center(name, wall, team, glass, variant=""):
    """Joint operations centre: a three-storey glazed command block with a sensor tower, a dish farm,
    a helipad and a roof deck for the bombardment gun (drawn by its own model, ABGXSTRATGUN). Retail
    footprint 124 x 88, height 24."""
    k = Kit(name, wall, team, glass, height=24.0)
    k.pad(-60.0, -42.0, 60.0, 42.0)
    k.block(-44.0, -30.0, 20.0, 30.0, 0.8, 19.0, storey=6.2)
    k.parapet(-44.0, -30.0, 20.0, 30.0, 19.0)
    for z0, z1 in ((2.6, 5.0), (8.8, 11.2), (15.0, 17.4)):
        k.window_band(20.0, -28.0, 20.0, 28.0, z0, z1)
        k.window_band(-42.0, -30.0, 18.0, -30.0, z0, z1)
        k.window_band(-42.0, 30.0, 18.0, 30.0, z0, z1)
    k.team_band(20.0, -29.0, 20.0, 29.0, 6.2, 7.0)
    k.door(20.0, -6.0, 6.0, 5.0)
    # Sensor tower on the back corner.
    k.block(-42.0, 18.0, -32.0, 28.0, 19.0, 30.0, storey=5.5)
    k.antenna(-37.0, 23.0, 30.0, 12.0, r=0.3)
    k.dish(-37.0, 23.0, 30.0, 3.0, facing=0.0, tilt=50.0)
    # Roof plant and the gun deck in the middle of the roof.
    for x, y in ((-30.0, -22.0), (-22.0, -22.0), (0.0, 22.0), (8.0, 22.0)):
        k.ac_unit(x, y, 19.0)
    k.b.cylinder_z(-10.0, 0.0, 19.0, 20.0, 7.0, 7.0, sides=16, region=METAL)
    # Dish farm and helipad on the open front of the pad.
    for x, y, f in ((34.0, -32.0, 30.0), (46.0, -32.0, 10.0), (46.0, -18.0, 330.0)):
        k.b.box((x - 2.4, y - 2.4, 0.8), (x + 2.4, y + 2.4, 1.6), ROOF)
        k.dish(x, y, 1.6, 4.0, facing=f, tilt=40.0)
    k.b.cylinder_z(40.0, 24.0, 0.8, 1.2, 13.0, 13.0, sides=20, region=ROOF)
    k.t.box((36.0, 22.6, 1.2), (44.0, 25.4, 1.26), TEAM)
    k.t.box((36.0, 18.0, 1.2), (37.6, 30.0, 1.26), TEAM)
    k.t.box((42.4, 18.0, 1.2), (44.0, 30.0, 1.26), TEAM)
    k.fx_spots.append((30.0, -36.0, 52.0, 36.0, 1.2))
    k.hesco(58.0, -42.0, 58.0, -10.0)
    k.hesco(58.0, 10.0, 58.0, 42.0)
    return k.finish(variant, height=19.0)


def strategy_gun(name, wall, team, glass, variant=""):
    """The Strategy Center's bombardment gun on its roof deck: a turret with a long barrel (BARREL for
    recoil, MUZZLE at the tip), sitting on ABGXSTRATCTR's gun deck."""
    k = Kit(name, wall, team, glass, height=26.0)
    k.model.add_bone("BARREL", "ROOTTRANSFORM", (-6.0, 0.0, 23.6))
    k.model.add_bone("MUZZLE", "BARREL", (14.0, 0.0, 23.6))
    k.b.cylinder_z(-10.0, 0.0, 20.0, 21.0, 6.0, 5.6, sides=16, region=METAL)
    k.b.loft([(-15.0, -4.0, 21.0), (-4.0, -4.0, 21.0), (-4.0, 4.0, 21.0), (-15.0, 4.0, 21.0)],
             [(-14.0, -3.4, 25.0), (-6.0, -3.4, 25.0), (-6.0, 3.4, 25.0), (-14.0, 3.4, 25.0)], WALL)
    k.team_band(-15.0, -4.0, -4.0, -4.0, 22.0, 22.8)
    gun, g = turret_mesh(k, "BARREL", "BARREL")
    g.cylinder_x(-6.0, -2.0, 0.0, 23.6, 0.9, 0.8, sides=12, region=METAL)
    g.cylinder_x(-2.0, 13.0, 0.0, 23.6, 0.55, 0.45, sides=12, region=METAL, caps=False)
    g.cylinder_x(13.0, 14.0, 0.0, 23.6, 0.8, 0.8, sides=12, region=METAL)
    k.model.attach("BARREL", gun)
    for mesh in (k.body, k.glass, k.team):
        if mesh.triangles:
            k.model.attach("ROOTTRANSFORM", mesh)
    return k.model


def airfield(name, wall, team, glass, variant=""):
    """Air base: an open apron across the whole retail footprint (224 x 148, height 25) so jets taxi,
    park and take off from the retail runway and parking bones on clear concrete, with open aircraft
    shelters (roofs on thin posts) along the +Y edge, a control tower and an operations block at the
    -Y corners, edge lights in team colour and a helipad."""
    k = Kit(name, wall, team, glass, height=25.0)
    k.pad(-110.0, -72.0, 110.0, 72.0, h=0.4)
    # Runway edge and centre markings along X.
    for y in (-38.0, -8.0):
        k.t.box((-100.0, y - 0.4, 0.4), (100.0, y + 0.4, 0.44), TEAM)
    for i in range(10):
        x = -95.0 + i * 20.0
        k.b.box((x, -23.4, 0.4), (x + 10.0, -22.6, 0.44), METAL)
    # Open shelters along +Y.
    for x0 in (-96.0, -48.0, 0.0, 48.0):
        x1 = x0 + 40.0
        k.b.box((x0, 30.0, 12.0), (x1, 70.0, 13.0), ROOF)
        k.t.box((x0, 29.8, 11.4), (x1, 30.0, 12.6), TEAM)
        for x in (x0 + 0.6, x1 - 0.6):
            for y in (30.6, 69.4):
                k.b.cylinder_z(x, y, 0.4, 12.0, 0.35, 0.35, sides=6, region=METAL)
        k.fx_spots.append((x0, 30.0, x1, 70.0, 13.0))
    # Control tower and operations block on the -Y corners.
    k.block(-108.0, -70.0, -98.0, -60.0, 0.4, 18.0, storey=6.0)
    k.b.loft([(-110.0, -72.0, 18.0), (-96.0, -72.0, 18.0), (-96.0, -58.0, 18.0), (-110.0, -58.0, 18.0)],
             [(-110.0, -72.0, 18.4), (-96.0, -72.0, 18.4), (-96.0, -58.0, 18.4), (-110.0, -58.0, 18.4)], ROOF)
    k.g.loft([(-109.0, -71.0, 18.4), (-97.0, -71.0, 18.4), (-97.0, -59.0, 18.4), (-109.0, -59.0, 18.4)],
             [(-109.6, -71.6, 22.4), (-96.4, -71.6, 22.4), (-96.4, -58.4, 22.4), (-109.6, -58.4, 22.4)], GLASS, cap_bottom=False)
    k.b.box((-110.4, -72.4, 22.4), (-95.6, -57.6, 23.2), METAL)
    k.antenna(-103.0, -65.0, 23.2, 6.0)
    k.fx_spots.append((-108.0, -70.0, -98.0, -60.0, 23.2))
    k.block(84.0, -70.0, 108.0, -56.0, 0.4, 8.0, storey=8.0, region=METAL)
    k.window_band(84.0, -56.0, 106.0, -56.0, 3.0, 5.6)
    k.dish(96.0, -63.0, 8.0, 2.6, facing=180.0)
    # Helipad near the ops block.
    k.b.cylinder_z(70.0, -60.0, 0.4, 0.6, 9.0, 9.0, sides=20, region=ROOF)
    k.t.box((67.0, -60.6, 0.6), (73.0, -59.4, 0.64), TEAM)
    k.t.box((67.0, -63.0, 0.6), (68.2, -57.0, 0.64), TEAM)
    k.t.box((71.8, -63.0, 0.6), (73.0, -57.0, 0.64), TEAM)
    return k.finish(variant, height=13.0)


def particle_uplink(name, wall, team, glass, variant=""):
    """Orbital weapon uplink: a power and control block, a reactor ring of capacitor banks and a big
    tracking dish on a lattice mount pointed at the sky. Retail footprint 128 x 76, height 38."""
    k = Kit(name, wall, team, glass, height=38.0)
    k.pad(-62.0, -36.0, 62.0, 36.0)
    k.block(-58.0, -32.0, -24.0, 32.0, 0.8, 12.0, storey=6.0)
    k.parapet(-58.0, -32.0, -24.0, 32.0, 12.0)
    k.window_band(-24.0, -30.0, -24.0, 30.0, 6.4, 9.0)
    k.team_band(-24.0, -31.0, -24.0, 31.0, 10.4, 11.2)
    k.solar_rows(-56.0, -30.0, -26.0, 30.0, 12.0, rows=5)
    # Capacitor banks around the dish mount.
    for a in range(8):
        r = math.radians(a * 45.0 + 22.5)
        x, y = 16.0 + 24.0 * math.cos(r), 24.0 * math.sin(r) * 0.45
        k.b.cylinder_z(x, y, 0.8, 7.0, 2.6, 2.6, sides=10, region=METAL)
        k.b.cylinder_z(x, y, 7.0, 7.6, 2.0, 1.4, sides=10, region=METAL)
    # Lattice mount and the dish facing up and towards +X.
    k.b.cylinder_z(16.0, 0.0, 0.8, 4.0, 11.0, 10.0, sides=20, region=WALL)
    for a in range(4):
        r = math.radians(a * 90.0 + 45.0)
        x, y = 16.0 + 7.0 * math.cos(r), 7.0 * math.sin(r)
        k.b.cylinder_z(x, y, 4.0, 18.0, 0.7, 0.5, sides=6, region=METAL)
    k.b.cylinder_z(16.0, 0.0, 4.0, 33.0, 2.4, 1.6, sides=10, region=METAL)
    k.dish(16.0, 0.0, 18.0, 15.0, facing=0.0, tilt=62.0)
    k.antenna(16.0, 0.0, 26.0, 12.0, r=0.5)
    k.fx_spots.append((4.0, -10.0, 28.0, 10.0, 20.0))
    k.hesco(60.0, -36.0, 60.0, -8.0)
    k.hesco(60.0, 8.0, 60.0, 36.0)
    return k.finish(variant, height=20.0)


BUILDERS = {
    "ABGXSTRATCTR": strategy_center,
    "ABGXAIRFIELD": airfield,
    "ABGXUPLINK": particle_uplink,
    "ABGXDROPZONE": supply_drop_zone,
    "ABGXPATRIOT": patriot,
    "ABGXFIREBASE": fire_base,
    "ABGXPWR": power_plant,
    "ABGXBARRACKS": barracks,
    "ABGXWARFACT": war_factory,
    "ABGXSUPPLY": supply_center,
    "ABGXCMDHQ": command_center,
}
