#!/usr/bin/env python3
"""Make a skirmish map with the GeneralsX mechanics from a few parameters.

GeneralsX @feature Claude 16/10/2026 One command builds a ready .map and its skirmish menu
preview (.tga) with the base kit (bunkers, artillery, supply docks, two unmanned dozers of other
generals per base), capturable GLA compounds, airfields, factories, power plants, tech
buildings and superweapons. See README.md next to this script.

Usage: make_map.py --players 6 --biome snow --layout river --seed 42 [--name "My Map"]
                   [--out <maps folder>] [--repo <repo root>] [--preview <dir>]
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import custom  # noqa: E402
import mapfile  # noqa: E402
import preview  # noqa: E402


def register(repo, layout):
    """Add the map's display name to content/Data/generalsx.str unless it is there."""
    path = os.path.join(repo, "content", "Data", "generalsx.str")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if layout.NAME_TAG + "\n" in text:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(f'\n{layout.NAME_TAG}\n"{layout.NAME}"\nEND\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--players", type=int, default=4, choices=(2, 4, 6, 8))
    parser.add_argument("--biome", default="temperate", choices=sorted(custom.BIOMES))
    parser.add_argument("--layout", default="lines", choices=custom.LAYOUTS)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--name", help="display name (default: from the parameters)")
    parser.add_argument("--out", help="folder to write <map name>/<map name>.map into, e.g. the game's user Maps folder")
    parser.add_argument("--repo", help="repo root: write into content/Maps and add the name to generalsx.str")
    parser.add_argument("--preview", help="folder for a top view and a perspective view")
    args = parser.parse_args()

    layout = custom.Custom(args.players, args.biome, args.layout, args.seed, args.name,
                           string_tag=bool(args.repo))
    data, terrain, objs = layout.generate()
    mapfile.read_map(data)  # the written map parses back
    out = os.path.join(args.repo, "content", "Maps") if args.repo else (args.out or ".")
    folder = os.path.join(out, layout.NAME)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, layout.NAME + ".map"), "wb") as f:
        f.write(data)
    preview.tga(terrain, objs, os.path.join(folder, layout.NAME + ".tga"))
    if args.repo:
        register(args.repo, layout)
    if args.preview:
        os.makedirs(args.preview, exist_ok=True)
        preview.top_view(terrain, objs).save(os.path.join(args.preview, layout.NAME + " top.png"))
        preview.perspective(terrain, objs, 45).save(os.path.join(args.preview, layout.NAME + " 45.jpg"), quality=90)
    print(f"wrote {folder} ({len(data)} bytes, {len(objs.items)} objects)")


if __name__ == "__main__":
    main()
