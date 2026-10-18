"""Procedural textures for GeneralsX content (no third-party art).

GeneralsX @feature Claude 15/10/2026 Generates camouflage, metal, tread, team-colour and
muzzle-flash textures from seeded noise so the build is reproducible and every pixel is ours.
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def value_noise(size, cells, rng):
    """Tileable smooth noise in [0, 1]."""
    grid = rng.random((cells, cells))
    coords = np.arange(size) * cells / size
    i0 = np.floor(coords).astype(int)
    f = coords - i0
    f = f * f * (3 - 2 * f)
    i1 = (i0 + 1) % cells
    i0 %= cells
    a = grid[np.ix_(i0, i0)]
    b = grid[np.ix_(i0, i1)]
    c = grid[np.ix_(i1, i0)]
    d = grid[np.ix_(i1, i1)]
    fy = f[:, None]
    fx = f[None, :]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fbm(size, rng, octaves=5, base=4):
    total = np.zeros((size, size))
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        total += amp * value_noise(size, base * (2 ** o), rng)
        norm += amp
        amp *= 0.5
    return total / norm


def to_image(rgb):
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")


def camo_atlas(size, seed, palette):
    """Top 3/4: three-tone camouflage with panel lines and wear. Bottom 1/4: dark running gear."""
    rng = np.random.default_rng(seed)
    camo_h = size * 3 // 4
    n1 = fbm(size, rng, base=3)
    n2 = fbm(size, rng, base=3)
    detail = fbm(size, rng, octaves=6, base=16)
    base = np.array(palette[0], float)
    tone2 = np.array(palette[1], float)
    tone3 = np.array(palette[2], float)
    rgb = np.broadcast_to(base, (size, size, 3)).copy()
    rgb[n1 > 0.56] = tone2
    rgb[(n2 > 0.60) & (n1 <= 0.56)] = tone3
    # Paint grain, dust and worn edges.
    rgb *= (0.86 + 0.28 * detail)[..., None]
    dust = np.clip((fbm(size, rng, base=6) - 0.55) * 2.5, 0, 1)[..., None]
    rgb = rgb * (1 - 0.35 * dust) + np.array([170, 150, 115]) * 0.35 * dust

    img = to_image(rgb)
    draw = ImageDraw.Draw(img)
    # Armour panel seams and bolts, on a grid so they tile.
    step = size // 8
    for k in range(0, size, step):
        draw.line([(k, 0), (k, camo_h)], fill=(40, 40, 32), width=2)
        draw.line([(0, k), (size, k)], fill=(40, 40, 32), width=2)
        for j in range(step // 2, size, step):
            draw.ellipse([k + 6, j - 2, k + 10, j + 2], fill=(55, 55, 45))
    # Running gear strip: dark steel and rubber.
    gear = fbm(size, rng, octaves=4, base=8)[: size - camo_h]
    strip = np.stack([45 + 25 * gear, 45 + 25 * gear, 42 + 22 * gear], -1)
    arr = np.array(img)
    arr[camo_h:] = np.clip(strip, 0, 255).astype(np.uint8)
    arr[:camo_h] = np.array(Image.fromarray(arr[:camo_h]).filter(ImageFilter.SMOOTH))
    return Image.fromarray(arr, "RGB")


def infantry_atlas(size, seed, palette, gear, skin=(196, 150, 118), dark=(46, 46, 44)):
    """Soldier atlas. V from the bottom: 0-0.125 dark (boots, gloves, weapons), 0.125-0.25 skin,
    0.25-0.5 gear (vests, pouches, helmets) with webbing rows, 0.5-1 the uniform's camouflage in
    small blotches."""
    rng = np.random.default_rng(seed)
    n1 = fbm(size, rng, base=10)
    n2 = fbm(size, rng, base=10)
    grain = fbm(size, rng, octaves=6, base=32)
    rgb = np.broadcast_to(np.array(palette[0], float), (size, size, 3)).copy()
    rgb[n1 > 0.55] = palette[1]
    rgb[(n2 > 0.6) & (n1 <= 0.55)] = palette[2]
    rgb *= (0.88 + 0.24 * grain)[..., None]
    h = size // 8
    rgb[size - 2 * h:size - h] = np.array(skin, float) * (0.94 + 0.12 * grain[size - 2 * h:size - h])[..., None]
    rgb[size - h:] = np.array(dark, float) * (0.85 + 0.3 * grain[size - h:])[..., None]
    gear_rows = slice(size // 2, size - 2 * h)
    g = np.array(gear, float) * (0.86 + 0.24 * grain[gear_rows])[..., None]
    stripes = (np.arange(g.shape[0]) // max(1, size // 64)) % 2 == 0
    g[stripes] *= 0.9
    rgb[gear_rows] = g
    return to_image(rgb)


def tread(width, height, links, seed):
    """Track links along U so W3DTankDraw can scroll them."""
    rng = np.random.default_rng(seed)
    noise = fbm(max(width, height), rng, octaves=4, base=8)[:height, :width]
    rgb = np.stack([38 + 30 * noise, 37 + 28 * noise, 35 + 25 * noise], -1)
    img = to_image(rgb)
    draw = ImageDraw.Draw(img)
    pitch = width / links
    for i in range(links):
        x = int(i * pitch)
        draw.rectangle([x, 0, x + int(pitch * 0.18), height], fill=(18, 18, 18))
        draw.rectangle([x + int(pitch * 0.35), height // 3, x + int(pitch * 0.7), 2 * height // 3], fill=(95, 92, 85))
        draw.line([(x + int(pitch * 0.5), 0), (x + int(pitch * 0.5), height)], fill=(70, 68, 62), width=1)
    return img


def team_panel(size, seed):
    """Near-white panel the engine tints with the player's colour."""
    rng = np.random.default_rng(seed)
    noise = fbm(size, rng, octaves=4, base=8)
    v = 205 + 50 * noise
    img = to_image(np.stack([v, v, v], -1))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, size - 1, size - 1], outline=(90, 90, 90), width=3)
    return img


