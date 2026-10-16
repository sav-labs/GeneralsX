"""Procedural particle textures for the GeneralsX effects pack (no third-party art).

GeneralsX @feature Claude 16/10/2026 Flipbook atlases (fireball, smoke, flame, dust) and single
sprites (flash, spark, shockwave ring, debris) generated from seeded 3D value noise, so every
pixel is ours and the build is reproducible. Flipbooks are square grids of square frames read
row by row from the top left, matching the FlipbookGrid particle field.
"""

import os

import numpy as np
from PIL import Image


class Noise3:
    """Smooth 3D value noise in [0, 1] on a periodic lattice."""

    def __init__(self, seed, cells=32):
        self.cells = cells
        self.grid = np.random.default_rng(seed).random((cells, cells, cells))

    def sample(self, x, y, z):
        c = self.cells
        xi, yi, zi = np.floor(x), np.floor(y), np.floor(z)
        fx, fy, fz = x - xi, y - yi, z - zi
        fx = fx * fx * (3 - 2 * fx)
        fy = fy * fy * (3 - 2 * fy)
        fz = fz * fz * (3 - 2 * fz)
        x0, y0, z0 = xi.astype(int) % c, yi.astype(int) % c, zi.astype(int) % c
        x1, y1, z1 = (x0 + 1) % c, (y0 + 1) % c, (z0 + 1) % c
        g = self.grid

        def lerp(a, b, t):
            return a + (b - a) * t

        return lerp(
            lerp(lerp(g[x0, y0, z0], g[x1, y0, z0], fx), lerp(g[x0, y1, z0], g[x1, y1, z0], fx), fy),
            lerp(lerp(g[x0, y0, z1], g[x1, y0, z1], fx), lerp(g[x0, y1, z1], g[x1, y1, z1], fx), fy),
            fz)

    def fbm(self, x, y, z, octaves=5, lacunarity=2.03, gain=0.5):
        total = np.zeros_like(x)
        amp, norm = 1.0, 0.0
        for o in range(octaves):
            total += amp * self.sample(x, y, z + o * 7.31)
            norm += amp
            amp *= gain
            x, y, z = x * lacunarity, y * lacunarity, z * lacunarity
        return total / norm


def _grid(size):
    v = (np.arange(size) + 0.5) / size * 2.0 - 1.0
    return np.meshgrid(v, v)  # u to the right, v downwards


def _smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _ramp(t, stops):
    """Piecewise linear colour ramp; stops are (position, (r, g, b)) in 0..1 colour."""
    t = np.clip(t, 0.0, 1.0)
    pos = np.array([s[0] for s in stops])
    out = np.zeros(t.shape + (3,))
    for ch in range(3):
        out[..., ch] = np.interp(t, pos, [s[1][ch] for s in stops])
    return out


def _atlas(frames, grid):
    size = frames[0].shape[0]
    atlas = np.zeros((size * grid, size * grid, 4))
    for i, f in enumerate(frames):
        r, c = divmod(i, grid)
        atlas[r * size:(r + 1) * size, c * size:(c + 1) * size] = f
    return atlas


def _loop_noise(noise, x, y, t, speed, octaves=5):
    """Noise that loops over t in [0, 1): cross-fade of two time offsets."""
    a = noise.fbm(x, y, np.full_like(x, t * speed), octaves)
    b = noise.fbm(x, y, np.full_like(x, (t - 1.0) * speed), octaves)
    return a * (1 - t) + b * t


