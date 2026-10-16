"""Parametric skirmish layout: any even player count, biome, layout and seed.

GeneralsX @feature Claude 16/10/2026 The hand-made layouts each describe one map; this one
builds a map from a few parameters so new maps need no code. Players split into a west and an
east team, one to four bases per side in a column along the map edge; the east half mirrors
the west half. Every map gets the mechanics of the hand-made ones: per base indestructible
bunkers, artillery and sandbags in front, supply docks with large reserves and two unmanned,
indestructible dozers of other generals; between the bases fenced, capturable GLA compounds;
a column of capturable airfields, war factories, power plants, a hospital, a repair bay and
oil derricks; and capturable superweapons in the middle. The "lines" layout is open ground
with superweapons on the centre line; "river" puts a winding river with a bridge per base row
between the two teams and gives each bank its own superweapons.
"""

import math

import numpy as np

import kit
import mapgen

BIOMES = {
    "temperate": {
        "base": "GrassMediumType2", "patch": "GrassMediumType11", "patch2": "GrassMediumType25",
        "forest": "GrassMediumType31", "rocky": "RocksType2", "road": "DirtMediumType5", "bed": "SandMediumType9",
        "concrete": "ConcreteType1", "cliff": "CliffLargeType1",
        "trees": ["TreeOak02", "TreeBirch02", "TreeSpruce04", "TreeSpruce05", "TreeMaple06", "TreeFir05",
                  "TreeDogwood8"],
        "rocks": ["Rocks1Brown", "Rocks2Brown", "Rocks3Brown", "RockClusterSmall01", "RockClusterMedium01"],
        "forest_density": 0.7, "tree_scatter": 0.04,
    },
    "desert": {
        "base": "SandLargeType4", "patch": "SandLargeType3Light", "patch2": "SandMediumType13d",
        "forest": "GrassMediumType11", "rocky": "SandLargeType3", "road": "DirtMediumType5", "bed": "SandMediumType9",
        "concrete": "ConcreteType1", "cliff": "CliffLargeType8",
        "trees": ["TreePalm1short", "TreePalm2short", "TreePalm1", "TreePalm2", "TreePalm03", "TreePalm04",
                  "DesertShrub01", "DesertShrub02", "DesertShrub03"],
        "rocks": ["Rocks1Brown", "Rocks2Brown", "Rocks3Brown", "RockClusterSmall01", "RockClusterMedium01"],
        "forest_density": 0.3, "tree_scatter": 0.03,
    },
    "snow": {
        "base": "SnowType2", "patch": "SnowType3", "patch2": "GrassMediumType15",
        "forest": "SnowType3", "rocky": "RocksType2", "road": "DirtMediumType5", "bed": "SandMediumType9",
        "concrete": "ConcreteType2", "cliff": "CliffMediumType1",
        "trees": ["TreeFir06Snow", "TreeFir07Snow", "TreeSpruce04Snow", "TreeSpruce05Snow", "TreePine4snow",
                  "TreePine5snow", "TreeOak02Snow", "TreeMaple03Snow"],
        "rocks": ["RockClusterSmallSnow01", "RockClusterMediumSnow01", "RockClusterLargeSnow01"],
        "forest_density": 0.6, "tree_scatter": 0.03,
    },
}
LAYOUTS = ("lines", "river")

BORDER = 30
LAND = 60.0
WATER_Z = 24
ROW = 1000.0  # distance between base rows
BASE_X = 450.0
BASE_R = 360.0
COMPOUND_X = (880.0, 1280.0)
COMPOUND_H = 300.0
TECH_X = 1450.0
TECH_DY = 260.0
ROAD_X = 1650.0
RIVER_HALF = 120.0
SECOND_DOZER = (60.0, 250.0)
DOCK_VALUE = 100000

DOZERS = ["Boss_VehicleDozer", "Nuke_ChinaVehicleDozer", "Tank_ChinaVehicleDozer", "Lazr_AmericaVehicleDozer",
          "AirF_AmericaVehicleDozer", "Infa_ChinaVehicleDozer", "SupW_AmericaVehicleDozer", "ChinaVehicleDozer"]
GLAS = ["Chem", "Demo", "Slth", ""]
TECH = [("AmericaAirfield", 140), ("ChinaWarFactory", 85), ("AmericaPowerPlant", 55), ("ChinaAirfield", 140)]
TECH_SMALL = ["TechHospital", "TechRepairbay"]
SUPERWEAPONS = ["ChinaNuclearMissileLauncher", "AmericaParticleCannonUplink", "GLAScudStorm",
                "Lazr_AmericaParticleCannonUplink", "SupW_AmericaParticleCannonUplink"]


