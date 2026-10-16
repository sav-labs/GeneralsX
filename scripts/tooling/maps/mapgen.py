"""Building blocks for generated skirmish maps: terrain, texture blends, objects, scripts.

GeneralsX @feature Claude 16/10/2026 A map layout (see twin_rivers.py) describes its height
field, texture rules and object placements; this module turns that into the chunk data that
mapfile.write_map() saves. The rules follow the engine and WorldBuilder:
- tile indexes as WorldHeightMapEdit::getTileNdxForClass (4 sub-cells per 64x64 source tile),
- blends as WorldHeightMapEdit::blendSpecificTiles (horizontal, vertical, diagonal, long diagonal),
- cliff flags as WorldHeightMap::setCellCliffFlagFromHeights (corner spread over 9.8 world units).
Only retail names (terrain classes, object templates, script templates) are referenced; no
retail map data is copied.
"""

import math
import os
import random
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "content"))

import mapfile  # noqa: E402

CELL = mapfile.MAP_XY_FACTOR
HEIGHT_SCALE = mapfile.MAP_HEIGHT_SCALE
CLIFF_LIMIT = 9.8  # PATHFIND_CLIFF_SLOPE_LIMIT_F, world units

# Retail terrain classes (Terrain.ini) with their tile widths, as WorldBuilder saves them.
TEXTURE_WIDTH = {
    "GrassMediumType2": 4,
    "GrassMediumType11": 4,
    "GrassMediumType25": 4,
    "GrassMediumType31": 4,
    "DirtMediumType5": 4,
    "SandMediumType9": 4,
    "SandLargeType3": 6,
    "ConcreteMediumType1": 4,
    "AsphaltType1": 2,
    "CliffMediumType1": 4,
    "CliffLargeType1": 6,
    "RocksType2": 2,
    "SandLargeType3Light": 6,
    "SandLargeType4": 6,
    "SandMediumType13d": 4,
    "CliffMediumType16": 4,
    "CliffLargeType8": 6,
    "ConcreteType1": 2,
    "SnowType2": 2,
    "GrassMediumType15": 4,
}

# Script templates: (enum value, internal name) from ScriptEngine.cpp. The reader re-matches by
# name, so the name is what counts.
CONDITION_TRUE = (3, "CONDITION_TRUE")
ACTION_SET_UNMANNED = (338, "NAMED_SET_UNMANNED_STATUS")
ACTION_WAREHOUSE_SET_VALUE = (212, "WAREHOUSE_SET_VALUE")
PARAM_INT = 0
PARAM_UNIT = 14

NEUTRAL_TEAM = "team"
CIVILIAN_TEAM = "teamPlyrCivilian"


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def value_noise(shape_xy, scale, rng, octaves=3):
    """Fractal value noise sampled on a world-unit grid. shape_xy = (xs, ys) world coordinate
    arrays (any shape); scale is the feature size of the first octave in world units."""
    xs, ys = shape_xy
    total = np.zeros_like(xs, dtype=np.float64)
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        s = scale / (2 ** o)
        gx = int(xs.max() / s) + 3
        gy = int(ys.max() / s) + 3
        grid = rng.rand(gy, gx)
        fx, fy = xs / s, ys / s
        x0, y0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
        tx, ty = fx - x0, fy - y0
        tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
        x0, y0 = np.clip(x0, 0, gx - 2), np.clip(y0, 0, gy - 2)
        a = grid[y0, x0] * (1 - tx) + grid[y0, x0 + 1] * tx
        b = grid[y0 + 1, x0] * (1 - tx) + grid[y0 + 1, x0 + 1] * tx
        total += amp * (a * (1 - ty) + b * ty)
        norm += amp
        amp *= 0.5
    return total / norm


