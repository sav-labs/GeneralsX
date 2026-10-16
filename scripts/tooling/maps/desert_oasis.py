"""Desert Oasis: 6-player (3 vs 3) skirmish map with the Twin Rivers mechanics.

GeneralsX @feature Claude 16/10/2026 Two lines of three bases face each other across a dune
desert. In the middle lies an oasis lake ringed by palms and oil derricks, with an island
reached by two bridges where two capturable superweapons and a power plant stand; two more
superweapons sit between the oasis and the central mesas, and a capturable airfield lies at the
north and south end of the centre line. Mesas with cliff sides give cover in front of the
outer bases. Every base gets, as on Twin Rivers Fortress, indestructible bunkers and artillery
in front, an unmanned, indestructible dozer of another general, supply docks with large
reserves, and a capturable GLA compound between it and its neighbour. The east half mirrors
the west half, so opposite start positions are equal.
"""

import math

import numpy as np

import kit
import mapgen

NAME = "GX Desert Oasis"
NAME_TAG = "MAP:GXDesertOasis"
DISPLAY_NAME = "Desert Oasis"
PLAYERS = 6
SEED = 3606

SIZE = 3600.0
MID = SIZE / 2
BORDER = 30
LAND = 60.0
WATER_Z = 24
LAKE_R = 420.0
ISLAND_R = 230.0
MESA_H = 66.0

# West half (east mirrors x).
BASES = [(450.0, 600.0), (450.0, 1800.0), (450.0, 3000.0)]
BASE_R = 360.0
DOZERS = [("Boss_VehicleDozer", "Nuke_ChinaVehicleDozer"), ("Tank_ChinaVehicleDozer", "Lazr_AmericaVehicleDozer"),
          ("AirF_AmericaVehicleDozer", "Infa_ChinaVehicleDozer")]  # (west, east) per row
COMPOUNDS = [((120.0, 1060.0, 520.0, 1340.0), ("Chem", "Slth")), ((120.0, 2260.0, 520.0, 2540.0), ("Demo", ""))]
FACTORY = ((1180.0, 1200.0), ("ChinaWarFactory", "AmericaWarFactory"))
POWER = ((1180.0, 2400.0), ("AmericaPowerPlant", "ChinaPowerPlant"))
TECH = [((690.0, 1320.0), "TechHospital"), ((690.0, 2280.0), "TechRepairbay")]
ROAD_X = 1000.0
BRIDGE_X = (MID - LAKE_R - 60.0, MID - ISLAND_R + 30.0)
MESAS = [((1290.0, 560.0), 170.0), ((1290.0, 3040.0), 170.0)]
CENTRE_MESAS = [((MID, 860.0), 210.0), ((MID, 2740.0), 210.0)]
AIRFIELDS = [((MID, 300.0), "AmericaAirfield"), ((MID, 3300.0), "ChinaAirfield")]
SUPERWEAPONS = [((MID, 1665.0), "ChinaNuclearMissileLauncher"), ((MID, 1935.0), "AmericaParticleCannonUplink"),
                ((MID, 1245.0), "GLAScudStorm"), ((MID, 2355.0), "SupW_AmericaParticleCannonUplink")]
SHORE_DERRICKS = [150.0, 210.0]  # degrees around the oasis, west side
SLOTS = [(0, False), (1, False), (2, False), (0, True), (1, True), (2, True)]

ROADS = [[(560.0, y), (ROAD_X, y)] for _, y in BASES] + [
    [(ROAD_X, 600.0), (ROAD_X, 3000.0)],
    [(ROAD_X, MID), (BRIDGE_X[0], MID)],
    [(ROAD_X, 600.0), (1160.0, 330.0), (MID - 160.0, 300.0)],
    [(ROAD_X, 3000.0), (1160.0, 3270.0), (MID - 160.0, 3300.0)],
    [(ROAD_X, 1200.0), (1090.0, 1200.0)],
    [(ROAD_X, 2400.0), (1110.0, 2400.0)],
]

