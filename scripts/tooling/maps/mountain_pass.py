"""Mountain Pass: 4-player (2 vs 2) skirmish map with the Twin Rivers mechanics.

GeneralsX @feature Claude 16/10/2026 A rocky ridge with snow on top runs north to south
through the middle and splits the map into a west and an east team side. Three passes cross
it: one in the north, one in the south and one through a sheltered valley in the middle where
two capturable superweapons stand. What every base gets, as on Twin Rivers Fortress:
- indestructible garrisonable bunkers and artillery platforms in front, and bunkers at the
  inner end of each pass;
- an unmanned, indestructible dozer of another general (any infantry can crew it);
- supply docks with large reserves, and a capturable GLA compound shared by the two bases of
  a side;
- a capturable airfield (north bases) or war factory (south bases), a power plant, oil
  derricks and a hospital or repair bay.
The layout is written for the north-west quadrant and mirrored to the other three, so every
start position is equal.
"""

import math

import numpy as np

import kit
import mapgen

NAME = "GX Mountain Pass"
NAME_TAG = "MAP:GXMountainPass"
DISPLAY_NAME = "Mountain Pass"
PLAYERS = 4
SEED = 2804

SIZE = 2800.0
MID = SIZE / 2
BORDER = 30
LAND = 60.0
WATER_Z = 24
RIDGE_FOOT = 270.0  # distance from the centre line where the ridge starts to rise
RIDGE_TOP = 120.0  # distance where it reaches full height
PASS_Y = 450.0  # north pass; the south pass mirrors it
PASS_FLOOR = 95.0  # half width of the flat pass floor
VALLEY_R = 300.0
LAKE = ((230.0, 230.0), 130.0)

# North-west quadrant (x from the west edge, y from the north edge).
BASE = (450.0, 800.0)
BASE_R = 360.0
CORNER = (900.0, 235.0)  # airfield in the north, war factory in the south
POWER = (1120.0, 1010.0)
TECH = (630.0, 1130.0)  # hospital in the north, repair bay in the south
DERRICKS = [(1110.0, 290.0), (300.0, 1120.0)]
PASS_BUNKERS = [(1290.0, PASS_Y - 72.0), (1290.0, PASS_Y + 72.0)]
VALLEY_BUNKERS = [(1215.0, 1290.0)]
ROADS = [[(560.0, 800.0), (960.0, 800.0), (1090.0, 580.0), (1200.0, PASS_Y), (MID, PASS_Y)],
         [(960.0, 800.0), (1060.0, 1100.0), (1140.0, MID), (MID, MID)],
         [(800.0, 800.0), (800.0, MID)],
         [(800.0, MID), (560.0, MID)],
         [(1090.0, 580.0), (960.0, 390.0)]]

QUADRANTS = [  # NW, NE, SW, SE: mirror flags (x, y), dozer, corner building, power plant, tech
    {"mirror": (False, False), "dozer": "Boss_VehicleDozer", "corner": "AmericaAirfield",
     "power": "AmericaPowerPlant", "tech": "TechHospital"},
    {"mirror": (True, False), "dozer": "AirF_AmericaVehicleDozer", "corner": "ChinaAirfield",
     "power": "ChinaPowerPlant", "tech": "TechHospital"},
    {"mirror": (False, True), "dozer": "Tank_ChinaVehicleDozer", "corner": "ChinaWarFactory",
     "power": "Tank_ChinaPowerPlant", "tech": "TechRepairbay"},
    {"mirror": (True, True), "dozer": "Nuke_ChinaVehicleDozer", "corner": "AmericaWarFactory",
     "power": "AirF_AmericaPowerPlant", "tech": "TechRepairbay"},
]
SLOTS = [0, 2, 1, 3]  # players 1-2 west (north, south), 3-4 east
COMPOUNDS = [("Chem", False), ("Slth", True)]  # GLA general of the west and east compound
COMPOUND_BOX = (130.0, 1235.0, 560.0, 1565.0)
SUPERWEAPONS = [((MID, 1235.0), "ChinaNuclearMissileLauncher"), ((MID, 1565.0), "AmericaParticleCannonUplink")]

