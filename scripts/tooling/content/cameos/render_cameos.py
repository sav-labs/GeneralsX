"""Command bar cameos for the detailed USA vehicles, in the look of the retail Zero Hour art.

GeneralsX @feature Claude 16/10/2026 The retail USA cameos show the vehicle large and close, from a low
front quarter, under a hard desert sun with blue sky and sand behind it, inside a dark navy bevel.
This renders each source model (.glb from the model-sources release) that way with Cycles and writes
the button (120x96) and the selection portrait (216x178) per unit, plus 4x masters for review.

Usage: python render_cameos.py <glb dir> <out dir> [--units crusader,paladin] [--samples 64] [--preview]
"""

import argparse
import math
import os
import sys

import bpy
from mathutils import Euler, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import frame  # noqa: E402

# Unit -> (cameo name, yaw that turns the model's front to the camera's right, framing zoom, mesh name
# parts to leave out). Names follow the content pack's CAMEOS table so the images drop into its sheets.
# Every unit is tinted desert tan over its source colours, as the content pack's importer does (see
# content/blend/sources.py "tint"); hidden lists the pieces it drops (the Abrams' alpha-cut decal layer
# would render as black panels here).
UNITS = {
    "crusader": ("GXCameo_MBT", 0, 1.0, ("misc_a.4",)),
    "paladin": ("GXCameo_Paladin", 0, 1.0, ()),
    "humvee": ("GXCameo_JLTV", 0, 0.72, ()),
    "ambulance": ("GXCameo_Medic", 0, 0.72, ()),
    "tomahawk": ("GXCameo_MLRS", 180, 0.72, ("Default_2",)),  # a spare rocket lies beside the truck
    "microwave": ("GXCameo_Microwave", 180, 0.82, ()),
    "avenger": ("GXCameo_Avenger", 0, 0.72, ()),
    "bulldozer": ("GXCameo_Dozer", 0, 0.82, ()),
}
TAN = (0.45, 0.35, 0.21, 1.0)  # sources.py tint (176, 156, 112), linear
TINT = 0.85
KEEP_COLOUR = ("glass", "window", "tire", "tyre", "rubber", "light", "mirror", "missle", "missile")
# Damaged copies of parts some models carry next to the intact ones, and stray default cubes.
ALWAYS_HIDDEN = ("_dam", "Cube")
LENGTH = 8.0  # every model is scaled to this hull length, so lights and ground behave the same
# Shot per image: (size, camera yaw from the front, camera pitch, focal length mm).
SHOTS = {"button": ((480, 384), 40, 7, 32), "portrait": ((864, 712), 34, 11, 35)}


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def load(path, yaw, hidden):
    bpy.ops.import_scene.gltf(filepath=path)
    meshes = []
    for o in list(bpy.context.scene.objects):
        names = [o.name] + [m.name for m in getattr(o.data, "materials", []) if m]
        if o.type == "MESH" and any(h in n for h in hidden + ALWAYS_HIDDEN for n in names):
            bpy.data.objects.remove(o)
        elif o.type == "MESH":
            meshes.append(o)
    root = bpy.data.objects.new("unit", None)
    bpy.context.scene.collection.objects.link(root)
    for o in bpy.context.scene.objects:
        if o.parent is None and o is not root:
            o.parent = root
    bpy.context.view_layer.update()
    lo, hi = bbox(meshes)
    # Longest horizontal side along X, wheels on the ground, centred.
    if hi.y - lo.y > hi.x - lo.x:
        root.rotation_euler = Euler((0, 0, math.pi / 2))
    root.rotation_euler.z += math.radians(yaw)
    bpy.context.view_layer.update()
    lo, hi = bbox(meshes)
    root.scale *= LENGTH / max(hi.x - lo.x, hi.y - lo.y)
    bpy.context.view_layer.update()
    lo, hi = bbox(meshes)
    root.location -= Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    bpy.context.view_layer.update()
    return meshes


