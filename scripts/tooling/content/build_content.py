#!/usr/bin/env python3
"""Build the GeneralsX content pack (GeneralsXContent.big).

GeneralsX @feature Claude 15/10/2026 Generates our own models and textures, renders their
command-bar cameos, copies the INI and string sources from content/ and packs everything into
one .big next to the game executable. Nothing from the retail game goes into the pack: the INI
only references retail names (sounds, effects, weapons), which load from the player's own copy.

Usage: build_content.py <repo root> <output dir> [--preview <dir>]
"""

import argparse
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "models"))

import textures  # noqa: E402
from PIL import Image  # noqa: E402
from render import render  # noqa: E402
import gx_mbt  # noqa: E402

PACK_NAME = "GeneralsXContent.big"


def write_big(path, files):
    """files: list of (archive path with backslashes, bytes). Same layout as retail .big archives."""
    entries = sorted(files, key=lambda f: f[0].lower())
    header_size = 16 + sum(8 + len(name.encode("ascii")) + 1 for name, _ in entries)
    offset = header_size
    table = b""
    for name, data in entries:
        table += struct.pack(">II", offset, len(data)) + name.encode("ascii") + b"\0"
        offset += len(data)
    with open(path, "wb") as f:
        f.write(b"BIGF" + struct.pack("<I", offset) + struct.pack(">II", len(entries), header_size))
        f.write(table)
        for _, data in entries:
            f.write(data)


def build_textures(tex_dir):
    out = {}
    out["gxmbt_body.tga"] = textures.camo_atlas(1024, seed=11, palette=[(176, 160, 118), (128, 116, 82), (92, 86, 64)])
    out["gxmbt_bodyd.tga"] = textures.burnt(out["gxmbt_body.tga"], seed=12)
    out["gxmbt_tread.tga"] = textures.tread(256, 64, links=8, seed=13)
    out["gxteam.tga"] = textures.team_panel(128, seed=14)
    out["gxflash.tga"] = textures.flash(128)
    for name, img in out.items():
        textures.save_tga(img, os.path.join(tex_dir, name))
    return out


def build_models(w3d_dir, tex):
    models = {
        "AVGXMBT": gx_mbt.build("AVGXMBT", "gxmbt_body.tga", "gxmbt_tread.tga", "gxteam.tga", "gxflash.tga"),
        "AVGXMBT_D": gx_mbt.build("AVGXMBT_D", "gxmbt_bodyd.tga", "gxmbt_tread.tga", "gxteam.tga", "gxflash.tga"),
    }
    for name, model in models.items():
        with open(os.path.join(w3d_dir, name + ".w3d"), "wb") as f:
            f.write(model.pack())
    return models


def fit(img, size, pad=3):
    """Crop a render to its silhouette and scale it to fill size."""
    img = img.crop(img.getbbox())
    scale = min((size[0] - 2 * pad) / img.width, (size[1] - 2 * pad) / img.height)
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.alpha_composite(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2))
    return out


def build_cameos(tex_dir, models, tex):
    """One 512x256 sheet: button (120x96) and selection portrait (216x178), per unit."""
    sheet = textures.cameo_sheet()
    tank = models["AVGXMBT"]
    button = textures.cameo_frame(fit(render(tank, tex, size=(480, 480), yaw=35, pitch=24), (120, 96)), (120, 96))
    portrait = textures.cameo_frame(fit(render(tank, tex, size=(640, 640), yaw=30, pitch=20), (216, 178)), (216, 178))
    sheet.paste(button, (0, 0))
    sheet.paste(portrait, (128, 0))
    textures.save_tga(sheet, os.path.join(tex_dir, "gxcameos.tga"))
    return sheet


def collect(root):
    files = []
    for dirpath, _, names in os.walk(root):
        for name in names:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace("/", "\\")
            with open(full, "rb") as f:
                files.append((rel, f.read()))
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("out")
    parser.add_argument("--preview")
    args = parser.parse_args()

    stage = os.path.join(args.out, "stage")
    shutil.rmtree(stage, ignore_errors=True)
    shutil.copytree(os.path.join(args.repo, "content"), stage)
    tex_dir = os.path.join(stage, "Art", "Textures")
    w3d_dir = os.path.join(stage, "Art", "W3D")
    os.makedirs(tex_dir, exist_ok=True)
    os.makedirs(w3d_dir, exist_ok=True)

    tex = build_textures(tex_dir)
    models = build_models(w3d_dir, tex)
    build_cameos(tex_dir, models, tex)

    write_big(os.path.join(args.out, PACK_NAME), collect(stage))

    if args.preview:
        os.makedirs(args.preview, exist_ok=True)
        for name, model in models.items():
            for yaw in (35, 150):
                render(model, tex, size=(960, 720), yaw=yaw, pitch=26, background=(70, 78, 70, 255)).save(
                    os.path.join(args.preview, f"{name}_{yaw}.png"))
    print(f"wrote {os.path.join(args.out, PACK_NAME)}")


if __name__ == "__main__":
    main()
