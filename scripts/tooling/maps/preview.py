"""Map previews: the in-game 128x128 TGA and larger top-down and perspective pictures.

GeneralsX @feature Claude 16/10/2026 Draws from the generator's own terrain and objects, so a
layout can be reviewed without the game. Colours stand in for the retail terrain textures.
"""

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import mapgen

CLASS_COLOURS = {
    "GrassMediumType2": (92, 118, 60), "GrassMediumType11": (104, 124, 66), "GrassMediumType25": (84, 106, 56),
    "GrassMediumType31": (60, 86, 44), "DirtMediumType5": (128, 110, 80), "SandMediumType9": (150, 138, 104),
    "SandLargeType3": (176, 160, 120), "ConcreteMediumType1": (150, 150, 146), "AsphaltType1": (70, 70, 72),
    "CliffMediumType1": (112, 100, 86), "CliffLargeType1": (104, 94, 82), "RocksType2": (120, 116, 110),
}
WATER = np.array((52, 92, 120), dtype=np.float64)

# Object categories for the legend: (colour, half size in world units, label)
CATEGORIES = [
    ("bunker", (230, 230, 230), 26, "Неуничтожимые бункеры"),
    ("artillery", (200, 200, 255), 30, "Артиллерийские платформы"),
    ("dozer", (255, 150, 30), 32, "Бульдозеры других генералов"),
    ("gla", (220, 60, 50), 60, "Штаб и казарма GLA (захват)"),
    ("factory", (240, 120, 200), 55, "Заводы (захват)"),
    ("airfield", (80, 170, 255), 80, "Аэродромы (захват)"),
    ("super", (170, 90, 255), 65, "Супероружие (захват)"),
    ("power", (250, 230, 90), 34, "Электростанции (захват)"),
    ("supply", (255, 215, 0), 34, "Склады снабжения"),
    ("tech", (90, 230, 120), 30, "Нефть, госпиталь, ремонт"),
]


def category(template):
    if template == "CivilianBunker01":
        return "bunker"
    if template == "TechArtilleryPlatform":
        return "artillery"
    if "Dozer" in template:
        return "dozer"
    if "GLACommandCenter" in template or "GLABarracks" in template:
        return "gla"
    if "WarFactory" in template or "ArmsDealer" in template:
        return "factory"
    if "Airfield" in template:
        return "airfield"
    if "PowerPlant" in template:
        return "power"
    if any(k in template for k in ("ParticleCannon", "NuclearMissile", "ScudStorm")):
        return "super"
    if template == "SupplyDock":
        return "supply"
    if template.startswith("Tech"):
        return "tech"
    if template.startswith("Tree"):
        return "tree"
    if template.startswith("Rock"):
        return "rock"
    return None