TREES = ["TreeSpruce04", "TreeSpruce05", "TreeFir05", "TreeBirch02", "TreeOak02", "TreeMaple06"]
HIGH_TREES = ["TreeSpruce04", "TreeSpruce05", "TreeFir05"]
ROCKS = ["RocksG02", "RocksG14", "Rocks3Brown", "RockClusterMedium01", "RockClusterSmall01"]
DOCK_VALUE = 100000


def to_world(q, p):
    mx, my = QUADRANTS[q]["mirror"]
    return (SIZE - p[0] if mx else p[0], SIZE - p[1] if my else p[1])


def all_roads():
    return [[to_world(q, p) for p in road] for q in range(4) for road in ROADS]


def heights(t, nprng):
    x, y = t.wx, t.wy
    fx, fy = MID - np.abs(x - MID), MID - np.abs(y - MID)  # folded into the north-west quadrant
    noise = mapgen.value_noise((fx, fy), 900.0, nprng, octaves=4)
    h = LAND + (noise - 0.5) * 44.0

    edge = np.minimum(fx, fy)
    peaks = mapgen.value_noise((fx, fy), 260.0, nprng, octaves=3)
    h += (45.0 + 60.0 * peaks) * mapgen.smoothstep(40.0, -160.0, edge)

    # The ridge: a cliff wall at a wandering foot line, then broken rocky peaks.
    across = MID - fx
    wander = mapgen.value_noise((fx * 0.0, fy), 420.0, nprng, octaves=2)
    foot = RIDGE_FOOT + (wander - 0.5) * 120.0
    crest = mapgen.value_noise((fx, fy), 110.0, nprng, octaves=4)
    wall = mapgen.smoothstep(foot, foot - 70.0, across)
    peaks_in = mapgen.smoothstep(foot - 60.0, foot - 200.0, across)
    ridge = 58.0 * wall + (15.0 + 100.0 * crest ** 1.5) * peaks_in * wall
    ridge += 22.0 * mapgen.smoothstep(foot + 260.0, foot, across) * peaks
    cut = mapgen.smoothstep(PASS_FLOOR + 60.0, PASS_FLOOR, np.abs(fy - PASS_Y))
    r = np.hypot(x - MID, y - MID)
    cut = np.maximum(cut, mapgen.smoothstep(VALLEY_R + 40.0, VALLEY_R - 30.0, r))
    h += ridge * (1 - cut)

    pads = []
    for q in range(4):
        pads += [(to_world(q, BASE), BASE_R, LAND + 2), (to_world(q, CORNER), 180, LAND),
                 (to_world(q, POWER), 80, LAND + 2), (to_world(q, TECH), 90, LAND)]
    for west in (True, False):
        x0, y0, x1, y1 = COMPOUND_BOX
        c = ((x0 + x1) / 2, MID)
        pads.append((c if west else (SIZE - c[0], MID), 210, LAND))
    h = kit.blend_pads(h, x, y, pads)
    h = kit.blend_pads(h, x, y, [((MID, MID), VALLEY_R - 40, LAND + 6)], falloff=60.0)
    # Pass floors stay level with the land on both sides.
    for py in (PASS_Y, SIZE - PASS_Y):
        w = mapgen.smoothstep(PASS_FLOOR + 30.0, PASS_FLOOR - 10.0, np.abs(y - py)) * \
            mapgen.smoothstep(RIDGE_FOOT + 120.0, RIDGE_FOOT - 40.0, np.abs(x - MID))
        h = h * (1 - w) + (LAND + 4) * w

    # Mountain lakes in the corners behind the bases.
    (lx, ly), lr = LAKE
    shore = mapgen.value_noise((fx, fy), 90.0, nprng, octaves=2)
    for q in range(4):
        px, py = to_world(q, (lx, ly))
        rr = lr + (shore - 0.5) * 90.0
        w = mapgen.smoothstep(rr + 40.0, rr - 20.0, np.hypot(x - px, y - py))
        h = h * (1 - w) + 18.0 * w
    t.h = np.minimum(h, 250.0)


