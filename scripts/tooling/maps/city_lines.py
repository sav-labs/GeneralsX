"""City Lines: 8-player (4 vs 4) city skirmish map with the Twin Rivers mechanics.

GeneralsX @feature Claude 16/10/2026 Four bases on the west edge face four on the east edge
across a city of street blocks lined with garrisonable buildings. What every base gets, as on
Twin Rivers Fortress: indestructible bunkers and artillery in front, an unmanned,
indestructible dozer of another general, and supply docks with large reserves. Each side's
half of the city holds a capturable airfield, a fenced GLA compound, a war factory and a power
plant, and the city centre a park with two capturable superweapons; two more stand in the
middle blocks to the north and south. The east half mirrors the west half.
"""

import math

import numpy as np

import kit
import mapgen

NAME = "GX City Lines"
NAME_TAG = "MAP:GXCityLines"
DISPLAY_NAME = "City Lines"
PLAYERS = 8
SEED = 3612

SIZE = 3600.0
MID = SIZE / 2
BORDER = 30
LAND = 60.0
WATER_Z = 20

BASE_YS = [500.0, 1350.0, 2250.0, 3100.0]
BASE_X = 450.0
DOZERS = [("Boss_VehicleDozer", "Lazr_AmericaVehicleDozer"), ("Tank_ChinaVehicleDozer", "Infa_ChinaVehicleDozer"),
          ("AirF_AmericaVehicleDozer", "SupW_AmericaVehicleDozer"), ("Nuke_ChinaVehicleDozer", "ChinaVehicleDozer")]
SLOTS = [(r, False) for r in range(4)] + [(r, True) for r in range(4)]

# The city: avenues (x) and streets (y) on the west half; the east half mirrors them.
CITY_X0 = 1000.0
AVENUES = [CITY_X0, 1500.0]
STREETS = BASE_YS
STREET_HALF = 55.0  # building setback from a road centre line
PLAZA_R = 300.0

# Capturable buildings in the west half's blocks (block column 0 = between the avenues).
AIRFIELD = ((1250.0, 925.0), ("AmericaAirfield", "ChinaAirfield"))
COMPOUND_BOX = (1060.0, 1600.0, 1440.0, 2000.0)
COMPOUND_GLA = ("Chem", "Slth")
FACTORY = ((1250.0, 2560.0), ("ChinaWarFactory", "AmericaWarFactory"))
POWER = ((1250.0, 2840.0), ("AmericaPowerPlant", "ChinaPowerPlant"))
TECH = [((1650.0, 1520.0), "TechHospital"), ((1650.0, 2080.0), "TechRepairbay")]
DERRICKS = [(1580.0, 600.0), (1580.0, 3000.0)]
SUPERWEAPONS = [((MID, 1660.0), "ChinaNuclearMissileLauncher"), ((MID, 1940.0), "AmericaParticleCannonUplink"),
                ((MID, 925.0), "GLAScudStorm"), ((MID, 2675.0), "Lazr_AmericaParticleCannonUplink")]

# Garrisonable civilian buildings: (template, half size x, half size y) from the retail Geometry.
BUILDINGS = [("GermanTownHouse1", 25, 16), ("GermanTownHouse2", 27, 16), ("GermanPub02", 29, 19),
             ("StanApartment01", 50, 25), ("StanApartment02", 26, 22), ("StanHotel01", 37, 29),
             ("EuroHighrise", 43, 36), ("CivilianHighrise01", 29, 18), ("CivilianHighrise02", 31, 29),
             ("AmericanHome01", 50, 30), ("AmericanFastFood", 29, 28), ("AsianOffice02", 42, 42),
             ("SovietBuilding", 51, 36), ("EuropeanParkingGarage", 46, 24), ("GermanTownHall", 35, 49)]
CARS = ["CarSedan01", "CarCompact", "CarTaxiCab01", "CarEuroVan1", "CarLuxury01", "CarSUV01"]
STREET_PROPS = ["ParkBench", "BusStop", "PhoneBooth", "TrashCanA", "MailBox"]
TREES = ["TreeOak02", "TreeMaple06", "TreeBirch02", "TreeDogwood8"]
DOCK_VALUE = 100000