def colour_map(t):
    """Per height sample RGB with hill shading and water, shape (height, width, 3)."""
    lut = np.array([CLASS_COLOURS[n] for n in t.classes], dtype=np.float64)
    rgb = lut[t.cls]
    z = t.h * mapgen.HEIGHT_SCALE
    gy, gx = np.gradient(z, mapgen.CELL)
    light = np.array([-0.6, 0.5, 0.62])
    light /= np.linalg.norm(light)
    n = np.stack([-gx, -gy, np.ones_like(z)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    shade = np.clip(n @ light, 0.0, 1.0) * 0.7 + 0.45
    rgb = rgb * shade[..., None]
    water_z = t.water_z
    depth = np.clip((water_z - z) / 10.0, 0.0, 1.0)[..., None]
    rgb = rgb * (1 - 0.85 * depth) + WATER * (0.85 * depth)
    return np.clip(rgb, 0, 255)


def _icons(objs):
    out = []
    for x, y, _, angle, flags, template, props in objs.items:
        cat = category(template)
        if cat:
            out.append((x, y, cat, template, props))
    return out


def top_view(t, objs, size=1200, legend=True, starts=True):
    rgb = colour_map(t)[::-1]  # north up
    img = Image.fromarray(rgb.astype(np.uint8)).resize((size, size), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    total = t.width * mapgen.CELL
    s = size / total
    b = t.border * mapgen.CELL

    def px(x, y):
        return (x + b) * s, size - (y + b) * s

    # Playable border.
    x0, y0 = px(0, 0)
    x1, y1 = px(total - 2 * b, total - 2 * b)
    d.rectangle([x0, y1, x1, y0], outline=(255, 255, 255, 120), width=2)
    # Roads and bridges.
    pending = None
    for x, y, _, _, flags, template, _ in objs.items:
        if flags & (0x2 | 0x10):
            pending = (x, y, flags)
        elif flags & (0x4 | 0x20) and pending:
            width = 10 if flags & 0x20 else 4
            colour = (200, 190, 170) if flags & 0x20 else (60, 60, 64)
            d.line([px(pending[0], pending[1]), px(x, y)], fill=colour, width=width)
            pending = None
    colours = {c[0]: (c[1], c[2]) for c in CATEGORIES}
    for x, y, cat, template, _ in _icons(objs):
        cx, cy = px(x, y)
        if cat == "tree":
            d.ellipse([cx - 2.5, cy - 2.5, cx + 2.5, cy + 2.5], fill=(34, 58, 30))
            continue
        if cat == "rock":
            d.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(130, 124, 116))
            continue
        colour, half = colours[cat]
        r = max(3.0, half * s)
        if cat in ("dozer", "artillery"):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colour, outline=(0, 0, 0), width=1)
        else:
            d.rectangle([cx - r, cy - r, cx + r, cy + r], fill=colour, outline=(0, 0, 0), width=1)
    if starts:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(size / 40))
        except OSError:
            font = ImageFont.load_default()
        for x, y, _, _, _, template, props in objs.items:
            name = props.get("waypointName", "")
            if template.startswith("*Waypoints") and name.startswith("Player_"):
                cx, cy = px(x, y)
                r = size / 50
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(20, 20, 20), outline=(255, 255, 255), width=3)
                label = name.split("_")[1]
                w = d.textlength(label, font=font)
                d.text((cx - w / 2, cy - r * 0.8), label, fill=(255, 255, 255), font=font)
    if legend:
        img = _with_legend(img)
    return img


