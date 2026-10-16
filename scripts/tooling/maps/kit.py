"""Shared pieces for generated skirmish maps whose east half mirrors the west half.

GeneralsX @feature Claude 16/10/2026 The mountain pass and desert oasis layouts place everything
for the west half and mirror it across the vertical centre line, so every start position is
equal. This module holds what both use: the base kit (supply docks, an unmanned dozer of
another general, indestructible bunkers and artillery in front), the fenced GLA compound,
street lamps, tree and rock scatter, the AI's start waypoints, perimeters and approach paths,
and the scripts that set the dozers unmanned and fill the docks.
"""

import math

import numpy as np

import mapgen

DOCK_PROPS = ["Crate", "StackedBoxes", "Barrel", "55GallonDrum", "ShippingContainer01", "ShippingContainer02",
              "SupplyPileSmall"]
COMPOUND_PROPS = ["Barrel", "55GallonDrum", "TirePile", "Lumber", "Crate", "ShippingContainer03"]


def segment_distance(x, y, p0, p1):
    """Distance from points (arrays or floats) to the segment p0-p1."""
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    k = np.clip(((x - x0) * dx + (y - y0) * dy) / (dx * dx + dy * dy), 0.0, 1.0)
    return np.hypot(x - (x0 + k * dx), y - (y0 + k * dy))


class Mirror:
    """World positions for a layout written for the west half of a map `width` wide."""

    def __init__(self, width, height):
        self.width, self.height = width, height

    def both(self, p):
        return [p, (self.width - p[0], p[1])]

    def east(self, p):
        return (self.width - p[0], p[1])

    def facing(self, x, y, target):
        """Angle from (x, y) towards target."""
        return math.atan2(target[1] - y, target[0] - x)


def blend_pads(h, x, y, pads, falloff=120.0):
    """Flatten circular pads: ((px, py), radius, level)."""
    for (px, py), r, level in pads:
        w = mapgen.smoothstep(r + falloff, r, np.hypot(x - px, y - py))
        h = h * (1 - w) + level * w
    return h


# Base kit, west side, offsets from the start position (+u points east, at the enemy).
DOCK_OFFSETS = [(-270.0, -130.0), (-270.0, 130.0)]
DOZER_OFFSET = (60.0, -250.0)
BUNKER_U = 400.0
BUNKER_V = [-280.0, -180.0, -85.0, 85.0, 180.0, 280.0]  # gap in the middle for the base road
ARTILLERY_OFFSETS = [(310.0, -350.0), (310.0, 350.0)]
SANDBAG_U = 450.0


def base_kit(objs, m, base, east, dozer, tag, pyrng, names, centre, frame=None):
    """Docks, an unmanned dozer, bunkers and artillery around one start position. The kit faces
    east (or west when `east`), or along frame = ((fx, fy), (sx, sy)): forward and side unit
    vectors."""
    if frame is None:
        frame = ((-1.0 if east else 1.0, 0.0), (0.0, 1.0))
    (fx, fy), (sx, sy) = frame
    bx, by = base

    def at(du, dv):
        return bx + fx * du + sx * dv, by + fy * du + sy * dv

    for i, off in enumerate(DOCK_OFFSETS):
        x, y = at(*off)
        name = f"GXDock{tag}{i + 1}"
        objs.add("SupplyDock", x, y, m.facing(x, y, base), owner=mapgen.NEUTRAL_TEAM, indestructible=True,
                 name=name, radius=70)
        names["docks"].append(name)
        for k in range(5):
            du, dv = off[0] - pyrng.uniform(-60, 20), off[1] + pyrng.uniform(-80, 80)
            px, py = at(du - 75, dv)
            if all(math.hypot(px - fx, py - fy) > fr + 15 for fx, fy, fr, _ in objs.footprints):
                objs.add(pyrng.choice(DOCK_PROPS), px, py, pyrng.choice((0.0, math.pi / 2)),
                         owner=mapgen.NEUTRAL_TEAM)
    x, y = at(*DOZER_OFFSET)
    name = f"GXDozer{tag}"
    objs.add(dozer, x, y, m.facing(x, y, centre), indestructible=True, name=name, radius=30)
    names["dozers"].append(name)
    front = math.atan2(fy, fx)
    along = math.atan2(sy, sx)
    for v in BUNKER_V:
        x, y = at(BUNKER_U, v)
        objs.add("CivilianBunker01", x, y, front, owner=mapgen.NEUTRAL_TEAM, indestructible=True, radius=45)
    for off in ARTILLERY_OFFSETS:
        x, y = at(*off)
        objs.add("TechArtilleryPlatform", x, y, front, indestructible=True, radius=50, objectMaxHPs=2500)
        for dv in (-62.0, 62.0):
            objs.add("SandbagPile02", *at(off[0] + 40.0, off[1] + dv), front + math.pi / 2,
                     owner=mapgen.NEUTRAL_TEAM)
    v = -320.0
    while v <= 320.0:
        if abs(v) > 50 and all(abs(v - b) > 22 for b in BUNKER_V):
            objs.add("SandBagWall01", *at(SANDBAG_U, v), along, owner=mapgen.NEUTRAL_TEAM)
        v += 40.0


