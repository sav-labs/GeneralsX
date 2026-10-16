"""Forest Duel: 2-player (1 vs 1) skirmish map with the Twin Rivers mechanics.

GeneralsX @feature Claude 16/10/2026 Two bases face each other across a forested valley. Each
base gets indestructible bunkers and artillery in front, supply docks with large reserves and
two unmanned, indestructible dozers of other generals, so one player can build for three
generals at once. Between each base and the centre stand a capturable airfield, war factory,
power plant, hospital, repair bay and two fenced GLA compounds. On a low plateau in the middle
two superweapons and a power plant wait to be captured, with two more superweapons at the north
and south end of the centre line and forest ponds between them. The east half mirrors the west
half, so both start positions are equal.
"""

import math

import numpy as np

import kit
import mapgen

NAME = "GX Forest Duel"
NAME_TAG = "MAP:GXForestDuel"
DISPLAY_NAME = "Forest Duel"
PLAYERS = 2
SEED = 2202

SIZE = 2800.0
MID = SIZE / 2
BORDER = 30
LAND = 60.0
WATER_Z = 24
PLATEAU_R = 300.0
PLATEAU_H = 22.0
PONDS = [((MID, 930.0), 140.0), ((MID, 1870.0), 140.0)]

# West half (east mirrors x).
BASE = (450.0, 1400.0)
BASE_R = 360.0
DOZERS = (("Boss_VehicleDozer", "Nuke_ChinaVehicleDozer"), ("Tank_ChinaVehicleDozer", "Lazr_AmericaVehicleDozer"))
SECOND_DOZER = (60.0, 250.0)  # base-kit offset (u, v) of the second dozer
COMPOUNDS = [((120.0, 2000.0, 520.0, 2300.0), ("Chem", "Slth")), ((120.0, 500.0, 520.0, 800.0), ("Demo", ""))]
AIRFIELD = ((1180.0, 520.0), ("AmericaAirfield", "ChinaAirfield"))
FACTORY = ((1180.0, 2280.0), ("ChinaWarFactory", "AmericaWarFactory"))
POWER = ((1250.0, 1000.0), ("AmericaPowerPlant", "ChinaPowerPlant"))
TECH = [((700.0, 2000.0), "TechHospital"), ((700.0, 800.0), "TechRepairbay")]
DERRICKS = [(1250.0, 1800.0), (850.0, 250.0), (850.0, 2550.0)]
ROAD_X = 1000.0
SUPERWEAPONS = [((MID, 1260.0), "ChinaNuclearMissileLauncher"), ((MID, 1540.0), "AmericaParticleCannonUplink"),
                ((MID, 520.0), "GLAScudStorm"), ((MID, 2280.0), "Lazr_AmericaParticleCannonUplink")]
SLOTS = [False, True]

ROADS = [
    [(560.0, MID), (ROAD_X, MID), (MID - PLATEAU_R, MID)],
    [(ROAD_X, 520.0), (ROAD_X, 2280.0)],
    [(ROAD_X, 2280.0), (1110.0, 2280.0)],
    [(ROAD_X, 1000.0), (1170.0, 1000.0)],
]

TREES = ["TreeOak02", "TreeBirch02", "TreeSpruce04", "TreeSpruce05", "TreeMaple06", "TreeFir05", "TreeDogwood8"]
ROCKS = ["Rocks1Brown", "Rocks2Brown", "Rocks3Brown", "RockClusterSmall01", "RockClusterMedium01"]
DOCK_VALUE = 100000


def mirror(p):
    return (SIZE - p[0], p[1])


def all_roads():
    return [r for road in ROADS for r in (road, [mirror(p) for p in road])]


