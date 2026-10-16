"""Twin Rivers Fortress: 8-player skirmish map in the spirit of "A River Divided".

GeneralsX @feature Claude 16/10/2026 Two rivers cross in the middle and cut the map into four
quadrants with two bases each. What the layout keeps from the maps Artem likes:
- indestructible garrisonable bunkers and artillery platforms on the river banks in front of
  every base, plus bunkers at every bridge head;
- next to each base an unmanned, indestructible dozer of another general (any infantry can
  climb in and the player can then build that general's base as well);
- behind each pair of bases a capturable command centre and barracks of a GLA general, which
  gives GLA workers to whoever captures it;
- capturable war factories, airfields and power plants in every quadrant and four capturable
  superweapons on the island where the rivers meet;
- supply docks with large reserves and oil derricks.
The four quadrants are mirror images, so every start position is equal. The layout is written
for the north-west quadrant in local coordinates (a from the west edge, b from the north
edge) and mirrored.
"""

import math

import numpy as np

import mapgen

NAME = "GX Twin Rivers Fortress"
NAME_TAG = "MAP:GXTwinRiversFortress"
DISPLAY_NAME = "Twin Rivers Fortress"
SEED = 1610

SIZE = 3400.0  # playable world units per side
MID = SIZE / 2
BORDER = 30

LAND = 60.0  # height units
BED = 16.0
WATER_Z = 24  # world units; terrain below this is river
ISLAND_R = 300.0  # inner edge of the ring of water around the island
RING_R = 470.0  # outer edge


def river_half_width(t):
    """Half width of a river arm at distance t (world units) along it from the map centre."""
    return 105.0 + 22.0 * math.cos(t / 230.0)


# Quadrant factions: the GLA general whose compound sits behind the bases, the two dozers next
# to the bases, the airfield, power plant and war factory in front. Order: NW, NE, SW, SE.
QUADRANTS = [
    {"mirror": (False, False), "gla": "Chem", "dozers": ("Boss_VehicleDozer", "Tank_ChinaVehicleDozer"),
     "airfield": "AmericaAirfield", "power": "AmericaPowerPlant", "factory": "ChinaWarFactory"},
    {"mirror": (True, False), "gla": "Slth", "dozers": ("AirF_AmericaVehicleDozer", "Nuke_ChinaVehicleDozer"),
     "airfield": "ChinaAirfield", "power": "ChinaPowerPlant", "factory": "AmericaWarFactory"},
    {"mirror": (False, True), "gla": "Demo", "dozers": ("Lazr_AmericaVehicleDozer", "Infa_ChinaVehicleDozer"),
     "airfield": "AirF_AmericaAirfield", "power": "AirF_AmericaPowerPlant", "factory": "Boss_WarFactory"},
    {"mirror": (True, True), "gla": "", "dozers": ("SupW_AmericaVehicleDozer", "ChinaVehicleDozer"),
     "airfield": "Tank_ChinaAirfield", "power": "Tank_ChinaPowerPlant", "factory": "GLAArmsDealer"},
]

# Start slots, clockwise from the west side of the north-west quadrant.
SLOTS = [(0, "A"), (0, "B"), (1, "B"), (1, "A"), (3, "A"), (3, "B"), (2, "B"), (2, "A")]

