"""Turn a third-party source model (.glb) into a game-ready detailed unit.

GeneralsX @feature Claude 16/10/2026 Imports the model, turns it to face +X and scales it to the unit's
game length, sorts its loose pieces onto bones by name or position (turret, barrel, wheels, hatches),
cuts it down to the triangle budget, lays everything out in one atlas and bakes the source colours
together with our ambient occlusion, dust and wear into it, adds low-poly shadow shells and exports W3D
through kit.to_w3d. Tracks can be replaced by blend.kit's scrolling track band. Each unit is described
by a spec in sources.py; the damaged model is the same mesh with a burnt and sooted bake.
"""

import math
import os
import re
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kit  # noqa: E402


def load(path, spec):
    """Import, apply transforms, orient, scale and seat the model on the ground. Returns mesh objects."""
    kit.reset()
    bpy.ops.import_scene.gltf(filepath=path)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in list(bpy.context.scene.objects):
        if o.type != "MESH":
            continue
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.make_single_user(object=True, obdata=True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for o in [o for o in bpy.context.scene.objects if o.type != "MESH"]:
        bpy.data.objects.remove(o)
    rot = Matrix.Rotation(math.radians(spec.get("yaw", 0.0)), 4, "Z")
    for o in objs:
        o.data.transform(rot)
    lo, hi = bounds(objs)
    scale = spec["length"] / (hi.x - lo.x)
    centre = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    m = Matrix.Scale(scale, 4) @ Matrix.Translation(-centre)
    for o in objs:
        o.data.transform(m)
        o.data.update()
    return objs


def bounds(objs):
    pts = [v.co for o in objs for v in o.data.vertices]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def pieces(objs):
    """Split every object into its loose parts, keeping object and material names for the rules."""
    out = []
    for o in objs:
        name, mats = o.name, [m.name if m else "" for m in o.data.materials]
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.separate(type="LOOSE")
        bpy.ops.object.mode_set(mode="OBJECT")
        for p in bpy.context.selected_objects:
            p["src"] = name
            p["mat"] = ",".join(mats)
            out.append(p)
    return out


def classify(parts, spec):
    """Assign each piece to (bone, group, kind) by the first matching rule: {"name": regex on object or
    material name, "box": (x0, x1, y0, y1, z0, z1) holding the piece's centre, "bone", "group", "kind"}.
    A bone ending in '#' is numbered per side by x (wheels): WHEEL# -> WHEELL01.., WHEELR01..."""
    out = {}
    for p in parts:
        lo, hi = bounds([p])
        c = (lo + hi) / 2
        key = ("ROOTTRANSFORM", "HULL", "body")
        for rule in spec["rules"]:
            if "name" in rule and not re.search(rule["name"], f"{p['src']} {p['mat']}", re.I):
                continue
            if "box" in rule:
                x0, x1, y0, y1, z0, z1 = rule["box"]
                if not (x0 <= c.x <= x1 and y0 <= c.y <= y1 and z0 <= c.z <= z1):
                    continue
            if "maxsize" in rule and max(hi - lo) > rule["maxsize"]:
                continue
            key = (rule.get("bone", "ROOTTRANSFORM"), rule.get("group", rule.get("bone", "HULL")), rule.get("kind", "body"))
            break
        p["centre"] = tuple(c)
        p["extent"] = tuple(hi - lo)
        out.setdefault(key, []).append(p)
    return out


def number_wheels(groups):
    """Split '#' bones into one bone per piece cluster, numbered front to back on each side."""
    out = {}
    for (bone, group, kind), ps in groups.items():
        if not bone.endswith("#"):
            out[(bone, group, kind)] = ps
            continue
        stem = bone[:-1]
        clusters = []
        for p in sorted(ps, key=lambda p: p["centre"][0]):
            c = Vector(p["centre"])
            for cl in clusters:
                if (Vector(cl[0]["centre"]) - c).xz.length < 0.6 * max(p["extent"][0], p["extent"][2]) and \
                        (cl[0]["centre"][1] > 0) == (c.y > 0):
                    cl.append(p)
                    break
            else:
                clusters.append([p])
        for side, tag in ((1, "L"), (-1, "R")):
            mine = sorted([cl for cl in clusters if (cl[0]["centre"][1] > 0) == (side > 0)],
                          key=lambda cl: -cl[0]["centre"][0])
            for i, cl in enumerate(mine):
                name = f"{stem}{tag}{i + 1:02d}"
                out[(name, name, kind)] = cl
    return out


def join(ps, name):
    bpy.ops.object.select_all(action="DESELECT")
    for p in ps:
        p.select_set(True)
    bpy.context.view_layer.objects.active = ps[0]
    if len(ps) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    return obj


def decimate(objs, budget):
    total = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs)
    ratio = min(1.0, budget / max(1, total))
    if ratio >= 1.0:
        return
    for o in objs:
        mod = o.modifiers.new("dec", "DECIMATE")
        mod.ratio = ratio
        mod.use_collapse_triangulate = True
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=mod.name)


def pivot_of(obj, bone):
    lo, hi = bounds([obj])
    c = (lo + hi) / 2
    if bone == "TURRET":
        return Vector((c.x, c.y, lo.z))
    if bone == "BARREL":
        return Vector((lo.x, c.y, c.z))
    return c


