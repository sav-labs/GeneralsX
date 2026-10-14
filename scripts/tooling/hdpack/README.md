# HD texture pack builder

`hdpack.py` builds an HD texture pack from the player's own copy of the game. No retail file is shipped or modified: the tool reads the installed `.big` archives and writes a new mod archive next to them.

## What it does

1. Reads every retail `*.big` in the given game folders (archives starting with `!` are skipped).
2. Takes the textures under `Art/Textures/` and skips the ones used by `MappedImage` INI entries (UI, cameos, cursors), whose coordinates depend on the original size. Terrain tiles live outside `Art/Textures/` and are not touched.
3. Upscales colour with Real-ESRGAN (`realesrgan-ncnn-vulkan`, runs on Vulkan) and alpha with Lanczos, capped at 2048 px.
4. Writes mipmapped DXT1 (opaque) or DXT5 (alpha) `.dds` files into `!HDTextures.big`. The `!` prefix makes the game prefer this archive over retail ones, and the texture loader opens `name.dds` before `name.tga`.

Delete `!HDTextures.big` to go back to the original textures.

## Requirements

- Python 3.9+ and Pillow 11.2+ (`python -m pip install pillow`)
- [realesrgan-ncnn-vulkan](https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan/releases) (BSD-3-Clause) with its `models/` folder

## Usage

Windows package (artifact `hdpack-win64` of the "Build HD texture pack tool" workflow, Real-ESRGAN included):

```
hdpack.exe --game-dir "<Zero Hour folder>" --out "<Zero Hour folder>\!HDTextures.big" --include "AV*" --limit 30 --preview-dir previews
```

From source:

```
python hdpack.py --game-dir "<Zero Hour folder>" --out "<Zero Hour folder>/!HDTextures.big" \
    --esrgan "<path>/realesrgan-ncnn-vulkan.exe"
```

Useful options:

- `--include "AV*"`: only textures matching a glob (prototype on one faction)
- `--limit 30`: stop after N textures
- `--preview-dir previews`: write `<name>_before.png` / `<name>_after.png` pairs and `compare.jpg` (1:1 crops, bicubic on the left, pack on the right)
- `--exclude-list keep.txt`: texture names that keep the original (one per line)
- `--upscaler lanczos`: plain resize, to check the pipeline without a GPU
- `--scale 2`: 2x instead of 4x
- `--tile 64`: smaller Real-ESRGAN tiles if the GPU runs out of memory (default 128)