# North-west quadrant, local coordinates (a, b). "A" faces the west-east river, "B" the
# north-south river; B entries are A entries with a and b swapped.
BASE = (430.0, 1080.0)
BASE_R = 360.0
DOCKS = [(150.0, 960.0), (150.0, 1220.0)]
DOZER = (380.0, 740.0)
BUNKER_ROW = [(200.0, 1440.0), (320.0, 1440.0), (440.0, 1440.0), (560.0, 1440.0), (680.0, 1440.0)]
BRIDGE_BUNKERS = [(765.0, 1475.0), (875.0, 1475.0)]
ARTILLERY = [(260.0, 1350.0), (620.0, 1350.0)]
ARM_BRIDGE_A = 820.0  # a of the bridge over the west-east river
GLA_CC = (300.0, 300.0)
GLA_BARRACKS = (600.0, 410.0)
HOSPITAL = (780.0, 120.0)
REPAIR = (120.0, 780.0)
DERRICKS = [(800.0, 920.0), (920.0, 800.0)]
AIRFIELD = (1060.0, 1060.0)
FACTORY = (1300.0, 1080.0)
POWER = (1080.0, 1300.0)
ISLAND_BRIDGE_IN, ISLAND_BRIDGE_OUT = 235.0, 535.0  # distance from centre along the diagonal

# Island: superweapons on the axes (between two quadrants), a power plant in the middle.
SUPERWEAPONS = [((-160.0, 0.0), "ChinaNuclearMissileLauncher"), ((160.0, 0.0), "AmericaParticleCannonUplink"),
                ((0.0, -160.0), "GLAScudStorm"), ((0.0, 160.0), "Lazr_AmericaParticleCannonUplink")]

TREES = ["TreeOak02", "TreeBirch02", "TreeSpruce04", "TreeSpruce05", "TreeMaple06", "TreeFir05", "TreeDogwood8"]
ROCKS = ["RocksG02", "RocksG14", "Rocks3Brown"]

DOCK_VALUE = 120000

# Roads in local coordinates: per base side (B mirrored by local_side) and per quadrant. The
# diagonal stops at the airfield apron and goes on to the island bridge.
SIDE_ROADS = [[(560.0, 1000.0), (ARM_BRIDGE_A, 1200.0), (ARM_BRIDGE_A, 1520.0)],
              [(560.0, 1000.0), (700.0, 700.0)]]
QUADRANT_ROADS = [[(420.0, 420.0), (700.0, 700.0), (930.0, 930.0)], [(1190.0, 1190.0), (1322.0, 1322.0)]]
# Chain-link fence around the GLA compound, with gates where the roads leave it.
COMPOUND_BOX = (170.0, 170.0, 740.0, 540.0)
COMPOUND_GATES = [((540.0, 540.0), 60.0)]
GUARD_TOWERS = [(740.0, 540.0), (170.0, 170.0)]
DOCK_PROPS = ["Crate", "StackedBoxes", "Barrel", "55GallonDrum", "ShippingContainer01", "ShippingContainer02",
              "SupplyPileSmall"]
COMPOUND_PROPS = ["Barrel", "55GallonDrum", "TirePile", "Lumber", "Crate", "ShippingContainer03"]


def to_world(q, a, b):
    mx, my = QUADRANTS[q]["mirror"]
    x = SIZE - a if mx else a
    y = b if my else SIZE - b
    return x, y


def local_side(side, p):
    return p if side == "A" else (p[1], p[0])


def all_roads():
    """Every road as a world-space polyline."""
    out = []
    for q in range(4):
        for side in "AB":
            for road in SIDE_ROADS:
                out.append([to_world(q, *local_side(side, p)) for p in road])
        for road in QUADRANT_ROADS:
            out.append([to_world(q, *p) for p in road])
    return out


def segment_distance(x, y, p0, p1):
    """Distance from points (arrays or floats) to the segment p0-p1."""
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    k = np.clip(((x - x0) * dx + (y - y0) * dy) / (dx * dx + dy * dy), 0.0, 1.0)
    return np.hypot(x - (x0 + k * dx), y - (y0 + k * dy))


def face_centre(x, y):
    return math.atan2(MID - y, MID - x)


