#!/usr/bin/env python3
"""Build an HD texture pack from the player's own Zero Hour installation.

The tool reads the retail .big archives, upscales the model textures under
Art/Textures/ and writes them as mipmapped DXT .dds files into a single mod
archive (default `!HDTextures.big`). Archives whose name starts with `!` take
priority over the retail archives, and the texture loader opens the .dds before
the .tga of the same name, so no retail file is changed or redistributed.

Excluded on purpose:
- textures used by MappedImage INI entries (UI, cameos, cursors): their INI
  coordinates are in pixels of the original texture size;
- everything outside Art/Textures/ (terrain tiles, maps, INI, audio).

Upscalers:
- `esrgan`: runs realesrgan-ncnn-vulkan (Vulkan, works on AMD/NVIDIA/Apple)
  on the colour channels; alpha is resized with Lanczos to keep cut-outs clean;
- `lanczos`: plain resize, for pipeline checks without a GPU.

Requires Python 3.9+ and Pillow 11.2+ (DXT1/DXT5 writing).
"""

# GeneralsX @feature sav-labs 14/10/2026 HD texture pack builder (graphics plan, step 2).

import argparse
import fnmatch
import io
import os
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

TEXTURE_DIR = "art/textures/"
TEXTURE_EXTS = (".tga", ".dds")
MIN_SOURCE_SIZE = 32
MAX_OUTPUT_SIZE = 2048


# ---------------------------------------------------------------- BIG archives

def read_big(path):
    """Return {lowercase name: (archive path, offset, size, original name)}."""
    entries = {}
    with open(path, "rb") as f:
        if f.read(4) != b"BIGF":
            return entries
        f.read(4)  # archive size, little endian, unused
        count, _first = struct.unpack(">II", f.read(8))
        for _ in range(count):
            offset, size = struct.unpack(">II", f.read(8))
            name = bytearray()
            while (c := f.read(1)) not in (b"\0", b""):
                name += c
            name = name.decode("latin-1")
            entries[name.replace("\\", "/").lower()] = (path, offset, size, name)
    return entries


def read_entry(entry):
    path, offset, size, _ = entry
    with open(path, "rb") as f:
        f.seek(offset)
        return f.read(size)


def write_big(path, files):
    """files: list of (archive name with backslashes, bytes)."""
    names = [n.encode("latin-1") + b"\0" for n, _ in files]
    header_size = 16 + sum(8 + len(n) for n in names)
    offset = header_size
    table = b""
    for (_, data), name in zip(files, names):
        table += struct.pack(">II", offset, len(data)) + name
        offset += len(data)
    with open(path, "wb") as f:
        f.write(b"BIGF" + struct.pack("<I", offset) + struct.pack(">II", len(files), header_size))
        f.write(table)
        for _, data in files:
            f.write(data)


def collect_archives(game_dirs):
    """Later directories and later archives win, like the game's load order."""
    merged = {}
    for d in game_dirs:
        for big in sorted(Path(d).glob("*.big"), key=lambda p: p.name.lower()):
            if big.name.startswith("!"):
                continue  # never read our own or other mods' output
            merged.update(read_big(big))
    return merged


# ---------------------------------------------------------------- exclusions

def mapped_image_textures(archives, game_dirs):
    """Texture names referenced by MappedImage INI blocks (UI atlases)."""
    texts = []
    for name, entry in archives.items():
        if name.endswith(".ini") and "mappedimages" in name:
            texts.append(read_entry(entry).decode("latin-1", "replace"))
    for d in game_dirs:
        for ini in Path(d).glob("Data/INI/MappedImages/**/*.ini"):
            texts.append(ini.read_text("latin-1", "replace"))
    names = set()
    for t in texts:
        for m in re.finditer(r"^\s*Texture\s*=\s*(\S+)", t, re.MULTILINE | re.IGNORECASE):
            names.add(Path(m.group(1)).stem.lower())
    return names


# ---------------------------------------------------------------- upscaling

