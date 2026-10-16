"""Bake fire, smoke and explosion flipbooks: fx_fluid simulation rendered by Blender Cycles.

GeneralsX @feature Claude 16/10/2026 Runs with Blender's Python module (pip install bpy==5.2.2).
fx_fluid.py simulates the gas; every atlas frame is written as an OpenVDB volume, rendered by Cycles
under a sun and sky so smoke is self-shadowed and fire lights it from inside, and packed into one RGBA
atlas (straight alpha) for FlipbookGrid particles. Bright fire is kept opaque in the alpha so the
glow survives alpha blending in game.

Usage: python blender_flipbook.py <kind> <out.png> [--grid 8] [--tile 256] [--scale 1.0] [--samples 48]
Kinds: explosion, smoke, fire, dust. --scale multiplies the simulation grid resolution.
"""

import argparse
import importlib.util
import math
import os
import sys
import tempfile
import time

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_BPY_DIR = os.path.dirname(importlib.util.find_spec("bpy").origin)
_VER = "%d.%d" % bpy.app.version[:2]
sys.path.append(os.path.join(_BPY_DIR, _VER, "python", "lib",
                             "python%d.%d" % sys.version_info[:2], "site-packages"))

import fx_fluid  # noqa: E402
import openvdb  # noqa: E402


def setup_explosion(g, rng):
    nx, ny, nz = g.shape
    g.buoyancy, g.weight, g.vorticity = 5.0, 0.0, 6.0
    g.burn_rate, g.heat, g.soot, g.expansion, g.cooling = 2.0, 1.5, 0.9, 0.8, 0.9
    g.flame_decay, g.glow_temp = 2.5, 1.1
    base = (nx / 2, ny / 2, nz * 0.14)
    for i in range(9):
        off = rng.normal(0, nx * 0.05, 3) * (1, 1, 0.6)
        c = (base[0] + off[0], base[1] + off[1], base[2] + abs(off[2]))
        m = g.blob(c, nx * rng.uniform(0.04, 0.07), 0.5)
        g.fuel += m * rng.uniform(2.0, 3.0)
        g.temp += m * 2.0
        g.density += m * 0.4
        g.expand += m * 70.0
        g.radial(c, m, rng.uniform(8.0, 12.0), 3.0)
    g.turbulence(np.clip(g.fuel, 0, 1), 4.0)
    return dict(frames=72, substeps=2, dt=1 / 60.0, emit=None)


def setup_smoke(g, rng):
    # A hot soot burst with no fuel: the same rolling billows as the explosion's late frames.
    nx, ny, nz = g.shape
    g.buoyancy, g.weight, g.vorticity = 4.0, 0.0, 6.0
    g.cooling, g.expansion = 0.7, 0.0
    base = (nx / 2, ny / 2, nz * 0.16)
    for i in range(7):
        off = rng.normal(0, nx * 0.05, 3) * (1, 1, 0.6)
        c = (base[0] + off[0], base[1] + off[1], base[2] + abs(off[2]))
        m = g.blob(c, nx * rng.uniform(0.05, 0.08), 0.5)
        g.density += m * 2.0
        g.temp += m * 1.6
        g.expand += m * 50.0
        g.radial(c, m, rng.uniform(3.0, 5.0), 1.0)
    g.turbulence(np.clip(g.density, 0, 1), 3.0)
    return dict(frames=96, substeps=2, dt=1 / 60.0, emit=None)


def setup_fire(g, rng):
    nx, ny, nz = g.shape
    g.buoyancy, g.weight, g.vorticity = 12.0, 0.0, 7.0
    g.burn_rate, g.heat, g.soot, g.expansion, g.cooling = 12.0, 1.4, 0.25, 0.3, 3.5
    g.flame_decay, g.glow_temp, g.flame_gain = 9.0, 3.0, 1.0
    g.density_decay = 1.5
    c = (nx / 2, ny / 2, nz * 0.06)
    src = g.blob(c, nx * 0.16, 0.6) * (g.gz < nz * 0.08)

    def emit(frame):
        # Steady burning: the atlas loops a fully developed fire, so feed it for the whole run.
        g.fuel += src * 0.3
        g.temp += src * 0.6
        g.turbulence(src, 2.5)
    return dict(frames=88, warmup=24, substeps=2, dt=1 / 60.0, emit=emit)


