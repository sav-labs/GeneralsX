"""Bake the spark shower and gun flash flipbooks.

GeneralsX @feature Claude 16/10/2026 Sparks and muzzle flashes are emissive and thin, so they need no
volume render: this script traces ballistic sparks with motion blur and draws noisy flame petals in
numpy, then writes DXT5 atlases for assets/effects next to the Cycles bakes.

Usage: fx_bake2d.py <sparks|muzzle> <out.dds> [--png preview.png]
"""

import argparse

import numpy as np

import fx_dds


def _ramp(t, stops):
    t = np.clip(t, 0.0, 1.0)
    out = np.zeros(t.shape + (3,), np.float32)
    for (t0, c0), (t1, c1) in zip(stops[:-1], stops[1:]):
        m = (t >= t0) & (t <= t1)
        k = ((t - t0) / max(t1 - t0, 1e-6))[m][:, None]
        out[m] = np.array(c0, np.float32) * (1 - k) + np.array(c1, np.float32) * k
    return out


# Blackbody-ish cooling: white hot -> yellow -> orange -> dull red.
HEAT = [(0.0, (0.35, 0.03, 0.0)), (0.3, (1.0, 0.28, 0.03)), (0.6, (1.0, 0.62, 0.18)),
        (0.85, (1.0, 0.88, 0.55)), (1.0, (1.0, 0.98, 0.9))]


def _segments(img, a, b, width, colour, intensity):
    """Add motion-blurred glowing segments a->b (N x 2, pixels) into img (H x W x 3)."""
    h, w = img.shape[:2]
    for p0, p1, wd, c, i in zip(a, b, width, colour, intensity):
        if i <= 1e-3:
            continue
        r = wd * 4 + 2
        x0 = int(max(min(p0[0], p1[0]) - r, 0))
        x1 = int(min(max(p0[0], p1[0]) + r + 1, w))
        y0 = int(max(min(p0[1], p1[1]) - r, 0))
        y1 = int(min(max(p0[1], p1[1]) + r + 1, h))
        if x0 >= x1 or y0 >= y1:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        d = p1 - p0
        ll = float(d @ d)
        t = np.clip(((xx - p0[0]) * d[0] + (yy - p0[1]) * d[1]) / ll, 0, 1) if ll > 1e-6 else 0.0
        dist2 = (xx - p0[0] - t * d[0]) ** 2 + (yy - p0[1] - t * d[1]) ** 2
        # Energy spreads along the streak, so a fast spark is dimmer per pixel than a slow one.
        spread = np.sqrt(wd / max(wd, np.sqrt(ll)))
        core = np.exp(-dist2 / (2 * wd * wd))
        halo = 0.18 * np.exp(-dist2 / (2 * (wd * 3.5) ** 2))
        img[y0:y1, x0:x1] += (core + halo)[..., None] * (c * i * spread)


def sparks(tile=256, grid=8, seed=11, count=46):
    """Shower of sparks thrown off an armour hit: hot flash, then sparks arcing out and falling."""
    rng = np.random.default_rng(seed)
    frames = grid * grid
    # Directions: mostly outward and upward from the hit, a few skipping sideways.
    ang = rng.uniform(-np.pi, np.pi, count) * 0.85 + np.pi / 2
    speed = rng.uniform(1.4, 4.5, count) ** 1.1
    vel = np.stack([np.cos(ang), np.sin(ang)], 1) * speed[:, None]
    life = rng.uniform(0.25, 1.0, count)
    width = rng.uniform(0.9, 1.6, count)
    bright = rng.uniform(0.7, 1.6, count)
    gravity, drag, shutter = 3.2, 1.3, 0.05
    centre = np.array([0.0, -0.25])

    def pos(t):
        # Ballistic with linear drag; y up, units of the tile half width.
        e = (1 - np.exp(-drag * t)) / drag
        p = vel * e[:, None] if np.ndim(t) else vel * e
        g = gravity / drag * (t - e)
        p = p.copy()
        p[:, 1] -= g
        return p + centre

    atlas = np.zeros((tile * grid, tile * grid, 4), np.float32)
    yy, xx = np.mgrid[0:tile, 0:tile].astype(np.float32)
    u = (xx + 0.5) / tile * 2 - 1
    v = 1 - (yy + 0.5) / tile * 2
    for f in range(frames):
        t = (f + 0.5) / frames
        img = np.zeros((tile, tile, 3), np.float32)
        age = np.full(count, t)
        heat = np.clip(1 - age / life, 0, 1)
        alive = heat > 0
        tt = np.full(count, t)
        p1 = pos(tt)
        p0 = pos(np.maximum(tt - shutter, 0))
        to_px = lambda p: np.stack([(p[:, 0] + 1) * 0.5 * tile, (1 - p[:, 1]) * 0.5 * tile], 1)
        col = _ramp(heat ** 0.7, HEAT)
        inten = np.where(alive, bright * (0.35 + 0.65 * heat) * (heat > 0.02), 0) * 2.2
        _segments(img, to_px(p0), to_px(p1), width * tile / 256, col, inten)
        # Flash at the hit point for the first few frames.
        r = np.sqrt((u - centre[0]) ** 2 + (v - centre[1]) ** 2)
        k = np.exp(-t / 0.05)
        flash = k * (np.exp(-(r / 0.07) ** 2) * 2.5 + np.exp(-(r / 0.25) ** 2) * 0.5)
        img += flash[..., None] * np.array([1.0, 0.85, 0.6], np.float32)
        img = 1 - np.exp(-img)  # soft clip keeps cores white instead of flat
        a = np.clip(img.max(-1) * 1.1, 0, 1)
        gy, gx = divmod(f, grid)
        atlas[gy * tile:(gy + 1) * tile, gx * tile:(gx + 1) * tile] = np.dstack([img, a])
    return atlas