def upscale_rgb_esrgan(images, esrgan, model, scale, tile):
    """Upscale a dict of {key: RGB image} with realesrgan-ncnn-vulkan in one run."""
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp, "in"), Path(tmp, "out")
        src.mkdir()
        dst.mkdir()
        for i, img in enumerate(images.values()):
            img.save(src / f"{i:05d}.png")
        # The x4 models only run at 4x; target_size() brings the result down to the requested scale.
        model_scale = 4 if "x4" in model else scale
        # A fixed tile size keeps VRAM use bounded; auto tiling overflows the 2 GB UMA heap of iGPUs like the Radeon 780M.
        cmd = [esrgan, "-i", str(src), "-o", str(dst), "-n", model, "-s", str(model_scale), "-f", "png", "-t", str(tile)]
        models = Path(esrgan).resolve().parent / "models"
        if models.is_dir():
            cmd += ["-m", str(models)]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        out = {}
        for i, key in enumerate(images):
            with Image.open(dst / f"{i:05d}.png") as up:
                out[key] = up.convert("RGB")
        return out


def target_size(w, h, scale):
    factor = scale
    while factor > 1 and max(w, h) * factor > MAX_OUTPUT_SIZE:
        factor //= 2
    return w * factor, h * factor


# ---------------------------------------------------------------- DDS writing

DDSD_CAPS, DDSD_HEIGHT, DDSD_WIDTH, DDSD_PIXELFORMAT = 0x1, 0x2, 0x4, 0x1000
DDSD_MIPMAPCOUNT, DDSD_LINEARSIZE = 0x20000, 0x80000
DDSCAPS_COMPLEX, DDSCAPS_TEXTURE, DDSCAPS_MIPMAP = 0x8, 0x1000, 0x400000
DDPF_FOURCC = 0x4


def dxt_level(img, fourcc):
    """Compress one mip level with Pillow and return the raw block data."""
    buf = io.BytesIO()
    img.save(buf, "DDS", pixel_format=fourcc)
    return buf.getvalue()[128:]


