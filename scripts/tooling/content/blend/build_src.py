"""Build detailed units from third-party source models (see import_src.py and sources.py).

GeneralsX @feature Claude 16/10/2026 Usage: build_src.py <source dir with <unit>.glb> <out dir>
[--only UNIT] [--size 2048] [--blend dir]. Writes <out>/w3d, <out>/tex (TGA plus PNG copies) and
<out>/cameos like build_hd.py, so build_content.py --hd packs both the same way.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import bpy  # noqa: E402
import import_src  # noqa: E402
import kit  # noqa: E402
import sources  # noqa: E402
import textures  # noqa: E402
import w3d  # noqa: E402
from PIL import Image  # noqa: E402


def level(px, target, reference=None):
    """Scale the baked atlas so the brighter paint (70th percentile of covered texels) sits at `target`
    (sRGB 0-1): sources differ a lot in how dark their textures are. The damaged atlas takes the intact
    one's scale, so burning still darkens it."""
    import numpy as np
    ref = px if reference is None else reference
    rgb = ref[..., :3]
    covered = rgb.max(axis=2) > 0.02
    lum = rgb[covered].mean(axis=1)
    gain = target / max(1e-3, float(np.percentile(lum, 70)))
    if reference is not None:
        gain = getattr(level, "gain", gain)
    level.gain = gain
    out = px.copy()
    out[..., :3] = np.clip(px[..., :3] * gain, 0, 1)
    return out


# W3D material per finish: same atlas, own specular, so paint, bare metal and rubber catch the sun
# differently.
FINISH_SPECULAR = {"body": ((46, 44, 40), 12.0), "metal": ((110, 108, 100), 28.0), "rubber": ((10, 10, 10), 3.0),
                   "canvas": ((14, 13, 12), 3.0), "glass": ((170, 170, 170), 40.0)}


def build(unit, spec, src, w3d_dir, tex_dir, size, blend_dir=None, cameo_dir=None, intact_only=False):
    reference = None
    for suffix, damaged in (("", False), ("_D", True))[:1 if intact_only else 2]:
        name = spec["model"] + suffix
        d = "d" if damaged else ""
        k, objs, px = import_src.build(src, spec, name, size, damaged)
        if spec.get("level"):
            px = level(px, spec["level"], reference)
        reference = reference if damaged else px
        body_tex = f"{spec['stem']}_body{d}.tga"
        img = Image.fromarray(kit.save_image(px, os.path.join(tex_dir, body_tex.replace(".tga", ".png"))))
        textures.save_tga(img, os.path.join(tex_dir, body_tex))
        materials = {kind: w3d.Material(f"GX{kind.capitalize()}", body_tex, specular=spec_, shininess=shine)
                     for kind, (spec_, shine) in FINISH_SPECULAR.items()}
        materials["shadow"] = materials["team"] = materials["body"]
        if any(kind == "tread" for _, _, kind in objs):
            tread_tex = f"{spec['stem']}_tread.tga"
            import build_hd
            timg = build_hd.track_texture()
            textures.save_tga(timg, os.path.join(tex_dir, tread_tex))
            timg.save(os.path.join(tex_dir, tread_tex.replace(".tga", ".png")))
            materials["tread"] = w3d.Material("GXTread", tread_tex, scroll_mapper=True)
        model = kit.to_w3d(k, objs, name, None, materials)
        with open(os.path.join(w3d_dir, name + ".w3d"), "wb") as f:
            f.write(model.pack())
        blend = os.path.join(blend_dir or tex_dir, name + ".blend")
        bpy.ops.wm.save_as_mainfile(filepath=blend)
        if not damaged and cameo_dir:
            # Command bar art, rendered in a separate Blender session from the saved file.
            import subprocess
            subprocess.run([sys.executable, os.path.join(HERE, "render_hd.py"), blend, tex_dir, cameo_dir, "--cameo",
                            "--stem", spec["stem"], "--samples", "32"], check=True, stdout=subprocess.DEVNULL)
        if not blend_dir:
            os.remove(blend)
        tris = sum(len(m.triangles) for _, m in model.meshes)
        print(f"{name}: {tris} triangles, {len(model.meshes)} meshes, {len(model.bones)} bones", flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("src")
    p.add_argument("out")
    p.add_argument("--only")
    p.add_argument("--size", type=int, default=2048)
    p.add_argument("--blend")
    p.add_argument("--no-cameos", action="store_true")
    p.add_argument("--intact-only", action="store_true", help="skip the damaged model (quick looks)")
    a = p.parse_args()
    w3d_dir, tex_dir, cameo_dir = (os.path.join(a.out, d) for d in ("w3d", "tex", "cameos"))
    for dd in (w3d_dir, tex_dir, cameo_dir, a.blend):
        if dd:
            os.makedirs(dd, exist_ok=True)
    for unit, spec in sources.UNITS.items():
        src = os.path.join(a.src, unit + ".glb")
        if (a.only and a.only != unit) or not os.path.exists(src):
            continue
        build(unit, spec, src, w3d_dir, tex_dir, a.size, a.blend, None if a.no_cameos else cameo_dir,
              a.intact_only)


if __name__ == "__main__":
    main()