def heights(t, nprng):
    x, y = t.wx, t.wy
    fx = MID - np.abs(x - MID)
    noise = mapgen.value_noise((fx, y), 900.0, nprng, octaves=4)
    h = LAND + (noise - 0.5) * 44.0
    edge = np.minimum(fx, np.minimum(y, SIZE - y))
    peaks = mapgen.value_noise((fx, y), 260.0, nprng, octaves=3)
    h += (40.0 + 60.0 * peaks) * mapgen.smoothstep(40.0, -160.0, edge)

    r = np.hypot(x - MID, y - MID)
    h += PLATEAU_H * mapgen.smoothstep(PLATEAU_R + 140.0, PLATEAU_R, r)

    pads = [(b, BASE_R, LAND + 2) for b in (BASE, mirror(BASE))]
    for box, _ in COMPOUNDS:
        c = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        pads += [(c, 200, LAND), (mirror(c), 200, LAND)]
    for p in (FACTORY[0], POWER[0]) + tuple(p for p, _ in TECH) + tuple(DERRICKS):
        pads += [(p, 110, LAND), (mirror(p), 110, LAND)]
    pads += [(AIRFIELD[0], 190, LAND), (mirror(AIRFIELD[0]), 190, LAND)]
    pads += [(SUPERWEAPONS[2][0], 110, LAND), (SUPERWEAPONS[3][0], 110, LAND)]
    for road in all_roads():
        for p in road:
            if math.hypot(p[0] - MID, p[1] - MID) > PLATEAU_R + 50:
                pads.append((p, 60, LAND))
    h = kit.blend_pads(h, x, y, pads)

    shore = mapgen.value_noise((fx, y), 90.0, nprng, octaves=2)
    for (px, py), pr in PONDS:
        d = np.hypot(x - px, y - py) + (shore - 0.5) * 50.0
        bank = mapgen.smoothstep(pr + 110.0, pr + 10.0, d)
        h = h * (1 - bank) + (LAND - 4) * bank
        water = mapgen.smoothstep(pr + 10.0, pr - 40.0, d)
        h = h * (1 - water) + 14.0 * water
    t.h = np.minimum(h, 250.0)


def textures(t, nprng):
    grass = t.texture("GrassMediumType2")
    grass_b = t.texture("GrassMediumType11")
    grass_c = t.texture("GrassMediumType25")
    forest = t.texture("GrassMediumType31")
    dirt = t.texture("DirtMediumType5")
    bed = t.texture("SandMediumType9")
    rocky = t.texture("RocksType2")
    concrete = t.texture("ConcreteType1")
    cliff = t.texture("CliffLargeType1")

    x, y, h = t.wx + 5.0, t.wy + 5.0, t.h
    fx = MID - np.abs(x - MID)
    patch = mapgen.value_noise((fx, y), 420.0, nprng, octaves=3)
    patch2 = mapgen.value_noise((fx, y), 200.0, nprng, octaves=2)
    t.forest_noise = mapgen.value_noise((fx, y), 330.0, nprng, octaves=3)
    cls = np.full(h.shape, grass, dtype=np.int32)
    cls[patch > 0.58] = grass_b
    cls[(patch2 > 0.63) & (patch < 0.5)] = grass_c
    cls[t.forest_noise > 0.52] = forest
    cls[h - LAND > 30 + 10 * patch2] = rocky

    for road in all_roads():
        for p0, p1 in zip(road, road[1:]):
            cls[kit.segment_distance(x, y, p0, p1) < 32] = dirt
    for bx, by in (BASE, mirror(BASE)):
        d = np.hypot(x - bx, y - by)
        cls[d < 120] = concrete
        cls[(d >= 120) & (d < 170)] = dirt
    for px, py in (AIRFIELD[0], mirror(AIRFIELD[0])):
        cls[np.hypot(x - px, y - py) < 150] = concrete
    cls[np.hypot(x - MID, y - MID) < 120] = concrete

    z = h * mapgen.HEIGHT_SCALE
    cls[z < WATER_Z + 5] = bed
    cls[t.cliff_cells()] = cliff
    t.cls = cls


