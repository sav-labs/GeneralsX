"""Frozen Divide: 8-player (2 vs 6) winter skirmish map after the scheme of "A River Divided".

GeneralsX @feature Claude 16/10/2026 Two strong bases in the north face six bases in the south
across a cold river, the way the map Artem likes most is set up: the two northern players are
the small team, the six southern slots are for the AI. The layout and terrain are our own:
- the northern bases get two unmanned, indestructible dozers of other generals each (any
  infantry can crew them), a bunker row and artillery in front, a fenced capturable GLA
  compound, a capturable war factory, airfield and power plant, and two capturable
  superweapons between them;
- a line of indestructible bunkers holds the whole northern river bank; three bridges cross,
  each with bunkers at its southern head;
- the six southern bases stand in two columns with supply docks, oil derricks run down the
  middle, and two more capturable superweapons sit between the columns.
The east half mirrors the west half.
"""

import math

import numpy as np

import kit
import mapgen

NAME = "GX Frozen Divide"
NAME_TAG = "MAP:GXFrozenDivide"
DISPLAY_NAME = "Frozen Divide"
PLAYERS = 8
SEED = 4208

WIDTH = 2600.0
HEIGHT = 4200.0
MID = WIDTH / 2
BORDER = 30
LAND = 60.0
WATER_Z = 24
RIVER_Y = 2900.0
RIVER_HW = 115.0
BRIDGES_X = [450.0, MID]  # west bridge (mirrored) and the centre bridge

# North (small team), west side.
NORTH_BASE = (450.0, 3650.0)
NORTH_FRAME = ((0.0, -1.0), (1.0, 0.0))  # the base kit faces south
SECOND_DOZER = (60.0, 250.0)  # base-kit offset (u, v) of the second dozer
NORTH_DOZERS = ("Boss_VehicleDozer", "Nuke_ChinaVehicleDozer")
COMPOUND_BOX = (770.0, 3850.0, 1180.0, 4110.0)
COMPOUND_GLA = ("Chem", "Slth")
FACTORY = ((900.0, 3600.0), ("ChinaWarFactory", "AmericaWarFactory"))
AIRFIELD = ((1010.0, 3270.0), ("AmericaAirfield", "ChinaAirfield"))
POWER = ((1180.0, 3620.0), ("AmericaPowerPlant", "ChinaPowerPlant"))
NORTH_SUPERWEAPONS = [((MID, 3900.0), "ChinaNuclearMissileLauncher"), ((MID, 3500.0), "AmericaParticleCannonUplink")]
BANK_BUNKER_Y = 3110.0

# South (six bases), west column; the east column mirrors it.
SOUTH_BASES = [(560.0, 2250.0), (560.0, 1400.0), (560.0, 550.0)]
SOUTH_DOCKS = [(-300.0, -130.0), (-300.0, 130.0)]  # offsets (dx, dy), west of the base
SOUTH_SUPERWEAPONS = [((MID, 1830.0), "GLAScudStorm"), ((MID, 975.0), "Lazr_AmericaParticleCannonUplink")]
SOUTH_TECH = [((MID, 2330.0), "TechHospital"), ((MID, 1400.0), "TechRepairbay")]
DERRICK_Y = [2250.0, 1250.0, 550.0]
# Player slots as on A River Divided: 1 and 2 north (east, west), 3-8 south in pairs.
SLOTS = [("N", True), ("N", False), (0, False), (0, True), (1, True), (1, False), (2, False), (2, True)]

ROADS = [
    [(450.0, 3540.0), (450.0, 3150.0)],
    [(450.0, 3150.0), (MID, 3150.0)],
    [(450.0, 2640.0), (560.0, 2360.0)],
    [(560.0, 2250.0), (560.0, 550.0)],
    [(560.0, 1400.0), (MID - 100.0, 1400.0)],
    [(MID, 2640.0), (MID, 2420.0)],
    [(MID, 2240.0), (MID, 1900.0)],
    [(560.0, 2250.0), (1000.0, 2420.0), (MID, 2420.0)],
    [(MID, 3150.0), (MID, 3400.0)],
]

TREES = ["TreeFir06Snow", "TreeFir07Snow", "TreeSpruce04Snow", "TreeSpruce05Snow", "TreePine4snow",
         "TreePine5snow", "TreeOak02Snow", "TreeMaple03Snow"]
