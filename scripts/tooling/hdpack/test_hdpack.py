#!/usr/bin/env python3
"""Pipeline check for hdpack.py on a synthetic archive (no retail files, no GPU)."""

# GeneralsX @feature sav-labs 14/10/2026 Self-test for the HD texture pack builder.

import io
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hdpack  # noqa: E402


def tga(size, rgba):
    buf = io.BytesIO()
    Image.new("RGBA", size, rgba).save(buf, "TGA")
    return buf.getvalue()


def check_dds(data, width, height):
    assert data[:4] == b"DDS "
    h, w = struct.unpack_from("<II", data, 12)
    mips = struct.unpack_from("<I", data, 28)[0]
    fourcc = data[84:88]
    assert (w, h) == (width, height), (w, h)
    block = 8 if fourcc == b"DXT1" else 16
    expected = sum(max(1, (w >> i) // 4) * max(1, (h >> i) // 4) * block for i in range(mips))
    assert len(data) == 128 + expected, (len(data), expected)
    return fourcc


def main():
    with tempfile.TemporaryDirectory() as tmp:
        game = Path(tmp, "game")
        game.mkdir()
        ini = b"MappedImage SCSmShellUserMB\n  Texture = SCShellUserInterface512_001.tga\nEnd\n"
        hdpack.write_big(game / "Textures.big", [
            ("Art\\Textures\\AVTank.tga", tga((128, 64), (90, 120, 60, 255))),
            ("Art\\Textures\\AVHouse.tga", tga((64, 64), (200, 200, 200, 128))),
            ("Art\\Textures\\SCShellUserInterface512_001.tga", tga((512, 512), (0, 0, 0, 255))),
            ("Art\\Textures\\tiny.tga", tga((16, 16), (0, 0, 0, 255))),
            ("Data\\INI\\MappedImages\\HandCreated\\HandCreatedMappedImages.ini", ini),
        ])
        out = Path(tmp, "!HDTextures.big")
        previews = Path(tmp, "previews")
        subprocess.run([sys.executable, str(HERE / "hdpack.py"), "--game-dir", str(game), "--out", str(out),
                        "--upscaler", "lanczos", "--preview-dir", str(previews)], check=True)

        entries = hdpack.read_big(out)
        assert sorted(entries) == ["art/textures/avhouse.dds", "art/textures/avtank.dds"], sorted(entries)
        assert check_dds(hdpack.read_entry(entries["art/textures/avtank.dds"]), 512, 256) == b"DXT1"
        assert check_dds(hdpack.read_entry(entries["art/textures/avhouse.dds"]), 256, 256) == b"DXT5"
        assert (previews / "compare.jpg").is_file()
    print("hdpack self-test passed")


if __name__ == "__main__":
    main()