def mirror(p):
    return (SIZE - p[0], p[1])


def same(p):
    return p


def west_roads():
    roads = [[(560.0, y), (MID, y)] for y in STREETS]
    for x in AVENUES:
        roads.append([(x, STREETS[0]), (x, STREETS[-1])])
    return roads


def all_roads():
    out = []
    for road in west_roads():
        out.append(road)
        if any(abs(p[0] - MID) > 1 for p in road):
            out.append([mirror(p) for p in road])
    return out


def blocks():
    """West-half city blocks (x0, y0, x1, y1) between road centre lines."""
    xs = AVENUES + [MID]
    out = []
    for i in range(len(xs) - 1):
        for j in range(len(STREETS) - 1):
            out.append((xs[i], STREETS[j], xs[i + 1], STREETS[j + 1]))
    return out


def reserved_west():
    """Areas in the west half that hold capturable buildings or the plaza: (x, y, radius)."""
    out = [(*AIRFIELD[0], 190), (*FACTORY[0], 130), (*POWER[0], 90), (MID, MID, PLAZA_R + 40)]
    x0, y0, x1, y1 = COMPOUND_BOX
    out.append(((x0 + x1) / 2, (y0 + y1) / 2, 300))
    out += [(p[0], p[1], 110) for p, _ in TECH]
    out += [(p[0], p[1], 70) for p in DERRICKS]
    out += [(p[0], p[1], 120) for p, _ in SUPERWEAPONS]
    return out


def heights(t, nprng):
    x, y = t.wx, t.wy
    fx = MID - np.abs(x - MID)
    noise = mapgen.value_noise((fx, y), 900.0, nprng, octaves=4)
    h = LAND + (noise - 0.5) * 30.0
    edge = np.minimum(fx, np.minimum(y, SIZE - y))
    peaks = mapgen.value_noise((fx, y), 280.0, nprng, octaves=3)
    h += (45.0 + 70.0 * peaks) * mapgen.smoothstep(40.0, -160.0, edge)
    # The city is level; the ground eases into it.
    city = mapgen.smoothstep(CITY_X0 - 220.0, CITY_X0 - 40.0, fx) * mapgen.smoothstep(
        STREETS[0] - 260.0, STREETS[0] - 80.0, y) * mapgen.smoothstep(STREETS[-1] + 260.0, STREETS[-1] + 80.0, y)
    h = h * (1 - city) + LAND * city
    pads = [(f((BASE_X, by)), 360, LAND + 2) for by in BASE_YS for f in (same, mirror)]
    h = kit.blend_pads(h, x, y, pads)
    t.h = np.minimum(h, 250.0)


def textures(t, nprng):
    grass = t.texture("GrassMediumType2")
    grass_b = t.texture("GrassMediumType11")
    park = t.texture("GrassMediumType25")
    dirt = t.texture("DirtMediumType5")
    pavement = t.texture("ConcreteType1")
    yard = t.texture("ConcreteType4")
    asphalt = t.texture("AsphaltType1")
    concrete = t.texture("ConcreteMediumType1")
    cliff = t.texture("CliffLargeType1")
    rocks = t.texture("RocksType2")

    x, y, h = t.wx + 5.0, t.wy + 5.0, t.h
    fx = MID - np.abs(x - MID)
    patch = mapgen.value_noise((fx, y), 400.0, nprng, octaves=3)
    patch2 = mapgen.value_noise((fx, y), 200.0, nprng, octaves=2)
    cls = np.full(h.shape, grass, dtype=np.int32)
    cls[patch > 0.58] = grass_b
    cls[(patch < 0.33) & (patch2 > 0.5)] = dirt
    in_city = (fx > CITY_X0 - 40) & (y > STREETS[0] - 40) & (y < STREETS[-1] + 40)
    cls[in_city] = pavement
    cls[in_city & (patch2 > 0.62)] = yard
    r = np.hypot(x - MID, y - MID)
    cls[r < PLAZA_R] = park
    t.cliff_mask = t.cliff_cells()
    cls[(h - LAND) > 30] = rocks
    for road in all_roads():
        for p0, p1 in zip(road, road[1:]):
            d = kit.segment_distance(x, y, p0, p1)
            cls[(d < 36) & ~in_city] = dirt
            cls[d < 26] = asphalt
    for by in BASE_YS:
        for f in (same, mirror):
            bx, bby = f((BASE_X, by))
            d = np.hypot(x - bx, y - bby)
            cls[d < 120] = concrete
            cls[(d >= 120) & (d < 170)] = dirt
    for p, _ in SUPERWEAPONS:
        cls[np.hypot(x - p[0], y - p[1]) < 95] = concrete
    cls[t.cliff_mask] = cliff
    t.cls = cls