ROCKS = ["RockClusterSmallSnow01", "RockClusterMediumSnow01", "RockClusterLargeSnow01"]
DOCK_VALUE = 100000


def mirror(p):
    return (WIDTH - p[0], p[1])


def river_centre(x):
    return RIVER_Y + 55.0 * np.cos((x - MID) / 330.0)


def all_roads():
    out = []
    for road in ROADS:
        out.append(road)
        if any(abs(p[0] - MID) > 1 for p in road):
            out.append([mirror(p) for p in road])
    return out


def bridge_ends():
    ends = []
    for x in BRIDGES_X:
        c = float(river_centre(x))
        p = ((x, c + RIVER_HW + 55.0), (x, c - RIVER_HW - 55.0))
        ends.append(p)
        if x != MID:
            ends.append((mirror(p[0]), mirror(p[1])))
    return ends


def heights(t, nprng):
    x, y = t.wx, t.wy
    fx = MID - np.abs(x - MID)
    noise = mapgen.value_noise((fx, y), 1000.0, nprng, octaves=4)
    h = LAND + (noise - 0.5) * 40.0
    edge = np.minimum(fx, np.minimum(y, HEIGHT - y))
    peaks = mapgen.value_noise((fx, y), 280.0, nprng, octaves=3)
    h += (45.0 + 70.0 * peaks) * mapgen.smoothstep(40.0, -160.0, edge)
    # Snowy hills between the southern columns and behind the northern bases.
    hills = mapgen.value_noise((fx, y), 360.0, nprng, octaves=3)
    h += 30.0 * mapgen.smoothstep(0.55, 0.8, hills)

    pads = []
    for east in (False, True):
        f = mirror if east else (lambda p: p)
        pads.append((f(NORTH_BASE), 360, LAND + 4))
        c = ((COMPOUND_BOX[0] + COMPOUND_BOX[2]) / 2, (COMPOUND_BOX[1] + COMPOUND_BOX[3]) / 2)
        pads.append((f(c), 230, LAND + 2))
        for p, r in ((FACTORY[0], 120), (AIRFIELD[0], 190), (POWER[0], 90)):
            pads.append((f(p), r, LAND + 2))
        for b in SOUTH_BASES:
            pads.append((f(b), 340, LAND))
    for p, _ in NORTH_SUPERWEAPONS + SOUTH_SUPERWEAPONS + SOUTH_TECH:
        pads.append((p, 110, LAND))
    h = kit.blend_pads(h, x, y, pads)

    # The river: a winding channel across the map with a low frozen bank on each side.
    c = river_centre(x)
    across = np.abs(y - c)
    bank = mapgen.smoothstep(RIVER_HW + 160.0, RIVER_HW + 20.0, across)
    h = h * (1 - bank) + (LAND - 4) * bank
    water = mapgen.smoothstep(RIVER_HW + 20.0, RIVER_HW - 10.0, across)
    h = h * (1 - water) + 14.0 * water
    for p0, p1 in bridge_ends():
        for px, py in (p0, p1):
            w = mapgen.smoothstep(90.0, 40.0, np.hypot(x - px, y - py))
            h = h * (1 - w) + LAND * w
    t.h = np.minimum(h, 250.0)