PALMS = ["TreePalm1short", "TreePalm2short", "TreePalm1", "TreePalm2", "TreePalm03", "TreePalm04"]
SHRUBS = ["DesertShrub01", "DesertShrub02", "DesertShrub03", "DesertShrub04", "DesertShrub05", "DesertShrub06"]
ROCKS = ["Rocks1Brown", "Rocks2Brown", "Rocks3Brown", "RockClusterSmall01", "RockClusterMedium01"]
DOCK_VALUE = 100000


def mirror(p):
    return (SIZE - p[0], p[1])


def all_roads():
    return [r for road in ROADS for r in (road, [mirror(p) for p in road])]


def mesa_list():
    return [(p, r) for p, r in MESAS] + [(mirror(p), r) for p, r in MESAS] + CENTRE_MESAS


def heights(t, nprng):
    x, y = t.wx, t.wy
    fx = MID - np.abs(x - MID)  # folded into the west half
    noise = mapgen.value_noise((fx, y), 1000.0, nprng, octaves=4)
    h = LAND + (noise - 0.5) * 34.0
    # Dunes: long crests running north-east, bent by noise.
    bend = mapgen.value_noise((fx, y), 700.0, nprng, octaves=2)
    dunes = np.sin((fx * 0.55 + y) / 85.0 + bend * 7.0)
    h += 12.0 * dunes * mapgen.smoothstep(0.35, 0.65, noise)

    edge = np.minimum(fx, np.minimum(y, SIZE - y))
    peaks = mapgen.value_noise((fx, y), 280.0, nprng, octaves=3)
    h += (45.0 + 70.0 * peaks) * mapgen.smoothstep(40.0, -160.0, edge)

    rim = mapgen.value_noise((fx, y), 70.0, nprng, octaves=2)
    for (px, py), r in mesa_list():
        d = np.hypot(x - px, y - py) + (rim - 0.5) * 70.0
        h += MESA_H * mapgen.smoothstep(r + 25.0, r - 15.0, d) * (0.9 + 0.2 * rim)

    pads = [(mirror(b) if east else b, BASE_R, LAND + 2) for b in BASES for east in (False, True)]
    for box, _ in COMPOUNDS:
        c = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        pads += [(c, 200, LAND), (mirror(c), 200, LAND)]
    for p in (FACTORY[0], POWER[0]) + tuple(p for p, _ in TECH):
        pads += [(p, 110, LAND), (mirror(p), 110, LAND)]
    pads += [(p, 190, LAND) for p, _ in AIRFIELDS]
    pads += [((MID, 1245.0), 110, LAND), ((MID, 2355.0), 110, LAND)]
    h = kit.blend_pads(h, x, y, pads)

    # The oasis: a lake with an island, shallow banks.
    r = np.hypot(x - MID, y - MID)
    shore = mapgen.value_noise((fx, y), 120.0, nprng, octaves=2)
    lake_r = LAKE_R + (shore - 0.5) * 70.0
    bank = mapgen.smoothstep(lake_r + 160.0, lake_r + 20.0, r)
    h = h * (1 - bank) + (LAND - 4) * bank
    water = mapgen.smoothstep(lake_r + 20.0, lake_r - 30.0, r) * mapgen.smoothstep(ISLAND_R - 10.0, ISLAND_R + 50.0, r)
    h = h * (1 - water) + 14.0 * water
    island = mapgen.smoothstep(ISLAND_R, ISLAND_R - 50.0, r)
    h = h * (1 - island) + (LAND + 2) * island
    for p in bridge_ends()[0] + bridge_ends()[1]:
        w = mapgen.smoothstep(90.0, 40.0, np.hypot(x - p[0], y - p[1]))
        h = h * (1 - w) + LAND * w
    t.h = np.minimum(h, 250.0)


def bridge_ends():
    west = ((BRIDGE_X[0], MID), (BRIDGE_X[1], MID))
    return [west, (mirror(west[0]), mirror(west[1]))]


