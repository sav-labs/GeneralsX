#!/usr/bin/env python3
"""Self-test for the GeneralsX content tools.

GeneralsX @feature Claude 15/10/2026 Builds the pack into a temporary folder and checks the W3D
chunk layout against the structure sizes in w3d_file.h, that every HLOD entry names a mesh in
the file, that every model and texture the INI refers to is in the pack, and that the .big
round-trips.
"""

import os
import re
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)

import w3d  # noqa: E402

STRUCT_SIZES = {
    w3d.MESH_HEADER3: 116,
    w3d.HIERARCHY_HEADER: 36,
    w3d.HLOD_HEADER: 40,
    w3d.HLOD_SUB_OBJECT_ARRAY_HEADER: 8,
    w3d.HLOD_SUB_OBJECT: 36,
    w3d.VERTEX_MATERIAL_INFO: 32,
    w3d.MATERIAL_INFO: 16,
}


def read_big(path):
    with open(path, "rb") as f:
        data = f.read()
    assert data[:4] == b"BIGF", "bad .big magic"
    assert struct.unpack_from("<I", data, 4)[0] == len(data), ".big size field mismatch"
    count, _ = struct.unpack_from(">II", data, 8)
    files, pos = {}, 16
    for _ in range(count):
        offset, size = struct.unpack_from(">II", data, pos)
        end = data.index(b"\0", pos + 8)
        name = data[pos + 8:end].decode("ascii")
        files[name.lower()] = data[offset:offset + size]
        pos = end + 1
    return files


def check_w3d(name, data):
    chunks = w3d.read_chunks(data)
    ids = [c[0] for c in chunks]
    assert ids[0] == w3d.HIERARCHY and w3d.HLOD in ids, f"{name}: unexpected top-level order {ids}"
    npivots = struct.unpack_from("<I", chunks[0][2][0][1], 20)[0]

    def walk(nodes):
        for cid, payload, children in nodes:
            if cid in STRUCT_SIZES:
                assert len(payload) == STRUCT_SIZES[cid], f"{name}: chunk 0x{cid:x} is {len(payload)} bytes"
            if children:
                walk(children)
    walk(chunks)

    container = name.upper()
    meshes = set()
    for cid, payload, children in chunks:
        if cid == w3d.MESH:
            header = next(p for c, p, _ in children if c == w3d.MESH_HEADER3)
            mesh = header[8:24].split(b"\0")[0].decode()
            owner = header[24:40].split(b"\0")[0].decode()
            assert owner == container, f"{name}: mesh {mesh} belongs to {owner}"
            ntris, nverts = struct.unpack_from("<II", header, 40)
            sizes = {c: len(p) for c, p, _ in children}
            assert sizes[w3d.VERTICES] == nverts * 12 and sizes[w3d.VERTEX_NORMALS] == nverts * 12
            assert sizes[w3d.TRIANGLES] == ntris * 32
            meshes.add(f"{owner}.{mesh}")
    for cid, payload, children in chunks:
        if cid == w3d.ANIMATION:
            header = children[0][1]
            assert len(header) == 44, f"{name}: animation header is {len(header)} bytes"
            assert header[4:20].split(b"\0")[0].decode() == container, f"{name}: animation name"
            frames = struct.unpack_from("<I", header, 36)[0]
            for ccid, chan, _ in children[1:]:
                first, last, veclen, _, pivot, _ = struct.unpack_from("<6H", chan)
                assert ccid == w3d.ANIMATION_CHANNEL and last < frames and pivot < npivots
                assert len(chan) == 12 + 4 * veclen * (last - first + 1), f"{name}: channel size"
    hlod = next(ch for c, _, ch in chunks if c == w3d.HLOD)
    lod = next(ch for c, _, ch in hlod if c == w3d.HLOD_LOD_ARRAY)
    for cid, payload, _ in lod:
        if cid == w3d.HLOD_SUB_OBJECT:
            sub = payload[4:].split(b"\0")[0].decode()
            assert sub in meshes, f"{name}: HLOD refers to missing mesh {sub}"


def main():
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([sys.executable, os.path.join(HERE, "build_content.py"), REPO, tmp], check=True)
        files = read_big(os.path.join(tmp, "GeneralsXContent.big"))

    models = [n for n in files if n.endswith(".w3d")]
    assert models, "no models in the pack"
    for path in models:
        check_w3d(path.rsplit("\\", 1)[-1][:-4], files[path])
        for tex in set(re.findall(rb"([a-z0-9_]+\.tga)\0", files[path])):
            assert f"art\\textures\\{tex.decode()}" in files, f"{path} uses missing texture {tex.decode()}"

    for path, data in files.items():
        if not path.endswith(".ini"):
            continue
        text = data.decode("ascii")
        # ArtRemap lines name a retail model (or animation) and the pack's replacement.
        for model in re.findall(r"^\s*Model\s*=\s*\S+\s+(\S+)", text, re.M):
            if model.upper() != "NONE":
                assert f"art\\w3d\\{model.lower()}.w3d" in files, f"{path}: model {model} is not in the pack"
        for anim in re.findall(r"^\s*Animation\s*=\s*\S+\s+(\S+)", text, re.M):
            if anim.upper() != "NONE":
                owner = anim.split(".")[0].lower()
                data = files.get(f"art\\w3d\\{owner}.w3d")
                assert data is not None, f"{path}: animation {anim} has no model {owner} in the pack"
                has_anim = any(cid == w3d.ANIMATION for cid, _, _ in w3d.read_chunks(data))
                assert anim.lower() == f"{owner}.{owner}" and has_anim, f"{path}: {owner}.w3d has no animation {anim}"
        for tex in re.findall(r"^\s*Texture\s*=\s*(\S+)", text, re.M):
            assert f"art\\textures\\{tex.lower()}" in files, f"{path}: texture {tex} is not in the pack"
    assert "data\\generalsx.str" in files
    print(f"content self-test passed: {len(files)} files, {len(models)} models")


if __name__ == "__main__":
    main()