def setup_dust(g, rng):
    # Ground burst: blobs hugging the floor thrown outward, little lift.
    nx, ny, nz = g.shape
    g.buoyancy, g.weight, g.vorticity = 1.2, 0.0, 6.0
    g.cooling, g.expansion, g.drag = 0.8, 0.0, 0.03
    base = (nx / 2, ny / 2, nz * 0.08)
    for i in range(8):
        off = rng.normal(0, nx * 0.05, 3) * (1, 1, 0.3)
        c = (base[0] + off[0], base[1] + off[1], base[2] + abs(off[2]))
        m = g.blob(c, nx * rng.uniform(0.04, 0.07), 0.5)
        g.density += m * 1.8
        g.temp += m * 0.8
        g.expand += m * 70.0
        g.radial(c, m, rng.uniform(6.0, 9.0), 1.5)
    g.turbulence(np.clip(g.density, 0, 1), 3.0)
    return dict(frames=80, substeps=2, dt=1 / 60.0, emit=None)


KINDS = {
    # grid shape at scale 1, cell size, smoke colour, density gain, fire emission gain, view framing
    "explosion": dict(setup=setup_explosion, shape=(80, 80, 128), smoke=(0.42, 0.39, 0.36), dens=2.0, fire=12.0),
    "smoke": dict(setup=setup_smoke, shape=(72, 72, 112), smoke=(0.5, 0.47, 0.44), dens=2.5, fire=0.0),
    "fire": dict(setup=setup_fire, shape=(64, 64, 112), smoke=(0.06, 0.05, 0.045), dens=2.0, fire=1.6, flame_body=0.5),
    "dust": dict(setup=setup_dust, shape=(96, 96, 56), smoke=(0.85, 0.76, 0.6), dens=0.55, fire=0.0, firm=0.02),
}


def parse_args():
    argv = sys.argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    p.add_argument("kind", choices=sorted(KINDS))
    p.add_argument("out")
    p.add_argument("--grid", type=int, default=8)
    p.add_argument("--tile", type=int, default=256)
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--samples", type=int, default=48)
    p.add_argument("--seed", type=int, default=3)
    p.add_argument("--only", help="comma list of atlas frames: render just these into a strip (tuning)")
    p.add_argument("--reuse", action="store_true", help="render the cached simulation again")
    return p.parse_args(argv)


def simulate(kind, scale, seed, grid):
    cfg = KINDS[kind]
    shape = tuple(int(round(s * scale)) for s in cfg["shape"])
    g = fx_fluid.Gas(shape, 0.1 / scale, seed)
    rng = np.random.default_rng(seed)
    run = cfg["setup"](g, rng)
    n = grid * grid
    first = run.get("warmup", 0) + 1
    pick = set(int(round(first + i * (run["frames"] - first) / (n - 1))) for i in range(n))
    frames = []
    t = time.time()
    for f in range(1, run["frames"] + 1):
        if run["emit"]:
            run["emit"](f)
        for _ in range(run["substeps"]):
            g.step(run["dt"])
        if f in pick:
            frames.append((g.density.copy(), g.flame.copy(), g.temp.copy()))
        if f % 8 == 0:
            print("sim %s frame %d/%d %.0fs" % (kind, f, run["frames"], time.time() - t), flush=True)
    return g, frames


def write_vdb(path, dx, fields):
    grids = []
    for name, arr in fields.items():
        grid = openvdb.FloatGrid()
        grid.copyFromArray(np.ascontiguousarray(arr, dtype=np.float32), tolerance=1e-4)
        grid.name = name
        grid.transform = openvdb.createLinearTransform(voxelSize=dx)
        grids.append(grid)
    openvdb.write(path, grids=grids)


