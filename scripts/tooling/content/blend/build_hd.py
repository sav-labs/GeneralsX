"""Build the detailed units with Blender (bpy) into W3D models and baked TGA textures.

GeneralsX @feature Claude 16/10/2026 Each unit is built twice, intact and damaged (_D), each with its
own baked body and team-colour atlases. Usage: build_hd.py <out dir> [--blend dir]
[--only NAME] [--size 1024]
"""

import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import bpy  # noqa: E402
import kit  # noqa: E402
import w3d  # noqa: E402
import textures  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402

TAN = [(176, 160, 118), (128, 116, 82), (92, 86, 64)]

# Unit name -> (builder module, texture stem, palette, pattern). The procedural Abrams gave way
# to one built from an openly licensed source model (build_src.py, sources.py); this keeps the procedural
# pipeline and the track texture both use.
UNITS = {}


def track_texture(seed=13, links=4, w=512, h=256):
    """Tread atlas with its relief painted in: a height map of rubber pads, steel shoes, end connectors with
    wedge bolts, link gaps and guide horns, lit from above-left and darkened in its creases. U holds `links`
    links (3 world units, the band's `links` scale); V follows blend.kit's track profile: 0.5-1 the ground
    side, 0.4-0.5 the edges, 0-0.4 the side the wheels run on."""
    rng = np.random.default_rng(seed)
    u = (np.arange(w)[None, :] + 0.5) / w
    v = 1.0 - (np.arange(h)[:, None] + 0.5) / h
    p = (u * links) % 1.0  # position within one link
    u = np.broadcast_to(u, (h, w))
    v = np.broadcast_to(v, (h, w))
    p = np.broadcast_to(p, (h, w))
    height = np.zeros((h, w))
    colour = np.zeros((h, w, 3))
    steel, rubber, bright = np.array([74, 72, 66.0]), np.array([36, 36, 35.0]), np.array([150, 146, 136.0])

    def box(a0, a1, b0, b1, a, b, r):
        """Rounded rectangle mask, soft over r."""
        da = np.minimum(a - a0, a1 - a) / r
        db = np.minimum(b - b0, b1 - b) / r
        return np.clip(np.minimum(da, db), 0, 1)

    outer = v >= 0.5
    wo = (v - 0.5) / 0.5
    gap = np.minimum(p, 1 - p) < 0.035
    pads = (box(0.17, 0.4, 0.08, 0.92, wo, p, 0.04) + box(0.6, 0.83, 0.08, 0.92, wo, p, 0.04)) * outer
    conn = ((wo < 0.16) | (wo > 0.84) | ((wo > 0.41) & (wo < 0.59))) & outer
    bolt = np.clip(1 - np.hypot((p - 0.5) / 0.09, ((wo % 0.5) - np.where(wo < 0.5, 0.08, 0.0)) / 0.06), 0, 1)
    bolt = bolt * conn * (np.abs(wo - 0.5) > 0.3)
    centre_bolt = np.clip(1 - np.hypot((p - 0.5) / 0.09, (wo - 0.5) / 0.05), 0, 1) * conn
    height[outer] = 0.3
    height += pads * 0.55 + conn * 0.6 + (bolt + centre_bolt) * 0.25
    colour[:] = steel
    m = pads > 0.3
    colour[m] = rubber
    inner = v < 0.4
    wi = v / 0.4
    track_path = ((np.abs(wi - 0.25) < 0.15) | (np.abs(wi - 0.75) < 0.15)) & inner
    horn = box(0.44, 0.56, 0.3, 0.7, wi, p, 0.05) * inner
    height[inner] = 0.3 + horn[inner] * 0.7
    colour[track_path] = bright
    side = (~outer) & (~inner)
    pin = np.clip(1 - np.hypot((p - 0.5) / 0.12, (v - 0.45) / 0.03), 0, 1) * side
    height[side] = 0.4 + pin[side] * 0.3
    height[gap] = 0.0
    colour[gap] = steel * 0.35
    # Relief lighting and creases.
    gy, gx = np.gradient(height * 6.0)
    nrm = np.dstack([-gx, gy, np.ones_like(height)])
    nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
    light = np.array([-0.45, 0.45, 0.77])
    shade = 0.55 + 0.6 * np.clip(nrm @ light, 0, 1)
    blur = np.array(Image.fromarray((height * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(4)), float) / 255
    crease = np.clip(1 - (blur - height) * 2.5, 0.45, 1)
    grain = textures.fbm(w, rng, octaves=5, base=16)[:h, :w]
    img = colour * shade[..., None] * crease[..., None] * (0.85 + 0.3 * grain[..., None])
    # Packed dirt in the low parts, polish on the high parts of the ground side.
    dust = np.clip((0.5 - height) * 1.4 + (textures.fbm(w, rng, base=6)[:h, :w] - 0.5), 0, 1)[..., None] * 0.7
    img = img * (1 - dust) + np.array([128, 110, 82]) * dust
    # Dry dust caked on the band's edges and end connectors: from above the track reads as a light-edged
    # band, not one dark mass with the wheels.
    edges = (side | (conn & ((wo < 0.16) | (wo > 0.84)))).astype(float)
    edges = (edges * (0.45 + 0.35 * textures.fbm(w, rng, base=24)[:h, :w]))[..., None]
    img = img * (1 - edges) + np.array([156, 138, 104]) * edges
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


def build_unit(name, module, stem, palette, pattern, w3d_dir, tex_dir, size, blend_dir=None, cameo_dir=None):
    out = {}
    for suffix, damaged in (("", False), ("_D", True)):
        k = kit.Kit(name + suffix)
        module.build(k, damaged=damaged)
        objs = kit.finalize(k, damaged=damaged)
        body = [o for key, o in objs.items() if key[2] == "body"]
        team = [o for key, o in objs.items() if key[2] == "team"]
        tread = [o for key, o in objs.items() if key[2] == "tread"]
        d = "d" if damaged else ""
        body_tex, team_tex, tread_tex = f"{stem}_body{d}.tga", f"{stem}_team{d}.tga", f"{stem}_tread.tga"
        kit.unwrap(body)
        _, px = kit.bake(body, palette, size, damaged, pattern, f"{stem}_body{d}", getattr(k, "burns", None))
        body_img = Image.fromarray(kit.save_image(px, os.path.join(tex_dir, body_tex.replace(".tga", ".png"))))
        textures.save_tga(body_img, os.path.join(tex_dir, body_tex))
        if team:
            kit.unwrap(team, margin=0.01)
            _, px = kit.bake(team, palette, size // 4, damaged, pattern, f"{stem}_team{d}", getattr(k, "burns", None))
            team_img = Image.fromarray(kit.save_image(px, os.path.join(tex_dir, team_tex.replace(".tga", ".png"))))
            textures.save_tga(team_img, os.path.join(tex_dir, team_tex))
        tread_img = track_texture()
        textures.save_tga(tread_img, os.path.join(tex_dir, tread_tex))
        tread_img.save(os.path.join(tex_dir, tread_tex.replace(".tga", ".png")))
        materials = {
            "body": w3d.Material("GXBody", body_tex, specular=(50, 50, 46), shininess=10.0),
            "team": w3d.Material("GXTeam", team_tex),
            "tread": w3d.Material("GXTread", tread_tex, scroll_mapper=True),
        }
        materials["shadow"] = materials["body"]
        model = kit.to_w3d(k, objs, name + suffix, None, materials)
        tris = sum(len(m.triangles) for _, m in model.meshes)
        with open(os.path.join(w3d_dir, name + suffix + ".w3d"), "wb") as f:
            f.write(model.pack())
        blend = os.path.join(blend_dir or tex_dir, name + suffix + ".blend")
        bpy.ops.wm.save_as_mainfile(filepath=blend)
        if not damaged and cameo_dir:
            # Command bar art, rendered in a separate Blender session from the saved file.
            import subprocess
            subprocess.run([sys.executable, os.path.join(HERE, "render_hd.py"), blend, tex_dir, cameo_dir, "--cameo",
                            "--stem", stem, "--samples", "32"], check=True, stdout=subprocess.DEVNULL)
        if not blend_dir:
            os.remove(blend)
        print(f"{name + suffix}: {tris} triangles, {len(model.meshes)} meshes, {len(model.bones)} bones", flush=True)
        out[name + suffix] = model
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", help="writes <out>/w3d, <out>/tex (TGA plus PNG copies) and <out>/cameos")
    p.add_argument("--blend")
    p.add_argument("--only")
    p.add_argument("--size", type=int, default=2048)
    a = p.parse_args()
    w3d_dir, tex_dir, cameo_dir = (os.path.join(a.out, d) for d in ("w3d", "tex", "cameos"))
    for d in (w3d_dir, tex_dir, cameo_dir):
        os.makedirs(d, exist_ok=True)
    if a.blend:
        os.makedirs(a.blend, exist_ok=True)
    for name, (module, stem, palette, pattern) in UNITS.items():
        if a.only and a.only != name:
            continue
        build_unit(name, module, stem, palette, pattern, w3d_dir, tex_dir, a.size, a.blend, cameo_dir)


if __name__ == "__main__":
    main()
