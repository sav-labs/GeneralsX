"""Bake fire, smoke and explosion flipbooks with Blender (Mantaflow + Cycles).

GeneralsX @feature Claude 16/10/2026 Runs inside Blender's Python (the bpy module): simulates a gas
volume with Mantaflow, renders every frame with Cycles under a sun and sky so smoke is self-shadowed,
and writes the frames as one RGBA atlas (straight alpha) for FlipbookGrid particles.

Usage: python blender_flipbook.py <kind> <out.png> [--grid 8] [--tile 256] [--res 96] [--samples 32]
Kinds: explosion, smoke, fire, dust.
"""

import argparse
import math
import os
import sys
import tempfile

import bpy
import numpy as np

# kind -> simulation and look. "frames" is how many sim frames the atlas spans (sampled evenly).
KINDS = {
    "explosion": dict(flow="BOTH", fuel=2.4, burst=4, frames=72, temp=2.6, buoy=1.6, vort=0.35,
                      flame_rate=1.6, flame_smoke=1.4, smoke_color=(0.06, 0.055, 0.05), dissolve=0,
                      emitter=0.45, velocity=(0, 0, 2.0), radial=4.5, fire=True, view=4.2),
    "smoke": dict(flow="SMOKE", fuel=0, burst=10, frames=96, temp=1.2, buoy=0.9, vort=0.25,
                  flame_rate=0, flame_smoke=0, smoke_color=(0.08, 0.075, 0.07), dissolve=0,
                  emitter=0.35, velocity=(0, 0, 1.2), radial=0.6, fire=False, view=4.0),
    "fire": dict(flow="BOTH", fuel=1.4, burst=0, frames=64, temp=2.0, buoy=1.4, vort=0.5,
                 flame_rate=1.2, flame_smoke=0.4, smoke_color=(0.05, 0.045, 0.04), dissolve=30,
                 emitter=0.4, velocity=(0, 0, 0.8), radial=0.2, fire=True, view=3.2),
    "dust": dict(flow="SMOKE", fuel=0, burst=5, frames=80, temp=0.3, buoy=0.15, vort=0.2,
                 flame_rate=0, flame_smoke=0, smoke_color=(0.42, 0.36, 0.28), dissolve=0,
                 emitter=0.5, velocity=(0, 0, 0.6), radial=3.5, fire=False, view=4.6),
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
    p.add_argument("--res", type=int, default=96)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--seed", type=int, default=1)
    return p.parse_args(argv)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def add_domain(cfg, res, cache):
    size = cfg["view"] * 1.5
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, size * 0.5 - 0.6))
    dom = bpy.context.object
    dom.scale = (size, size, size)
    mod = dom.modifiers.new("Fluid", "FLUID")
    mod.fluid_type = "DOMAIN"
    s = mod.domain_settings
    s.domain_type = "GAS"
    s.resolution_max = res
    s.cache_directory = cache
    s.cache_type = "ALL"
    s.cache_frame_start = 1
    s.cache_frame_end = cfg["frames"] + 4
    s.use_adaptive_domain = False
    s.alpha = 0.0
    s.beta = cfg["buoy"]
    s.vorticity = cfg["vort"]
    s.use_dissolve_smoke = cfg["dissolve"] > 0
    if cfg["dissolve"]:
        s.dissolve_speed = cfg["dissolve"]
    s.burning_rate = 0.75
    s.flame_smoke = cfg["flame_smoke"]
    s.flame_vorticity = 0.6
    s.flame_ignition = 1.25
    s.flame_max_temp = 3.0
    s.use_noise = True
    s.noise_scale = 2
    s.noise_strength = 1.2
    s.use_collision_border_bottom = True
    return dom


def add_flow(cfg, seed):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=cfg["emitter"], location=(0, 0, 0))
    flow = bpy.context.object
    # Lumpy emitter so the plume is not a perfect sphere.
    rng = np.random.default_rng(seed)
    for v in flow.data.vertices:
        v.co *= 1.0 + 0.35 * rng.random()
    mod = flow.modifiers.new("Fluid", "FLUID")
    mod.fluid_type = "FLOW"
    f = mod.flow_settings
    f.flow_type = cfg["flow"]
    f.flow_behavior = "INFLOW"
    f.flow_source = "MESH"
    f.surface_distance = 0.6
    f.use_initial_velocity = True
    f.velocity_normal = cfg["radial"]
    f.velocity_coord = cfg["velocity"]
    f.temperature = cfg["temp"]
    f.smoke_color = cfg["smoke_color"]
    f.density = 1.0
    if cfg["flow"] == "BOTH":
        f.fuel_amount = cfg["fuel"]
    f.use_plane_init = False
    if cfg["burst"]:
        # Emit only for the first frames: a single burst that then evolves.
        f.keyframe_insert("density", frame=1)
        f.density = 1.0
        f.keyframe_insert("density", frame=cfg["burst"])
        f.density = 0.0
        f.keyframe_insert("density", frame=cfg["burst"] + 1)
        if cfg["flow"] == "BOTH":
            f.keyframe_insert("fuel_amount", frame=cfg["burst"])
            f.fuel_amount = 0.0
            f.keyframe_insert("fuel_amount", frame=cfg["burst"] + 1)
        f.keyframe_insert("temperature", frame=cfg["burst"])
        f.temperature = 0.0
        f.keyframe_insert("temperature", frame=cfg["burst"] + 1)
        f.keyframe_insert("velocity_normal", frame=cfg["burst"])
        f.velocity_normal = 0.0
        f.keyframe_insert("velocity_normal", frame=cfg["burst"] + 1)
    flow.hide_render = True
    return flow


