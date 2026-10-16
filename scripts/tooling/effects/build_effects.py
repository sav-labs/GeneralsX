#!/usr/bin/env python3
"""Build the GeneralsX effects pack (GeneralsXEffects.big).

GeneralsX @feature Claude 16/10/2026 Generates our own particle textures (fx_textures.py) and the
particle system and FX list INI (fx_systems.py) and packs them into one .big next to the game
executable. The INI lands in Data\\INI\\GeneralsX, which the game loads before every match, so the
pack replaces retail explosions by FX list name without touching any retail file.

Usage: build_effects.py <output dir> [--preview <file.mp4>]
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "content"))

import fx_systems  # noqa: E402
import fx_textures  # noqa: E402
from build_content import write_big  # noqa: E402

PACK_NAME = "GeneralsXEffects.big"


def build(out_dir):
    files = []
    for name, rgba in fx_textures.build_all().items():
        path = os.path.join(out_dir, "stage", name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fx_textures.to_image(rgba).save(path, format="TGA", compression=None)
        with open(path, "rb") as f:
            files.append(("Art\\Textures\\" + name, f.read()))
    for name, text in fx_systems.write_ini().items():
        files.append((name, text.replace("\n", "\r\n").encode("ascii")))
    pack = os.path.join(out_dir, PACK_NAME)
    write_big(pack, files)
    return pack


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--preview")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    print("wrote " + build(args.out))
    if args.preview:
        import preview
        preview.simulate("tank", 9.0, 1280, args.preview)
        print("wrote " + args.preview)


if __name__ == "__main__":
    main()
