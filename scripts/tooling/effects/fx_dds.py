"""Write RGBA images as DXT5 DDS files with a full mip chain.

GeneralsX @feature Claude 16/10/2026 The engine's texture loader picks up a .dds next to any .tga name
the INI asks for, so baked 2048 px flipbook atlases ship as DXT5 (1 byte per pixel) instead of 16 MB
TGAs. Pillow encodes each mip level; this module builds the one DDS header around them.
"""

import io
import struct

import numpy as np
from PIL import Image

DDSD_CAPS, DDSD_HEIGHT, DDSD_WIDTH, DDSD_PIXELFORMAT = 0x1, 0x2, 0x4, 0x1000
DDSD_MIPMAPCOUNT, DDSD_LINEARSIZE = 0x20000, 0x80000
DDPF_FOURCC = 0x4
DDSCAPS_COMPLEX, DDSCAPS_TEXTURE, DDSCAPS_MIPMAP = 0x8, 0x1000, 0x400000


def _dxt5_level(img):
    buf = io.BytesIO()
    img.save(buf, format="DDS", pixel_format="DXT5")
    data = buf.getvalue()
    assert data[:4] == b"DDS "
    return data[128:]


def mip_chain(rgba):
    """rgba: HxWx4 uint8. Halves with premultiplied box filtering so transparent texels don't bleed
    dark fringes into the smaller levels."""
    levels = [rgba]
    cur = rgba.astype(np.float32) / 255.0
    while min(cur.shape[:2]) > 4:
        a = cur[..., 3:]
        pm = np.concatenate([cur[..., :3] * a, a], -1)
        h, w = pm.shape[0] // 2, pm.shape[1] // 2
        pm = pm[:h * 2, :w * 2].reshape(h, 2, w, 2, 4).mean((1, 3))
        a = pm[..., 3:]
        rgb = np.where(a > 1e-4, pm[..., :3] / np.maximum(a, 1e-4), 0)
        cur = np.concatenate([rgb, a], -1)
        levels.append((np.clip(cur, 0, 1) * 255 + 0.5).astype(np.uint8))
    return levels


def write_dxt5(rgba, path):
    levels = mip_chain(rgba)
    h, w = rgba.shape[:2]
    blobs = [_dxt5_level(Image.fromarray(lv, "RGBA")) for lv in levels]
    header = struct.pack(
        "<4s7I44x", b"DDS ", 124,
        DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_MIPMAPCOUNT | DDSD_LINEARSIZE,
        h, w, len(blobs[0]), 0, len(blobs))
    pixel_format = struct.pack("<2I4s5I", 32, DDPF_FOURCC, b"DXT5", 0, 0, 0, 0, 0)
    caps = struct.pack("<5I", DDSCAPS_COMPLEX | DDSCAPS_TEXTURE | DDSCAPS_MIPMAP, 0, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(header + pixel_format + caps + b"".join(blobs))
    return path


if __name__ == "__main__":
    import sys
    # fx_dds.py <atlas.png> <out.dds>: convert a baked atlas for assets/effects.
    write_dxt5(np.asarray(Image.open(sys.argv[1]).convert("RGBA")), sys.argv[2])
    print("wrote " + sys.argv[2])
