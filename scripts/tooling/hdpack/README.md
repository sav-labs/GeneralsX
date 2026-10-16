# HD texture pack builder

`hdpack.py` builds an HD texture pack from the player's own copy of the game. No retail file is shipped or modified: the tool reads the installed `.big` archives and writes a new mod archive next to them.

## What it does

1. Reads every retail `*.big` in the given game folders (archives starting with `!` are skipped).
2. Takes the textures under `Art/Textures/` and skips the ones used by `MappedImage` INI entries (UI, cameos, cursors), whose coordinates depend on the original size. Terrain tiles live outside `Art/Textures/` and are not touched.
3. Upscales colour with Real-ESRGAN x4plus (ONNX Runtime with DirectML on the GPU, or the CPU; `realesrgan-ncnn-vulkan` as an alternative) and alpha with Lanczos, capped at 2048 px.
4. Writes mipmapped DXT1 (opaque) or DXT5 (alpha) `.dds` files into `!HDTextures.big`. The `!` prefix makes the game prefer this archive over retail ones, and the texture loader opens `name.dds` before `name.tga`.

Packs over 2 GB are split into `!HDTextures_01.big`, `!HDTextures_02.big`, ... because BIG archives use 32-bit offsets. Delete the `!HDTextures*.big` files to go back to the original textures.

After each run `<out name>.report.json` lists textures written, reused from the cache and skipped, part sizes, time and the upscaler used. Textures already at `--max-size` are skipped, since upscaling them changes nothing.

## Requirements

- Python 3.9+ and Pillow 11.2+ (`python -m pip install pillow`)
- For `--upscaler onnx` (the default when `realesrgan_x4plus.onnx` sits next to the tool): numpy and `onnxruntime-directml` (Windows GPU) or `onnxruntime` (CPU). Build the model with `python export_onnx.py RealESRGAN_x4plus.pth realesrgan_x4plus.onnx` (needs `onnx`, no PyTorch).
- [realesrgan-ncnn-vulkan](https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan/releases) (BSD-3-Clause) with its `models/` folder, or [upscayl-bin](https://github.com/upscayl/upscayl-ncnn/releases) (AGPL-3.0, same command line on a newer ncnn) with the same models. Both ncnn builds fail `vkAllocateMemory` while loading the model on the Radeon 780M, so the Windows package defaults to the ONNX/DirectML path and keeps them only as `--upscaler esrgan`.

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
- `--preview-dir previews`: write `<name>_before.png` / `<name>_after.png` pairs and `compare_001.jpg`, `compare_002.jpg`, ... (40 textures per sheet, 1:1 crops, bicubic on the left, pack on the right)
- `--exclude-list keep.txt`: texture names that keep the original (one per line)
- `--safe-list safe.txt`: texture names or globs (one per line, `#` comments) upscaled with Lanczos and a light unsharp mask instead of the AI model, for lettering the model would warp. Built-in patterns (`SAFE_PATTERNS` in hdpack.py, from the review of the full retail set) always take this path: lettering, flags and emblems, water caustics, fine ground and snow noise, night light maps and a few textures the model fills with invented patterns. The report lists them under `safe_upscaled`.
- `--check <pack>`: check a built pack (repeat for each `_01`, `_02` part) without building. Lists tree textures (magenta trees), UI textures and GeneralsX content pack textures in it and exits 1 if there are any. Needs `--game-dir` only.
- `--upscaler lanczos`: plain resize, to check the pipeline without a GPU
- `--scale 2`: 2x instead of 4x
- `--esrgan-args "-g 0 -j 1:1:1"`: extra upscaler arguments (GPU id, thread counts)
- `--cache-dir <dir>`: where upscaled `.dds` files are kept (default `<out name>.cache` next to the output). A rerun only upscales textures that are not cached yet, so an interrupted full run resumes instead of starting over.
- `--max-size 1024`: cap the output size (default 2048) to keep the pack and video memory smaller
- GeneralsX content packs (`GeneralsX*.big`, e.g. `GeneralsXContent.big`) are never read, and their texture names are left out of the HD pack, so the pack's `.dds` copies (mod priority) cannot hide new or updated content art. The report lists them under `content_pack_textures_excluded`.
- `--review-dir <dir>`: check quality before shipping. Ranks the cached results by how much the model changed them compared with a plain Lanczos upscale (8 px blocks, 99th percentile), and writes `compare_NNN.jpg` (left: plain upscale with name and score, right: pack result) and `review.json` for the worst `--review-count` (default 200). No pack is written. Bad ones go into `--exclude-list`.
- `--terrain`: build a terrain pack instead (`--out "<game>\!HDTerrain.big"`): Art/Terrain/ tiles are upscaled to exactly 4x (2x when 4x would pass `--max-size`) and written as RLE TGA under their original names, which the HD terrain loader picks up. Only sheets that `Data/INI/Terrain.ini` uses as terrain textures are upscaled; tree textures (`TextureName` of W3DTreeDraw) stay retail, because the tree atlas reads them as 64 px cells and an upscaled sheet makes every tree render magenta. Use its own `--cache-dir` or the default next to the output.
- `--tile 64`: smaller Real-ESRGAN tiles if the GPU runs out of memory (default 128)

## Comparing upscalers on the safe textures (`--lab`)

Textures on the safe list (lettering, flags, water caustics, ground strips, noise and night maps) skip the AI model and get Lanczos. To try other upscalers on them without building a pack, put loose `.dds`/`.tga` copies in a folder and run:

```
hdpack.exe --lab <folder> --lab-out <sheets folder> --lab-model pbrify=<models>\pbrify-rplksrd-v3.onnx --lab-model dn50=<models>\general-dn50.onnx
```

Each row of `lab_001.jpg`, ... shows the source (4x nearest), Lanczos (the current safe path) and each `--lab-model` (default: the bundled x4plus). `lab.json` holds per method the drift (lower is closer to the source) and the sharpness (mean absolute Laplacian, higher is crisper). Models run with wrap-around context on tiling axes, like the pack.

Candidate models come from the `hdpack-lab-models` artifact of the same workflow, exported by `export_lab_models.py` (PyTorch and spandrel, weights pinned by SHA-256): Real-ESRGAN Compact `general-x4v3` and its half-denoised blend `general-dn50` (BSD-3-Clause), and the PBRify texture upscalers `pbrify-rplksrd-v3` and `pbrify-v4` (CC0-1.0).

- Tiling is detected per axis (`tile_axes`): the jump from the last column or row to the first is compared with the jumps inside. Tiling textures are resized and upscaled with wrap-around context, so they stay seamless.
- The pack uses the seamless Lanczos for safe textures that tile (colour and alpha). A blend of x4plus detail over Lanczos was tried and dropped: no visible gain, and faint ghosts of invented detail came through.