def _with_legend(img):
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    rows = CATEGORIES
    pad, line = 16, 34
    out = Image.new("RGB", (img.width, img.height + pad * 2 + line * ((len(rows) + 1) // 2)), (24, 26, 28))
    out.paste(img, (0, 0))
    d = ImageDraw.Draw(out)
    for k, (_, colour, _, label) in enumerate(rows):
        col, row = k % 2, k // 2
        x = pad + col * img.width // 2
        y = img.height + pad + row * line
        d.rectangle([x, y + 4, x + 22, y + 26], fill=colour, outline=(0, 0, 0))
        d.text((x + 32, y + 2), label, fill=(230, 230, 230), font=font)
    return out


def tga(t, objs, path):
    """The 128x128 map preview the skirmish menu shows, 32-bit and bottom-up like WorldBuilder's."""
    img = top_view(t, objs, size=128, legend=False, starts=False).convert("RGBA")
    _write_tga(img, path)


def _write_tga(img, path):
    w, h = img.size
    header = bytes([0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, w & 255, w >> 8, h & 255, h >> 8, 32, 8])
    data = np.asarray(img)[::-1, :, [2, 1, 0, 3]].tobytes()  # bottom-up BGRA
    with open(path, "wb") as f:
        f.write(header + data)


def perspective(t, objs, yaw_deg, pitch_deg=38, size=(1600, 1000), target=None, distance=None, fov=50, step=2):
    """A painter's-algorithm render of the height field as quads, with objects as boxes."""
    rgb = colour_map(t)
    total = t.width * mapgen.CELL
    b = t.border * mapgen.CELL
    z = t.h * mapgen.HEIGHT_SCALE
    zw = np.maximum(z, t.water_z)
    wx, wy = t.wx, t.wy
    tx, ty = target or ((total - 2 * b) / 2, (total - 2 * b) / 2)
    dist = distance or total * 0.95
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    eye = np.array([tx - dist * math.cos(pitch) * math.cos(yaw), ty - dist * math.cos(pitch) * math.sin(yaw),
                    dist * math.sin(pitch)])
    fwd = np.array([tx, ty, 30.0]) - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    W, H = size
    f = (W / 2) / math.tan(math.radians(fov) / 2)

    def project(p):
        v = p - eye
        cz = v @ fwd
        return np.stack([W / 2 + f * (v @ right) / cz, H / 2 - f * (v @ up) / cz], axis=-1), cz

    polys = []
    js = np.arange(0, t.height - step, step)
    is_ = np.arange(0, t.width - step, step)
    J, I = np.meshgrid(js, is_, indexing="ij")
    corners = [(J, I), (J, I + step), (J + step, I + step), (J + step, I)]
    pts = np.stack([np.stack([wx[j, i], wy[j, i], zw[j, i]], axis=-1) for j, i in corners], axis=-2)
    scr, depth = project(pts.reshape(-1, 3))
    scr = scr.reshape(pts.shape[:-1] + (2,))
    depth = depth.reshape(pts.shape[:-1])
    col = rgb[J + step // 2, I + step // 2]
    fog = np.clip((depth.mean(axis=-1) - dist * 0.6) / (dist * 1.6), 0, 0.45)[..., None]
    col = col * (1 - fog) + np.array([170, 185, 200]) * fog
    for idx in np.ndindex(J.shape):
        if depth[idx].min() <= 1:
            continue
        polys.append((depth[idx].mean(), [tuple(p) for p in scr[idx]], tuple(int(c) for c in col[idx])))

    colours = {c[0]: (c[1], c[2]) for c in CATEGORIES}
    sun = np.array([-0.6, 0.5, 0.62])
    for x, y, cat, template, props in _icons(objs):
        i, j = int(x / mapgen.CELL) + t.border, int(y / mapgen.CELL) + t.border
        base = zw[j, i]
        if cat == "tree":
            p = np.array([[x, y, base + 34], [x - 9, y, base], [x + 9, y, base]])
            s, dz = project(p)
            if dz.min() > 1:
                polys.append((dz.mean() - 5, [tuple(q) for q in s], (40, 66, 34)))
            continue
        if cat == "rock":
            continue
        colour, half = colours[cat]
        height = {"bunker": 18, "artillery": 22, "dozer": 14, "airfield": 26, "super": 70}.get(cat, 40)
        hw = half * 0.8
        box = [(-hw, -hw), (hw, -hw), (hw, hw), (-hw, hw)]
        top = np.array([[x + a, y + c, base + height] for a, c in box])
        bot = np.array([[x + a, y + c, base] for a, c in box])
        faces = [(top, np.array([0, 0, 1.0]))]
        for k in range(4):
            n = k + 1 if k < 3 else 0
            quad = np.array([bot[k], bot[n], top[n], top[k]])
            normal = np.cross(bot[n] - bot[k], top[k] - bot[k])
            faces.append((quad, normal / np.linalg.norm(normal)))
        for quad, normal in faces:
            s, dz = project(quad)
            if dz.min() <= 1:
                continue
            if (quad.mean(axis=0) - eye) @ normal > 0:
                continue
            k = 0.55 + 0.45 * max(0.0, float(normal @ sun / np.linalg.norm(sun)))
            polys.append((dz.mean() - 8, [tuple(q) for q in s], tuple(int(c * k) for c in colour)))

    img = Image.new("RGB", size, (150, 170, 190))
    d = ImageDraw.Draw(img)
    for _, pts, colour in sorted(polys, key=lambda p: -p[0]):
        d.polygon(pts, fill=colour)
    return img