def material(cfg):
    mat = bpy.data.materials.new("Gas")
    nt = mat.node_tree if mat.node_tree else None
    if nt is None:
        mat.use_nodes = True
        nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    pv = nt.nodes.new("ShaderNodeVolumePrincipled")
    pv.inputs["Color"].default_value = (*cfg["smoke"], 1)
    pv.inputs["Anisotropy"].default_value = 0.35
    dens = nt.nodes.new("ShaderNodeAttribute")
    dens.attribute_name = "density"
    # Fine noise breaks the solver's soft voxels into crisp billows.
    tex = nt.nodes.new("ShaderNodeTexNoise")
    tex.noise_dimensions = "3D"
    tex.inputs["Scale"].default_value = 3.0
    coords = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(coords.outputs["Object"], tex.inputs["Vector"])
    tex.inputs["Detail"].default_value = 4.0
    tex.inputs["Roughness"].default_value = 0.62
    shape = nt.nodes.new("ShaderNodeMapRange")
    shape.inputs["From Min"].default_value = 0.3
    shape.inputs["From Max"].default_value = 0.7
    shape.inputs["To Min"].default_value = 0.8
    shape.inputs["To Max"].default_value = 1.2
    nt.links.new(tex.outputs["Fac"], shape.inputs["Value"])
    m1 = nt.nodes.new("ShaderNodeMath")
    m1.operation = "MULTIPLY"
    nt.links.new(dens.outputs["Fac"], m1.inputs[0])
    nt.links.new(shape.outputs["Result"], m1.inputs[1])
    m2 = nt.nodes.new("ShaderNodeMath")
    m2.operation = "MULTIPLY"
    m2.inputs[1].default_value = cfg["dens"]
    nt.links.new(m1.outputs[0], m2.inputs[0])
    nt.links.new(m2.outputs[0], pv.inputs["Density"])
    if cfg["fire"]:
        flame = nt.nodes.new("ShaderNodeAttribute")
        flame.attribute_name = "flame"
        heat = nt.nodes.new("ShaderNodeAttribute")
        heat.attribute_name = "temperature"
        fsum = nt.nodes.new("ShaderNodeMath")
        fsum.operation = "MULTIPLY_ADD"
        nt.links.new(heat.outputs["Fac"], fsum.inputs[0])
        fsum.inputs[1].default_value = 0.025
        fsum.use_clamp = True
        fl = nt.nodes.new("ShaderNodeMath")
        fl.operation = "MULTIPLY"
        fl.inputs[1].default_value = 0.85
        nt.links.new(flame.outputs["Fac"], fl.inputs[0])
        nt.links.new(fl.outputs[0], fsum.inputs[2])
        fmod = nt.nodes.new("ShaderNodeMath")
        fmod.operation = "MULTIPLY"
        nt.links.new(fsum.outputs[0], fmod.inputs[0])
        nt.links.new(shape.outputs["Result"], fmod.inputs[1])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        r = ramp.color_ramp
        r.elements[0].position = 0.0
        r.elements[0].color = (0, 0, 0, 1)
        r.elements[1].position = 1.0
        r.elements[1].color = (1.0, 0.78, 0.38, 1)
        for pos, col in ((0.15, (0.3, 0.03, 0.0, 1)), (0.4, (0.95, 0.2, 0.02, 1)), (0.7, (1.0, 0.48, 0.08, 1))):
            e = r.elements.new(pos)
            e.color = col
        nt.links.new(fmod.outputs[0], ramp.inputs["Fac"])
        inv = nt.nodes.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.use_clamp = True
        inv.inputs[0].default_value = 1.0
        nt.links.new(fsum.outputs[0], inv.inputs[1])
        tint = nt.nodes.new("ShaderNodeMix")
        tint.data_type = "RGBA"
        tint.inputs["A"].default_value = (0.05, 0.035, 0.025, 1)
        tint.inputs["B"].default_value = (*cfg["smoke"], 1)
        nt.links.new(inv.outputs[0], tint.inputs["Factor"])
        nt.links.new(tint.outputs["Result"], pv.inputs["Color"])
        nt.links.new(ramp.outputs["Color"], pv.inputs["Emission Color"])
        gain = nt.nodes.new("ShaderNodeMath")
        gain.operation = "MULTIPLY"
        gain.inputs[1].default_value = cfg["fire"]
        sq = nt.nodes.new("ShaderNodeMath")
        sq.operation = "POWER"
        sq.inputs[1].default_value = 2.6
        nt.links.new(fmod.outputs[0], sq.inputs[0])
        nt.links.new(sq.outputs[0], gain.inputs[0])
        # Patchy fire: a second, coarser noise opens and closes glowing pockets inside the smoke.
        pn = nt.nodes.new("ShaderNodeTexNoise")
        pn.noise_dimensions = "3D"
        pn.inputs["Scale"].default_value = 1.4
        pn.inputs["Detail"].default_value = 3.0
        nt.links.new(coords.outputs["Object"], pn.inputs["Vector"])
        patch = nt.nodes.new("ShaderNodeMapRange")
        patch.interpolation_type = "SMOOTHSTEP"
        patch.inputs["From Min"].default_value = 0.42
        patch.inputs["From Max"].default_value = 0.62
        patch.inputs["To Min"].default_value = 0.08
        patch.inputs["To Max"].default_value = 1.0
        nt.links.new(pn.outputs["Fac"], patch.inputs["Value"])
        # Hottest gas glows everywhere; cooler fire only in the pockets.
        hot = nt.nodes.new("ShaderNodeMath")
        hot.operation = "MAXIMUM"
        nt.links.new(patch.outputs["Result"], hot.inputs[0])
        hotr = nt.nodes.new("ShaderNodeMapRange")
        hotr.inputs["From Min"].default_value = 0.75
        hotr.inputs["From Max"].default_value = 1.0
        nt.links.new(fsum.outputs[0], hotr.inputs["Value"])
        nt.links.new(hotr.outputs["Result"], hot.inputs[1])
        em = nt.nodes.new("ShaderNodeMath")
        em.operation = "MULTIPLY"
        nt.links.new(gain.outputs[0], em.inputs[0])
        nt.links.new(hot.outputs[0], em.inputs[1])
        nt.links.new(em.outputs[0], pv.inputs["Emission Strength"])
    nt.links.new(pv.outputs["Volume"], out.inputs["Volume"])
    return mat