class Custom:
    """A layout module built from parameters: has the NAME, PLAYERS, generate() interface the
    hand-made layouts have."""

    def __init__(self, players, biome, layout, seed, name=None, string_tag=True):
        if players not in (2, 4, 6, 8):
            raise ValueError("players must be 2, 4, 6 or 8")
        if biome not in BIOMES:
            raise ValueError(f"biome must be one of {', '.join(BIOMES)}")
        if layout not in LAYOUTS:
            raise ValueError(f"layout must be one of {', '.join(LAYOUTS)}")
        self.players, self.biome, self.layout, self.seed = players, biome, layout, seed
        self.b = BIOMES[biome]
        self.rows = players // 2
        self.width = 4400.0 if layout == "river" else 4000.0
        self.height = max(2800.0, self.rows * ROW + 400.0)
        self.mid = self.width / 2
        self.base_ys = [self.height / 2 + (i - (self.rows - 1) / 2) * ROW for i in range(self.rows)]
        # Compounds and derricks sit half a row from a base: between neighbours and beyond the ends.
        gaps = sorted({round(y + d) for y in self.base_ys for d in (-ROW / 2, ROW / 2)})
        self.gap_ys = [float(g) for g in gaps if 350.0 <= g <= self.height - 350.0]
        self.DISPLAY_NAME = name or f"{biome.capitalize()} {layout.capitalize()} {players}p {seed}"
        self.NAME = "GX " + self.DISPLAY_NAME
        self.NAME_TAG = "MAP:GX" + "".join(c for c in self.DISPLAY_NAME.title() if c.isalnum())
        # Without a string table entry the game would show "MISSING: MAP:..."; an empty map name
        # makes it show the file name instead.
        self.map_name = self.NAME_TAG if string_tag else ""
        self.PLAYERS = players

    def mirror(self, p):
        return (self.width - p[0], p[1])

    def river_x(self, y):
        return self.mid + 70.0 * np.sin(y / 420.0 + self.seed % 7)

    def roads(self):
        roads = []
        end = self.mid - RIVER_HALF - 40.0 if self.layout == "river" else self.mid
        for y in self.base_ys:
            roads.append([(BASE_X + 110.0, y), (ROAD_X, y), (end, y)])
        ys = self.base_ys + self.gap_ys
        roads.append([(ROAD_X, min(ys)), (ROAD_X, max(ys))])
        for y in self.gap_ys:
            roads.append([(COMPOUND_X[1], y), (ROAD_X, y)])
        west = [r for r in roads if r[-1][0] < self.mid - 1]
        centre = [r for r in roads if r[-1][0] >= self.mid - 1]
        out = west + [[self.mirror(p) for p in r] for r in west]
        for r in centre:
            out.append(r + [self.mirror(p) for p in reversed(r)][1:])
        return out

    def superweapon_spots(self):
        """West-side spots in river layouts (mirrored east), centre-line spots in lines layouts."""
        if self.layout == "river":
            return [(self.mid - 300.0, y) for y in self.gap_ys]
        return [(self.mid, y) for y in self.gap_ys]

    def heights(self, t, nprng):
        x, y = t.wx, t.wy
        fx = self.mid - np.abs(x - self.mid)
        noise = mapgen.value_noise((fx, y), 900.0, nprng, octaves=4)
        h = LAND + (noise - 0.5) * 44.0
        if self.biome == "desert":
            bend = mapgen.value_noise((fx, y), 700.0, nprng, octaves=2)
            h += 12.0 * np.sin((fx * 0.55 + y) / 85.0 + bend * 7.0) * mapgen.smoothstep(0.35, 0.65, noise)
        edge = np.minimum(fx, np.minimum(y, self.height - y))
        peaks = mapgen.value_noise((fx, y), 260.0, nprng, octaves=3)
        h += (40.0 + 60.0 * peaks) * mapgen.smoothstep(40.0, -160.0, edge)

        pads = []
        for by in self.base_ys:
            pads += [((BASE_X, by), BASE_R, LAND + 2)]
            pads += [((TECH_X, by - TECH_DY), 170, LAND), ((TECH_X, by + TECH_DY), 110, LAND)]
        for gy in self.gap_ys:
            pads += [(((COMPOUND_X[0] + COMPOUND_X[1]) / 2, gy), 200, LAND)]
        for p in self.superweapon_spots():
            pads += [(p, 110, LAND)]
        pads += [(self.mirror(p), r, lv) for p, r, lv in pads]
        for road in self.roads():
            for p in road:
                pads.append((p, 60, LAND))
        h = kit.blend_pads(h, x, y, pads)

        if self.layout == "river":
            shore = mapgen.value_noise((fx, y), 120.0, nprng, octaves=2)
            d = np.abs(x - self.river_x(y)) + (shore - 0.5) * 50.0
            bank = mapgen.smoothstep(RIVER_HALF + 140.0, RIVER_HALF + 10.0, d)
            h = h * (1 - bank) + (LAND - 4) * bank
            water = mapgen.smoothstep(RIVER_HALF + 10.0, RIVER_HALF - 40.0, d)
            h = h * (1 - water) + 14.0 * water
            for p0, p1 in self.bridges():
                for px, py in (p0, p1):
                    w = mapgen.smoothstep(90.0, 40.0, np.hypot(x - px, y - py))
                    h = h * (1 - w) + LAND * w
        t.h = np.minimum(h, 250.0)

    def bridges(self):
        out = []
        for y in self.base_ys:
            rx = float(self.river_x(y))
            out.append(((rx - RIVER_HALF - 40.0, y), (rx + RIVER_HALF + 40.0, y)))
        return out

    def textures(self, t, nprng):
        b = self.b
        base, patch_t, patch2_t = t.texture(b["base"]), t.texture(b["patch"]), t.texture(b["patch2"])
        forest, rocky, road = t.texture(b["forest"]), t.texture(b["rocky"]), t.texture(b["road"])
        bed, concrete, cliff = t.texture(b["bed"]), t.texture(b["concrete"]), t.texture(b["cliff"])
        x, y, h = t.wx + 5.0, t.wy + 5.0, t.h
        fx = self.mid - np.abs(x - self.mid)
        patch = mapgen.value_noise((fx, y), 420.0, nprng, octaves=3)
        patch2 = mapgen.value_noise((fx, y), 200.0, nprng, octaves=2)
        t.forest_noise = mapgen.value_noise((fx, y), 330.0, nprng, octaves=3)
        cls = np.full(h.shape, base, dtype=np.int32)
        cls[patch > 0.58] = patch_t
        cls[(patch2 > 0.65) & (patch < 0.48)] = patch2_t
        cls[t.forest_noise > 0.52] = forest
        cls[h - LAND > 30 + 10 * patch2] = rocky
        for r in self.roads():
            for p0, p1 in zip(r, r[1:]):
                cls[kit.segment_distance(x, y, p0, p1) < 32] = road
        for by in self.base_ys:
            for bx in (BASE_X, self.width - BASE_X):
                d = np.hypot(x - bx, y - by)
                cls[d < 120] = concrete
                cls[(d >= 120) & (d < 170)] = road
        z = h * mapgen.HEIGHT_SCALE
        cls[z < WATER_Z + 5] = bed
        cls[t.cliff_cells()] = cliff
        t.cls = cls

    def place(self, objs, t, pyrng):
        centre = (self.mid, self.height / 2)
        m = kit.Mirror(self.width, self.height)
        names = {"docks": [], "dozers": []}
        for east in (False, True):
            f = self.mirror if east else (lambda p: p)
            for row, by in enumerate(self.base_ys):
                slot = row + 1 + (self.rows if east else 0)
                tag = f"{'E' if east else 'W'}{row + 1}"
                gap = by + ROW / 2 if by + ROW / 2 < self.height - 350 else by - ROW / 2
                kit.ai_setup(objs, slot, f((BASE_X, by)),
                             center=[f(p) for p in ((self.mid - 200.0, by), (ROAD_X, by))],
                             flank=[f(p) for p in ((self.mid - 200.0, gap), (ROAD_X, gap), (ROAD_X, by))],
                             backdoor=[f(p) for p in ((150.0, gap), (150.0, by))])
                k = (2 * row + (1 if east else 0)) % len(DOZERS)
                bx, bpy = f((BASE_X, by))
                kit.base_kit(objs, m, (bx, bpy), east, DOZERS[k], tag, pyrng, names, centre)
                u, v = SECOND_DOZER
                x, y = bx + (-u if east else u), bpy + v
                name = f"GXDozer{tag}2"
                objs.add(DOZERS[(k + 3) % len(DOZERS)], x, y, m.facing(x, y, centre), indestructible=True, name=name,
                         radius=30)
                names["dozers"].append(name)
                template, radius = TECH[row % len(TECH)]
                x, y = f((TECH_X, by - TECH_DY))
                objs.add(template, x, y, m.facing(x, y, centre), radius=radius)
                x, y = f((TECH_X, by + TECH_DY))
                objs.add(TECH_SMALL[row % 2], x, y, m.facing(x, y, centre), indestructible=True, radius=80)
            for n, gy in enumerate(self.gap_ys):
                x0, x1 = COMPOUND_X
                box = (x0, gy - COMPOUND_H / 2, x1, gy + COMPOUND_H / 2)
                gla = GLAS[(n + (1 if east else 0)) % len(GLAS)]
                if east:
                    box = (self.width - x1, box[1], self.width - x0, box[3])
                    gates = [((box[0], gy), 60.0)]
                else:
                    gates = [((box[2], gy), 60.0)]
                kit.compound(objs, box, gla, gates, pyrng, centre)
                x, y = f((ROAD_X + 130.0, gy))
                objs.add("TechOilDerrick", x, y, m.facing(x, y, centre), radius=35)

        spots = self.superweapon_spots()
        for n, p in enumerate(spots):
            template = SUPERWEAPONS[n % len(SUPERWEAPONS)]
            for q in ([p, self.mirror(p)] if self.layout == "river" else [p]):
                objs.add(template, *q, math.pi / 2 if q[1] < self.height / 2 else -math.pi / 2, radius=75)
        if self.layout == "lines":
            for y in self.base_ys:
                objs.add("AmericaPowerPlant", self.mid, y + 170.0, 0.0, radius=50)
        else:
            for n, (p0, p1) in enumerate(self.bridges(), start=1):
                objs.bridge("ConcreteFourLane", p0, p1, f"GXBridge{n}")

        for r in self.roads():
            objs.road("TwoLaneDark", r)
        kit.lamps(objs, self.roads())
        self.scatter(objs, t, pyrng)
        return names

    def scatter(self, objs, t, pyrng):
        b = self.b
        circles = [(x, y, r + 50) for x, y, r, _ in objs.footprints]
        for by in self.base_ys:
            circles += [(BASE_X, by, BASE_R + 20), (self.width - BASE_X, by, BASE_R + 20)]
        for gy in self.gap_ys:
            cx = (COMPOUND_X[0] + COMPOUND_X[1]) / 2
            circles += [(cx, gy, 230), (self.width - cx, gy, 230)]
        if self.layout == "river":
            for p0, p1 in self.bridges():
                circles += [(*p0, 100), (*p1, 100)]
        segments = [seg for r in self.roads() for seg in zip(r, r[1:])]
        cliffs = t.cliff_cells()
        trees, rocks = b["trees"], b["rocks"]

        def place_one(x, y, i, j, roll, pick):
            z = t.h[j, i] * mapgen.HEIGHT_SCALE
            if z < WATER_Z + 6 or cliffs[j, i] or kit.blocked(x, y, circles, segments, road_clear=55.0):
                return None
            if t.forest_noise[j, i] > 0.52:
                return trees[int(pick * len(trees))] if roll < b["forest_density"] else None
            if t.h[j, i] - LAND > 30:
                return rocks[int(pick * len(rocks))] if roll < 0.2 else None
            if roll < b["tree_scatter"]:
                return trees[int(pick * len(trees))]
            if roll < b["tree_scatter"] + 0.01:
                return rocks[int(pick * len(rocks))]
            return None

        kit.scatter(objs, t, pyrng, self.width, self.height, BORDER, place_one)

    def generate(self):
        pyrng, nprng = mapgen.rng(self.seed)
        t = mapgen.Terrain(int(self.width / mapgen.CELL), int(self.height / mapgen.CELL), BORDER)
        t.water_z = WATER_Z
        self.heights(t, nprng)
        self.textures(t, nprng)
        objs = mapgen.Objects()
        names = self.place(objs, t, pyrng)
        kit.water_plane(objs, self.width, self.height, BORDER, WATER_Z)
        data = kit.finish(t, objs, self.map_name, names, DOCK_VALUE)
        return data, t, objs
