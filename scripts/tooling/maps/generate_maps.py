#!/usr/bin/env python3
"""Generate the GeneralsX skirmish maps into content/Maps (packed into GeneralsXContent.big).

GeneralsX @feature Claude 16/10/2026 Each layout module returns the .map bytes plus its
terrain and objects; this writes Maps\\<name>\\<name>.map and the 128x128 .tga the skirmish
menu shows, and optionally larger review pictures.

Usage: generate_maps.py <repo root> [--preview <dir>]
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import preview  # noqa: E402
import city_lines  # noqa: E402
import desert_oasis  # noqa: E402
import frozen_divide  # noqa: E402
import mountain_pass  # noqa: E402
import twin_rivers  # noqa: E402

LAYOUTS = [twin_rivers, mountain_pass, desert_oasis, frozen_divide, city_lines]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("--preview")
    args = parser.parse_args()
    for layout in LAYOUTS:
        data, terrain, objs = layout.generate()
        folder = os.path.join(args.repo, "content", "Maps", layout.NAME)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, layout.NAME + ".map"), "wb") as f:
            f.write(data)
        preview.tga(terrain, objs, os.path.join(folder, layout.NAME + ".tga"))
        print(f"wrote {folder} ({len(data)} bytes, {len(objs.items)} objects)")
        if args.preview:
            os.makedirs(args.preview, exist_ok=True)
            preview.top_view(terrain, objs).save(os.path.join(args.preview, layout.NAME + " top.png"))
            for yaw in (45, 135, 225):
                preview.perspective(terrain, objs, yaw).save(
                    os.path.join(args.preview, f"{layout.NAME} {yaw}.jpg"), quality=90)


if __name__ == "__main__":
    main()