def place(objs, t, pyrng):
    m = kit.Mirror(SIZE, SIZE)
    centre = (MID, MID)
    for slot, (row, east) in enumerate(SLOTS, start=1):
        f = mirror if east else same
        by = BASE_YS[row]
        north = by < MID
        side_y = STREETS[row + 1] if north else STREETS[row - 1]
        kit.ai_setup(objs, slot, f((BASE_X, by)),
                     center=[f(p) for p in ((MID - PLAZA_R, MID), (AVENUES[1], MID), (AVENUES[1], by),
                                            (CITY_X0, by), (850.0, by))],
                     flank=[f(p) for p in ((AVENUES[1], side_y), (CITY_X0, side_y), (CITY_X0, by), (850.0, by))],
                     backdoor=[f(p) for p in ((120.0, by + (420.0 if north else -420.0)), (150.0, by))])

    names = {"docks": [], "dozers": []}
    for row, by in enumerate(BASE_YS):
        for east in (False, True):
            base = mirror((BASE_X, by)) if east else (BASE_X, by)
            kit.base_kit(objs, m, base, east, DOZERS[row][east], f"{'E' if east else 'W'}{row + 1}", pyrng,
                         names, centre)
    for east in (False, True):
        f = mirror if east else same
        for (p, templates), r in ((AIRFIELD, 140), (FACTORY, 85), (POWER, 55)):
            x, y = f(p)
            objs.add(templates[east], x, y, math.atan2(MID - y, MID - x), radius=r)
        x0, y0, x1, y1 = COMPOUND_BOX
        box = (SIZE - x1, y0, SIZE - x0, y1) if east else COMPOUND_BOX
        gate = ((box[0] if not east else box[2]), (y0 + y1) / 2)
        kit.compound(objs, box, COMPOUND_GLA[east], [(gate, 60.0)], pyrng, centre)
        for p, template in TECH:
            x, y = f(p)
            objs.add(template, x, y, math.atan2(MID - y, MID - x), indestructible=True, radius=80)
        for p in DERRICKS:
            x, y = f(p)
            objs.add("TechOilDerrick", x, y, 0.0, radius=35)
    for p, template in SUPERWEAPONS:
        objs.add(template, *p, math.pi / 2 if p[1] < MID else -math.pi / 2, radius=75)
    objs.add("AmericaPowerPlant", MID, MID, 0.0, radius=50)

    for road in all_roads():
        objs.road("TwoLaneDark", road)
    city(objs, pyrng)
    kit.lamps(objs, all_roads(), spacing=150.0)
    plaza(objs, pyrng)
    scatter(objs, t, pyrng)
    return names


