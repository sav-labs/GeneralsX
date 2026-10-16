#!/usr/bin/env python3
"""Preview video of a GeneralsX FX list, simulated outside the game.

GeneralsX @feature Claude 16/10/2026 Steps the particle systems of fx_systems.py with the retail
particle rules (bursts, per-frame velocity, damping, gravity, drift, size rates, alpha and colour
key frames, flipbook frames) and draws them over a simple terrain and tank stand-in from an RTS
camera. It is a look-development aid only: lighting, sorting and fog differ from the game.

Usage: preview.py <output.mp4> [--scene tank|building] [--seconds 10] [--width 960]
"""

import argparse
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fx_systems  # noqa: E402
import fx_textures  # noqa: E402

FPS = 30


class Camera:
    def __init__(self, width, height, target=(0.0, 0.0, 6.0), yaw=-60.0, pitch=38.0, dist=150.0, fov=42.0):
        self.w, self.h = width, height
        y, p = math.radians(yaw), math.radians(pitch)
        f = np.array([math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), -math.sin(p)])
        self.pos = np.array(target) - f * dist
        r = np.cross(f, [0, 0, 1.0])
        self.right = r / np.linalg.norm(r)
        self.up = np.cross(self.right, f)
        self.fwd = f
        self.focal = (height / 2) / math.tan(math.radians(fov) / 2)

    def project(self, p):
        d = np.asarray(p, float) - self.pos
        x, y, z = d @ self.right, d @ self.up, d @ self.fwd
        z = np.maximum(z, 1e-3)
        return self.w / 2 + x / z * self.focal, self.h / 2 - y / z * self.focal, z


def terrain(cam):
    """Ground plane z = 0 with dry grass and dirt, plus a scorch mark that appears after the blast."""
    h, w = cam.h, cam.w
    ys, xs = np.mgrid[0:h, 0:w]
    dx = (xs - w / 2) / cam.focal
    dy = -(ys - h / 2) / cam.focal
    ray = cam.fwd[None, None] + dx[..., None] * cam.right + dy[..., None] * cam.up
    t = -cam.pos[2] / np.minimum(ray[..., 2], -1e-4)
    gx = cam.pos[0] + ray[..., 0] * t
    gy = cam.pos[1] + ray[..., 1] * t
    noise = fx_textures.Noise3(9)
    n1 = noise.fbm(gx / 60.0, gy / 60.0, np.zeros_like(gx), 4)
    n2 = noise.fbm(gx / 9.0, gy / 9.0, np.ones_like(gx) * 3, 3)
    grass = np.array([0.36, 0.38, 0.22])
    dirt = np.array([0.50, 0.42, 0.30])
    m = np.clip((n1 - 0.45) * 4, 0, 1)[..., None]
    rgb = grass * (1 - m) + dirt * m
    rgb = rgb * (0.82 + 0.3 * n2)[..., None]
    dist = np.sqrt(gx * gx + gy * gy)
    scorch = np.clip(1 - dist / 22.0, 0, 1) ** 0.7 * (0.75 + 0.3 * n2)
    return rgb, scorch


def box_faces(center, size, yaw):
    cx, cy, cz = center
    sx, sy, sz = size[0] / 2, size[1] / 2, size[2]
    c, s = math.cos(yaw), math.sin(yaw)

    def pt(x, y, z):
        return (cx + x * c - y * s, cy + x * s + y * c, cz + z)

    corners = {k: pt(*k) for k in [(a * sx, b * sy, z) for a in (-1, 1) for b in (-1, 1) for z in (0, sz)]}
    faces = [
        ([(-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz)], (0, 0, 1)),
        ([(sx, -sy, 0), (sx, sy, 0), (sx, sy, sz), (sx, -sy, sz)], (c, s, 0)),
        ([(-sx, -sy, 0), (-sx, sy, 0), (-sx, sy, sz), (-sx, -sy, sz)], (-c, -s, 0)),
        ([(-sx, sy, 0), (sx, sy, 0), (sx, sy, sz), (-sx, sy, sz)], (-s, c, 0)),
        ([(-sx, -sy, 0), (sx, -sy, 0), (sx, -sy, sz), (-sx, -sy, sz)], (s, -c, 0)),
    ]
    return [([corners[k] for k in quad], normal) for quad, normal in faces]


TANK = [((0, 0, 1.5), (26, 14, 5.5)), ((-1.5, 0, 7.0), (12, 9, 3.6)), ((9.5, 0, 8.2), (14, 1.3, 1.3))]
BUILDING = [((0, 0, 0), (60, 44, 22)), ((-12, -6, 22), (22, 18, 8)), ((18, 12, 22), (8, 8, 14))]