def write_dds_mipmapped(img, has_alpha):
    fourcc = "DXT5" if has_alpha else "DXT1"
    levels = []
    level = img
    while True:
        levels.append(dxt_level(level, fourcc))
        if level.width <= 4 or level.height <= 4:
            break
        level = level.resize((level.width // 2, level.height // 2), Image.Resampling.LANCZOS)
    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_MIPMAPCOUNT | DDSD_LINEARSIZE
    caps = DDSCAPS_TEXTURE | DDSCAPS_COMPLEX | DDSCAPS_MIPMAP
    pixel_format = struct.pack("<II4s5I", 32, DDPF_FOURCC, fourcc.encode(), 0, 0, 0, 0, 0)
    header = struct.pack("<7I44x", 124, flags, img.height, img.width, len(levels[0]), 0, len(levels))
    header += pixel_format + struct.pack("<5I", caps, 0, 0, 0, 0)
    return b"DDS " + header + b"".join(levels)


# ---------------------------------------------------------------- previews

SHEET_CELL = 256


def comparison_sheet(pairs, path):
    """One image with a row per texture: plain resize on the left, pack result on the right.

    Each cell is a centre crop of SHEET_CELL px at output resolution, so detail is
    compared 1:1 instead of being hidden by a thumbnail downscale.
    """
    if not pairs:
        return
    sheet = Image.new("RGB", (SHEET_CELL * 2 + 12, len(pairs) * (SHEET_CELL + 4)), (32, 32, 32))
    for row, (before, after) in enumerate(pairs):
        plain = before.convert("RGB").resize(after.size, Image.Resampling.BICUBIC)
        w, h = after.size
        cw, ch = min(SHEET_CELL, w), min(SHEET_CELL, h)
        box = ((w - cw) // 2, (h - ch) // 2, (w - cw) // 2 + cw, (h - ch) // 2 + ch)
        y = row * (SHEET_CELL + 4)
        sheet.paste(plain.crop(box), (0, y))
        sheet.paste(after.convert("RGB").crop(box), (SHEET_CELL + 12, y))
    sheet.save(path, quality=90)


# ---------------------------------------------------------------- main

def decode(data):
    img = Image.open(io.BytesIO(data))
    img.load()
    return img.convert("RGBA")


def default_esrgan():
    """The packaged hdpack.exe ships realesrgan-ncnn-vulkan.exe next to itself."""
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).parent / "realesrgan-ncnn-vulkan.exe"
        if bundled.is_file():
            return str(bundled)
    return "realesrgan-ncnn-vulkan"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-dir", action="append", required=True,
                    help="Folder with the retail .big files (repeat for Generals + Zero Hour; later wins)")
    ap.add_argument("--out", required=True, help="Output archive, e.g. <game>/!HDTextures.big")
    ap.add_argument("--upscaler", choices=("esrgan", "lanczos"), default="esrgan")
    ap.add_argument("--esrgan", default=default_esrgan(), help="Path to realesrgan-ncnn-vulkan")
    ap.add_argument("--model", default="realesrgan-x4plus", help="Real-ESRGAN model name")
    ap.add_argument("--scale", type=int, choices=(2, 4), default=4)
    ap.add_argument("--tile", type=int, default=128, help="Real-ESRGAN tile size in px (lower uses less VRAM, min 32)")
    ap.add_argument("--include", action="append", help="Only texture names matching this glob (e.g. AV*)")
    ap.add_argument("--exclude-list", help="Text file with texture names (no extension) to keep original")
    ap.add_argument("--limit", type=int, default=0, help="Process at most N textures (prototype runs)")
    ap.add_argument("--batch", type=int, default=64, help="Textures per upscaler run")
    ap.add_argument("--preview-dir", help="Also write before/after PNGs here for comparison")
    args = ap.parse_args()

    archives = collect_archives(args.game_dir)
    ui_textures = mapped_image_textures(archives, args.game_dir)
    excluded = set(ui_textures)
    if args.exclude_list:
        excluded |= {l.strip().lower() for l in open(args.exclude_list) if l.strip() and not l.startswith("#")}

    # One source per texture name; a .dds beats a .tga like in the texture loader.
    sources = {}
    for name, entry in archives.items():
        if not name.startswith(TEXTURE_DIR) or not name.endswith(TEXTURE_EXTS):
            continue
        stem = Path(name).stem
        if stem in excluded:
            continue
        if args.include and not any(fnmatch.fnmatch(stem, p.lower()) for p in args.include):
            continue
        if stem not in sources or name.endswith(".dds"):
            sources[stem] = entry
    keys = sorted(sources)
    if args.limit:
        keys = keys[:args.limit]
    print(f"{len(archives)} archive entries, {len(ui_textures)} UI textures skipped, {len(keys)} to upscale")

    if args.preview_dir:
        os.makedirs(args.preview_dir, exist_ok=True)

    output = []
    pairs = []
    for start in range(0, len(keys), args.batch):
        batch = {}
        for stem in keys[start:start + args.batch]:
            try:
                img = decode(read_entry(sources[stem]))
            except Exception as e:  # unreadable or unsupported source: keep the original
                print(f"  skip {stem}: {e}", file=sys.stderr)
                continue
            if min(img.size) < MIN_SOURCE_SIZE:
                continue
            batch[stem] = img
        if not batch:
            continue

        rgb = {k: v.convert("RGB") for k, v in batch.items()}
        if args.upscaler == "esrgan":
            up_rgb = upscale_rgb_esrgan(rgb, args.esrgan, args.model, args.scale, args.tile)
        else:
            up_rgb = {k: v.resize(target_size(*v.size, args.scale), Image.Resampling.LANCZOS) for k, v in rgb.items()}

        for stem, img in batch.items():
            size = target_size(*img.size, args.scale)
            colour = up_rgb[stem]
            if colour.size != size:
                colour = colour.resize(size, Image.Resampling.LANCZOS)
            alpha = img.getchannel("A")
            has_alpha = alpha.getextrema()[0] < 255
            result = colour.convert("RGBA")
            result.putalpha(alpha.resize(size, Image.Resampling.LANCZOS))
            original = sources[stem][3]
            name = original[:original.rfind(".")] + ".dds"
            output.append((name, write_dds_mipmapped(result, has_alpha)))
            if args.preview_dir:
                img.save(Path(args.preview_dir, f"{stem}_before.png"))
                result.save(Path(args.preview_dir, f"{stem}_after.png"))
                pairs.append((img, result))
        print(f"  {min(start + args.batch, len(keys))}/{len(keys)}")

    write_big(args.out, output)
    if args.preview_dir:
        comparison_sheet(pairs, Path(args.preview_dir, "compare.jpg"))
    print(f"wrote {len(output)} textures to {args.out}")


if __name__ == "__main__":
    main()
