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
- everything outside Art/Textures/ (maps, INI, audio); terrain tiles under
  Art/Terrain/ only with `--terrain`.

`--terrain` builds a separate pack (e.g. `!HDTerrain.big`) for the HD terrain
loader: the same Art/Terrain/ names as RLE TGA (24-bit, or 32-bit with alpha),
exactly 2x or 4x the original size, since the engine detects HD tiles by an
integer ratio to the retail size.

Upscalers:
- `onnx`: Real-ESRGAN x4plus through ONNX Runtime, DirectML on any DirectX 12 GPU
  (onnxruntime-directml) or the CPU; the Windows package uses this by default;
- `esrgan`: runs realesrgan-ncnn-vulkan (Vulkan, works on AMD/NVIDIA/Apple)
  on the colour channels; alpha is resized with Lanczos to keep cut-outs clean;
- `lanczos`: plain resize, for pipeline checks without a GPU.

Requires Python 3.9+ and Pillow 11.2+ (DXT1/DXT5 writing).
"""

# GeneralsX @feature sav-labs 14/10/2026 HD texture pack builder (graphics plan, step 2).

import argparse
import fnmatch
import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

TEXTURE_DIR = "art/textures/"
TEXTURE_EXTS = (".tga", ".dds")
TERRAIN_DIR = "art/terrain/"
TERRAIN_EXTS = (".tga",)
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
    """files: list of (archive name with backslashes, bytes or Path of a file to copy in).

    Path entries are streamed, so a full pack never has to fit in memory.
    """
    sizes = [len(data) if isinstance(data, bytes) else Path(data).stat().st_size for _, data in files]
    names = [n.encode("latin-1") + b"\0" for n, _ in files]
    header_size = 16 + sum(8 + len(n) for n in names)
    offset = header_size
    table = b""
    for size, name in zip(sizes, names):
        table += struct.pack(">II", offset, size) + name
        offset += size
    with open(path, "wb") as f:
        f.write(b"BIGF" + struct.pack("<I", offset) + struct.pack(">II", len(files), header_size))
        f.write(table)
        for _, data in files:
            if isinstance(data, bytes):
                f.write(data)
            else:
                with open(data, "rb") as src:
                    shutil.copyfileobj(src, f)


PART_LIMIT = 2_000_000_000  # BIG offsets are 32-bit; stay well clear of 4 GiB and signed 2 GiB


def write_big_parts(out, files, part_limit=PART_LIMIT):
    """Write files into one archive, or <stem>_01.big, <stem>_02.big, ... when too large.

    Parts from an earlier run that this run does not rewrite are removed, so a
    smaller pack never leaves stale textures behind. Returns the written paths.
    """
    out = Path(out)
    parts, current, size = [], [], 0
    for name, data in files:
        length = len(data) if isinstance(data, bytes) else Path(data).stat().st_size
        if current and size + length + 64 > part_limit:
            parts.append(current)
            current, size = [], 0
        current.append((name, data))
        size += length + 64
    if current or not parts:
        parts.append(current)
    stale = set(out.parent.glob(f"{glob_escape(out.stem)}_[0-9][0-9].big"))
    if len(parts) == 1:
        paths = [out]
    else:
        paths = [out.with_name(f"{out.stem}_{i:02d}.big") for i in range(1, len(parts) + 1)]
        stale.add(out)
    for path in stale - set(paths):
        path.unlink(missing_ok=True)
    for path, part in zip(paths, parts):
        write_big(path, part)
    return paths


def glob_escape(text):
    return re.sub(r"([\[\]*?])", r"[\1]", text)


def is_own_content(big):
    """GeneralsX's own content packs (GeneralsXContent.big and later ones)."""
    return big.name.lower().startswith("generalsx")


def collect_archives(game_dirs):
    """Later directories and later archives win, like the game's load order."""
    merged = {}
    for d in game_dirs:
        for big in sorted(Path(d).glob("*.big"), key=lambda p: p.name.lower()):
            if big.name.startswith("!") or is_own_content(big):
                continue  # never read our own or other mods' output
            merged.update(read_big(big))
    return merged


