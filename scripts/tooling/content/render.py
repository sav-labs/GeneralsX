"""Small software renderer for previews and command-bar cameos of generated models.

GeneralsX @feature Claude 15/10/2026 Rasterizes a w3d.Model with its textures, vertex shading
and team colour, so cameos come from the same geometry the game draws and models can be
reviewed without the game.
"""

import math

import numpy as np
from PIL import Image


def _bone_world(model, index):
    return np.array(model.bone_world(index))


def render(model, textures, size=(512, 512), yaw=35.0, pitch=28.0, team=(40, 90, 230),
           background=(0, 0, 0, 0), margin=0.08, light=(-0.4, 0.5, 0.75), supersample=2, hide=()):
    """Orthographic three-quarter view. textures maps texture file name -> PIL image."""
    w, h = size[0] * supersample, size[1] * supersample
    yaw_r, pitch_r = math.radians(yaw), math.radians(pitch)
    # Camera looks at the model from the front-left, above.
    forward = np.array([-math.cos(pitch_r) * math.cos(yaw_r), -math.cos(pitch_r) * math.sin(yaw_r), -math.sin(pitch_r)])
    right = np.cross(forward, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    light_dir = np.array(light, float)
    light_dir /= np.linalg.norm(light_dir)

    tris = []
    for bone, mesh in model.meshes:
        if mesh.attributes & 0x1000 or mesh.material.shader.dest_blend != 0 or mesh.name in hide:
            continue  # hidden (muzzle flash) or blended (rotor blur): not part of a still picture
        offset = _bone_world(model, bone)
        pos = np.array(mesh.positions) + offset
        nrm = np.array(mesh.normals)
        uv = np.array(mesh.uvs)
        col = np.array(mesh.colors, float)[:, :3] / 255.0
        tex = np.asarray(textures[mesh.material.texture].convert("RGB"), float) / 255.0
        tint = np.array(team, float) / 255.0 if mesh.name.startswith("HOUSECOLOR") else np.ones(3)
        for a, b, c in mesh.triangles:
            tris.append((pos[[a, b, c]], nrm[[a, b, c]], uv[[a, b, c]], col[[a, b, c]], tex, tint))

    all_pos = np.concatenate([t[0] for t in tris])
    sx = all_pos @ right
    sy = all_pos @ up
    span = max(sx.max() - sx.min(), sy.max() - sy.min()) * (1 + 2 * margin)
    scale = min(w, h) / span
    cx, cy = (sx.max() + sx.min()) / 2, (sy.max() + sy.min()) / 2

    color = np.zeros((h, w, 3))
    alpha = np.zeros((h, w))
    depth = np.full((h, w), np.inf)

    for pos, nrm, uv, col, tex, tint in tris:
        px = (pos @ right - cx) * scale + w / 2
        py = h / 2 - (pos @ up - cy) * scale
        pz = pos @ forward
        area = (px[1] - px[0]) * (py[2] - py[0]) - (px[2] - px[0]) * (py[1] - py[0])
        if area >= 0:  # back-facing for counter-clockwise front faces (screen Y points down)
            continue
        x0, x1 = int(max(0, math.floor(px.min()))), int(min(w - 1, math.ceil(px.max())))
        y0, y1 = int(max(0, math.floor(py.min()))), int(min(h - 1, math.ceil(py.max())))
        if x0 > x1 or y0 > y1:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((px[1] - gx) * (py[2] - gy) - (px[2] - gx) * (py[1] - gy)) / area
        w1 = ((px[2] - gx) * (py[0] - gy) - (px[0] - gx) * (py[2] - gy)) / area
        w2 = 1 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        z = w0 * pz[0] + w1 * pz[1] + w2 * pz[2]
        sub = depth[y0:y1 + 1, x0:x1 + 1]
        mask = inside & (z < sub)
        if not mask.any():
            continue
        u = (w0 * uv[0, 0] + w1 * uv[1, 0] + w2 * uv[2, 0]) % 1.0
        v = (w0 * uv[0, 1] + w1 * uv[1, 1] + w2 * uv[2, 1]) % 1.0
        th, tw = tex.shape[:2]
        texel = tex[(v * th).astype(int).clip(0, th - 1), (u * tw).astype(int).clip(0, tw - 1)]
        shade = w0[..., None] * col[0] + w1[..., None] * col[1] + w2[..., None] * col[2]
        n = nrm[0]
        lambert = 0.45 + 0.75 * max(0.0, float(n @ light_dir))
        rgb = texel * shade * tint * lambert
        sub[mask] = z[mask]
        color[y0:y1 + 1, x0:x1 + 1][mask] = rgb[mask]
        alpha[y0:y1 + 1, x0:x1 + 1][mask] = 1.0

    img = Image.fromarray((np.clip(np.dstack([color, alpha]), 0, 1) * 255).astype(np.uint8), "RGBA")
    img = img.resize(size, Image.LANCZOS)
    if background[3]:
        bg = Image.new("RGBA", size, background)
        bg.alpha_composite(img)
        img = bg
    return img