def textures(t, nprng):
    snow = t.texture("SnowType2")
    snow_b = t.texture("SnowType3")
    thaw = t.texture("GrassMediumType15")
    dirt = t.texture("DirtMediumType5")
    rocks = t.texture("RocksType2")
    bed = t.texture("SandMediumType9")
    concrete = t.texture("ConcreteType2")
    concrete_b = t.texture("ConcreteType4")
    asphalt = t.texture("AsphaltType2")
    cliff = t.texture("CliffMediumType1")

    x, y, h = t.wx + 5.0, t.wy + 5.0, t.h
    fx = MID - np.abs(x - MID)
    patch = mapgen.value_noise((fx, y), 420.0, nprng, octaves=3)
    patch2 = mapgen.value_noise((fx, y), 200.0, nprng, octaves=2)
    cls = np.full(h.shape, snow, dtype=np.int32)
    cls[patch > 0.56] = snow_b
    cls[(patch2 > 0.7) & (patch < 0.45)] = thaw
    t.forest_noise = mapgen.value_noise((fx, y), 300.0, nprng, octaves=3)
    rise = h - LAND
    cls[rise > 26 + 8 * patch2] = rocks

    for road in all_roads():
        for p0, p1 in zip(road, road[1:]):
            d = kit.segment_distance(x, y, p0, p1)
            cls[d < 34] = dirt
            cls[d < 20] = asphalt
    for east in (False, True):
        f = mirror if east else (lambda p: p)
        for b, r in [(NORTH_BASE, 130)] + [(b, 110) for b in SOUTH_BASES]:
            bx, by = f(b)
            d = np.hypot(x - bx, y - by)
            cls[d < r] = concrete
            cls[(d >= r) & (d < r + 50)] = dirt
        ax, ay = f(AIRFIELD[0])
        cls[np.hypot(x - ax, y - ay) < 150] = concrete_b
        x0, y0, x1, y1 = COMPOUND_BOX
        if east:
            x0, x1 = WIDTH - x1, WIDTH - x0
        cls[(x > x0 + 30) & (x < x1 - 30) & (y > y0 + 30) & (y < y1 - 30) & (patch2 > 0.45)] = dirt
    for p, _ in NORTH_SUPERWEAPONS + SOUTH_SUPERWEAPONS:
        cls[np.hypot(x - p[0], y - p[1]) < 100] = concrete_b

    z = h * mapgen.HEIGHT_SCALE
    cls[z < WATER_Z + 5] = bed
    cls[t.cliff_cells()] = cliff
    t.cls = cls


def place(objs, t, pyrng):
    m = kit.Mirror(WIDTH, HEIGHT)
    centre = (MID, RIVER_Y)
    for slot, (row, east) in enumerate(SLOTS, start=1):
        f = mirror if east else (lambda p: p)
        if row == "N":
            base = f(NORTH_BASE)
            kit.ai_setup(objs, slot, base,
                         center=[f(p) for p in ((MID, 2700.0), (MID, 3150.0), (450.0, 3150.0))],
                         flank=[f(p) for p in ((450.0, 2640.0), (450.0, 3150.0))],
                         backdoor=[f(p) for p in ((120.0, 3150.0), (150.0, 3500.0))])
        else:
            bx, by = SOUTH_BASES[row]
            base = f((bx, by))
            kit.ai_setup(objs, slot, base, inner=300, outer=480,
                         center=[f(p) for p in ((MID, 3150.0), (MID, 2420.0), (1000.0, 2420.0), (560.0, by + 200.0))],
                         flank=[f(p) for p in ((450.0, 3150.0), (450.0, 2640.0), (560.0, by + 200.0))],
                         backdoor=[f(p) for p in ((MID, by), (900.0, by))])

    names = {"docks": [], "dozers": []}
    for east in (False, True):
        f = mirror if east else (lambda p: p)
        tag = "NE" if east else "NW"
        bx, by = f(NORTH_BASE)
        kit.base_kit(objs, m, (bx, by), east, NORTH_DOZERS[0], tag, pyrng, names, centre, frame=NORTH_FRAME)
        (fx, fy), (sx, sy) = NORTH_FRAME
        u, v = SECOND_DOZER
        x, y = bx + fx * u + sx * v, by + fy * u + sy * v
        name = f"GXDozer{tag}2"
        objs.add(NORTH_DOZERS[1], x, y, m.facing(x, y, centre), indestructible=True, name=name, radius=30)
        names["dozers"].append(name)
        for (p, templates), r in ((FACTORY, 85), (AIRFIELD, 140), (POWER, 55)):
            x, y = f(p)
            objs.add(templates[east], x, y, -math.pi / 2, radius=r)
        x0, y0, x1, y1 = COMPOUND_BOX
        box = (WIDTH - x1, y0, WIDTH - x0, y1) if east else COMPOUND_BOX
        gate_x = box[0] if not east else box[2]
        gate_y = (y0 + y1) / 2
        kit.compound(objs, (box[0], box[1], box[2], box[3]), COMPOUND_GLA[east], [((gate_x, gate_y), 60.0)],
                     pyrng, centre)
        for row, b in enumerate(SOUTH_BASES):
            bx, by = f(b)
            for i, (dx, dy) in enumerate(SOUTH_DOCKS):
                x, y = bx + (-dx if east else dx), by + dy
                name = f"GXDockS{'E' if east else 'W'}{row + 1}{i + 1}"
                objs.add("SupplyDock", x, y, m.facing(x, y, (bx, by)), owner=mapgen.NEUTRAL_TEAM,
                         indestructible=True, name=name, radius=70)
                names["docks"].append(name)
        for yy in DERRICK_Y:
            x, y = f((MID - 90.0, yy))
            objs.add("TechOilDerrick", x, y, 0.0, radius=35)

    for p, template in NORTH_SUPERWEAPONS + SOUTH_SUPERWEAPONS:
        objs.add(template, *p, -math.pi / 2 if p[1] > RIVER_Y else math.pi / 2, radius=75)
    for p, template in SOUTH_TECH:
        objs.add(template, *p, 0.0, indestructible=True, radius=80)

    # Bunkers along the whole northern bank, clear of the bridges; pairs at the southern heads.
    x = 140.0
    while x <= MID:
        if all(abs(x - bx) > 120 for bx in BRIDGES_X) and all(
                math.hypot(x - fx_, BANK_BUNKER_Y - fy_) > fr + 50 for fx_, fy_, fr, _ in objs.footprints):
            for p in ([(x, BANK_BUNKER_Y)] if abs(x - MID) < 1 else [(x, BANK_BUNKER_Y), mirror((x, BANK_BUNKER_Y))]):
                objs.add("CivilianBunker01", *p, -math.pi / 2, owner=mapgen.NEUTRAL_TEAM, indestructible=True,
                         radius=45)
        x += 165.0
    for p0, p1 in bridge_ends():
        sx_, sy_ = p1
        for d in (-110.0, 110.0):
            objs.add("CivilianBunker01", sx_ + d, sy_ - 40.0, math.pi / 2, owner=mapgen.NEUTRAL_TEAM,
                     indestructible=True, radius=45)

    for n, (p0, p1) in enumerate(bridge_ends(), start=1):
        objs.bridge("ConcreteFourLane", p0, p1, f"GXBridge{n}")
    for road in all_roads():
        objs.road("TwoLaneDark", road)
    kit.lamps(objs, all_roads())
    scatter(objs, t, pyrng)
    return names