def own_content_textures(game_dirs):
    """Texture stems shipped in GeneralsX content packs.

    `!` packs load with mod priority and the loader prefers .dds over .tga, so an HD
    copy of any of these names would hide the content pack's own (and newer) art.
    """
    names = set()
    for d in game_dirs:
        for big in Path(d).glob("*.big"):
            if is_own_content(big):
                names |= {Path(n).stem for n in read_big(big) if n.endswith(TEXTURE_EXTS)}
    return names


# ---------------------------------------------------------------- exclusions

def ini_texture_names(archives, game_dirs, path_part, key):
    """Stems of `key = <file>` values in INI files whose path contains path_part."""
    texts = []
    for name, entry in archives.items():
        if name.endswith(".ini") and path_part in name:
            texts.append(read_entry(entry).decode("latin-1", "replace"))
    for d in game_dirs:
        for ini in Path(d).glob("Data/INI/**/*.ini"):
            if path_part in ini.as_posix().lower():
                texts.append(ini.read_text("latin-1", "replace"))
    names = set()
    for t in texts:
        for m in re.finditer(rf"^\s*{key}\s*=\s*(\S+)", t, re.MULTILINE | re.IGNORECASE):
            names.add(Path(m.group(1)).stem.lower())
    return names


def mapped_image_textures(archives, game_dirs):
    """Texture names referenced by MappedImage INI blocks (UI atlases)."""
    return ini_texture_names(archives, game_dirs, "mappedimages", "Texture")


def terrain_tile_textures(archives, game_dirs):
    """Art/Terrain/ sheets that Terrain.ini uses as terrain texture classes.

    Tree textures (W3DTreeDraw TextureName) also live in Art/Terrain/, but the tree
    buffer packs them into its own atlas assuming retail 64 px cells: an upscaled
    tree sheet is read as a 4x4 grid, the atlas overflows and every tree on the map
    falls back to missing.tga (magenta). Only real terrain tiles are upscaled.
    """
    tiles = ini_texture_names(archives, game_dirs, "data/ini/terrain.ini", "Texture")
    trees = ini_texture_names(archives, game_dirs, "data/ini/", "TextureName")
    return tiles - trees, trees


# ---------------------------------------------------------------- upscaling

def upscale_rgb_esrgan(images, esrgan, model, scale, tile, extra_args):
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
        cmd += extra_args
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        out = {}
        for i, key in enumerate(images):
            with Image.open(dst / f"{i:05d}.png") as up:
                out[key] = up.convert("RGB")
        return out


TILE_PAD = 10


def onnx_session(model):
    """DirectML on any DirectX 12 GPU when onnxruntime-directml is installed, CPU otherwise."""
    import onnxruntime as ort
    options = ort.SessionOptions()
    providers = ["CPUExecutionProvider"]
    if "DmlExecutionProvider" in ort.get_available_providers():
        # DirectML needs these off; see the onnxruntime DirectML execution provider docs.
        options.enable_mem_pattern = False
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        providers.insert(0, "DmlExecutionProvider")
    session = ort.InferenceSession(str(model), options, providers=providers)
    print(f"ONNX upscaler on {session.get_providers()[0]}")
    return session