def place(objs, t, pyrng):
    centre = (MID, MID)
    m = kit.Mirror(SIZE, SIZE)
    for slot, east in enumerate(SLOTS, start=1):
        f = mirror if east else (lambda p: p)
        kit.ai_setup(objs, slot, f(BASE),
                     center=[f(p) for p in ((MID - PLATEAU_R, MID), (ROAD_X, MID))],
                     flank=[f(p) for p in ((MID, 520.0), (ROAD_X, 520.0), (ROAD_X, MID))],
                     backdoor=[f(p) for p in ((MID, 2280.0), (ROAD_X, 2280.0), (ROAD_X, MID))])

    names = {"docks": [], "dozers": []}
    for east in (False, True):
        f = mirror if east else (lambda p: p)
        tag = "E" if east else "W"
        bx, by = f(BASE)
        kit.base_kit(objs, m, (bx, by), east, DOZERS[0][east], tag, pyrng, names, centre)
        u, v = SECOND_DOZER
        x, y = bx + (-u if east else u), by + v
        name = f"GXDozer{tag}2"
        objs.add(DOZERS[1][east], x, y, m.facing(x, y, centre), indestructible=True, name=name, radius=30)
        names["dozers"].append(name)
        for (p, templates), r in ((AIRFIELD, 140), (FACTORY, 85), (POWER, 55)):
            x, y = f(p)
            objs.add(templates[east], x, y, math.atan2(MID - y, MID - x), radius=r)
        for p, template in TECH:
            x, y = f(p)
            objs.add(template, x, y, math.atan2(MID - y, MID - x), indestructible=True, radius=80)
        for p in DERRICKS:
            x, y = f(p)
            objs.add("TechOilDerrick", x, y, math.atan2(MID - y, MID - x), radius=35)
    for p, template in SUPERWEAPONS:
        objs.add(template, *p, math.pi / 2 if p[1] < MID else -math.pi / 2, radius=75)
    objs.add("AmericaPowerPlant", MID, MID, 0.0, radius=50)

    for box, glas in COMPOUNDS:
        cy = (box[1] + box[3]) / 2
        kit.compound(objs, box, glas[0], [((box[2], cy), 60.0)], pyrng, centre)
        ebox = (SIZE - box[2], box[1], SIZE - box[0], box[3])
        kit.compound(objs, ebox, glas[1], [((SIZE - box[2], cy), 60.0)], pyrng, centre)
        objs.road("TwoLaneDark", [(box[2], cy), (ROAD_X, cy)])
        objs.road("TwoLaneDark", [(SIZE - box[2], cy), (SIZE - ROAD_X, cy)])

    for road in all_roads():
        objs.road("TwoLaneDark", road)
    kit.lamps(objs, all_roads())
    scatter(objs, t, pyrng)
    return names


def scatter(objs, t, pyrng):
    circles = [(x, y, r + 50) for x, y, r, _ in objs.footprints]
    for b in (BASE, mirror(BASE)):
        circles.append((*b, BASE_R + 20))
    for box, _ in COMPOUNDS:
        c = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        circles += [(*c, 230), (*mirror(c), 230)]
    circles.append((MID, MID, PLATEAU_R - 60))
    segments = [seg for road in all_roads() for seg in zip(road, road[1:])]
    for box, _ in COMPOUNDS:
        cy = (box[1] + box[3]) / 2
        segments += [((box[2], cy), (ROAD_X, cy)), ((SIZE - box[2], cy), (SIZE - ROAD_X, cy))]
    cliffs = t.cliff_cells()

    def place_one(x, y, i, j, roll, pick):
        z = t.h[j, i] * mapgen.HEIGHT_SCALE
        if z < WATER_Z + 6 or cliffs[j, i] or kit.blocked(x, y, circles, segments, road_clear=55.0):
            return None
        if t.forest_noise[j, i] > 0.52:
            return TREES[int(pick * len(TREES))] if roll < 0.7 else None
        if t.h[j, i] - LAND > 30:
            return ROCKS[int(pick * len(ROCKS))] if roll < 0.2 else None
        if roll < 0.04:
            return TREES[int(pick * len(TREES))]
        if roll < 0.05:
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