def trilinear(f, x, y, z):
    nx, ny, nz = f.shape
    x = np.clip(x, 0, nx - 1.001)
    y = np.clip(y, 0, ny - 1.001)
    z = np.clip(z, 0, nz - 1.001)
    x0, y0, z0 = x.astype(np.int32), y.astype(np.int32), z.astype(np.int32)
    fx, fy, fz = x - x0, y - y0, z - z0
    c00 = f[x0, y0, z0] * (1 - fx) + f[x0 + 1, y0, z0] * fx
    c10 = f[x0, y0 + 1, z0] * (1 - fx) + f[x0 + 1, y0 + 1, z0] * fx
    c01 = f[x0, y0, z0 + 1] * (1 - fx) + f[x0 + 1, y0, z0 + 1] * fx
    c11 = f[x0, y0 + 1, z0 + 1] * (1 - fx) + f[x0 + 1, y0 + 1, z0 + 1] * fx
    return (c00 * (1 - fy) + c10 * fy) * (1 - fz) + (c01 * (1 - fy) + c11 * fy) * fz


class Upres:
    """Doubles the grid and adds sub-cell billows by sampling the coarse fields at noise-warped
    positions (a cheap wavelet-turbulence stand-in). The noise drifts slowly with time so the detail
    does not flicker between atlas frames."""

    def __init__(self, shape, factor=2, seed=7):
        self.factor = factor
        rng = np.random.default_rng(seed)
        self.octaves = []
        for period, amp in ((9.0, 2.6), (3.5, 1.3), (1.5, 0.55)):
            n = [int(s / period) + 3 for s in shape]
            self.octaves.append((period, amp, [rng.standard_normal(n).astype(np.float32) for _ in range(3)]))
        hi = [s * factor for s in shape]
        g = np.meshgrid(*[np.arange(h, dtype=np.float32) / factor for h in hi], indexing="ij")
        self.gx, self.gy, self.gz = g

    def warp(self, t):
        wx = np.zeros_like(self.gx)
        wy = np.zeros_like(self.gx)
        wz = np.zeros_like(self.gx)
        for period, amp, (nx, ny, nz) in self.octaves:
            drift = t * 1.5 / period
            px, py, pz = self.gx / period, self.gy / period, self.gz / period - drift
            wx += amp * trilinear(nx, px, py, pz)
            wy += amp * trilinear(ny, px, py, pz)
            wz += amp * trilinear(nz, px, py, pz)
        return self.gx + wx, self.gy + wy, self.gz + wz

    def __call__(self, fields, t):
        x, y, z = self.warp(t)
        return [trilinear(f, x, y, z) for f in fields]