def textures(t, nprng):
    sand = t.texture("SandLargeType4")
    light = t.texture("SandLargeType3Light")
    dark = t.texture("SandMediumType13d")
    rocky = t.texture("SandLargeType3")
    bed = t.texture("SandMediumType9")
    grass = t.texture("GrassMediumType11")
    dirt = t.texture("DirtMediumType5")
    concrete = t.texture("ConcreteType1")
    cliff = t.texture("CliffLargeType8")

    x, y, h = t.wx + 5.0, t.wy + 5.0, t.h
    fx = MID - np.abs(x - MID)
    patch = mapgen.value_noise((fx, y), 450.0, nprng, octaves=3)
    patch2 = mapgen.value_noise((fx, y), 210.0, nprng, octaves=2)
    cls = np.full(h.shape, sand, dtype=np.int32)
    cls[patch > 0.57] = light
    cls[(patch2 > 0.64) & (patch < 0.5)] = dark
    rise = h - LAND
    cls[rise > 24 + 8 * patch2] = rocky

    r = np.hypot(x - MID, y - MID)
    t.green = mapgen.value_noise((fx, y), 160.0, nprng, octaves=2)
    cls[(r < LAKE_R + 150 + 90 * t.green) & (r > ISLAND_R - 40)] = grass
    cls[r < ISLAND_R - 40] = grass

    for road in all_roads():
        for p0, p1 in zip(road, road[1:]):
            cls[kit.segment_distance(x, y, p0, p1) < 32] = dirt
    for b in BASES:
        for bx, by in (b, mirror(b)):
            d = np.hypot(x - bx, y - by)
            cls[d < 120] = concrete
            cls[(d >= 120) & (d < 170)] = dirt
    for (px, py), _ in AIRFIELDS:
        cls[np.hypot(x - px, y - py) < 150] = concrete
    cls[r < 90] = concrete

    z = h * mapgen.HEIGHT_SCALE
    cls[z < WATER_Z + 5] = bed
    cls[t.cliff_cells()] = cliff
    t.cls = cls


def place(objs, t, pyrng):
    centre = (MID, MID)
    m = kit.Mirror(SIZE, SIZE)
    for slot, (row, east) in enumerate(SLOTS, start=1):
        f = mirror if east else (lambda p: p)
        bx, by = BASES[row]
        north = by < MID
        flank = [(MID - 160.0, 300.0), (1160.0, 330.0)] if row == 0 else \
            [(MID - 160.0, 3300.0), (1160.0, 3270.0)] if row == 2 else [(1180.0, 1200.0)]
        kit.ai_setup(objs, slot, f(BASES[row]),
                     center=[f(p) for p in ((MID - ISLAND_R, MID), (BRIDGE_X[0], MID), (ROAD_X, MID), (ROAD_X, by))],
                     flank=[f(p) for p in flank + [(ROAD_X, by)]],
                     backdoor=[f(p) for p in ((90.0, by + (480.0 if north else -480.0)), (120.0, by))])

    names = {"docks": [], "dozers": []}
    for row, base in enumerate(BASES):
        for east in (False, True):
            tag = f"{'E' if east else 'W'}{row + 1}"
            kit.base_kit(objs, m, mirror(base) if east else base, east, DOZERS[row][east], tag, pyrng, names,
                         centre)
    for (p, templates) in (FACTORY, POWER):
        for east in (False, True):
            x, y = mirror(p) if east else p
            objs.add(templates[east], x, y, math.atan2(MID - y, MID - x), radius=85 if "Factory" in templates[0] else 55)
    for p, template in TECH:
        for east in (False, True):
            x, y = mirror(p) if east else p
            objs.add(template, x, y, math.atan2(MID - y, MID - x), indestructible=True, radius=80)
    for a in SHORE_DERRICKS:
        for east in (False, True):
            x = MID + (LAKE_R + 110.0) * math.cos(math.radians(a))
            y = MID + (LAKE_R + 110.0) * math.sin(math.radians(a))
            if east:
                x = SIZE - x
            objs.add("TechOilDerrick", x, y, math.atan2(MID - y, MID - x), radius=35)
    for (px, py), r in MESAS:
        for east in (False, True):
            x, y = (SIZE - px, py) if east else (px, py)
            dx = 1.0 if (x < MID) else -1.0
            objs.add("TechOilDerrick", x - dx * (r + 90.0), y + (150.0 if y < MID else -150.0),
                     0.0, radius=35)
    for p, template in AIRFIELDS:
        objs.add(template, *p, math.pi / 2 if p[1] < MID else -math.pi / 2, radius=140)
    for p, template in SUPERWEAPONS:
        objs.add(template, *p, math.pi / 2 if p[1] < MID else -math.pi / 2, radius=75)
    objs.add("AmericaPowerPlant", MID, MID, 0.0, radius=50)

    for box, glas in COMPOUNDS:
        cy = (box[1] + box[3]) / 2
        gate = [((box[2], cy), 60.0)]
        kit.compound(objs, box, glas[0], gate, pyrng, centre)
        ebox = (SIZE - box[2], box[1], SIZE - box[0], box[3])
        kit.compound(objs, ebox, glas[1], [((SIZE - box[2], cy), 60.0)], pyrng, centre)
        objs.road("TwoLaneDark", [(box[2], cy), (ROAD_X, cy)])
        objs.road("TwoLaneDark", [(SIZE - box[2], cy), (SIZE - ROAD_X, cy)])

    for n, (p0, p1) in enumerate(bridge_ends(), start=1):
        objs.bridge("ConcreteFourLane", p0, p1, f"GXBridge{n}")
    for road in all_roads():
        objs.road("TwoLaneDark", road)
    kit.lamps(objs, all_roads())
    scatter(objs, t, pyrng)
    return names