def bake_source(objs, size, damaged, burns, name):
    """Bake source colour (through each object's original UVs) plus our weathering into a new atlas UV."""
    for o in objs:
        me = o.data
        if me.uv_layers[0].name != "Atlas":
            me.uv_layers[0].active_render = True
        me.uv_layers.active = me.uv_layers["Atlas"]
    image = bpy.data.images.new(name, size, size, alpha=False)
    image.colorspace_settings.name = "sRGB"
    for o in objs:
        for slot, mat in enumerate(o.data.materials):
            if mat is None:
                continue
            o.data.materials[slot] = weathered(mat, image, damaged, burns)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 48
    scene.render.bake.margin = 6
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.bake(type="EMIT", margin=6, use_clear=True)
    px = np.array(image.pixels[:]).reshape(size, size, 4)
    # The atlas is now the only UV map the game sees.
    for o in objs:
        me = o.data
        for layer in [l for l in me.uv_layers if l.name != "Atlas"]:
            me.uv_layers.remove(layer)
    return px


def weathered(src, image, damaged, burns):
    """Copy of a source material whose emission is its base colour (texture or value) weathered by
    blend.kit's paint shader: the source colour stands in for the paint palette."""
    base = kit._paint_material(f"{src.name}_w", "paint", [(255, 255, 255)], image, damaged, "solid", burns)
    nt = base.node_tree
    em = next(n for n in nt.nodes if n.type == "EMISSION")
    weather = em.inputs["Color"].links[0].from_socket
    colour = source_colour(src, nt)
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    nt.links.new(colour, mul.inputs[6])
    nt.links.new(weather, mul.inputs[7])
    nt.links.new(mul.outputs[2], em.inputs["Color"])
    return base


def source_colour(src, nt):
    """The source material's base colour as a socket in nt: its texture (copied with its UV map) or value."""
    bsdf = next((n for n in (src.node_tree.nodes if src.use_nodes else []) if n.type == "BSDF_PRINCIPLED"), None)
    rgb = nt.nodes.new("ShaderNodeRGB")
    if bsdf is None:
        rgb.outputs[0].default_value = (*src.diffuse_color[:3], 1)
        return rgb.outputs[0]
    sock = bsdf.inputs["Base Color"]
    rgb.outputs[0].default_value = tuple(sock.default_value)
    if not sock.links:
        return rgb.outputs[0]
    node = sock.links[0].from_node
    while node.type != "TEX_IMAGE" and node.inputs and any(i.links for i in node.inputs):
        node = next(i for i in node.inputs if i.links).links[0].from_node
    if node.type != "TEX_IMAGE":
        return rgb.outputs[0]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = node.image
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = ""  # the active render UV: the source's own
    nt.links.new(uvn.outputs[0], tex.inputs["Vector"])
    for o in bpy.context.scene.objects:
        if o.type == "MESH" and o.data.uv_layers and o.data.uv_layers[0].name != "Atlas":
            uvn.uv_map = o.data.uv_layers[0].name
            break
    return tex.outputs["Color"]


def shadow_shell(obj, name, budget=300):
    """Convex hull of a bone's mesh, pulled 3% inside it: the stencil shadow caster for that bone."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    hull = bmesh.ops.convex_hull(bm, input=bm.verts)
    bmesh.ops.delete(bm, geom=[g for g in hull["geom_interior"] + hull["geom_unused"] if isinstance(g, bmesh.types.BMVert)],
                     context="VERTS")
    c = sum((v.co for v in bm.verts), Vector()) / max(1, len(bm.verts))
    for v in bm.verts:
        v.co = c + (v.co - c) * 0.97
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    shell = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(shell)
    decimate([shell], budget)
    return shell


def build(path, spec, name, size, damaged=False):
    """Returns (Kit with bones, {(bone, group, kind): object}, body pixels)."""
    objs = load(path, spec)
    groups = number_wheels(classify(pieces(objs), spec))
    k = kit.Kit.__new__(kit.Kit)
    k.name, k.parts, k.cutters = name, [], []
    k.bones = [("ROOTTRANSFORM", None, (0.0, 0.0, 0.0))]
    joined = {}
    for (bone, group, kind), ps in sorted(groups.items()):
        obj = join(ps, f"{bone}_{group}")
        obj["bone"], obj["group"], obj["kind"] = bone, group, kind
        joined[(bone, group, kind)] = obj
    decimate(list(joined.values()), spec.get("tris", 12000))
    parents = spec.get("parents", {})
    for (bone, group, kind), obj in joined.items():
        if bone != "ROOTTRANSFORM" and bone not in [b for b, _, _ in k.bones]:
            parent = parents.get(bone, parents.get(re.sub(r"[LR]\d\d$", "#", bone), "ROOTTRANSFORM"))
            k.bones.append((bone, parent, tuple(pivot_of(obj, bone))))
    for bone in ("ROOTTRANSFORM", "TURRET", "BARREL"):
        hits = [o for (b, g, kd), o in joined.items() if b == bone and kd == "body"]
        if hits:
            shell = shadow_shell(hits[0] if len(hits) == 1 else join(hits, bone), f"SHADOW{bone[:4]}")
            joined[(bone, f"SHADOW{bone[:4]}", "shadow")] = shell
    k.burns = spec.get("burns") if damaged else None
    visible = [o for (b, g, kd), o in joined.items() if kd != "shadow"]
    for o in visible:
        o.data.uv_layers.new(name="Atlas")
        o.data.uv_layers.active = o.data.uv_layers["Atlas"]
    kit.unwrap(visible)
    px = bake_source(visible, size, damaged, k.burns, f"{name}_body")
    # Custom normals for to_w3d.
    for o in visible:
        me = o.data
        nrm = np.zeros(len(me.loops) * 3)
        me.corner_normals.foreach_get("vector", nrm)
        me.attributes.new("nrm", "FLOAT_VECTOR", "CORNER").data.foreach_set("vector", nrm)
    bpy.context.scene["bones"] = repr(k.bones)
    return k, joined, px