def heights(t, nprng):
    x, y = t.wx, t.wy
    # Distances folded into the north-west quadrant keep all four quadrants mirror images.
    fx, fy = np.abs(x - MID), np.abs(y - MID)
    noise = mapgen.value_noise((fx, fy), 1100.0, nprng, octaves=4)
    h = LAND + (noise - 0.5) * 30.0

    # Mountains outside the playable area frame the map; rocky ground near the edges.
    edge = MID - np.maximum(fx, fy)  # distance inside the playable edge
    ridge = mapgen.value_noise((fx, fy), 300.0, nprng, octaves=3)
    h += (40.0 + 60.0 * ridge) * mapgen.smoothstep(40.0, -160.0, edge)

    # Flat pads: base areas, compounds, the island.
    pads = []
    for q in range(4):
        for side in "AB":
            pads.append((to_world(q, *local_side(side, BASE)), BASE_R, LAND + 2))
            for p, r in ((AIRFIELD, 190), (FACTORY, 120), (POWER, 90),
                         (GLA_CC, 140), (GLA_BARRACKS, 110), (local_side(side, DOZER), 60)):
                pads.append((to_world(q, *p), r, LAND))
    for (px, py), r, level in pads:
        d = np.hypot(x - px, y - py)
        w = mapgen.smoothstep(r + 120.0, r, d)
        h = h * (1 - w) + level * w

    r = np.hypot(x - MID, y - MID)
    island = mapgen.smoothstep(ISLAND_R + 20, ISLAND_R - 60, r)
    h = h * (1 - island) + (LAND + 4) * island

    # Rivers: two arms crossing, ending in a ring around the island.
    water = np.zeros_like(h)
    for along, across in ((fy, fx), (fx, fy)):
        hw = 105.0 + 22.0 * np.cos(along / 230.0)
        arm = mapgen.smoothstep(hw + 22.0, hw, across)
        arm *= mapgen.smoothstep(ISLAND_R + 10, ISLAND_R + 80, r)
        water = np.maximum(water, arm)
    ring_mid, ring_hw = (ISLAND_R + RING_R) / 2, (RING_R - ISLAND_R) / 2
    water = np.maximum(water, mapgen.smoothstep(ring_hw + 22.0, ring_hw, np.abs(r - ring_mid)))
    h = h * (1 - water) + BED * water

    # Bridge heads: level the ground where the bridge ends meet the banks.
    for (p0, p1) in bridge_ends():
        for px, py in (p0, p1):
            d = np.hypot(x - px, y - py)
            w = mapgen.smoothstep(90.0, 40.0, d)
            h = h * (1 - w) + LAND * w
    t.h = h


def bridge_ends():
    ends = []
    # Arm bridges: one per river arm per quadrant pair, at a = ARM_BRIDGE_A from the edge.
    for q in (0, 1):  # north quadrants own the bridge to the south over the west-east river
        for along in (ARM_BRIDGE_A,):
            x = along if q == 0 else SIZE - along
            hw = river_half_width(abs(x - MID)) + 60.0
            ends.append(((x, MID + hw), (x, MID - hw)))
    for q in (0, 2):  # west quadrants own the bridge to the east over the north-south river
        y = SIZE - ARM_BRIDGE_A if q == 0 else ARM_BRIDGE_A
        hw = river_half_width(abs(y - MID)) + 60.0
        ends.append(((MID - hw, y), (MID + hw, y)))
    for sx, sy in ((-1, 1), (1, 1), (-1, -1), (1, -1)):
        k = 1 / math.sqrt(2)
        ends.append(((MID + sx * k * ISLAND_BRIDGE_OUT, MID + sy * k * ISLAND_BRIDGE_OUT),
                     (MID + sx * k * ISLAND_BRIDGE_IN, MID + sy * k * ISLAND_BRIDGE_IN)))
    return ends