class Terrain:
    """Height samples and per-cell texture classes for a map of `cells` playable cells per side
    and `border` cells of off-map border, in the engine's layout (index = y * width + x)."""

    def __init__(self, cells_x, cells_y, border):
        self.border = border
        self.width = cells_x + 2 * border
        self.height = cells_y + 2 * border
        ii, jj = np.meshgrid(np.arange(self.width), np.arange(self.height))
        self.wx = (ii - border) * CELL  # world coordinates of each height sample
        self.wy = (jj - border) * CELL
        self.h = np.zeros((self.height, self.width))  # height units (0..255), 1 unit = 0.625 world
        self.classes = []
        self.cls = np.zeros((self.height, self.width), dtype=np.int32)

    def texture(self, name):
        if name not in TEXTURE_WIDTH:
            raise ValueError(f"unknown terrain class {name}")
        if name not in self.classes:
            self.classes.append(name)
        return self.classes.index(name)

    def height_at(self, x, y):
        i = int(round(x / CELL)) + self.border
        j = int(round(y / CELL)) + self.border
        return self.h[j, i]

    def cliff_cells(self):
        z = np.round(np.clip(self.h, 0, 255)) * HEIGHT_SCALE
        corners = np.stack([z[:-1, :-1], z[:-1, 1:], z[1:, :-1], z[1:, 1:]])
        spread = corners.max(axis=0) - corners.min(axis=0)
        out = np.zeros((self.height, self.width), dtype=bool)
        out[:-1, :-1] = spread > CLIFF_LIMIT
        return out

    def encode(self):
        """Returns the HeightMapData and BlendTileData fields of mapfile.write_map()."""
        heights = np.clip(np.round(self.h), 0, 255).astype(np.uint8)
        first, classes = 0, []
        for name in self.classes:
            w = TEXTURE_WIDTH[name]
            classes.append((first, w * w, w, name))
            first += w * w
        num_bitmap_tiles = first

        def tile_index(i, j, c):
            f, _, w, _ = classes[c]
            ndx = f + (i // 2) % w + w * ((j // 2) % w)
            return (ndx << 2) + 2 * (j & 1) + (i & 1)

        W, H = self.width, self.height
        tiles = [0] * (W * H)
        for j in range(H):
            for i in range(W):
                tiles[j * W + i] = tile_index(i, j, int(self.cls[j, i]))

        # Blends: a cell takes the highest-priority (latest registered) different neighbour
        # class, the way the WorldBuilder brush feathers a painted edge one cell outwards.
        blend = [0] * (W * H)
        blended, lookup = [], {}

        def blend_id(info):
            key = tuple(sorted(info.items()))
            if key not in lookup:
                blended.append(info)
                lookup[key] = len(blended)  # record 0 is the engine's empty blend
            return lookup[key]

        cls = self.cls
        for j in range(1, H - 1):
            for i in range(1, W - 1):
                c = cls[j, i]
                best = -1
                for dj in (-1, 0, 1):
                    for di in (-1, 0, 1):
                        n = cls[j + dj, i + di]
                        if n > c and n > best:
                            best = n
                if best < 0:
                    continue
                r, l = cls[j, i + 1] == best, cls[j, i - 1] == best
                u, d = cls[j + 1, i] == best, cls[j - 1, i] == best
                info = {"blendNdx": tile_index(i, j, int(best)), "horiz": 0, "vert": 0,
                        "rightDiagonal": 0, "leftDiagonal": 0, "inverted": 0, "longDiagonal": 0,
                        "customBlendEdgeClass": -1}
                if (r or l) and (u or d) and not (r and l) and not (u and d):
                    # Inner corner: long diagonal towards the two painted sides.
                    sx, sy = (1 if r else -1), (1 if u else -1)
                    info["longDiagonal"] = 1
                    info["inverted"] = 0 if sy < 0 else 1
                    info["rightDiagonal"] = 0 if sx > 0 else 1
                    info["leftDiagonal"] = 1 if sx > 0 else 0
                elif r or l:
                    info["horiz"] = 1
                    info["inverted"] = 1 if l else 0
                elif u or d:
                    info["vert"] = 1
                    info["inverted"] = 1 if d else 0
                else:
                    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                        if cls[j + sy, i + sx] == best:
                            break
                    info["rightDiagonal"] = 1 if sx > 0 else 0
                    info["leftDiagonal"] = 0 if sx > 0 else 1
                    info["inverted"] = 1 if sy < 0 else 0
                blend[j * W + i] = blend_id(info)
        if len(blended) + 1 > mapfile.NUM_BLEND_TILES:
            raise mapfile.MapError("too many blend tiles")

        cliff = self.cliff_cells()
        flip_width = (W + 7) // 8
        cliff_state = bytearray(H * flip_width)
        for j, i in zip(*np.nonzero(cliff)):
            cliff_state[j * flip_width + (i >> 3)] |= 1 << (i & 7)

        return {
            "width": W, "height": H, "border": self.border,
            "heights": heights.tobytes(),
            "tiles": tiles, "blend": blend, "extra_blend": [0] * (W * H), "cliff_info": [0] * (W * H),
            "cliff_state": bytes(cliff_state),
            "num_bitmap_tiles": num_bitmap_tiles,
            "texture_classes": classes,
            "blended_tiles": blended,
        }


class Objects:
    """Map objects, waypoints, waypoint links and polygon triggers."""

    def __init__(self):
        self.items = []  # (x, y, z, angle, flags, template, props)
        self.counts = {}
        self.links = []
        self.triggers = []
        self.next_waypoint = 1
        self.next_trigger = 1
        self.footprints = []  # (x, y, radius, template) for overlap checks

    def _props(self, owner, indestructible, unique):
        return {
            "objectInitialHealth": 100, "objectEnabled": True,
            "objectIndestructible": bool(indestructible), "objectUnsellable": False,
            "objectPowered": True, "objectRecruitableAI": True, "objectTargetable": False,
            "originalOwner": owner, "uniqueID": unique, "objectLayer": "",
        }

    def add(self, template, x, y, angle=0.0, owner=CIVILIAN_TEAM, indestructible=False,
            name=None, flags=0, radius=0.0, **extra):
        n = self.counts.get(template, 0) + 1
        self.counts[template] = n
        props = self._props(owner, indestructible, f"{template} {n}")
        if name:
            props["objectName"] = name
        props.update(extra)
        self.items.append((float(x), float(y), 0.0, float(angle), flags, template, props))
        if radius:
            self.footprints.append((x, y, radius, name or template))
        return props

    def waypoint(self, x, y, name=None, labels=("", "", "")):
        wid = self.next_waypoint
        self.next_waypoint += 1
        wname = name or f"Waypoint {wid}"
        props = self._props(NEUTRAL_TEAM, False, wname)
        props.update({"waypointID": wid, "waypointName": wname})
        if name is None:
            props.update({"waypointPathLabel1": labels[0], "waypointPathLabel2": labels[1],
                          "waypointPathLabel3": labels[2]})
        self.items.append((float(x), float(y), 0.0, 0.0, 0, "*Waypoints/Waypoint", props))
        return wid

    def path(self, points, label):
        """A waypoint path; the AI follows it from the first point to the last."""
        ids = [self.waypoint(x, y, labels=(label, "", "")) for x, y in points]
        for a, b in zip(ids, ids[1:]):
            self.links.append((a, b))
        return ids

    def road(self, template, points):
        """A road is a run of segments, each a point1/point2 object pair."""
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            self.add(template, x0, y0, owner=NEUTRAL_TEAM, flags=mapfile.FLAG_ROAD_POINT1)
            self.add(template, x1, y1, owner=NEUTRAL_TEAM, flags=mapfile.FLAG_ROAD_POINT2)

    def bridge(self, template, p0, p1, name):
        for (x, y), flag in ((p0, mapfile.FLAG_BRIDGE_POINT1), (p1, mapfile.FLAG_BRIDGE_POINT2)):
            self.add(template, x, y, owner=NEUTRAL_TEAM, indestructible=True, name=name, flags=flag,
                     objectRecruitableAI=False)

    def polygon(self, name, points, z=0, water=False):
        self.triggers.append({"name": name, "layer": "", "id": self.next_trigger, "water": water,
                              "river": False, "river_start": 0,
                              "points": [(int(round(x)), int(round(y)), int(z)) for x, y in points]})
        self.next_trigger += 1

    def check_overlaps(self):
        bad = []
        for a in range(len(self.footprints)):
            xa, ya, ra, na = self.footprints[a]
            for b in range(a + 1, len(self.footprints)):
                xb, yb, rb, nb = self.footprints[b]
                if math.hypot(xa - xb, ya - yb) < ra + rb:
                    bad.append((na, nb, round(math.hypot(xa - xb, ya - yb))))
        return bad


def standard_sides():
    """Neutral and civilian players, as every WorldBuilder multiplayer map has them."""
    def side(name, display, faction):
        return ({"playerName": name, "playerIsHuman": False,
                 "playerDisplayName": mapfile.Unicode(display), "playerFaction": faction,
                 "playerAllies": "", "playerEnemies": ""}, [])
    sides = [side("", "Neutral", ""), side("PlyrCivilian", "PlyrCivilian", "FactionCivilian")]
    teams = [{"teamName": NEUTRAL_TEAM, "teamOwner": "", "teamIsSingleton": True},
             {"teamName": CIVILIAN_TEAM, "teamOwner": "PlyrCivilian", "teamIsSingleton": True}]
    return sides, teams


def sunny_lighting():
    def light(amb, dif, pos):
        return {"ambient": list(amb), "diffuse": list(dif), "pos": list(pos)}
    sun = light((0.30, 0.29, 0.27), (1.0, 0.96, 0.86), (-0.81, 0.38, -0.45))
    fill = light((0, 0, 0), (0.24, 0.26, 0.36), (0.79, 0.62, 0.0))
    back = light((0, 0, 0), (0.12, 0.12, 0.08), (0.81, -0.48, -0.34))
    tod = {"terrain": [sun, fill, back], "objects": [sun, fill, back]}
    return {"time_of_day": 2, "times": [tod, tod, tod, tod], "shadow_color": 0xFFA0A0A0}


def build(terrain, objects, map_name_tag, scripts):
    m = terrain.encode()
    sides, teams = standard_sides()
    m.update({
        "world": {"weather": 0, "mapName": map_name_tag},
        "sides": sides, "teams": teams,
        "scripts": {1: scripts},  # on PlyrCivilian, so the default skirmish AI scripts still load
        "objects": objects.items,
        "triggers": objects.triggers,
        "lighting": sunny_lighting(),
        "waypoint_links": objects.links,
    })
    return mapfile.write_map(m)


def rng(seed):
    return random.Random(seed), np.random.RandomState(seed)