# Preview scenes: stand-in model, camera distance, and (system, offset, start frame) entries; an FX list
# name as the first entry expands to its particle systems.
SCENES = {
    "tank": {"model": TANK, "dist": 150.0, "fx": [("FX_GenericTankDeathExplosion", (0, 0, 0), 18)]},
    "building": {"model": BUILDING, "dist": 260.0, "fx": [
        ("StructureTransitionSmallExplosion", (6, -4, 24), 18),
        ("StructureTransitionSmallSmoke", (0, 0, 10), 18),
        ("SmolderingFire", (-20, -10, 22), 30), ("SmolderingSmoke", (-20, -10, 24), 30),
        ("SmolderingFire", (14, 8, 30), 40), ("SmolderingSmoke", (14, 8, 33), 40),
        ("SmolderingFlameCore", (14, 8, 30), 40),
        ("SmolderingFire", (22, -16, 14), 50), ("SmolderingSmoke", (22, -16, 16), 50),
        ("SmolderingFire", (-26, 14, 22), 36), ("SmolderingSmoke", (-26, 14, 24), 36),
    ]},
}


def draw_tank(img, cam, burnt, parts=TANK):
    """Very simple stand-in model made of boxes, sand coloured or charred."""
    d = ImageDraw.Draw(img)
    light = np.array([-0.4, -0.5, 0.75])
    light /= np.linalg.norm(light)
    base = np.array([0.20, 0.17, 0.14]) if burnt else np.array([0.62, 0.56, 0.40])
    yaw = math.radians(20)
    faces = []
    for center, size in parts:
        for quad, normal in box_faces(center, size, yaw):
            n = np.array(normal, float)
            centre = np.mean(quad, axis=0)
            if (centre - cam.pos) @ n >= 0:
                continue
            sx, sy, sz = cam.project(np.array(quad))
            faces.append((float(np.mean(sz)), list(zip(sx, sy)), max(n @ light, 0)))
    for _, poly, lam in sorted(faces, key=lambda f: -f[0]):
        col = base * (0.35 + 0.75 * lam)
        d.polygon(poly, fill=tuple(int(c * 255) for c in col))


class Particle:
    __slots__ = ("pos", "vel", "size", "size_rate", "size_damp", "angle", "ang_rate", "ang_damp",
                 "vel_damp", "age", "life", "alpha_keys", "color_keys", "frame_pick")


class System:
    def __init__(self, name, spec, offset, rng):
        self.name, self.s, self.rng = name, spec, rng
        self.origin = np.array(offset, float)
        self.delay = int(self.rand(spec["InitialDelay"]))
        self.life = spec["SystemLifetime"]
        self.forever = self.life == 0
        self.burst_left = 0
        self.particles = []

    def rand(self, pair):
        return self.rng.uniform(pair[0], pair[1]) if pair[1] > pair[0] else pair[0]

    def emit(self):
        s = self.s
        p = Particle()
        vt, vol = s["VolumeType"], s["VolumeType"]
        pos = np.zeros(3)
        if vol == "SPHERE":
            v = self.rng.normal(size=3)
            v /= np.linalg.norm(v)
            r = s["VolSphereRadius"] * (1.0 if s["IsHollow"] == "Yes" else self.rng.random() ** (1 / 3))
            pos = v * r
        elif vol == "CYLINDER":
            a = self.rng.uniform(0, 2 * math.pi)
            r = s["VolCylinderRadius"] * (1.0 if s["IsHollow"] == "Yes" else math.sqrt(self.rng.random()))
            pos = np.array([math.cos(a) * r, math.sin(a) * r, self.rng.uniform(0, s["VolCylinderLength"])])
        vel = np.zeros(3)
        if vt == "SPHERICAL":
            v = self.rng.normal(size=3)
            vel = v / np.linalg.norm(v) * self.rand(s["VelSpherical"])
        elif vt == "HEMISPHERICAL":
            v = self.rng.normal(size=3)
            v[2] = abs(v[2])
            vel = v / np.linalg.norm(v) * self.rand(s["VelHemispherical"])
        elif vt == "OUTWARD":
            speed, other = self.rand(s["VelOutward"]), self.rand(s["VelOutwardOther"])
            if vol == "CYLINDER":
                d = pos[:2] / max(np.linalg.norm(pos[:2]), 1e-6)
                vel = np.array([d[0] * speed, d[1] * speed, other])
            else:
                d = pos / max(np.linalg.norm(pos), 1e-6)
                vel = d * speed
        p.pos = self.origin + pos
        p.vel = vel
        p.size = self.rand(s["Size"])
        p.size_rate = self.rand(s["SizeRate"])
        p.size_damp = self.rand(s["SizeRateDamping"])
        p.angle = self.rand(s["AngleZ"])
        p.ang_rate = self.rand(s["AngularRateZ"])
        p.ang_damp = self.rand(s["AngularDamping"])
        p.vel_damp = self.rand(s["VelocityDamping"])
        p.age = 0
        p.life = max(int(self.rand(s["Lifetime"])), 1)
        p.alpha_keys = [(self.rand((lo, hi)), f) for lo, hi, f in s["Alpha"]]
        p.color_keys = list(s["Color"])
        p.frame_pick = int(self.rng.integers(0, 256))
        self.particles.append(p)

    def step(self):
        s = self.s
        if self.delay > 0:
            self.delay -= 1
            return
        if self.forever or self.life > 0:
            if self.burst_left == 0:
                for _ in range(int(self.rand(s["BurstCount"]))):
                    self.emit()
                self.burst_left = int(self.rand(s["BurstDelay"]))
            else:
                self.burst_left -= 1
            if not self.forever:
                self.life -= 1
        drift = np.array(s["DriftVelocity"])
        alive = []
        for p in self.particles:
            p.age += 1
            if p.age >= p.life:
                continue
            p.vel[2] += s["Gravity"]
            p.vel *= p.vel_damp
            p.pos = p.pos + p.vel + drift
            p.size = max(p.size + p.size_rate, 0.0)
            p.size_rate *= p.size_damp
            p.angle += p.ang_rate
            p.ang_rate *= p.ang_damp
            alive.append(p)
        self.particles = alive