def flash(size):
    """Radial muzzle flash for an additive mesh."""
    y, x = np.mgrid[0:size, 0:size]
    c = (size - 1) / 2
    r = np.sqrt((x - c) ** 2 + (y - c) ** 2) / c
    angle = np.arctan2(y - c, x - c)
    rays = 0.6 + 0.4 * np.abs(np.cos(angle * 4))
    k = np.clip(1 - r / rays, 0, 1) ** 1.6
    rgb = np.stack([255 * k, 210 * k ** 1.3, 120 * k ** 2.2], -1)
    return to_image(rgb)


def save_tga(img, path, alpha=None):
    if alpha is not None:
        img = img.convert("RGB")
        img.putalpha(alpha)
    img.save(path, format="TGA", compression=None)


def burnt(img, seed):
    """Scorched variant for the REALLYDAMAGED state."""
    rng = np.random.default_rng(seed)
    size = img.size[0]
    soot = np.clip((fbm(size, rng, base=4) - 0.35) * 1.8, 0, 1)[: img.size[1], : img.size[0]]
    rgb = np.asarray(img.convert("RGB"), float)
    dark = rgb * 0.35 + np.array([20, 18, 16])
    out = rgb * (1 - soot[..., None]) + dark * soot[..., None]
    return to_image(out * 0.8)


def cameo_frame(render_img, size):
    """Command-bar style backdrop: dark blue-grey gradient with the vehicle on top."""
    w, h = size
    y = np.linspace(0, 1, h)[:, None]
    top = np.array([62, 78, 96])
    bottom = np.array([18, 22, 30])
    bg = top * (1 - y[..., None]) + bottom * y[..., None]
    bg = np.broadcast_to(bg, (h, w, 3))
    base = to_image(bg).convert("RGBA")
    base.alpha_composite(render_img)
    return base.convert("RGB")