def textures(t, nprng):
    grass = t.texture("GrassMediumType2")
    grass_b = t.texture("GrassMediumType15")
    grass_c = t.texture("GrassMediumType25")
    forest = t.texture("GrassMediumType31")
    dirt = t.texture("DirtMediumType5")
    rocks = t.texture("RocksType2")
    snow = t.texture("SnowType2")
    beach = t.texture("SandMediumType9")
    concrete = t.texture("ConcreteMediumType1")
    cliff = t.texture("CliffMediumType16")
    cliff_large = t.texture("CliffLargeType1")

    x, y, h = t.wx + 5.0, t.wy + 5.0, t.h
    fx, fy = MID - np.abs(x - MID), MID - np.abs(y - MID)
    patch = mapgen.value_noise((fx, fy), 380.0, nprng, octaves=3)
    patch2 = mapgen.value_noise((fx, fy), 230.0, nprng, octaves=2)
    cls = np.full(h.shape, grass, dtype=np.int32)
    cls[patch > 0.58] = grass_b
    cls[patch2 > 0.66] = grass_c
    cls[(patch < 0.33) & (patch2 > 0.5)] = dirt
    t.forest_noise = mapgen.value_noise((fx, fy), 300.0, nprng, octaves=3)
    cls[t.forest_noise > 0.54] = forest
    rise = h - LAND
    cls[rise > 22 + 10 * patch2] = rocks
    cls[rise > 128 + 12 * patch] = snow

    for road in all_roads():
        for p0, p1 in zip(road, road[1:]):
            cls[kit.segment_distance(x, y, p0, p1) < 34] = dirt
    for q in range(4):
        bx, by = to_world(q, BASE)
        d = np.hypot(x - bx, y - by)
        cls[d < 120] = concrete
        cls[(d >= 120) & (d < 170)] = dirt
        cx, cy = to_world(q, CORNER)
        cls[np.hypot(x - cx, y - cy) < 150] = concrete
    for west in (True, False):
        x0, y0, x1, y1 = COMPOUND_BOX
        if not west:
            x0, x1 = SIZE - x1, SIZE - x0
        cls[(x > x0 + 40) & (x < x1 - 40) & (y > y0 + 40) & (y < y1 - 40) & (patch > 0.4)] = dirt
    cls[np.hypot(x - MID, y - MID) < 200] = dirt

    z = h * mapgen.HEIGHT_SCALE
    cls[z < WATER_Z + 5] = beach
    cliffs = t.cliff_cells()
    cls[cliffs] = cliff
    cls[cliffs & (rise > 70)] = cliff_large
    t.cls = cls