def bunker_pair(objs, p, angle, gap=110.0, along_y=True):
    """Two indestructible bunkers either side of a road or pass mouth."""
    for s in (-1, 1):
        x, y = (p[0], p[1] + s * gap) if along_y else (p[0] + s * gap, p[1])
        objs.add("CivilianBunker01", x, y, angle, owner=mapgen.NEUTRAL_TEAM, indestructible=True, radius=45)


def compound(objs, box, gla, gates, pyrng, centre, keep_clear=()):
    """A fenced, capturable GLA command centre and barracks with guard towers and clutter.
    box = (x0, y0, x1, y1) in world units; gates = [((x, y), radius)] gaps in the fence."""
    x0, y0, x1, y1 = box
    prefix = gla + "_" if gla else ""
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    cc = (x0 + (x1 - x0) * 0.3, cy)
    barracks = (x0 + (x1 - x0) * 0.76, cy + (y1 - y0) * 0.12)
    objs.add(f"{prefix}GLACommandCenter", *cc, math.atan2(centre[1] - cc[1], centre[0] - cc[0]), radius=100)
    objs.add(f"{prefix}GLABarracks", *barracks, math.atan2(centre[1] - barracks[1], centre[0] - barracks[0]),
             radius=70)
    edges = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
    for (pa, pb), (qa, qb) in edges:
        n = int(math.hypot(qa - pa, qb - pb) / 27.0)
        for k in range(n):
            f = (k + 0.5) / n
            x, y = pa + (qa - pa) * f, pb + (qb - pb) * f
            if any(math.hypot(x - gx, y - gy) < gr for (gx, gy), gr in gates):
                continue
            if any(math.hypot(x - fx, y - fy) < fr + 10 for fx, fy, fr, _ in objs.footprints):
                continue
            objs.add("ChainLinkFence03", x, y, 0.0 if abs(qa - pa) > abs(qb - pb) else math.pi / 2,
                     owner=mapgen.CIVILIAN_TEAM)
    for x, y in ((x0, y0), (x1, y1)):
        objs.add("GuardTower", x, y, math.atan2(centre[1] - y, centre[0] - x), indestructible=True, radius=25)
    for k in range(14):
        x, y = pyrng.uniform(x0 + 30, x1 - 30), pyrng.uniform(y0 + 30, y1 - 30)
        if all(math.hypot(x - ex, y - ey) > r for (ex, ey), r in ((cc, 150), (barracks, 115))) and \
                all(segment_distance(x, y, *seg) > 50 for seg in keep_clear):
            objs.add(pyrng.choice(COMPOUND_PROPS), x, y, pyrng.uniform(0, math.pi), owner=mapgen.NEUTRAL_TEAM)