def glass(size, seed):
    """Tinted canopy glass with a soft reflection band."""
    rng = np.random.default_rng(seed)
    y = np.linspace(0, 1, size)[:, None] * np.ones((1, size))
    band = np.exp(-((y - 0.3) ** 2) / 0.01)
    noise = fbm(size, rng, octaves=3, base=4)
    rgb = np.stack([30 + 60 * band + 10 * noise, 42 + 70 * band + 10 * noise, 52 + 80 * band + 12 * noise], -1)
    return to_image(rgb)


def rotor_disc(size):
    """Blurred rotor: faint ring, transparent centre gaps. Returns (rgb, alpha)."""
    y, x = np.mgrid[0:size, 0:size]
    c = (size - 1) / 2
    r = np.sqrt((x - c) ** 2 + (y - c) ** 2) / c
    a = np.where(r <= 1.0, 0.22 + 0.10 * np.cos(r * 18) ** 2, 0.0) * np.clip((r - 0.08) / 0.1, 0, 1)
    a *= np.clip((1.0 - r) / 0.04, 0, 1)
    rgb = np.full((size, size, 3), 40.0)
    return to_image(rgb), Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "L")


def building_atlas(size, seed, wall=(168, 164, 150), roof=(78, 80, 78), metal=(70, 74, 72)):
    """Atlas for structures. V from the bottom: 0-0.25 dark metal (doors, machinery, pipes),
    0.25-0.5 roof membrane with vents, 0.5-1.0 precast wall panels with seams, window bands and stains."""
    rng = np.random.default_rng(seed)
    q = size // 4
    detail = fbm(size, rng, octaves=6, base=16)
    stain = np.clip((fbm(size, rng, base=6) - 0.5) * 2.2, 0, 1)
    rgb = np.zeros((size, size, 3))

    # Walls (image rows 0 .. 2q): concrete panels, rain streaks below seams.
    w = rgb[: 2 * q]
    w[:] = np.array(wall, float)
    w *= (0.88 + 0.22 * detail[: 2 * q])[..., None]
    streak = np.clip(fbm(size, rng, octaves=3, base=24)[: 2 * q] * np.linspace(0.2, 1.0, 2 * q)[:, None] - 0.45, 0, 1)
    w *= (1 - 0.35 * streak)[..., None]
    # Roof (rows 2q .. 3q): dark membrane, a little grain.
    r = rgb[2 * q: 3 * q]
    r[:] = np.array(roof, float)
    r *= (0.85 + 0.3 * detail[2 * q: 3 * q])[..., None]
    # Metal (rows 3q .. 4q): ribbed cladding.
    m = rgb[3 * q:]
    m[:] = np.array(metal, float)
    ribs = 0.85 + 0.15 * np.cos(np.arange(size) / size * 2 * np.pi * 32)
    m *= (ribs[None, :] * (0.9 + 0.2 * detail[3 * q:]))[..., None]
    rgb = rgb * (1 - 0.25 * stain[..., None]) + np.array([60, 58, 50]) * 0.25 * stain[..., None]

    img = to_image(rgb)
    draw = ImageDraw.Draw(img)
    step = size // 8
    for k in range(0, size, step):
        draw.line([(k, 0), (k, 2 * q)], fill=(110, 108, 100), width=2)
    for k in range(0, 2 * q, q):
        draw.line([(0, k), (size, k)], fill=(112, 110, 102), width=3)
    # One band of dark window slots per storey-high wall course.
    for row in range(0, 2 * q, q):
        y0 = row + q * 3 // 10
        for k in range(0, size, step // 2):
            draw.rectangle([k + 8, y0, k + step // 2 - 8, y0 + q // 6], fill=(34, 42, 48))
            draw.line([(k + 8, y0), (k + step // 2 - 8, y0)], fill=(90, 104, 112), width=2)
    # Roof vents and hatches.
    for k in range(step // 2, size, step):
        draw.rectangle([k - 10, 2 * q + q // 3, k + 10, 2 * q + q // 3 + 18], fill=(52, 54, 52), outline=(100, 100, 96))
    draw.line([(0, 2 * q), (size, 2 * q)], fill=(60, 60, 58), width=3)
    return img
