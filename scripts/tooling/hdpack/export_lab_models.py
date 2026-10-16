#!/usr/bin/env python3
"""Export candidate 4x upscalers for the safe textures to ONNX, for `hdpack --lab`.

Runs in CI with PyTorch and spandrel (which knows the architectures); the weights
are pinned by SHA-256. Each model is checked against PyTorch on an odd-sized input
before it is kept, so a graph that only works at the export size is dropped.

- general-x4v3, general-dn50: Real-ESRGAN Compact (BSD-3-Clause); dn50 blends the
  plain and the denoise weights half and half, as Real-ESRGAN's --denoise_strength 0.5.
- pbrify-rplksrd-v3, pbrify-v4: Kim2091's PBRify texture upscalers (CC0-1.0), trained
  on PolyHaven, ambientCG and FreePBR material textures.
"""

# GeneralsX @feature sav-labs 16/10/2026 Candidate texture upscalers for the HD pack lab.

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

WEIGHTS = {
    "general-x4v3": ("https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth",
                     "8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292"),
    "general-wdn-x4v3": ("https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-wdn-x4v3.pth",
                         "1641f8c4464b9f097c9fdda5589273713f67cf59f3d909e0bd688f0cee269dca"),
    "pbrify-rplksrd-v3": ("https://github.com/Kim2091/Kim2091-Models/releases/download/4x-PBRify_RPLKSRd_V3/4x-PBRify_RPLKSRd_V3.pth",
                          "1325a08842ebfc18aea90e71594aa9b9e82b9c7e16321dccf5b757884a22daf1"),
    "pbrify-v4": ("https://github.com/Kim2091/Kim2091-Models/releases/download/4x-PBRify_UpscalerV4/4x-PBRify_UpscalerV4.pth",
                  "82db39e31e01da6816a9814c0553a8dcdb7bd2d655353e67075c9295068cb789"),
}
# name: [(weights, share)]
MODELS = {
    "general-x4v3": [("general-x4v3", 1.0)],
    "general-dn50": [("general-x4v3", 0.5), ("general-wdn-x4v3", 0.5)],
    "pbrify-rplksrd-v3": [("pbrify-rplksrd-v3", 1.0)],
    "pbrify-v4": [("pbrify-v4", 1.0)],
}


def fetch(name, cache):
    url, sha = WEIGHTS[name]
    path = cache / Path(url).name
    if not path.is_file():
        urllib.request.urlretrieve(url, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != sha:
        raise SystemExit(f"{name}: checksum mismatch {digest}")
    return path


def load(parts, cache):
    import torch
    from spandrel import ModelLoader
    first = ModelLoader().load_from_file(fetch(parts[0][0], cache))
    if len(parts) > 1:
        # Weight interpolation (DNI) between models of the same architecture.
        mixed = {}
        for name, share in parts:
            state = ModelLoader().load_from_file(fetch(name, cache)).model.state_dict()
            for k, v in state.items():
                mixed[k] = mixed.get(k, 0) + share * v.float()
        first.model.load_state_dict(mixed)
    assert first.scale == 4, f"expected a 4x model, got {first.scale}x"
    return first.model.eval().float(), torch


def export(name, parts, out, cache):
    model, torch = load(parts, cache)
    path = out / f"{name}.onnx"
    dummy = torch.rand(1, 3, 64, 64)
    torch.onnx.export(model, dummy, str(path), input_names=["input"], output_names=["output"], opset_version=17,
                      dynamic_axes={"input": {2: "height", 3: "width"}, "output": {2: "height4", 3: "width4"}})
    import numpy as np
    import onnxruntime as ort
    probe = torch.rand(1, 3, 52, 44)
    with torch.no_grad():
        want = model(probe).numpy()
    got = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"]).run(None, {"input": probe.numpy()})[0]
    err = float(np.abs(got - want).max())
    if got.shape != want.shape or err > 1e-3:
        path.unlink()
        raise RuntimeError(f"ONNX output differs from PyTorch (shape {got.shape}, max error {err:.4f})")
    print(f"wrote {path} ({path.stat().st_size / 2**20:.1f} MB, max error {err:.1e})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="Output folder for <name>.onnx")
    ap.add_argument("--cache", default="lab-weights", help="Folder for the downloaded weights")
    ap.add_argument("--only", action="append", help="Export only these models")
    args = ap.parse_args()
    out, cache = Path(args.out), Path(args.cache)
    out.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    failed = []
    for name, parts in MODELS.items():
        if args.only and name not in args.only:
            continue
        try:
            export(name, parts, out, cache)
        except Exception as e:  # one unsupported architecture must not drop the others
            print(f"{name}: {e}", file=sys.stderr)
            failed.append(name)
    if len(failed) == len(args.only or MODELS):
        sys.exit(1)


if __name__ == "__main__":
    main()
