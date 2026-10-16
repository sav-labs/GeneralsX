"""Preview renders of the detailed units: stills and a short animation of their moving parts.

GeneralsX @feature Claude 16/10/2026 Opens the .blend that build_hd.py saved, shades each mesh with its
baked texture under a sun and sky like the game's, and renders a turntable in which the turret
slews, the gun recoils, wheels and tracks turn, the weapon station and thermal viewer scan, hatches
open and antennas sway. Usage: render_hd.py <unit.blend> <texture dir> <out dir> [--frames 72]
[--size 960x540] [--samples 24] [--stills]
"""

import argparse
import math
import os
import sys

import bpy
from mathutils import Euler, Vector


def material(name, image_path, rough, team=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(image_path, check_existing=True)
    tex.interpolation = "Cubic"
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Specular IOR Level"].default_value = 0.3
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    colour = tex.outputs["Color"]
    if team:
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = 1.0
        nt.links.new(colour, mix.inputs[6])
        mix.inputs[7].default_value = team
        colour = mix.outputs[2]
    nt.links.new(colour, bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return mat, tex


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("blend")
    p.add_argument("tex_dir")
    p.add_argument("out_dir")
    p.add_argument("--frames", type=int, default=72)
    p.add_argument("--size", default="960x540")
    p.add_argument("--samples", type=int, default=24)
    p.add_argument("--stills", action="store_true")
    p.add_argument("--cameo", action="store_true")
    p.add_argument("--stem", default="gxmbt2")
    a = p.parse_args(argv)
    bpy.ops.wm.open_mainfile(filepath=a.blend)
    scene = bpy.context.scene
    damaged = a.blend.endswith("_D.blend")
    d = "d" if damaged else ""
    bones = eval(scene["bones"])  # written by kit.finalize: [(name, parent, pivot)]
    os.makedirs(a.out_dir, exist_ok=True)

    body, _ = material("body", os.path.join(a.tex_dir, f"{a.stem}_body{d}.png"), 0.62)
    team, _ = material("team", os.path.join(a.tex_dir, f"{a.stem}_team{d}.png"), 0.55, team=(0.05, 0.16, 0.75, 1))
    tread, tread_tex = material("tread", os.path.join(a.tex_dir, f"{a.stem}_tread.png"), 0.8)
    mapping = tread.node_tree.nodes.new("ShaderNodeMapping")
    uv = tread.node_tree.nodes.new("ShaderNodeTexCoord")
    tread.node_tree.links.new(uv.outputs["UV"], mapping.inputs["Vector"])
    tread.node_tree.links.new(mapping.outputs["Vector"], tread_tex.inputs["Vector"])

    # Bone empties so moving parts can be keyed.
    empties = {}
    for name, parent, pivot in bones:
        e = bpy.data.objects.new(name, None)
        scene.collection.objects.link(e)
        empties[name] = (e, Vector(pivot))
    for name, parent, pivot in bones:
        if parent:
            e, pv = empties[name]
            pe, ppv = empties[parent]
            e.parent = pe
            e.location = pv - ppv
        else:
            empties[name][0].location = (0, 0, 0)
    own = {}
    for obj in list(scene.objects):
        if obj.type != "MESH":
            continue
        kind = obj.get("kind")
        if kind == "shadow":
            obj.hide_render = True
            kind = "body"
        obj.data.materials.clear()
        if obj.get("tex"):
            # Models built by the older pipeline carry their own texture per mesh.
            key = (obj["tex"], kind)
            if key not in own:
                own[key] = material(obj["tex"], os.path.join(a.tex_dir, obj["tex"]), 0.6,
                                    team=(0.05, 0.16, 0.75, 1) if kind == "team" else None)[0]
            obj.data.materials.append(own[key])
        else:
            obj.data.materials.append({"body": body, "team": team, "tread": tread}[kind])
        for poly in obj.data.polygons:
            poly.material_index = 0
        e, pv = empties[obj["bone"]]
        obj.parent = e
        obj.matrix_parent_inverse = e.matrix_world.inverted()
        # Use the exported normals.
        nrm = obj.data.attributes.get("nrm")
        if nrm:
            obj.data.normals_split_custom_set([tuple(v.vector) for v in nrm.data])
    bpy.context.view_layer.update()
    for obj in scene.objects:
        if obj.type == "MESH":
            obj.matrix_parent_inverse = obj.parent.matrix_world.inverted()

    # Ground, sun and sky.
    bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, 0))
    ground = bpy.context.object
    gm = bpy.data.materials.new("ground")
    gm.use_nodes = True
    g = gm.node_tree.nodes["Principled BSDF"]
    g.inputs["Base Color"].default_value = (0.11, 0.09, 0.065, 1)
    g.inputs["Roughness"].default_value = 1.0
    ground.data.materials.append(gm)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 2.4
    sun.data.angle = math.radians(4)
    sun.rotation_euler = Euler((math.radians(48), 0, math.radians(-150)))
    scene.collection.objects.link(sun)
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    sky = world.node_tree.nodes.new("ShaderNodeTexSky")
    try:
        sky.sky_type = "MULTIPLE_SCATTERING"
    except TypeError:
        sky.sky_type = "NISHITA"
    sky.sun_disc = False
    sky.sun_elevation = math.radians(42)
    sky.sun_rotation = math.radians(-150 + 90)
    bg = world.node_tree.nodes["Background"]
    world.node_tree.links.new(sky.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.22
    scene.world = world

    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 52
    scene.collection.objects.link(cam)
    scene.camera = cam
    pivot = bpy.data.objects.new("pivot", None)
    scene.collection.objects.link(pivot)
    pivot.location = (6.5, 0, 4.0)
    cam.parent = pivot
    dist = 80
    pitch = math.radians(32)
    cam.location = (dist * math.cos(pitch), 0, dist * math.sin(pitch))
    cam.rotation_euler = Euler((math.pi / 2 - pitch, 0, math.pi / 2))
    # Rim light from behind the unit, turning with the camera, so silhouettes and relief read.
    rim = bpy.data.objects.new("rim", bpy.data.lights.new("rim", "AREA"))
    rim.data.energy = 60000
    rim.data.size = 30
    rim.data.color = (0.85, 0.9, 1.0)
    rim.parent = pivot
    rim.location = (-60, 25, 38)
    track = rim.constraints.new("TRACK_TO")
    track.target = pivot
    scene.collection.objects.link(rim)

    w, h = (int(v) for v in a.size.split("x"))
    scene.render.resolution_x, scene.render.resolution_y = w, h
    scene.render.engine = "CYCLES"
    scene.cycles.samples = a.samples
    scene.cycles.use_denoising = True
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.7

    def key(name, frame, loc=None, rot=None):
        if name not in empties:
            return
        e, _ = empties[name]
        if loc is not None:
            base = e.get("rest", None)
            if base is None:
                e["rest"] = tuple(e.location)
                base = e["rest"]
            e.location = Vector(base) + Vector(loc)
            e.keyframe_insert("location", frame=frame)
        if rot is not None:
            e.rotation_euler = Euler(rot)
            e.keyframe_insert("rotation_euler", frame=frame)

    n = a.frames
    scene.frame_start, scene.frame_end = 1, n
    if a.cameo:
        # Command bar art: the unit alone on a transparent background, framed later by build_content.py.
        ground.hide_render = True
        scene.render.film_transparent = True
        model = os.path.splitext(os.path.basename(a.blend))[0]
        for name, (w, h), yaw, pitch_deg in (("button", (480, 384), 35, 24), ("portrait", (640, 528), 30, 20)):
            scene.render.resolution_x, scene.render.resolution_y = w, h
            pitch = math.radians(pitch_deg)
            cam.location = (dist * math.cos(pitch), 0, dist * math.sin(pitch))
            cam.rotation_euler = Euler((math.pi / 2 - pitch, 0, math.pi / 2))
            pivot.rotation_euler = Euler((0, 0, math.radians(yaw)))
            scene.frame_set(1)
            scene.render.filepath = os.path.join(a.out_dir, f"{model}_{name}.png")
            bpy.ops.render.render(write_still=True)
        return
    if a.stills:
        # Hero shot: a low perspective view from the front quarter.
        cam.data.type = "PERSP"
        cam.data.lens = 50
        hp = math.radians(14)
        cam.location = (62 * math.cos(hp), 0, 62 * math.sin(hp))
        cam.rotation_euler = Euler((math.pi / 2 - hp, 0, math.pi / 2))
        pivot.location = (3.0, 0, 4.5)
        pivot.rotation_euler = Euler((0, 0, math.radians(32)))
        scene.frame_set(1)
        scene.render.filepath = os.path.join(a.out_dir, "hero.png")
        bpy.ops.render.render(write_still=True)
        cam.data.type = "ORTHO"
        cam.location = (dist * math.cos(pitch), 0, dist * math.sin(pitch))
        cam.rotation_euler = Euler((math.pi / 2 - pitch, 0, math.pi / 2))
        pivot.location = (6.5, 0, 4.0)
        for yaw in (35, 145, 215, 325):
            pivot.rotation_euler = Euler((0, 0, math.radians(yaw)))
            scene.frame_set(1)
            scene.render.filepath = os.path.join(a.out_dir, f"still_{yaw}.png")
            bpy.ops.render.render(write_still=True)
        return
    for f in range(1, n + 1):
        t = (f - 1) / n
        pivot.rotation_euler = Euler((0, 0, math.radians(35 + 360 * t)))
        pivot.keyframe_insert("rotation_euler", frame=f)
        key("TURRET", f, rot=(0, 0, math.radians(35 * math.sin(2 * math.pi * t))))
        # Two shots: barrel recoils 1.5 units and runs back out.
        rec = 0.0
        for shot in (0.3, 0.75):
            dt = t - shot
            if 0 <= dt < 0.08:
                rec = -1.5 * (1 - dt / 0.08) ** 2
        key("BARREL", f, loc=(rec, 0, 0))
        spin = -2 * math.pi * 3 * t
        for name in empties:
            if name.startswith(("WHEEL", "SPROCKET", "IDLER")):
                r = 1.05 if name.startswith("WHEEL") else 1.1
                key(name, f, rot=(0, -spin * 1.05 / r, 0))
        key("RWS", f, rot=(0, 0, math.radians(60 * math.sin(2 * math.pi * 2 * t))))
        key("CITV", f, rot=(0, 0, math.radians(-90 * math.sin(2 * math.pi * t))))
        key("HATCH01", f, rot=(0, math.radians(-100 * min(1, max(0, 4 * t - 0.4))), 0))
        key("HATCH02", f, rot=(0, math.radians(-95 * min(1, max(0, 4 * t - 1.2))), 0))
        for i, name in enumerate(("ANTENNA01", "ANTENNA02")):
            key(name, f, rot=(math.radians(4 * math.sin(2 * math.pi * 5 * t + i)), math.radians(6 * math.sin(2 * math.pi * 3 * t + i)), 0))
        mapping.inputs["Location"].default_value[0] = 3 * 30.0 / 3.0 * t * 0.35
        mapping.inputs["Location"].keyframe_insert("default_value", index=0, frame=f)
    for obj in scene.objects:
        if obj.animation_data and obj.animation_data.action:
            for fc in obj.animation_data.action.fcurves if hasattr(obj.animation_data.action, "fcurves") else []:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
    scene.render.filepath = os.path.join(a.out_dir, "f_####")
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