def key_value(keys, age):
    """Linear interpolation over retail key frames; keys after the first with frame 0 are unused."""
    used = [keys[0]] + [k for k in keys[1:] if k[1] > 0]
    if len(used) == 1 or age <= used[0][1]:
        return used[0][0]
    for (v0, f0), (v1, f1) in zip(used, used[1:]):
        if age <= f1:
            t = (age - f0) / max(f1 - f0, 1)
            return np.asarray(v0, float) * (1 - t) + np.asarray(v1, float) * t
    return used[-1][0]


class SpriteCache:
    def __init__(self):
        self.tex = {}

    def frame(self, name, grid, index):
        key = (name, grid, index)
        if key not in self.tex:
            if name not in self.tex:
                builder, _ = fx_textures.TEXTURES[name]
                self.tex[name] = builder()
            atlas = self.tex[name]
            if grid > 1:
                cell = atlas.shape[0] // grid
                r, c = divmod(index, grid)
                self.tex[key] = atlas[r * cell:(r + 1) * cell, c * cell:(c + 1) * cell]
            else:
                self.tex[key] = atlas
        return self.tex[key]


def splat(canvas, tex, center, axes, color, alpha, additive):
    """Draws a textured parallelogram: screen point = center + u * axes[0] + v * axes[1], u, v in [-0.5, 0.5]."""
    h, w = canvas.shape[:2]
    a, b = np.array(axes[0]), np.array(axes[1])
    ext = np.abs(a) / 2 + np.abs(b) / 2
    x0, x1 = int(max(center[0] - ext[0], 0)), int(min(center[0] + ext[0] + 1, w))
    y0, y1 = int(max(center[1] - ext[1], 0)), int(min(center[1] + ext[1] + 1, h))
    if x0 >= x1 or y0 >= y1:
        return
    m = np.array([[a[0], b[0]], [a[1], b[1]]])
    det = np.linalg.det(m)
    if abs(det) < 1e-6:
        return
    inv = np.linalg.inv(m)
    ys, xs = np.mgrid[y0:y1, x0:x1]
    px = xs + 0.5 - center[0]
    py = ys + 0.5 - center[1]
    u = inv[0, 0] * px + inv[0, 1] * py + 0.5
    v = inv[1, 0] * px + inv[1, 1] * py + 0.5
    inside = (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
    if not inside.any():
        return
    th, tw = tex.shape[:2]
    tx = np.clip((u * tw).astype(int), 0, tw - 1)
    ty = np.clip((v * th).astype(int), 0, th - 1)
    sample = tex[ty, tx]
    region = canvas[y0:y1, x0:x1]
    col = sample[..., :3] * np.asarray(color)[None, None]
    if additive:
        region += col * inside[..., None]
    else:
        al = (sample[..., 3] * alpha * inside)[..., None]
        region[:] = region * (1 - al) + col * al


def simulate(scene_name, seconds, width, out_path):
    rng = np.random.default_rng(5)
    scene = SCENES[scene_name]
    cam = Camera(width, int(width * 9 / 16), dist=scene["dist"])
    ground, scorch = terrain(cam)
    entries = []
    for name, offset, start in scene["fx"]:
        if name in fx_systems.FXLISTS:
            entries += [(n, np.add(offset, off), start) for n, off in fx_systems.FXLISTS[name]["particles"]]
        else:
            entries.append((name, offset, start))
    boom_frame = min(e[2] for e in entries)
    sprites = SpriteCache()
    systems = []
    frames = int(seconds * FPS)
    pulse = 0.0
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", "%dx%d" % (cam.w, cam.h), "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                             "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                             out_path], stdin=subprocess.PIPE)
    for f in range(frames):
        for n, off, start in entries:
            if f == start:
                systems.append(System(n, fx_systems.SYSTEMS[n], off, rng))
        if f == boom_frame and scene_name == "tank":
            pulse = 1.0
        for s in systems:
            s.step()
        burnt = f >= boom_frame
        base = ground.copy()
        if burnt:
            base *= (1 - 0.8 * scorch)[..., None]
        # Light pulse: warm light on the ground that fades over 900 ms.
        if pulse > 0:
            ys, xs = np.mgrid[0:cam.h, 0:cam.w]
            cx, cy, _ = cam.project([0, 0, 0])
            r = np.sqrt((xs - cx) ** 2 + ((ys - cy) * 1.6) ** 2) / (cam.focal * 90 / np.linalg.norm(cam.pos))
            base += (np.clip(1 - r, 0, 1) ** 2 * pulse)[..., None] * np.array([1.0, 0.59, 0.27]) * 0.9
            pulse = max(pulse - 1.0 / (0.9 * FPS), 0.0)
        img = Image.fromarray((np.clip(base, 0, 1) * 255).astype(np.uint8))
        draw_tank(img, cam, burnt, scene["model"])
        canvas = np.asarray(img).astype(float) / 255.0
        canvas = canvas.copy()
        draw = []
        for s in systems:
            spec = s.s
            grid = spec["FlipbookGrid"] if spec["FlipbookGrid"] in (2, 4, 8, 16) else 1
            for p in s.particles:
                # The terrain hides particles below the ground in the game.
                if p.pos[2] < 0.0 and spec["IsGroundAligned"] != "Yes":
                    continue
                sx, sy, sz = cam.project(p.pos)
                draw.append((float(sz), s, p, sx, sy, grid))
        for sz, s, p, sx, sy, grid in sorted(draw, key=lambda d: -d[0]):
            spec = s.s
            count = grid * grid
            if grid == 1:
                index = 0
            elif spec["FlipbookRandom"] == "Yes":
                index = p.frame_pick % count
            else:
                index = min(p.age * count // p.life, count - 1)
            tex = sprites.frame(spec["ParticleName"], grid, index)
            color = np.asarray(key_value(p.color_keys, p.age), float) / 255.0
            alpha = float(key_value(p.alpha_keys, p.age))
            additive = spec["Shader"] == "ADDITIVE"
            c, si = math.cos(p.angle), math.sin(p.angle)
            if spec["IsGroundAligned"] == "Yes":
                half = p.size / 2
                ex = cam.project(p.pos + np.array([c, si, 0]) * half)
                ey = cam.project(p.pos + np.array([-si, c, 0]) * half)
                axes = ((2 * (ex[0] - sx), 2 * (ex[1] - sy)), (2 * (ey[0] - sx), 2 * (ey[1] - sy)))
            else:
                px = p.size * cam.focal / sz
                axes = ((px * c, px * si), (-px * si, px * c))
            splat(canvas, tex, (sx, sy), axes, color, alpha, additive)
        # Simple display transform; the game adds bloom on top of this.
        out = 1 - np.exp(-canvas * 1.15)
        out = out / (1 - math.exp(-1.15))
        proc.stdin.write((np.clip(out, 0, 1) * 255).astype(np.uint8).tobytes())
    proc.stdin.close()
    proc.wait()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--scene", default="tank", choices=sorted(SCENES))
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--width", type=int, default=960)
    args = ap.parse_args()
    simulate(args.scene, args.seconds, args.width, args.out)


if __name__ == "__main__":
    main()