class Billow:
    """Cauliflower cloud: a fixed layout of sub-puffs whose union forms a height field.

    Shading uses the height field normals, so each sub-puff reads as a lit round lump. The
    same layout is used for every frame of a flipbook, which keeps the animation coherent.
    """

    def __init__(self, seed, puffs=14, spread=0.32, size=(0.22, 0.42)):
        rng = np.random.default_rng(seed)
        self.noise = Noise3(seed + 1)
        ang = rng.uniform(0, 2 * np.pi, puffs)
        dist = np.abs(rng.normal(0, spread, puffs))
        self.cx = np.cos(ang) * dist
        self.cy = np.sin(ang) * dist * 0.9
        self.r = rng.uniform(size[0], size[1], puffs)
        # The biggest lumps sit in the middle.
        self.r *= 1.15 - 0.5 * np.clip(dist / (2 * spread), 0, 1)

    def field(self, u, v, grow, t, warp=0.12, zoom=0.72, bumps=0.10):
        n = self.noise
        u, v = u * zoom, v * zoom
        wu = u + (n.fbm(u * 2.0, v * 2.0, np.full_like(u, t * 1.7), 3) - 0.5) * warp
        wv = v + (n.fbm(u * 2.0 + 11.0, v * 2.0, np.full_like(u, t * 1.7), 3) - 0.5) * warp
        h = np.zeros_like(u)
        for cx, cy, r in zip(self.cx, self.cy, self.r):
            rr = r * grow
            d2 = (wu - cx * grow) ** 2 + (wv - cy * grow) ** 2
            h = np.maximum(h, np.sqrt(np.clip(rr * rr - d2, 0, None)))
        h /= self.r.max() * grow
        # Small lumps on the surface so the shading is not smooth plastic.
        bump = n.fbm(u * 7.0, v * 7.0, np.full_like(u, 2.0 + t * 1.3), 4)
        return np.clip(h + (bump - 0.5) * bumps * (h > 0), 0, None)

    def shade(self, h, light=(-0.5, -0.7, 0.5)):
        gy, gx = np.gradient(h * h.shape[0] * 0.5)
        nrm = np.stack([-gx, -gy, np.ones_like(h)], axis=-1)
        nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
        l = np.array(light) / np.linalg.norm(light)
        lam = np.clip((nrm * l).sum(-1), 0, 1)
        return lam, nrm[..., 2]


def fireball(size=256, grid=4, seed=101):
    """Billowing explosion: white-hot core that cools to orange, red and sooty smoke."""
    cloud = Billow(seed, puffs=16, spread=0.30)
    u, v = _grid(size)
    frames = []
    count = grid * grid
    for i in range(count):
        t = i / (count - 1)
        grow = 0.55 + 0.45 * (1 - (1 - t) ** 2.2)
        h = cloud.field(u, v, grow, t, warp=0.10 + 0.12 * t)
        detail = cloud.noise.fbm(u * 5.0, v * 5.0 - t * 1.5, np.full_like(u, 3.0 + t * 2.0), 5)
        erosion = 0.05 + 0.75 * t ** 1.6
        density = np.clip(h * 1.6 - erosion * (1.25 - detail) - (1 - detail) * 0.12, 0, 1)
        density = _smooth(0.0, 0.35, density)
        lam, facing = cloud.shade(h)
        # Heat: the dense middle stays hot longest; noise breaks it into glowing veins.
        heat = np.clip((h * 1.15 + (detail - 0.5) * 0.9) * (1.25 - 1.2 * t ** 0.75), 0, 1)
        fire = _ramp(heat, [(0.0, (0.16, 0.06, 0.03)), (0.22, (0.55, 0.12, 0.02)), (0.45, (0.98, 0.42, 0.07)),
                            (0.7, (1.0, 0.72, 0.28)), (1.0, (1.0, 0.96, 0.82))])
        soot = (0.06 + 0.30 * lam ** 1.2 + 0.05 * detail)[..., None] * np.array([1.0, 0.92, 0.84])
        hot = _smooth(0.10, 0.42, heat)[..., None]
        rgb = soot * (1 - hot) + fire * hot * (0.75 + 0.35 * lam)[..., None]
        alpha = np.clip(density * (1.25 - 0.3 * t), 0, 1)
        frames.append(np.dstack([np.clip(rgb, 0, 1), alpha]))
    return _atlas(frames, grid)