def textures(t, nprng):
    grass = t.texture("GrassMediumType2")
    grass_b = t.texture("GrassMediumType11")
    grass_c = t.texture("GrassMediumType25")
    dirt = t.texture("DirtMediumType5")
    forest = t.texture("GrassMediumType31")
    beach = t.texture("SandLargeType3")
    bed = t.texture("SandMediumType9")
    concrete = t.texture("ConcreteMediumType1")
    cliff = t.texture("CliffLargeType1")

    x, y, h = t.wx + 5.0, t.wy + 5.0, t.h  # cell centres
    fx, fy = np.abs(x - MID), np.abs(y - MID)
    patch = mapgen.value_noise((fx, fy), 420.0, nprng, octaves=3)
    patch2 = mapgen.value_noise((fx, fy), 260.0, nprng, octaves=2)
    cls = np.full(h.shape, grass, dtype=np.int32)
    cls[patch > 0.58] = grass_b
    cls[patch2 > 0.66] = grass_c
    cls[(patch < 0.33) & (patch2 > 0.5)] = dirt
    t.forest_noise = mapgen.value_noise((fx, fy), 340.0, nprng, octaves=3)
    cls[t.forest_noise > 0.52] = forest

    # Worn ground along the roads.
    for road in all_roads():
        for p0, p1 in zip(road, road[1:]):
            cls[segment_distance(x, y, p0, p1) < 34] = dirt

    # Bases and building pads.
    for q in range(4):
        for side in "AB":
            bx, by = to_world(q, *local_side(side, BASE))
            d = np.hypot(x - bx, y - by)
            cls[d < 120] = concrete
            cls[(d >= 120) & (d < 170)] = dirt
        for p, r in ((AIRFIELD, 150), (GLA_CC, 110), (GLA_BARRACKS, 70)):
            px, py = to_world(q, *p)
            cls[np.hypot(x - px, y - py) < r] = concrete
    r = np.hypot(x - MID, y - MID)
    cls[r < 230] = concrete

    z = h * mapgen.HEIGHT_SCALE
    cls[z < WATER_Z + 6] = beach
    cls[z < WATER_Z - 2] = bed
    cls[t.cliff_cells()] = cliff
    t.cls = cls