def city(objs, pyrng):
    """Fill every west-half block with rows of buildings (mirrored east), leaving alleys, and park
    cars and street furniture along the kerbs."""
    reserved = reserved_west()
    for bx0, by0, bx1, by1 in blocks():
        x0, x1 = bx0 + STREET_HALF, bx1 - STREET_HALF
        if abs(bx1 - MID) < 1:
            x1 = bx1 - 20.0  # the mirrored half continues the block across the centre line
        y = by0 + STREET_HALF
        while True:
            row = []
            cursor = x0
            tallest = 0.0
            while True:
                template, hx, hy = pyrng.choice(BUILDINGS)
                if cursor + 2 * hx > x1:
                    break
                row.append((template, cursor + hx, hx, hy))
                tallest = max(tallest, hy)
                cursor += 2 * hx + pyrng.uniform(14.0, 30.0)
            if not row or y + 2 * tallest > by1 - STREET_HALF:
                break
            cy = y + tallest
            for template, cx, hx, hy in row:
                if any(math.hypot(cx - rx, cy - ry) < rr + max(hx, hy) for rx, ry, rr in reserved):
                    continue
                angle = 0.0 if pyrng.random() < 0.5 else math.pi
                for p in ((cx, cy), mirror((cx, cy))):
                    objs.add(template, *p, angle, radius=min(hx, hy))
            y += 2 * tallest + 46.0  # alley
    # Parked cars and street furniture along the streets, clear of junctions.
    for road in west_roads():
        (ax, ay), (bx, by) = road
        length = math.hypot(bx - ax, by - ay)
        ux, uy = (bx - ax) / length, (by - ay) / length
        nx, ny = -uy, ux
        s = 140.0
        while s < length - 60:
            px, py = ax + ux * s, ay + uy * s
            if abs(px - MID) > 40 and fx_in_city(px) and all(
                    math.hypot(px - jx, py - jy) > 90 for jx in AVENUES for jy in STREETS):
                side = 1 if pyrng.random() < 0.5 else -1
                qx, qy = px + nx * 36 * side, py + ny * 36 * side
                if pyrng.random() < 0.6:
                    template = pyrng.choice(CARS)
                    angle = math.atan2(uy, ux)
                else:
                    template = pyrng.choice(STREET_PROPS)
                    qx, qy = px + nx * 46 * side, py + ny * 46 * side
                    angle = math.atan2(-ny * side, -nx * side)
                if all(math.hypot(qx - fx, qy - fy) > fr + 12 for fx, fy, fr, _ in objs.footprints):
                    objs.add(template, qx, qy, angle, owner=mapgen.NEUTRAL_TEAM)
                    mx, my = mirror((qx, qy))
                    objs.add(template, mx, my, math.pi - angle, owner=mapgen.NEUTRAL_TEAM)
            s += pyrng.uniform(70.0, 130.0)


def fx_in_city(x):
    return CITY_X0 + 30 < x < SIZE - CITY_X0 - 30


def plaza(objs, pyrng):
    """A ring of park trees and benches around the central plaza."""
    for k in range(36):
        a = k * math.pi * 2 / 36
        r = PLAZA_R - 25.0
        x, y = MID + r * math.cos(a), MID + r * math.sin(a)
        if all(math.hypot(x - fx, y - fy) > fr + 15 for fx, fy, fr, _ in objs.footprints) and abs(y - MID) > 50:
            objs.add(TREES[k % len(TREES)], x, y, a, owner=mapgen.NEUTRAL_TEAM)


def scatter(objs, t, pyrng):
    circles = [(x, y, r + 50) for x, y, r, _ in objs.footprints]
    for by in BASE_YS:
        circles.append((BASE_X, by, 380))
    segments = [seg for road in all_roads() for seg in zip(road, road[1:])]
    forest = mapgen.value_noise((MID - np.abs(t.wx - MID), t.wy), 320.0, np.random.RandomState(SEED + 1), octaves=3)

    def place_one(x, y, i, j, roll, pick):
        if x > CITY_X0 - 80 and STREETS[0] - 120 < y < STREETS[-1] + 120:
            return None
        if t.cliff_mask[j, i] or kit.blocked(x, y, circles, segments):
            return None
        if forest[j, i] > 0.55 or roll < 0.03:
            return ["TreeOak02", "TreeBirch02", "TreeSpruce04", "TreeMaple06", "TreeFir05"][int(pick * 5)]
        if t.h[j, i] - LAND > 25 and roll < 0.2:
            return ["RocksG02", "RocksG14", "Rocks3Brown"][int(pick * 3)]
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