def volume_material(cfg):
    mat = bpy.data.materials.new("Gas")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    pv = nt.nodes.new("ShaderNodeVolumePrincipled")
    pv.inputs["Density"].default_value = 6.0 if cfg["fire"] else 4.5
    pv.inputs["Anisotropy"].default_value = 0.3
    pv.inputs["Color"].default_value = (*cfg["smoke_color"], 1)
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "color"
    nt.links.new(attr.outputs["Color"], pv.inputs["Color"])
    if cfg["fire"]:
        flame = nt.nodes.new("ShaderNodeAttribute")
        flame.attribute_name = "flame"
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        r = ramp.color_ramp
        r.elements[0].position = 0.0
        r.elements[0].color = (0, 0, 0, 1)
        r.elements[1].position = 1.0
        r.elements[1].color = (1.0, 0.85, 0.55, 1)
        mid = r.elements.new(0.25)
        mid.color = (0.9, 0.18, 0.02, 1)
        mid2 = r.elements.new(0.55)
        mid2.color = (1.0, 0.48, 0.08, 1)
        nt.links.new(flame.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], pv.inputs["Emission Color"])
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = 14.0
        nt.links.new(flame.outputs["Fac"], mul.inputs[0])
        nt.links.new(mul.outputs[0], pv.inputs["Emission Strength"])
    nt.links.new(pv.outputs["Volume"], out.inputs["Volume"])
    return mat


def setup_render(scene, cfg, tile, samples):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.volume_bounces = 2
    scene.cycles.volume_step_rate = 1.0
    scene.render.film_transparent = True
    scene.render.resolution_x = tile
    scene.render.resolution_y = tile
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    world = bpy.data.worlds.new("Sky")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.35, 0.42, 0.55, 1)
    bg.inputs["Strength"].default_value = 0.5
    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 4.0
    sun_data.angle = math.radians(3)
    sun = bpy.data.objects.new("Sun", sun_data)
    sun.rotation_euler = (math.radians(40), math.radians(15), math.radians(30))
    scene.collection.objects.link(sun)
    # RTS camera looks down at roughly 50 degrees; bake from the side-high so billboards read right.
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = cfg["view"]
    cam = bpy.data.objects.new("Cam", cam_data)
    d = 20.0
    cam.location = (0, -d * math.cos(math.radians(25)), cfg["view"] * 0.42 + d * math.sin(math.radians(25)))
    cam.rotation_euler = (math.radians(65), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam


def bake(dom):
    with bpy.context.temp_override(object=dom, active_object=dom, selected_objects=[dom]):
        bpy.ops.fluid.bake_all()


def render_atlas(scene, cfg, grid, tile, out):
    n = grid * grid
    tmp = tempfile.mkdtemp(prefix="fxframes")
    atlas = np.zeros((grid * tile, grid * tile, 4), np.float32)
    span = cfg["frames"]
    for i in range(n):
        frame = 2 + int(round(i * (span - 2) / (n - 1)))
        scene.frame_set(frame)
        path = os.path.join(tmp, "f%03d.png" % i)
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(path)
        px = np.array(img.pixels[:], np.float32).reshape(tile, tile, 4)[::-1]
        bpy.data.images.remove(img)
        r, c = divmod(i, grid)
        atlas[r * tile:(r + 1) * tile, c * tile:(c + 1) * tile] = px
        print("frame %d/%d (sim %d)" % (i + 1, n, frame), flush=True)
    # Edge fade so no tile shows a hard square border.
    yy, xx = np.mgrid[0:tile, 0:tile] / (tile - 1) * 2 - 1
    edge = np.clip((1.0 - np.maximum(abs(xx), abs(yy))) / 0.08, 0, 1)
    for r in range(grid):
        for c in range(grid):
            atlas[r * tile:(r + 1) * tile, c * tile:(c + 1) * tile, 3] *= edge
    img = bpy.data.images.new("atlas", grid * tile, grid * tile, alpha=True)
    img.pixels = atlas[::-1].ravel()
    img.filepath_raw = out
    img.file_format = "PNG"
    img.save()


def main():
    args = parse_args()
    cfg = KINDS[args.kind]
    if args.grid * args.grid > cfg["frames"]:
        cfg = dict(cfg, frames=args.grid * args.grid + 2)
    scene = reset_scene()
    scene.frame_start = 1
    scene.frame_end = cfg["frames"] + 2
    cache = tempfile.mkdtemp(prefix="fxcache")
    dom = add_domain(cfg, args.res, cache)
    dom.data.materials.append(volume_material(cfg))
    add_flow(cfg, args.seed)
    setup_render(scene, cfg, args.tile, args.samples)
    bake(dom)
    render_atlas(scene, cfg, args.grid, args.tile, os.path.abspath(args.out))
    print("wrote " + args.out)


if __name__ == "__main__":
    main()