def place(objs, t, pyrng):
        # Start positions and the AI's approach paths and perimeters.
    for slot, (q, side) in enumerate(SLOTS, start=1):
        bx, by = to_world(q, *local_side(side, BASE))
        objs.waypoint(bx, by, name=f"Player_{slot}_Start")
        objs.footprints.append((bx, by, 180, f"Player_{slot}_Start"))
        inner, outer = 330, 560
        objs.polygon(f"InnerPerimeter{slot}", [(bx - inner, by - inner), (bx + inner, by - inner),
                                               (bx + inner, by + inner), (bx - inner, by + inner)])
        objs.polygon(f"OuterPerimeter{slot}", [(bx - outer, by - outer), (bx + outer, by - outer),
                                               (bx + outer, by + outer), (bx - outer, by + outer)])
        bridge = local_side(side, (ARM_BRIDGE_A, 1700.0))
        front = local_side(side, (ARM_BRIDGE_A, 1250.0))
        island = (1330.0, 1330.0)
        objs.path([to_world(q, *p) for p in (island, AIRFIELD, (700.0, 900.0) if side == "A" else (900.0, 700.0),
                                             local_side(side, BASE))], f"Center{slot}")
        objs.path([to_world(q, *p) for p in (bridge, front, local_side(side, BASE))], f"Flank{slot}")
        objs.path([to_world(q, *p) for p in (local_side(side, (60.0, 1500.0)), local_side(side, (120.0, 1150.0)),
                                             local_side(side, BASE))], f"Backdoor{slot}")

    names = {"docks": [], "dozers": []}
    for q, quad in enumerate(QUADRANTS):
        tag = ["NW", "NE", "SW", "SE"][q]
        for k, side in enumerate("AB"):
            for i, p in enumerate(DOCKS):
                x, y = to_world(q, *local_side(side, p))
                name = f"GXDock{tag}{side}{i + 1}"
                objs.add("SupplyDock", x, y, face_centre(x, y), owner=mapgen.NEUTRAL_TEAM, indestructible=True,
                         name=name, radius=70)
                names["docks"].append(name)
            x, y = to_world(q, *local_side(side, DOZER))
            name = f"GXDozer{tag}{side}"
            objs.add(quad["dozers"][k], x, y, face_centre(x, y), indestructible=True, name=name, radius=30)
            names["dozers"].append(name)
            for p in BUNKER_ROW + BRIDGE_BUNKERS:
                x, y = to_world(q, *local_side(side, p))
                objs.add("CivilianBunker01", x, y, face_centre(x, y), owner=mapgen.NEUTRAL_TEAM,
                         indestructible=True, radius=45)
            for p in ARTILLERY:
                x, y = to_world(q, *local_side(side, p))
                objs.add("TechArtilleryPlatform", x, y, face_centre(x, y), indestructible=True, radius=50,
                         objectMaxHPs=2500)
        for p, template, r in ((AIRFIELD, quad["airfield"], 140), (FACTORY, quad["factory"], 85),
                               (POWER, quad["power"], 55)):
            x, y = to_world(q, *p)
            objs.add(template, x, y, face_centre(x, y), radius=r)
        prefix = quad["gla"] + "_" if quad["gla"] else ""
        x, y = to_world(q, *GLA_CC)
        objs.add(f"{prefix}GLACommandCenter", x, y, face_centre(x, y), radius=100)
        x, y = to_world(q, *GLA_BARRACKS)
        objs.add(f"{prefix}GLABarracks", x, y, face_centre(x, y), radius=70)
        for p, template, r in ((HOSPITAL, "TechHospital", 80), (REPAIR, "TechRepairbay", 70)):
            x, y = to_world(q, *p)
            objs.add(template, x, y, face_centre(x, y), indestructible=True, radius=r)
        for p in DERRICKS:
            x, y = to_world(q, *p)
            objs.add("TechOilDerrick", x, y, face_centre(x, y), radius=35)

    for (dx, dy), template in SUPERWEAPONS:
        x, y = MID + dx, MID + dy
        objs.add(template, x, y, face_centre(x, y) + math.pi, radius=75)
    objs.add("AmericaPowerPlant", MID, MID, 0.0, radius=50)

    # Bridges and roads.
    for n, (p0, p1) in enumerate(bridge_ends(), start=1):
        objs.bridge("ConcreteFourLane", p0, p1, f"GXBridge{n}")
    for road in all_roads():
        objs.road("TwoLaneDark", road)

    fortify(objs, pyrng)
    scatter(objs, t, pyrng)
    return names