def _value_noise(rng, res, size):
    c = rng.random((res + 1, res + 1)).astype(np.float32)
    x = np.linspace(0, res, size, endpoint=False, dtype=np.float32)
    i = x.astype(int)
    f = x - i
    f = f * f * (3 - 2 * f)
    rows = c[i] * (1 - f)[:, None] + c[i + 1] * f[:, None]
    return rows[:, i] * (1 - f)[None, :] + rows[:, i + 1] * f[None, :]


def muzzle(tile=512, grid=4, seed=23):
    """Gun flashes, one per frame: a white core with three to five ragged flame petals. The game picks
    a random frame per shot (FlipbookRandom), so bursts of fire never repeat the same flash."""
    rng = np.random.default_rng(seed)
    atlas = np.zeros((tile * grid, tile * grid, 4), np.float32)
    yy, xx = np.mgrid[0:tile, 0:tile].astype(np.float32)
    u = (xx + 0.5) / tile * 2 - 1
    v = 1 - (yy + 0.5) / tile * 2
    r = np.sqrt(u * u + v * v)
    th = np.arctan2(v, u)
    for f in range(grid * grid):
        n = _value_noise(rng, 12, tile) * 0.6 + _value_noise(rng, 28, tile) * 0.4
        petals = rng.integers(3, 6)
        base = rng.uniform(0, 2 * np.pi)
        field = np.zeros_like(r)
        warp = (_value_noise(rng, 6, tile) - 0.5) * 0.7 * np.clip(r, 0, 1)
        fray = _value_noise(rng, 48, tile)
        thw = th + warp
        for k in range(petals):
            a = base + 2 * np.pi * k / petals + rng.uniform(-0.35, 0.35)
            length = rng.uniform(0.45, 0.9)
            spread = rng.uniform(0.22, 0.4)
            dth = np.angle(np.exp(1j * (thw - a)))
            # Petal narrows towards its tip; noise frays the edge.
            wdt = spread * (1 - np.clip(r / length, 0, 1)) ** 0.6 + 1e-3
            field = np.maximum(field, np.exp(-(dth / wdt) ** 2) * np.clip(1 - r / length, 0, 1) ** 1.3)
        field *= np.clip(0.35 + 0.9 * n + 0.5 * (fray - 0.5), 0, None)
        field = np.maximum(field, np.exp(-(r / 0.2) ** 2) * (0.4 + 0.8 * n) * 0.7)
        core = np.exp(-(r / rng.uniform(0.06, 0.09)) ** 2) * 1.4
        glow = np.exp(-(r / 0.45) ** 2) * 0.22
        heat = np.clip(np.minimum(field * 2.6, 0.72) + core, 0, None)
        col = _ramp(np.clip(heat, 0, 1) ** 0.8, HEAT)
        img = col * (heat + glow)[..., None]
        img = 1 - np.exp(-img * 1.1)
        a = np.clip(img.max(-1) * 1.1, 0, 1)
        gy, gx = divmod(f, grid)
        atlas[gy * tile:(gy + 1) * tile, gx * tile:(gx + 1) * tile] = np.dstack([img, a])
    return atlas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["sparks", "muzzle"])
    ap.add_argument("out")
    ap.add_argument("--png")
    args = ap.parse_args()
    atlas = {"sparks": sparks, "muzzle": muzzle}[args.kind]()
    rgba = (np.clip(atlas, 0, 1) * 255 + 0.5).astype(np.uint8)
    if args.png:
        from PIL import Image
        Image.fromarray(rgba, "RGBA").save(args.png)
    fx_dds.write_dxt5(rgba, args.out)
    print("wrote " + args.out)


if __name__ == "__main__":
    main()