def smoke(size=256, grid=4, seed=202, tint=(0.56, 0.55, 0.53), lit=0.9):
    """Rolling smoke puff that expands and thins out over the flipbook; soft, see-through edges."""
    cloud = Billow(seed, puffs=12, spread=0.28, size=(0.24, 0.42))
    u, v = _grid(size)
    frames = []
    count = grid * grid
    for i in range(count):
        t = i / (count - 1)
        grow = 0.62 + 0.38 * t
        h = cloud.field(u, v, grow, t * 0.8, warp=0.20 + 0.12 * t, bumps=0.06)
        detail = cloud.noise.fbm(u * 3.5 + t * 0.5, v * 3.5 - t * 0.8, np.full_like(u, 5.0 + t * 1.2), 5)
        wisps = cloud.noise.fbm(u * 9.0, v * 9.0, np.full_like(u, 9.0 + t), 3)
        density = _smooth(0.0, 0.75, h) * (0.45 + 0.75 * detail) * (0.8 + 0.4 * wisps)
        density = np.clip(density - (0.15 + 0.4 * t) * (1 - detail), 0, 1)
        lam, facing = cloud.shade(cloud.field(u, v, grow, t * 0.8, warp=0.20 + 0.12 * t, bumps=0.03))
        light = 0.5 + lit * 0.6 * lam + 0.25 * (detail - 0.5)
        rgb = np.clip(light[..., None] * np.array(tint), 0, 1)
        alpha = np.clip(density * 1.3, 0, 1) * (1.0 - 0.5 * t)
        frames.append(np.dstack([rgb, alpha]))
    return _atlas(frames, grid)


def flame(size=256, grid=4, seed=303):
    """Looping fire for burning wrecks and buildings: upward-scrolling noise shaped into a
    flame body that is wide at the base (bottom of the frame) and breaks up into tongues."""
    noise = Noise3(seed)
    u, v = _grid(size)
    y = (1 - v) / 2  # 0 at the bottom, 1 at the top
    frames = []
    count = grid * grid
    for i in range(count):
        t = i / count
        n = _loop_noise(noise, u * 2.4, y * 3.0 - 0.0, t, 2.5, octaves=5)
        m = _loop_noise(noise, u * 5.0 + 17.0, y * 6.0, t, 5.0, octaves=3)
        width = 0.55 * (1 - 0.55 * y) + 0.05
        mask = np.exp(-(u / width) ** 2) * _smooth(0.0, 0.08, y)
        f = (n * 0.75 + m * 0.35) * mask * 2.1 - y * 1.05 - 0.25
        heat = np.clip(f, 0, 1)
        rgb = _ramp(heat, [(0.0, (0.25, 0.02, 0.0)), (0.25, (0.80, 0.18, 0.02)), (0.55, (1.0, 0.48, 0.07)),
                           (0.8, (1.0, 0.75, 0.30)), (1.0, (1.0, 0.92, 0.70))])
        alpha = _smooth(0.0, 0.35, heat)
        frames.append(np.dstack([rgb * alpha[..., None], alpha]))
    return _atlas(frames, grid)


def flash(size=256, seed=404, rays=9):
    """Additive muzzle and explosion flash: hot core, soft glow and a few uneven rays."""
    rng = np.random.default_rng(seed)
    u, v = _grid(size)
    r = np.sqrt(u * u + v * v)
    a = np.arctan2(v, u)
    ray = np.zeros_like(r)
    for _ in range(rays):
        ang = rng.uniform(-np.pi, np.pi)
        width = rng.uniform(0.05, 0.14)
        length = rng.uniform(0.55, 1.0)
        d = np.angle(np.exp(1j * (a - ang)))
        ray = np.maximum(ray, np.exp(-(d / width) ** 2) * np.clip(1 - r / length, 0, 1) ** 1.5)
    glow = np.exp(-(r / 0.28) ** 2) + 0.35 * np.exp(-(r / 0.6) ** 2)
    core = np.exp(-(r / 0.08) ** 2)
    i = np.clip(glow * 0.8 + ray * 0.7 + core, 0, None) * _smooth(1.0, 0.85, r)
    rgb = _ramp(np.clip(i, 0, 1), [(0.0, (0.0, 0.0, 0.0)), (0.3, (0.75, 0.30, 0.05)), (0.65, (1.0, 0.75, 0.35)),
                                   (1.0, (1.0, 1.0, 0.95))])
    return np.dstack([rgb, np.clip(i, 0, 1)])


def spark(size=64):
    """Small round additive glow for embers and sparks; white core, orange rim."""
    u, v = _grid(size)
    r = np.sqrt(u * u + v * v)
    i = np.exp(-(r / 0.22) ** 2) + 0.4 * np.exp(-(r / 0.5) ** 2)
    i *= _smooth(1.0, 0.8, r)
    rgb = _ramp(np.clip(i, 0, 1), [(0.0, (0.0, 0.0, 0.0)), (0.4, (1.0, 0.45, 0.08)), (1.0, (1.0, 0.95, 0.8))])
    return np.dstack([rgb, np.clip(i, 0, 1)])