def upscale_rgb_onnx(images, session, tile):
    """4x upscale with the Real-ESRGAN ONNX model, tile by tile to bound GPU memory.

    Each tile is read with TILE_PAD px of context on every side (edge-replicated at
    the image border) and only its centre is kept, so tile seams do not show.
    """
    import numpy as np
    out = {}
    for key, img in images.items():
        src = np.asarray(img, dtype=np.float32).transpose(2, 0, 1) / 255.0
        _, h, w = src.shape
        padded = np.pad(src, ((0, 0), (TILE_PAD, TILE_PAD), (TILE_PAD, TILE_PAD)), mode="edge")
        result = np.zeros((3, h * 4, w * 4), dtype=np.float32)
        for y in range(0, h, tile):
            for x in range(0, w, tile):
                th, tw = min(tile, h - y), min(tile, w - x)
                patch = padded[:, y:y + th + 2 * TILE_PAD, x:x + tw + 2 * TILE_PAD][None]
                up = session.run(None, {"input": np.ascontiguousarray(patch)})[0][0]
                p = TILE_PAD * 4
                result[:, y * 4:(y + th) * 4, x * 4:(x + tw) * 4] = up[:, p:p + th * 4, p:p + tw * 4]
        pixels = (np.clip(result, 0.0, 1.0) * 255.0).round().astype(np.uint8).transpose(1, 2, 0)
        out[key] = Image.fromarray(pixels, "RGB")
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


SHEET_ROWS = 40  # keeps each sheet far below the 65500 px JPEG limit


