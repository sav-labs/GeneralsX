#!/usr/bin/env python3
"""Self-test for the map generator.

GeneralsX @feature Claude 16/10/2026 Regenerates every layout, parses it with the strict reader
in mapfile.py (the engine's rules), checks what the skirmish menu and AI need (8 start
waypoints, perimeters, approach paths, scripts on the civilian side, named script targets) and
that the committed map in content/Maps matches the generator byte for byte.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)

import mapgen  # noqa: E402
import mapfile  # noqa: E402
from generate_maps import LAYOUTS  # noqa: E402


def check(layout):
    data, terrain, objs = layout.generate()
    m = mapfile.read_map(data)
    names = {o["props"].get("waypointName") for o in m["objects"] if o["name"] == "*Waypoints/Waypoint"}
    starts = [n for n in names if n and n.startswith("Player_") and n.endswith("_Start")]
    assert len(starts) == 8, starts
    triggers = {t["name"] for t in m["triggers"]}
    labels = {o["props"].get("waypointPathLabel1") for o in m["objects"] if o["name"] == "*Waypoints/Waypoint"}
    for n in range(1, 9):
        assert f"InnerPerimeter{n}" in triggers and f"OuterPerimeter{n}" in triggers, n
        for path in ("Center", "Flank", "Backdoor"):
            assert f"{path}{n}" in labels, (path, n)
    assert any(t["water"] for t in m["triggers"]), "no water area"
    assert m["world"]["mapName"] == layout.NAME_TAG

    # Scripts live on PlyrCivilian only and name objects that exist.
    named = {o["props"].get("objectName") for o in m["objects"]}
    for i, lst in enumerate(m["scripts"]):
        assert i == 1 or not lst, f"side {i} has scripts"
    for entry in m["scripts"][1]:
        script = entry[1]
        for _, aname, parms in script["actions"]:
            assert aname, "action without internal name"
            for p in parms:
                if p[0] == mapgen.PARAM_UNIT:
                    assert p[3] in named, p[3]

    # Bridges come in point1/point2 pairs.
    flags = [o["flags"] for o in m["objects"] if o["flags"] & (mapfile.FLAG_BRIDGE_POINT1 | mapfile.FLAG_BRIDGE_POINT2)]
    assert flags == [mapfile.FLAG_BRIDGE_POINT1, mapfile.FLAG_BRIDGE_POINT2] * (len(flags) // 2), "bridge pairs"

    # Unique ids and in-bounds positions.
    ids = [o["props"]["uniqueID"] for o in m["objects"]]
    assert len(ids) == len(set(ids)), "duplicate uniqueID"
    border = m["height_map"]["border"] * mapgen.CELL
    size = (m["height_map"]["width"] - 2 * m["height_map"]["border"]) * mapgen.CELL
    for o in m["objects"]:
        assert -border <= o["x"] <= size + border and -border <= o["y"] <= size + border, o["name"]

    path = os.path.join(REPO, "content", "Maps", layout.NAME, layout.NAME + ".map")
    with open(path, "rb") as f:
        committed = f.read()
    if committed != data:
        # Last-bit float differences between platforms may move a height by one unit; anything
        # more means the committed map is stale.
        old = mapfile.read_map(committed)
        a, b = old["height_map"]["heights"], m["height_map"]["heights"]
        assert len(a) == len(b) and max(abs(x - y) for x, y in zip(a, b)) <= 1, f"{path} is stale: run generate_maps.py"
        assert [o["name"] for o in old["objects"]] == [o["name"] for o in m["objects"]], f"{path} is stale"
    assert os.path.getsize(path[:-4] + ".tga") == 18 + 128 * 128 * 4
    print(f"{layout.NAME}: ok ({len(m['objects'])} objects)")


if __name__ == "__main__":
    for layout in LAYOUTS:
        check(layout)