def wall_fade(shape, cells=6):
    """1 inside, falling to 0 over the last cells at the sides and top (the floor stays)."""
    f = np.ones(shape, np.float32)
    for axis, n in enumerate(shape):
        ramp = np.clip(np.minimum(np.arange(n), n - 1 - np.arange(n)) / cells, 0, 1)
        if axis == 2:
            ramp = np.clip((n - 1 - np.arange(n)) / cells, 0, 1)
        f *= ramp.reshape([-1 if a == axis else 1 for a in range(3)])
    return f


def framing(frames, dx):
    """Centre and size of the square view (world units, x and z) that holds every frame."""
    occ = np.zeros(frames[0][0].shape[0::2], bool)
    for dens, flame, _ in frames:
        occ |= (dens.sum(axis=1) * dx > 0.15) | (flame.max(axis=1) > 0.1)
    xs, zs = np.nonzero(occ)
    x0, x1 = xs.min() * dx, (xs.max() + 1) * dx
    z0, z1 = zs.min() * dx, (zs.max() + 1) * dx
    size = max(x1 - x0, z1 - z0) * 1.08
    return ((x0 + x1) / 2, (z0 + z1) / 2), size


def setup_scene(shape, dx, tile, samples, view):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.volume_bounces = 3
    scene.cycles.volume_step_rate = 2.0
    scene.cycles.max_bounces = 4
    scene.render.film_transparent = True
    scene.render.resolution_x = tile
    scene.render.resolution_y = tile
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "16"
    # Standard keeps fire saturated; AgX washes it to peach.
    scene.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("Sky")
    scene.world = world
    if not world.node_tree:
        world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.42, 0.48, 0.58, 1)
    bg.inputs["Strength"].default_value = 0.7
    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 9.0
    sun_data.angle = math.radians(4)
    sun_data.color = (1.0, 0.95, 0.88)
    sun = bpy.data.objects.new("Sun", sun_data)
    # Light from the upper left, slightly behind the camera: lit tops, shadowed undersides.
    sun.rotation_euler = (math.radians(35), 0, math.radians(-40))
    scene.collection.objects.link(sun)
    sx, sy, sz = (s * dx for s in shape)
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.type = "ORTHO"
    (vx, vz), size = view
    cam_data.ortho_scale = size
    cam = bpy.data.objects.new("Cam", cam_data)
    pitch = math.radians(20)
    # Ortho with a 20 degree pitch: shift up so the frame's vertical centre lands on vz.
    centre = (vx, sy / 2, vz)
    dist = 50.0
    cam.location = (centre[0], centre[1] - dist * math.cos(pitch), centre[2] + dist * math.sin(pitch))
    cam.rotation_euler = (math.radians(90) - pitch, 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    return scene


def keep_glow(px):
    """Cycles' alpha only counts absorption, so pure fire would vanish under alpha blending: raise
    alpha to the brightness and divide the colour back so it reads as opaque glowing gas."""
    rgb, a = px[..., :3], px[..., 3:]
    premul = rgb * a
    lum = premul.max(-1, keepdims=True)
    a2 = np.clip(np.maximum(a, lum * 1.15), 0, 1)
    rgb2 = np.where(a2 > 1e-4, premul / np.maximum(a2, 1e-4), 0)
    return np.concatenate([np.clip(rgb2, 0, 1), a2], -1)


def pack_tiles(raw, grid, tile):
    """Crop every frame to the square that holds all of them, then scale it to the tile size, so the
    effect fills the sprite instead of floating in empty margin."""
    from PIL import Image
    occ = np.zeros(raw[0].shape[:2], bool)
    for px in raw:
        occ |= px[..., 3] > 0.2
    ys, xs = np.nonzero(occ)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    size = int(max(y1 - y0, x1 - x0) * 1.06)
    cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
    top = max(0, min(raw[0].shape[0] - size, cy - size // 2))
    left = max(0, min(raw[0].shape[1] - size, cx - size // 2))
    atlas = np.zeros((grid * tile, grid * tile, 4), np.float32)
    for i, px in enumerate(raw):
        crop = px[top:top + size, left:left + size]
        premul = np.concatenate([crop[..., :3] * crop[..., 3:], crop[..., 3:]], -1)
        chans = [np.asarray(Image.fromarray(premul[..., k]).resize((tile, tile), Image.LANCZOS)) for k in range(4)]
        out = np.clip(np.stack(chans, -1), 0, None)
        a = np.clip(out[..., 3:], 0, 1)
        out[..., :3] = np.where(a > 1e-4, out[..., :3] / np.maximum(a, 1e-4), 0)
        out[..., 3:] = a
        r, c = divmod(i, grid)
        atlas[r * tile:(r + 1) * tile, c * tile:(c + 1) * tile] = out
    return atlas


def render_atlas(kind, frames, shape, dx, grid, tile, samples, out, only=None):
    cfg = KINDS[kind]
    big = int(tile * 1.6)
    scene = setup_scene(shape, dx, big, samples, framing(frames, dx))
    mat = material(cfg)
    tmp = tempfile.mkdtemp(prefix="fx" + kind)
    raw = []
    up = Upres(shape)
    dx_hi = dx / up.factor
    for i, (dens, flame, temp) in enumerate(frames):
        if only is not None and i not in only:
            continue
        dens, flame, temp = up([dens, flame, temp], i * 0.25)
        # Firm up billow edges: thin wisps fade, bodies keep their density.
        # Flames are thin sheets: give them some body so they are not a speckle of emission.
        dens = dens + flame * cfg.get("flame_body", 0.0)
        firm = cfg.get("firm", 0.12)
        dens = dens * np.clip((dens - firm) / (0.5 if firm > 0.05 else 0.2), 0, 1) ** 0.9
        vdb = os.path.join(tmp, "f%03d.vdb" % i)
        wall = wall_fade(dens.shape)
        write_vdb(vdb, dx_hi, {"density": dens * wall, "flame": flame * wall, "temperature": temp * wall})
        vol = bpy.data.volumes.new("Gas")
        vol.filepath = vdb
        obj = bpy.data.objects.new("Gas", vol)
        scene.collection.objects.link(obj)
        vol.materials.append(mat)
        png = os.path.join(tmp, "f%03d.png" % i)
        scene.render.filepath = png
        bpy.ops.render.render(write_still=True)
        bpy.data.objects.remove(obj)
        bpy.data.volumes.remove(vol)
        img = bpy.data.images.load(png)
        raw.append(np.array(img.pixels[:], np.float32).reshape(big, big, 4)[::-1])
        bpy.data.images.remove(img)
        print("render %s %d/%d" % (kind, i + 1, len(frames)), flush=True)
    if only is not None:
        strip = keep_glow(np.concatenate(raw, 1))
        img = bpy.data.images.new("strip", strip.shape[1], strip.shape[0], alpha=True)
        img.pixels = strip[::-1].ravel()
        img.filepath_raw = out
        img.file_format = "PNG"
        img.save()
        return
    atlas = pack_tiles(raw, grid, tile)
    atlas = keep_glow(atlas)
    yy, xx = np.mgrid[0:tile, 0:tile] / (tile - 1) * 2 - 1
    edge = np.clip((1.0 - np.maximum(abs(xx), abs(yy))) / 0.06, 0, 1)
    for r in range(grid):
        for c in range(grid):
            atlas[r * tile:(r + 1) * tile, c * tile:(c + 1) * tile, 3] *= edge
    np.save(out + ".npy", atlas.astype(np.float16))
    img = bpy.data.images.new("atlas", grid * tile, grid * tile, alpha=True)
    img.pixels = atlas[::-1].ravel()
    img.filepath_raw = out
    img.file_format = "PNG"
    img.save()


def main():
    args = parse_args()
    cache = os.path.abspath(args.out) + ".sim.npz"
    if args.reuse and os.path.exists(cache):
        z = np.load(cache)
        frames = list(zip(z["density"], z["flame"], z["temp"]))
        shape, dx = tuple(z["shape"]), float(z["dx"])
    else:
        g, frames = simulate(args.kind, args.scale, args.seed, args.grid)
        shape, dx = g.shape, g.dx
        np.savez_compressed(cache, density=[f[0] for f in frames], flame=[f[1] for f in frames],
                            temp=[f[2] for f in frames], shape=shape, dx=dx)
    only = [int(x) for x in args.only.split(",")] if args.only else None
    render_atlas(args.kind, frames, shape, dx, args.grid, args.tile, args.samples, os.path.abspath(args.out), only)
    print("wrote " + args.out, flush=True)
    os._exit(0)  # skip interpreter teardown: the openvdb bindings report leaks on exit


if __name__ == "__main__":
    main()