def scatter(objs, t, pyrng):
    circles = [(x, y, r + 50) for x, y, r, _ in objs.footprints]
    for b in BASES:
        circles.append((*b, BASE_R + 20))
    for box, _ in COMPOUNDS:
        circles.append(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2, 230))
    for (p0, p1) in bridge_ends():
        for p in (p0, p1):
            circles.append((*p, 100))
    segments = [seg for road in all_roads() for seg in zip(road, road[1:])]
    cliffs = t.cliff_cells()

    def place_one(x, y, i, j, roll, pick):
        z = t.h[j, i] * mapgen.HEIGHT_SCALE
        if z < WATER_Z + 5 or cliffs[j, i] or kit.blocked(x, y, circles, segments, road_clear=50.0):
            return None
        r = math.hypot(x - MID, y - MID)
        if r < ISLAND_R - 40:
            return PALMS[int(pick * len(PALMS))] if roll < 0.25 else None
        if r < LAKE_R + 150 + 90 * t.green[j, i]:
            return PALMS[int(pick * len(PALMS))] if roll < 0.45 else None
        rise = t.h[j, i] - LAND
        if rise > 24:
            return ROCKS[int(pick * len(ROCKS))] if roll < 0.18 else None
        if roll < 0.05:
            return SHRUBS[int(pick * len(SHRUBS))]
        if roll < 0.058:
            return PALMS[int(pick * len(PALMS))]
        if roll < 0.07:
            return ROCKS[int(pick * len(ROCKS))]
        return None

    kit.scatter(objs, t, pyrng, SIZE, SIZE, BORDER, place_one)
    # Rock falls at the foot of the mesas; the west mesas' rocks are mirrored east.
    for (px, py), r in MESAS + CENTRE_MESAS:
        for k in range(14):
            a = pyrng.uniform(0, 2 * math.pi)
            d = r + pyrng.uniform(20, 70)
            x, y = px + d * math.cos(a), py + d * math.sin(a)
            template = pyrng.choice(ROCKS)
            if kit.blocked(x, y, circles, segments, road_clear=45.0):
                continue
            objs.add(template, x, y, a, owner=mapgen.NEUTRAL_TEAM)
            if px != MID:
                objs.add(template, SIZE - x, y, math.pi - a, owner=mapgen.NEUTRAL_TEAM)


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
