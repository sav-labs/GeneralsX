#!/usr/bin/env python3
"""Pipeline check for hdpack.py on a synthetic archive (no retail files, no GPU)."""

# GeneralsX @feature sav-labs 14/10/2026 Self-test for the HD texture pack builder.

import io
import json
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


def check_onnx_tiling(tmp):
    """Tiled ONNX upscale must match a single full-image pass (nearest 4x stand-in model)."""
    import numpy as np
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    scales = numpy_helper.from_array(np.array([1, 1, 4, 4], dtype=np.float32), "scales")
    graph = helper.make_graph(
        [helper.make_node("Resize", ["input", "", "scales"], ["output"], mode="nearest")], "x4",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, "h", "w"])],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 3, "h4", "w4"])], [scales])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    path = Path(tmp, "x4.onnx")
    onnx.save(model, path)

    rng = np.random.default_rng(1)
    img = Image.fromarray(rng.integers(0, 256, (70, 100, 3), dtype=np.uint8), "RGB")
    session = hdpack.onnx_session(path)
    tiled = hdpack.upscale_rgb_onnx({"t": img}, session, 32)["t"]
    full = img.resize((400, 280), Image.Resampling.NEAREST)
    assert tiled.size == (400, 280), tiled.size
    assert np.array_equal(np.asarray(tiled), np.asarray(full))
    return path


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
            ("Art\\Terrain\\TSGrass01.tga", tga((64, 128), (60, 140, 40, 255))),
            # Tree sheets sit in Art/Terrain/ too but feed the tree atlas, which needs retail size.
            ("Art\\Terrain\\PTSnowPine01.tga", tga((64, 64), (20, 60, 20, 255))),
            ("Art\\Terrain\\TSUnused01.tga", tga((64, 64), (90, 90, 90, 255))),
            ("Data\\INI\\Terrain.ini", b"Terrain GrassType1\n  Texture = TSGrass01.tga\nEnd\n"),
            ("Data\\INI\\Object\\CivilianProp.ini",
             b"Object SnowPine\n  Draw = W3DTreeDraw ModuleTag_01\n    TextureName = PTSnowPine01.tga\n  End\nEnd\n"),
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
        assert (previews / "compare_001.jpg").is_file()

        # A rerun reuses the cache; a small part size splits the pack and removes the single file.
        rerun = subprocess.run([sys.executable, str(HERE / "hdpack.py"), "--game-dir", str(game), "--out", str(out),
                                "--upscaler", "lanczos", "--part-size", "100000"],
                               check=True, capture_output=True, text=True).stdout
        assert "2 textures reused" in rerun, rerun
        report = json.loads(Path(tmp, "!HDTextures.report.json").read_text())
        assert report["textures_written"] == 2 and report["reused_from_cache"] == 2, report
        parts = sorted(p.name for p in Path(tmp).glob("!HDTextures*.big"))
        assert parts == ["!HDTextures_01.big", "!HDTextures_02.big"], parts
        merged = {**hdpack.read_big(Path(tmp, parts[0])), **hdpack.read_big(Path(tmp, parts[1]))}
        assert sorted(merged) == ["art/textures/avhouse.dds", "art/textures/avtank.dds"], sorted(merged)

        # Textures already at --max-size are left to the retail archive.
        capped = Path(tmp, "!HDCapped.big")
        subprocess.run([sys.executable, str(HERE / "hdpack.py"), "--game-dir", str(game), "--out", str(capped),
                        "--upscaler", "lanczos", "--max-size", "128"], check=True, capture_output=True)
        report = json.loads(Path(tmp, "!HDCapped.report.json").read_text())
        assert report["skipped_already_max_size"] == 1 and report["textures_written"] == 1, report
        assert len(report["skipped_files"]["already_max_size"]) == 1, report

        # Terrain mode: same names as RLE TGA at exactly 4x, nothing from Art/Textures/.
        terrain = Path(tmp, "!HDTerrain.big")
        subprocess.run([sys.executable, str(HERE / "hdpack.py"), "--game-dir", str(game), "--out", str(terrain),
                        "--upscaler", "lanczos", "--terrain"], check=True, capture_output=True)
        entries = hdpack.read_big(terrain)
        assert list(entries) == ["art/terrain/tsgrass01.tga"], list(entries)
        report = json.loads(Path(tmp, "!HDTerrain.report.json").read_text())
        assert report["tree_textures_excluded"] == 1, report
        data = hdpack.read_entry(entries["art/terrain/tsgrass01.tga"])
        assert data[2] == 10, data[2]  # RLE true-colour
        tile = Image.open(io.BytesIO(data))
        assert tile.size == (256, 512) and tile.mode == "RGB", (tile.size, tile.mode)

        # Textures in GeneralsX content packs stay with the content pack, never in the HD pack.
        game2 = Path(tmp, "game2")
        game2.mkdir()
        hdpack.write_big(game2 / "Textures.big", [
            ("Art\\Textures\\AVTank.tga", tga((64, 64), (90, 120, 60, 255))),
            ("Art\\Textures\\AVJeep.tga", tga((64, 64), (60, 60, 60, 255))),
        ])
        hdpack.write_big(game2 / "GeneralsXContent.big", [
            ("Art\\Textures\\AVJeep.tga", tga((64, 64), (200, 0, 0, 255))),
            ("Art\\Textures\\GXTank.tga", tga((64, 64), (0, 200, 0, 255))),
        ])
        content_out = Path(tmp, "!HDContent.big")
        subprocess.run([sys.executable, str(HERE / "hdpack.py"), "--game-dir", str(game2), "--out", str(content_out),
                        "--upscaler", "lanczos"], check=True, capture_output=True)
        assert list(hdpack.read_big(content_out)) == ["art/textures/avtank.dds"], list(hdpack.read_big(content_out))
        report = json.loads(Path(tmp, "!HDContent.report.json").read_text())
        assert report["content_pack_textures_excluded"] == ["avjeep", "gxtank"], report

        model = check_onnx_tiling(tmp)
        onnx_out = Path(tmp, "!HDTexturesOnnx.big")
        subprocess.run([sys.executable, str(HERE / "hdpack.py"), "--game-dir", str(game), "--out", str(onnx_out),
                        "--upscaler", "onnx", "--onnx", str(model), "--tile", "32"], check=True)
        entries = hdpack.read_big(onnx_out)
        assert check_dds(hdpack.read_entry(entries["art/textures/avtank.dds"]), 512, 256) == b"DXT1"
    print("hdpack self-test passed")


if __name__ == "__main__":
    main()