def place(objs, t, pyrng):
    centre = (MID, MID)
    for slot, q in enumerate(SLOTS, start=1):
        base = to_world(q, BASE)
        kit.ai_setup(objs, slot, base,
                     center=[centre] + [to_world(q, p) for p in ((1140.0, MID), (1060.0, 1100.0), (960.0, 800.0))],
                     flank=[to_world(q, p) for p in ((MID, PASS_Y), (1200.0, PASS_Y), (1090.0, 580.0), (960.0, 800.0))],
                     backdoor=[to_world(q, p) for p in ((800.0, MID), (800.0, 1050.0))])

    names = {"docks": [], "dozers": []}
    for q, quad in enumerate(QUADRANTS):
        tag = ["NW", "NE", "SW", "SE"][q]
        kit.base_kit(objs, kit.Mirror(SIZE, SIZE), to_world(q, BASE), quad["mirror"][0], quad["dozer"],
                     tag, pyrng, names, centre)
        for p, template, r in ((CORNER, quad["corner"], 140 if "Airfield" in quad["corner"] else 85),
                               (POWER, quad["power"], 55), (TECH, quad["tech"], 80)):
            x, y = to_world(q, p)
            objs.add(template, x, y, math.atan2(MID - y, MID - x), indestructible=template.startswith("Tech"),
                     radius=r)
        for p in DERRICKS:
            x, y = to_world(q, p)
            objs.add("TechOilDerrick", x, y, math.atan2(MID - y, MID - x), radius=35)
        for p in PASS_BUNKERS:
            x, y = to_world(q, p)
            objs.add("CivilianBunker01", x, y, 0.0 if x < MID else math.pi, owner=mapgen.NEUTRAL_TEAM,
                     indestructible=True, radius=45)
        for p in VALLEY_BUNKERS:
            x, y = to_world(q, p)
            objs.add("CivilianBunker01", x, y, math.atan2(MID - y, MID - x) + math.pi, owner=mapgen.NEUTRAL_TEAM,
                     indestructible=True, radius=45)

    for (x, y), template in SUPERWEAPONS:
        objs.add(template, x, y, math.atan2(MID - y, 0.0), radius=75)

    gate = [((560.0, MID), 60.0)]
    for gla, east in COMPOUNDS:
        x0, y0, x1, y1 = COMPOUND_BOX
        box = (SIZE - x1, y0, SIZE - x0, y1) if east else COMPOUND_BOX
        gates = [((SIZE - gx, gy), r) for (gx, gy), r in gate] if east else gate
        kit.compound(objs, box, gla, gates, pyrng, centre)

    for road in all_roads():
        objs.road("TwoLaneDark", road)
    kit.lamps(objs, all_roads())
    scatter(objs, t, pyrng)
    return names


def scatter(objs, t, pyrng):
    circles = [(x, y, r + 60) for x, y, r, _ in objs.footprints]
    for q in range(4):
        bx, by = to_world(q, BASE)
        circles.append((bx, by, BASE_R + 20))
    circles.append((MID, MID, VALLEY_R - 40))
    for west in (True, False):
        x0, y0, x1, y1 = COMPOUND_BOX
        c = ((x0 + x1) / 2 if west else SIZE - (x0 + x1) / 2, MID)
        circles.append((*c, 250))
    segments = [seg for road in all_roads() for seg in zip(road, road[1:])]
    cliffs = t.cliff_cells()

    def place_one(x, y, i, j, roll, pick):
        z = t.h[j, i] * mapgen.HEIGHT_SCALE
        if z < WATER_Z + 6 or kit.blocked(x, y, circles, segments):
            return None
        rise = t.h[j, i] - LAND
        if cliffs[j, i]:
            return None
        if rise > 95:
            return ROCKS[int(pick * len(ROCKS))] if roll < 0.08 else None
        if rise > 22:
            if roll < 0.22:
                return HIGH_TREES[int(pick * len(HIGH_TREES))]
            return ROCKS[int(pick * len(ROCKS))] if roll < 0.32 else None
        if t.forest_noise[j, i] > 0.52 or roll < 0.03:
            return TREES[int(pick * len(TREES))]
        if rise > 10 and roll < 0.12:
            return ROCKS[int(pick * len(ROCKS))]
        return None

    kit.scatter(objs, t, pyrng, SIZE, SIZE, BORDER, place_one)


def generate():
    pyrng, nprng = mapgen.rng(SEED)
    cells = int(SIZE / mapgen.CELL)
    t = mapgen.Terrain(cells, cells, BORDER)
    t.water_z = WATER_Z
    heights(t, nprng)
    textures(t, nprng)
    objs = mapgen.Objects()
    names = place(objs, t, pyrng)
    kit.water_plane(objs, SIZE, SIZE, BORDER, WATER_Z)
    data = kit.finish(t, objs, NAME_TAG, names, DOCK_VALUE)
    return data, t, objs