def shockwave(size=512, seed=505):
    """Ground-aligned dust ring; alpha blended, brightest at the leading edge."""
    noise = Noise3(seed)
    u, v = _grid(size)
    r = np.sqrt(u * u + v * v)
    a = np.arctan2(v, u)
    n = noise.fbm(np.cos(a) * 3 + 5, np.sin(a) * 3 + 5, r * 6, 5)
    edge = 0.86 + (n - 0.5) * 0.12
    ring = _smooth(edge - 0.42, edge - 0.02, r) * _smooth(edge + 0.06, edge - 0.01, r)
    ring *= 0.6 + 0.8 * n
    rgb = np.broadcast_to(np.array([0.78, 0.70, 0.58]), r.shape + (3,)) * (0.7 + 0.5 * n)[..., None]
    return np.dstack([rgb, np.clip(ring, 0, 1)])


def debris(size=128, grid=2, seed=606):
    """Charred metal fragments, one per frame; drawn with a random frame per particle."""
    rng = np.random.default_rng(seed)
    noise = Noise3(seed)
    u, v = _grid(size)
    frames = []
    for i in range(grid * grid):
        k = rng.integers(5, 9)
        angles = np.sort(rng.uniform(0, 2 * np.pi, k))
        radii = rng.uniform(0.45, 0.9, k)
        a = np.arctan2(v, u) % (2 * np.pi)
        r = np.sqrt(u * u + v * v)
        edge = np.interp(a, np.concatenate([angles, angles[:1] + 2 * np.pi]),
                         np.concatenate([radii, radii[:1]]), period=2 * np.pi)
        mask = _smooth(edge, edge - 0.06, r)
        n = noise.fbm(u * 4 + i * 3.7, v * 4, np.full_like(u, i * 1.3), 4)
        glow = _smooth(0.62, 0.9, n) * _smooth(edge - 0.25, edge - 0.02, r)
        metal = (0.10 + 0.20 * n)[..., None] * np.array([1.0, 0.95, 0.9])
        rgb = metal + glow[..., None] * np.array([1.0, 0.42, 0.08])
        frames.append(np.dstack([rgb, mask]))
    return _atlas(frames, grid)


def dust(size=256, grid=4, seed=707):
    """Brown ground dust thrown up by the blast."""
    return smoke(size, grid, seed, tint=(0.58, 0.50, 0.38), lit=0.7)


def to_image(rgba):
    return Image.fromarray(np.clip(rgba * 255.0 + 0.5, 0, 255).astype(np.uint8), "RGBA")


# Flipbooks baked offline and kept as DXT5 DDS in assets/effects; the engine loads the .dds for the
# .tga name the INI uses. Volumes come from blender_flipbook.py (fx_fluid simulation rendered with
# Cycles), sparks and gun flashes from fx_bake2d.py.
BAKED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "assets", "effects")
BAKED = {
    # texture name: (blender_flipbook.py or fx_bake2d.py kind, flipbook grid)
    "gxfx_fireball.tga": ("explosion", 8),
    "gxfx_smoke.tga": ("smoke", 8),
    "gxfx_flame.tga": ("fire", 8),
    "gxfx_dust.tga": ("dust", 8),
    "gxfx_burst.tga": ("burst", 8),
    "gxfx_sparks.tga": ("sparks", 8),
    "gxfx_muzzle.tga": ("muzzle", 4),
}


def baked_path(name):
    return os.path.join(BAKED_DIR, os.path.splitext(name)[0] + ".dds")


TEXTURES = {
    # name: (builder or None when baked, flipbook grid or 1)
    **{name: (None, grid) for name, (_, grid) in BAKED.items()},
    "gxfx_debris.tga": (debris, 2),
    "gxfx_flash.tga": (flash, 1),
    "gxfx_spark.tga": (spark, 1),
    "gxfx_ring.tga": (shockwave, 1),
}


def build_all():
    """Returns {texture name: RGBA float array}."""
    return {name: builder() for name, (builder, _) in TEXTURES.items() if builder}