def bbox(meshes):
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def drop_doubles(meshes):
    """Some sources stack two versions of a piece in the same place with the same material (the Abrams
    hull and turret come twice at different detail). Rendered together they z-fight into dark speckle;
    keep the more detailed one."""
    keep = {}
    for o in meshes:
        lo, hi = bbox([o])
        key = (o.data.materials[0].name if o.data.materials else "",
               tuple(round(c, 2) for c in lo), tuple(round(c, 2) for c in hi))
        best = keep.get(key)
        if best is None or len(o.data.polygons) > len(best.data.polygons):
            keep[key] = o
    out = []
    for o in meshes:
        if o in keep.values():
            out.append(o)
        else:
            bpy.data.objects.remove(o)
    return out


def clean_normals(meshes):
    """Drop the sources' custom split normals and let Blender derive them from the faces: some are broken
    (the Abrams side skirts render black facing the sun) and the game recomputes normals anyway."""
    for o in meshes:
        attr = o.data.attributes.get("custom_normal")
        if attr is not None:
            o.data.attributes.remove(attr)


def repaint(meshes):
    """Desert tan over the source colours (TINT of it): their brightness keeps panel lines, dirt and dark
    parts, a noise adds uneven fading and grime. Glass, tyres and lights keep their own colour."""
    done = set()
    for o in meshes:
        for mat in o.data.materials:
            if not mat or mat in done or not mat.use_nodes or any(k in mat.name.lower() for k in KEEP_COLOUR):
                continue
            done.add(mat)
            nt = mat.node_tree
            bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf is None:
                continue
            base = bsdf.inputs["Base Color"]
            if base.is_linked:
                src = base.links[0].from_socket
            else:
                rgb = nt.nodes.new("ShaderNodeRGB")
                rgb.outputs[0].default_value = base.default_value
                src = rgb.outputs[0]
            bw = nt.nodes.new("ShaderNodeRGBToBW")
            nt.links.new(src, bw.inputs[0])
            # The sources' paint averages about 0.3 brightness (sources.py tint): that maps to full tan,
            # darker parts stay darker, nothing goes past 1.15.
            lift = nt.nodes.new("ShaderNodeMapRange")
            lift.inputs["From Max"].default_value = 0.3
            lift.inputs["To Min"].default_value = 0.1
            lift.inputs["To Max"].default_value = 1.0
            lift.clamp = False
            cap = nt.nodes.new("ShaderNodeMath")
            cap.operation = "MINIMUM"
            cap.inputs[1].default_value = 1.15
            nt.links.new(bw.outputs[0], lift.inputs["Value"])
            noise = nt.nodes.new("ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = 6.0
            noise.inputs["Detail"].default_value = 8
            grime = nt.nodes.new("ShaderNodeMapRange")
            grime.inputs["To Min"].default_value = 0.72
            grime.inputs["To Max"].default_value = 1.08
            nt.links.new(noise.outputs["Fac"], grime.inputs["Value"])
            shade = nt.nodes.new("ShaderNodeMath")
            shade.operation = "MULTIPLY"
            nt.links.new(lift.outputs["Result"], cap.inputs[0])
            nt.links.new(cap.outputs[0], shade.inputs[0])
            nt.links.new(grime.outputs["Result"], shade.inputs[1])
            paint = nt.nodes.new("ShaderNodeMix")
            paint.data_type = "RGBA"
            paint.blend_type = "MULTIPLY"
            paint.inputs[0].default_value = 1.0
            paint.inputs[6].default_value = TAN
            nt.links.new(shade.outputs[0], paint.inputs[7])
            blend = nt.nodes.new("ShaderNodeMix")
            blend.data_type = "RGBA"
            blend.inputs[0].default_value = TINT
            nt.links.new(src, blend.inputs[6])
            nt.links.new(paint.outputs[2], blend.inputs[7])
            nt.links.new(blend.outputs[2], base)
            bsdf.inputs["Metallic"].default_value = 0.0
            bsdf.inputs["Roughness"].default_value = 0.7


def sand_material():
    mat = bpy.data.materials.new("sand")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.95
    coord = nt.nodes.new("ShaderNodeTexCoord")
    big = nt.nodes.new("ShaderNodeTexNoise")
    big.inputs["Scale"].default_value = 0.08
    big.inputs["Detail"].default_value = 6
    fine = nt.nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 14.0
    fine.inputs["Detail"].default_value = 10
    for n in (big, fine):
        nt.links.new(coord.outputs["Object"], n.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.36, 0.27, 0.16, 1)
    ramp.color_ramp.elements[1].color = (0.74, 0.62, 0.43, 1)
    mix = nt.nodes.new("ShaderNodeMath")
    mix.operation = "MULTIPLY_ADD"
    mix.inputs[1].default_value = 0.6
    nt.links.new(fine.outputs["Fac"], mix.inputs[0])
    nt.links.new(big.outputs["Fac"], mix.inputs[2])
    nt.links.new(mix.outputs[0], ramp.inputs["Fac"])
    pebbles = nt.nodes.new("ShaderNodeTexVoronoi")
    pebbles.inputs["Scale"].default_value = 22.0
    nt.links.new(coord.outputs["Object"], pebbles.inputs["Vector"])
    stones = nt.nodes.new("ShaderNodeMapRange")
    stones.inputs["From Min"].default_value = 0.0
    stones.inputs["From Max"].default_value = 0.35
    stones.inputs["To Min"].default_value = 0.62
    nt.links.new(pebbles.outputs["Distance"], stones.inputs["Value"])
    tint = nt.nodes.new("ShaderNodeMix")
    tint.data_type = "RGBA"
    tint.blend_type = "MULTIPLY"
    tint.inputs[0].default_value = 1.0
    nt.links.new(ramp.outputs["Color"], tint.inputs[6])
    nt.links.new(stones.outputs["Result"], tint.inputs[7])
    nt.links.new(tint.outputs[2], bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.8
    height = nt.nodes.new("ShaderNodeMath")
    height.operation = "ADD"
    nt.links.new(fine.outputs["Fac"], height.inputs[0])
    nt.links.new(stones.outputs["Result"], height.inputs[1])
    nt.links.new(height.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def stage(size_hint):
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=size_hint * 60)
    ground = bpy.context.active_object
    ground.data.materials.append(sand_material())
    # Deep blue sky that pales toward the horizon, with soft cumulus, like the retail backdrops.
    world = bpy.data.worlds.new("sky")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Generated"], sep.inputs[0])
    grad = nt.nodes.new("ShaderNodeValToRGB")
    grad.color_ramp.elements[0].position = 0.0
    grad.color_ramp.elements[0].color = (0.62, 0.70, 0.80, 1)
    grad.color_ramp.elements[1].position = 0.35
    grad.color_ramp.elements[1].color = (0.06, 0.20, 0.55, 1)
    nt.links.new(sep.outputs["Z"], grad.inputs["Fac"])
    clouds = nt.nodes.new("ShaderNodeTexNoise")
    clouds.inputs["Scale"].default_value = 2.2
    clouds.inputs["Detail"].default_value = 8
    clouds.inputs["Roughness"].default_value = 0.62
    nt.links.new(coord.outputs["Generated"], clouds.inputs["Vector"])
    cover = nt.nodes.new("ShaderNodeMapRange")
    cover.inputs["From Min"].default_value = 0.52
    cover.inputs["From Max"].default_value = 0.72
    nt.links.new(clouds.outputs["Fac"], cover.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[7].default_value = (0.95, 0.95, 0.97, 1)
    nt.links.new(cover.outputs["Result"], mix.inputs[0])
    nt.links.new(grad.outputs["Color"], mix.inputs[6])
    bg = nt.nodes["Background"]
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(mix.outputs[2], bg.inputs["Color"])
    # Hard key sun from the front left, like the retail art; the sky fills the shadows.
    sun_data = bpy.data.lights.new("sun", "SUN")
    sun_data.energy = 5.0
    sun_data.angle = math.radians(1.5)
    sun_data.color = (1.0, 0.93, 0.82)
    sun = bpy.data.objects.new("sun", sun_data)
    scene.collection.objects.link(sun)
    return ground, sun


def aim(cam, lo, hi, yaw, pitch, lens, aspect, zoom):
    """Perspective camera from the front quarter, close enough that the hull fills the frame."""
    cam.data.lens = lens
    cam.data.sensor_fit = "HORIZONTAL"
    centre = Vector((0, 0, (hi.z - lo.z) * 0.42))
    radius = max((hi - lo).length / 2, 0.1)
    fov = 2 * math.atan(cam.data.sensor_width / (2 * lens))
    dist = radius / math.tan(fov / 2) * 0.70 / zoom
    yaw_r, pitch_r = math.radians(yaw), math.radians(pitch)
    cam.location = centre + dist * Vector((math.cos(pitch_r) * math.cos(yaw_r), -math.cos(pitch_r) * math.sin(yaw_r),
                                           math.sin(pitch_r)))
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_start = dist * 0.02
    cam.data.clip_end = dist * 200


def light(sun, cam_yaw):
    """Sun high over the camera's right shoulder: the front and the near side are lit, the shadow falls
    behind the vehicle to the right, as in the retail art."""
    yaw, elev = math.radians(cam_yaw - 55), math.radians(48)
    towards = Vector((math.cos(elev) * math.cos(yaw), -math.cos(elev) * math.sin(yaw), math.sin(elev)))
    sun.rotation_euler = (-towards).to_track_quat("-Z", "Y").to_euler()


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("glb_dir")
    p.add_argument("out_dir")
    p.add_argument("--units", default=",".join(UNITS))
    p.add_argument("--samples", type=int, default=64)
    p.add_argument("--preview", action="store_true", help="small fast renders at four yaws, to set UNITS yaw")
    p.add_argument("--yaws", default="0,90,180,270")
    a = p.parse_args(argv)
    os.makedirs(a.out_dir, exist_ok=True)
    for unit in a.units.split(","):
        cameo, yaw, zoom, hidden = UNITS[unit]
        clear()
        meshes = load(os.path.join(a.glb_dir, f"{unit}.glb"), yaw, hidden)
        meshes = drop_doubles(meshes)
        clean_normals(meshes)
        repaint(meshes)
        lo, hi = bbox(meshes)
        _, sun = stage((hi - lo).length)
        scene = bpy.context.scene
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = 8 if a.preview else a.samples
        scene.cycles.use_denoising = True
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
        scene.view_settings.exposure = -0.7
        cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
        scene.collection.objects.link(cam)
        scene.camera = cam
        if a.preview:
            scene.render.resolution_x, scene.render.resolution_y = 320, 256
            for y in (int(v) for v in a.yaws.split(",")):
                aim(cam, lo, hi, y + 38, 20, 35, 1.25, 0.8)
                light(sun, y + 38)
                scene.render.filepath = os.path.join(a.out_dir, f"preview_{unit}_{y}.png")
                bpy.ops.render.render(write_still=True)
            continue
        for shot, ((w, h), cyaw, cpitch, lens) in SHOTS.items():
            scene.render.resolution_x, scene.render.resolution_y = w, h
            aim(cam, lo, hi, cyaw, cpitch, lens, w / h, zoom)
            light(sun, cyaw)
            raw = os.path.join(a.out_dir, f"{cameo}_{shot}_raw.png")
            scene.render.filepath = raw
            bpy.ops.render.render(write_still=True)
            frame.finish(raw, os.path.join(a.out_dir, f"{cameo}{'_L' if shot == 'portrait' else ''}"),
                         (120, 96) if shot == "button" else (216, 178))


if __name__ == "__main__":
    main()