def scatter(objs, t, pyrng):
    circles = [(x, y, r + 50) for x, y, r, _ in objs.footprints]
    for east in (False, True):
        f = mirror if east else (lambda p: p)
        circles.append((*f(NORTH_BASE), 380))
        for b in SOUTH_BASES:
            circles.append((*f(b), 350))
        c = ((COMPOUND_BOX[0] + COMPOUND_BOX[2]) / 2, (COMPOUND_BOX[1] + COMPOUND_BOX[3]) / 2)
        circles.append((*f(c), 250))
    for p0, p1 in bridge_ends():
        for p in (p0, p1):
            circles.append((*p, 110))
    segments = [seg for road in all_roads() for seg in zip(road, road[1:])]
    cliffs = t.cliff_cells()

    def place_one(x, y, i, j, roll, pick):
        z = t.h[j, i] * mapgen.HEIGHT_SCALE
        if z < WATER_Z + 6 or cliffs[j, i] or kit.blocked(x, y, circles, segments):
            return None
        if abs(y - float(river_centre(x))) < RIVER_HW + 120 and roll > 0.06:
            return None
        rise = t.h[j, i] - LAND
        if rise > 26:
            if roll < 0.2:
                return TREES[int(pick * 4)]
            return ROCKS[int(pick * len(ROCKS))] if roll < 0.3 else None
        if (t.forest_noise[j, i] > 0.55 and roll < 0.55) or roll < 0.025:
            return TREES[int(pick * len(TREES))]
        if roll < 0.04:
            return ROCKS[int(pick * len(ROCKS))]
        return None

    kit.scatter(objs, t, pyrng, WIDTH, HEIGHT, BORDER, place_one)


def generate():
    pyrng, nprng = mapgen.rng(SEED)
    t = mapgen.Terrain(int(WIDTH / mapgen.CELL), int(HEIGHT / mapgen.CELL), BORDER)
    t.water_z = WATER_Z
    heights(t, nprng)
    textures(t, nprng)
    objs = mapgen.Objects()
    names = place(objs, t, pyrng)
    kit.water_plane(objs, WIDTH, HEIGHT, BORDER, WATER_Z)
    data = kit.finish(t, objs, NAME_TAG, names, DOCK_VALUE)
    return data, t, objs