def lamps(objs, roads, spacing=170.0):
    """Street lamps along the roads, alternating sides, clear of anything with a footprint."""
    for road in roads:
        for (x0, y0), (x1, y1) in zip(road, road[1:]):
            length = math.hypot(x1 - x0, y1 - y0)
            nx, ny = -(y1 - y0) / length, (x1 - x0) / length
            for k in range(1, int(length / spacing) + 1):
                f = k * spacing / length
                side = 1 if k % 2 else -1
                x, y = x0 + (x1 - x0) * f + nx * 34 * side, y0 + (y1 - y0) * f + ny * 34 * side
                if all(math.hypot(x - fx, y - fy) > fr + 20 for fx, fy, fr, _ in objs.footprints):
                    objs.add("OldStreetLamppost", x, y, math.atan2(-ny * side, -nx * side), owner=mapgen.NEUTRAL_TEAM)


def ai_setup(objs, slot, base, center, flank, backdoor, inner=330, outer=560):
    """Start waypoint, base perimeters and the three approach paths (far end first)."""
    bx, by = base
    objs.waypoint(bx, by, name=f"Player_{slot}_Start")
    objs.footprints.append((bx, by, 180, f"Player_{slot}_Start"))
    for name, r in ((f"InnerPerimeter{slot}", inner), (f"OuterPerimeter{slot}", outer)):
        objs.polygon(name, [(bx - r, by - r), (bx + r, by - r), (bx + r, by + r), (bx - r, by + r)])
    for label, points in (("Center", center), ("Flank", flank), ("Backdoor", backdoor)):
        objs.path(list(points) + [base], f"{label}{slot}")


def scatter(objs, t, pyrng, width, height, border, place, step=30.0):
    """Mirrored scatter over the west half: place(x, y, roll, pyrng_choice) returns a template
    or None for each jittered grid point; the same object goes at the mirrored point."""
    for gi in range(int(width / 2 / step)):
        for gj in range(int(height / step)):
            x = (gi + 0.5 + pyrng.uniform(-0.35, 0.35)) * step
            y = (gj + 0.5 + pyrng.uniform(-0.35, 0.35)) * step
            roll = pyrng.random()
            pick = pyrng.random()
            angle = pyrng.uniform(0, 2 * math.pi)
            if not (20 < x < width / 2 - 10 and 20 < y < height - 20):
                continue
            i, j = int(x / mapgen.CELL) + border, int(y / mapgen.CELL) + border
            template = place(x, y, i, j, roll, pick)
            if template:
                objs.add(template, x, y, angle, owner=mapgen.NEUTRAL_TEAM)
                objs.add(template, width - x, y, math.pi - angle, owner=mapgen.NEUTRAL_TEAM)


def blocked(x, y, circles, segments, road_clear=60.0):
    if any(math.hypot(x - cx, y - cy) < cr for cx, cy, cr in circles):
        return True
    return any(segment_distance(x, y, p0, p1) < road_clear for p0, p1 in segments)


def scripts(names, dock_value):
    unmanned = [(mapgen.ACTION_SET_UNMANNED[0], mapgen.ACTION_SET_UNMANNED[1], [(mapgen.PARAM_UNIT, n)])
                for n in names["dozers"]]
    docks = [(mapgen.ACTION_WAREHOUSE_SET_VALUE[0], mapgen.ACTION_WAREHOUSE_SET_VALUE[1],
              [(mapgen.PARAM_UNIT, n), (mapgen.PARAM_INT, dock_value)]) for n in names["docks"]]
    always = [[(mapgen.CONDITION_TRUE[0], mapgen.CONDITION_TRUE[1], [])]]
    return [
        {"name": "GX_UnmannedDozers", "comment": "Dozers of other generals wait for a crew.",
         "conditions": always, "actions": unmanned},
        {"name": "GX_SupplyDocks", "comment": "Large supply reserves.", "conditions": always, "actions": docks},
    ]


def water_plane(objs, width, height, border, z):
    """One water plane over the whole map: the terrain is above it everywhere but in the water."""
    e = border * mapgen.CELL
    objs.polygon("GXWater", [(-e, -e), (width + e, -e), (width + e, height + e), (-e, height + e)], z=z, water=True)


def finish(t, objs, tag, names, dock_value):
    overlaps = objs.check_overlaps()
    if overlaps:
        raise RuntimeError(f"objects overlap: {overlaps}")
    return mapgen.build(t, objs, tag, scripts(names, dock_value))