def fortify(objs, pyrng):
    """Sandbags along the bunker lines, the fenced GLA compound, props at docks and compounds,
    lamps along the roads."""
    for q in range(4):
        for side in "AB":
            angle = 0.0 if side == "A" else math.pi / 2
            # Sandbag line on the river side of the bunkers, with a gap at each bunker.
            a = 150.0
            while a <= 730.0:
                if all(abs(a - bx) > 22 for bx, _ in BUNKER_ROW):
                    objs.add("SandBagWall01", *to_world(q, *local_side(side, (a, 1490.0))), angle,
                             owner=mapgen.NEUTRAL_TEAM)
                a += 40.0
            for ax, bx in ARTILLERY:
                for da in (-62.0, 62.0):
                    objs.add("SandbagPile02", *to_world(q, *local_side(side, (ax + da, bx + 40.0))), angle,
                             owner=mapgen.NEUTRAL_TEAM)
            # Dock yard clutter.
            for dx, dy in DOCKS:
                for k in range(5):
                    a, b = dx + pyrng.uniform(30, 95), dy + pyrng.uniform(-90, 90)
                    if all(math.hypot(a - ex, b - ey) > 80 for ex, ey in DOCKS):
                        objs.add(pyrng.choice(DOCK_PROPS), *to_world(q, *local_side(side, (a, b))),
                                 pyrng.choice((0.0, math.pi / 2)), owner=mapgen.NEUTRAL_TEAM)
        # Compound fence: posts every 27 units, skipping the gates.
        a0, b0, a1, b1 = COMPOUND_BOX
        edges = [((a0, b0), (a1, b0)), ((a1, b0), (a1, b1)), ((a1, b1), (a0, b1)), ((a0, b1), (a0, b0))]
        for (pa, pb), (qa, qb) in edges:
            length = math.hypot(qa - pa, qb - pb)
            n = int(length / 27.0)
            for k in range(n):
                f = (k + 0.5) / n
                a, b = pa + (qa - pa) * f, pb + (qb - pb) * f
                if any(math.hypot(a - ga, b - gb) < gr for (ga, gb), gr in COMPOUND_GATES):
                    continue
                if any(math.hypot(a - ex, b - ey) < 90 for ex, ey in (HOSPITAL, REPAIR)):
                    continue
                x, y = to_world(q, a, b)
                along_x = abs(qa - pa) > abs(qb - pb)
                objs.add("ChainLinkFence03", x, y, 0.0 if along_x else math.pi / 2, owner=mapgen.CIVILIAN_TEAM)
        for p in GUARD_TOWERS:
            x, y = to_world(q, *p)
            objs.add("GuardTower", x, y, face_centre(x, y), indestructible=True, radius=25)
        for k in range(14):
            a, b = pyrng.uniform(a0 + 30, a1 - 30), pyrng.uniform(b0 + 30, b1 - 30)
            if all(math.hypot(a - ex, b - ey) > 150 for ex, ey in (GLA_CC, GLA_BARRACKS)) and \
                    all(segment_distance(a, b, *seg) > 50 for seg in ((QUADRANT_ROADS[0][0], QUADRANT_ROADS[0][1]),)):
                objs.add(pyrng.choice(COMPOUND_PROPS), *to_world(q, a, b), pyrng.uniform(0, math.pi),
                         owner=mapgen.NEUTRAL_TEAM)
    # Street lamps along the roads, alternating sides.
    for road in all_roads():
        for p0, p1 in zip(road, road[1:]):
            (x0, y0), (x1, y1) = p0, p1
            length = math.hypot(x1 - x0, y1 - y0)
            nx, ny = -(y1 - y0) / length, (x1 - x0) / length
            for k in range(1, int(length / 170.0) + 1):
                f = k * 170.0 / length
                side = 1 if k % 2 else -1
                x, y = x0 + (x1 - x0) * f + nx * 34 * side, y0 + (y1 - y0) * f + ny * 34 * side
                if all(math.hypot(x - fx, y - fy) > fr + 20 for fx, fy, fr, _ in objs.footprints):
                    objs.add("OldStreetLamppost", x, y, math.atan2(-ny * side, -nx * side), owner=mapgen.NEUTRAL_TEAM)


def reserved(objs):
    circles = [(x, y, r + 60) for x, y, r, _ in objs.footprints]
    for (p0, p1) in bridge_ends():
        for px, py in (p0, p1):
            circles.append((px, py, 110))
    for q in range(4):
        for side in "AB":
            bx, by = to_world(q, *local_side(side, BASE))
            circles.append((bx, by, BASE_R + 60))
            for p in ((ARM_BRIDGE_A, 1200.0), (ARM_BRIDGE_A, 1380.0), (700.0, 1100.0)):
                circles.append((*to_world(q, *local_side(side, p)), 90))
    return circles