def comparison_cells(before, after):
    """Centre crops of SHEET_CELL px at output resolution: plain bicubic resize and pack result.

    Comparing 1:1 crops shows the detail a thumbnail downscale would hide. Only the
    crops are kept, so previews of a full pack stay small in memory.
    """
    plain = before.convert("RGB").resize(after.size, Image.Resampling.BICUBIC)
    w, h = after.size
    cw, ch = min(SHEET_CELL, w), min(SHEET_CELL, h)
    box = ((w - cw) // 2, (h - ch) // 2, (w - cw) // 2 + cw, (h - ch) // 2 + ch)
    return plain.crop(box), after.convert("RGB").crop(box)


def comparison_sheets(cells, preview_dir):
    """compare_001.jpg, compare_002.jpg, ...: a row per texture, SHEET_ROWS rows per sheet."""
    for page, first in enumerate(range(0, len(cells), SHEET_ROWS), start=1):
        rows = cells[first:first + SHEET_ROWS]
        sheet = Image.new("RGB", (SHEET_CELL * 2 + 12, len(rows) * (SHEET_CELL + 4)), (32, 32, 32))
        for row, (plain, upscaled) in enumerate(rows):
            y = row * (SHEET_CELL + 4)
            sheet.paste(plain, (0, y))
            sheet.paste(upscaled, (SHEET_CELL + 12, y))
        sheet.save(Path(preview_dir, f"compare_{page:03d}.jpg"), quality=90)


# ---------------------------------------------------------------- main

def decode(data):
    img = Image.open(io.BytesIO(data))
    img.load()
    return img.convert("RGBA")


def default_onnx():
    """realesrgan_x4plus.onnx next to hdpack.exe or hdpack.py (built by export_onnx.py)."""
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    return base / "realesrgan_x4plus.onnx"


def default_esrgan():
    """The packaged hdpack.exe ships realesrgan-ncnn-vulkan.exe next to itself."""
    if getattr(sys, "frozen", False):
        # upscayl-bin is the same CLI on a newer ncnn.
        for exe in ("upscayl-bin.exe", "realesrgan-ncnn-vulkan.exe"):
            bundled = Path(sys.executable).parent / exe
            if bundled.is_file():
                return str(bundled)
    return "realesrgan-ncnn-vulkan"


def main():
    global MAX_OUTPUT_SIZE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-dir", action="append", required=True,
                    help="Folder with the retail .big files (repeat for Generals + Zero Hour; later wins)")
    ap.add_argument("--out", required=True, help="Output archive, e.g. <game>/!HDTextures.big")
    ap.add_argument("--upscaler", choices=("onnx", "esrgan", "lanczos"),
                    default="onnx" if default_onnx().is_file() else "esrgan",
                    help="onnx: Real-ESRGAN via ONNX Runtime (DirectML/CPU); esrgan: ncnn Vulkan binary; lanczos: plain resize")
    ap.add_argument("--onnx", default=str(default_onnx()), help="Real-ESRGAN x4plus ONNX model")
    ap.add_argument("--esrgan", default=default_esrgan(), help="Path to realesrgan-ncnn-vulkan or upscayl-bin")
    ap.add_argument("--model", default="realesrgan-x4plus", help="Real-ESRGAN model name")
    ap.add_argument("--scale", type=int, choices=(2, 4), default=4)
    ap.add_argument("--esrgan-args", default="", help='Extra upscaler arguments, e.g. "-g 0 -j 1:1:1"')
    ap.add_argument("--tile", type=int, default=128, help="Upscaler tile size in source px (lower uses less VRAM, min 32)")
    ap.add_argument("--include", action="append", help="Only texture names matching this glob (e.g. AV*)")
    ap.add_argument("--exclude-list", help="Text file with texture names (no extension) to keep original")
    ap.add_argument("--limit", type=int, default=0, help="Process at most N textures (prototype runs)")
    ap.add_argument("--batch", type=int, default=64, help="Textures per upscaler run")
    ap.add_argument("--preview-dir", help="Also write before/after PNGs here for comparison")
    ap.add_argument("--max-size", type=int, default=MAX_OUTPUT_SIZE, help="Largest output side in px")
    ap.add_argument("--cache-dir", help="Keep upscaled .dds here and reuse them on the next run "
                    "(default: <out name>.cache next to the output)")
    ap.add_argument("--terrain", action="store_true",
                    help="Upscale Art/Terrain/ tiles to TGA for the HD terrain loader instead of model textures")
    ap.add_argument("--part-size", type=int, default=PART_LIMIT, help=argparse.SUPPRESS)
    args = ap.parse_args()
    MAX_OUTPUT_SIZE = args.max_size
    cache_dir = Path(args.cache_dir) if args.cache_dir else Path(args.out).with_suffix(".cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    mode = "terrain" if args.terrain else "textures"
    out_ext = ".tga" if args.terrain else ".dds"
    source_dir, source_exts = (TERRAIN_DIR, TERRAIN_EXTS) if args.terrain else (TEXTURE_DIR, TEXTURE_EXTS)
    settings = f"{args.upscaler}|{args.model}|{args.scale}|{args.max_size}|{mode}|v1".encode()

    archives = collect_archives(args.game_dir)
    ui_textures = mapped_image_textures(archives, args.game_dir)
    content_textures = own_content_textures(args.game_dir)
    excluded = set(ui_textures) | content_textures
    terrain_tiles = None
    if args.terrain:
        terrain_tiles, tree_textures = terrain_tile_textures(archives, args.game_dir)
        excluded |= tree_textures
        if not terrain_tiles:
            print("warning: no Terrain.ini found, upscaling every Art/Terrain/ sheet except tree textures",
                  file=sys.stderr)
            terrain_tiles = None
    if args.exclude_list:
        excluded |= {l.strip().lower() for l in open(args.exclude_list) if l.strip() and not l.startswith("#")}

    # One source per texture name; a .dds beats a .tga like in the texture loader.
    sources = {}
    for name, entry in archives.items():
        if not name.startswith(source_dir) or not name.endswith(source_exts):
            continue
        stem = Path(name).stem
        if stem in excluded or (terrain_tiles is not None and stem not in terrain_tiles):
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
    session = None
    cached = 0
    skipped = {"too_small": [], "already_max_size": [], "unreadable": []}
    started = time.monotonic()
    for start in range(0, len(keys), args.batch):
        batch = {}
        for stem in keys[start:start + args.batch]:
            original = sources[stem][3]
            name = original[:original.rfind(".")] + out_ext
            data = read_entry(sources[stem])
            # Cache key: source bytes plus every setting that changes the result.
            cache_file = cache_dir / f"{stem}-{hashlib.sha1(data + settings).hexdigest()[:16]}{out_ext}"
            if cache_file.is_file():
                output.append((name, cache_file))
                cached += 1
                continue
            try:
                img = decode(data)
            except Exception as e:  # unreadable or unsupported source: keep the original
                print(f"  skip {stem}: {e}", file=sys.stderr)
                skipped["unreadable"].append(original)
                continue
            if min(img.size) < MIN_SOURCE_SIZE:
                skipped["too_small"].append(original)
                continue
            if target_size(*img.size, args.scale) == img.size:
                # Already at --max-size: upscaling would only cost time and change nothing.
                skipped["already_max_size"].append(original)
                continue
            batch[stem] = (img, name, cache_file)
        if not batch:
            continue

        rgb = {k: v[0].convert("RGB") for k, v in batch.items()}
        if args.upscaler == "onnx":
            if session is None:
                session = onnx_session(args.onnx)
            up_rgb = upscale_rgb_onnx(rgb, session, args.tile)
        elif args.upscaler == "esrgan":
            up_rgb = upscale_rgb_esrgan(rgb, args.esrgan, args.model, args.scale, args.tile, args.esrgan_args.split())
        else:
            up_rgb = {k: v.resize(target_size(*v.size, args.scale), Image.Resampling.LANCZOS) for k, v in rgb.items()}

        for stem, (img, name, cache_file) in batch.items():
            size = target_size(*img.size, args.scale)
            colour = up_rgb[stem]
            if colour.size != size:
                colour = colour.resize(size, Image.Resampling.LANCZOS)
            alpha = img.getchannel("A")
            has_alpha = alpha.getextrema()[0] < 255
            result = colour.convert("RGBA")
            result.putalpha(alpha.resize(size, Image.Resampling.LANCZOS))
            partial = cache_file.with_suffix(".tmp")
            if args.terrain:
                # The terrain loader reads plain TGA; drop alpha when the tile has none.
                (result if has_alpha else result.convert("RGB")).save(partial, "TGA", compression="tga_rle")
            else:
                partial.write_bytes(write_dds_mipmapped(result, has_alpha))
            partial.replace(cache_file)  # only complete files count as cached
            output.append((name, cache_file))
            if args.preview_dir:
                img.save(Path(args.preview_dir, f"{stem}_before.png"))
                result.save(Path(args.preview_dir, f"{stem}_after.png"))
                pairs.append(comparison_cells(img, result))
        print(f"  {min(start + args.batch, len(keys))}/{len(keys)}")

    paths = write_big_parts(args.out, output, args.part_size)
    if args.preview_dir:
        comparison_sheets(pairs, args.preview_dir)
    report = {
        "textures_written": len(output),
        "reused_from_cache": cached,
        "upscaled_now": len(output) - cached,
        "skipped_too_small": len(skipped["too_small"]),
        "skipped_already_max_size": len(skipped["already_max_size"]),
        "skipped_unreadable": len(skipped["unreadable"]),
        "skipped_files": skipped,  # originals stay in the game as they are
        "ui_textures_excluded": len(ui_textures),
        "tree_textures_excluded": len(excluded - ui_textures - content_textures) if args.terrain else 0,
        "content_pack_textures_excluded": sorted(content_textures),
        "parts": {str(p): p.stat().st_size for p in paths},
        "total_bytes": sum(p.stat().st_size for p in paths),
        "seconds": round(time.monotonic() - started, 1),
        "upscaler": session.get_providers()[0] if session else args.upscaler,
        "settings": {"scale": args.scale, "max_size": args.max_size, "include": args.include, "limit": args.limit},
    }
    report_path = Path(args.out).with_suffix(".report.json")
    report_path.write_text(json.dumps(report, indent=2))
    print(f"{cached} textures reused from {cache_dir}")
    print(f"wrote {len(output)} textures to " + ", ".join(f"{p} ({p.stat().st_size / 2**20:.0f} MB)" for p in paths))
    print("skipped: " + ", ".join(f"{len(v)} {k.replace('_', ' ')}" for k, v in skipped.items()))
    print(f"report: {report_path}, {report['seconds']} s")


if __name__ == "__main__":
    main()