def scatter(objs, t, pyrng):
    """Trees in the forest patches and rocks on the hills, away from anything that matters."""
    circles = reserved(objs)
    road_segments = [seg for road in all_roads() for seg in zip(road, road[1:])]
    step = 30.0
    grid = int(MID / step)
    for gi in range(grid):
        for gj in range(grid):
            a = (gi + 0.5 + pyrng.uniform(-0.35, 0.35)) * step
            b = (gj + 0.5 + pyrng.uniform(-0.35, 0.35)) * step
            template = pyrng.choice(TREES)
            angle = pyrng.uniform(0, 2 * math.pi)
            roll = pyrng.random()
            for q in range(4):
                x, y = to_world(q, a, b)
                if not (20 < x < SIZE - 20 and 20 < y < SIZE - 20):
                    continue
                i, j = int(x / mapgen.CELL) + BORDER, int(y / mapgen.CELL) + BORDER
                z = t.h[j, i] * mapgen.HEIGHT_SCALE
                if z < WATER_Z + 8 or math.hypot(x - MID, y - MID) < RING_R + 80:
                    continue
                if any(math.hypot(x - cx, y - cy) < cr for cx, cy, cr in circles):
                    continue
                if any(segment_distance(x, y, p0, p1) < 60 for p0, p1 in road_segments):
                    continue
                if t.forest_noise[j, i] > 0.5 or roll < 0.035:
                    objs.add(template, x, y, angle, owner=mapgen.NEUTRAL_TEAM)
                elif z > (LAND + 14) * mapgen.HEIGHT_SCALE and roll < 0.25:
                    objs.add(ROCKS[(gi * 7 + gj) % len(ROCKS)], x, y, angle, owner=mapgen.NEUTRAL_TEAM)
    # Rocks along the river banks.
    for gi in range(int(MID / 30.0)):
        for gj in range(int(MID / 30.0)):
            a, b = gi * 30.0 + pyrng.uniform(0, 30), gj * 30.0 + pyrng.uniform(0, 30)
            roll = pyrng.random()
            template = pyrng.choice(ROCKS)
            for q in range(4):
                x, y = to_world(q, a, b)
                i, j = int(x / mapgen.CELL) + BORDER, int(y / mapgen.CELL) + BORDER
                z = t.h[j, i] * mapgen.HEIGHT_SCALE
                if WATER_Z + 2 < z < WATER_Z + 14 and roll < 0.12 and \
                        not any(math.hypot(x - cx, y - cy) < cr for cx, cy, cr in circles):
                    objs.add(template, x, y, roll * 50, owner=mapgen.NEUTRAL_TEAM)


def scripts(names):
    unmanned = [(mapgen.ACTION_SET_UNMANNED[0], mapgen.ACTION_SET_UNMANNED[1], [(mapgen.PARAM_UNIT, n)])
                for n in names["dozers"]]
    docks = [(mapgen.ACTION_WAREHOUSE_SET_VALUE[0], mapgen.ACTION_WAREHOUSE_SET_VALUE[1],
              [(mapgen.PARAM_UNIT, n), (mapgen.PARAM_INT, DOCK_VALUE)]) for n in names["docks"]]
    always = [[(mapgen.CONDITION_TRUE[0], mapgen.CONDITION_TRUE[1], [])]]
    return [
        {"name": "GX_UnmannedDozers", "comment": "Dozers of other generals wait for a crew.",
         "conditions": always, "actions": unmanned},
        {"name": "GX_SupplyDocks", "comment": "Large supply reserves.", "conditions": always, "actions": docks},
    ]


def generate():
    pyrng, nprng = mapgen.rng(SEED)
    cells = int(SIZE / mapgen.CELL)
    t = mapgen.Terrain(cells, cells, BORDER)
    t.water_z = WATER_Z
    heights(t, nprng)
    textures(t, nprng)
    objs = mapgen.Objects()
    names = place(objs, t, pyrng)
    # One water plane over the whole map: the terrain is above it everywhere but in the rivers.
    e = BORDER * mapgen.CELL
    objs.polygon("GXWater", [(-e, -e), (SIZE + e, -e), (SIZE + e, SIZE + e), (-e, SIZE + e)], z=WATER_Z, water=True)
    overlaps = objs.check_overlaps()
    if overlaps:
        raise RuntimeError(f"objects overlap: {overlaps}")
    data = mapgen.build(t, objs, NAME_TAG, scripts(names))
    return data, t, objs
