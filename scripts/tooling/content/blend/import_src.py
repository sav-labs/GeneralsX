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
import time

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
    # Objects that are not part of the vehicle (a loose prop beside it, a whip antenna far taller than the
    # vehicle) go before it is measured and scaled.
    if spec.get("exclude"):
        for o in list(objs):
            mats = " ".join(m.name for m in o.data.materials if m)
            if re.search(spec["exclude"], f"{o.name} {mats}", re.I):
                objs.remove(o)
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
    if spec.get("weld"):
        # Sources exported as loose triangles (every face its own island) fall apart under decimation and
        # split into thousands of single faces: weld coincident vertices first (UVs live on the corners,
        # so they survive).
        for o in objs:
            bm = bmesh.new()
            bm.from_mesh(o.data)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=spec["weld"])
            bm.to_mesh(o.data)
            bm.free()
            o.data.update()
    return objs


def bounds(objs):
    pts = [v.co for o in objs for v in o.data.vertices]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def pieces(objs, split):
    """Split the objects whose names match `split` into loose parts (wheel sets are usually one object);
    keep the rest whole. Every piece remembers its object and material names for the rules."""
    out = []
    for o in objs:
        name, mats = o.name, [m.name if m else "" for m in o.data.materials]
        result = [o]
        if split and re.search(split, f"{name} {' '.join(mats)}", re.I):
            bpy.ops.object.select_all(action="DESELECT")
            o.select_set(True)
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.mesh.separate(type="LOOSE")
            bpy.ops.object.mode_set(mode="OBJECT")
            result = list(bpy.context.selected_objects)
        for p in result:
            p["src"] = name
            p["mat"] = ",".join(mats)
            out.append(p)
    return out


def dedupe(parts):
    """Drop pieces that exactly duplicate another (same material, faces, position and size): some sources
    stack copies of their meshes, which only costs triangles and flickers."""
    seen, out = set(), []
    for p in parts:
        lo, hi = bounds([p])
        key = (p["mat"], len(p.data.polygons), tuple(round(c, 3) for c in lo), tuple(round(c, 3) for c in hi))
        if key in seen:
            bpy.data.objects.remove(p)
            continue
        seen.add(key)
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


def find_wheels(groups, cfg):
    """Sources whose wheels are not separate objects: unsorted hull pieces low on the vehicle, out at its
    sides and smaller than a wheel can be become wheel candidates (WHEEL#); number_wheels keeps the round
    ones and what sits inside them and returns the rest to the hull."""
    hull = groups.get(("ROOTTRANSFORM", "HULL", "body"), [])
    if not hull:
        return groups
    lo = Vector([min(p["centre"][i] - p["extent"][i] / 2 for p in hull) for i in range(3)])
    hi = Vector([max(p["centre"][i] + p["extent"][i] / 2 for p in hull) for i in range(3)])
    height, half = hi.z - lo.z, (hi.y - lo.y) / 2
    keep, wheels = [], []
    for p in hull:
        c, e = p["centre"], p["extent"]
        if (c[2] - lo.z < cfg.get("zmax", 0.3) * height and abs(c[1]) > cfg.get("ymin", 0.45) * half
                and max(e[0], e[2]) < cfg.get("size", 0.6) * height):
            wheels.append(p)
        else:
            keep.append(p)
    groups[("ROOTTRANSFORM", "HULL", "body")] = keep
    groups.setdefault(("WHEEL#", "WHEEL#", "body"), []).extend(wheels)
    return groups


def truck_tires(groups):
    """W3DTruckDraw names: the front and rear wheel on each side become TIRE01 (left front), TIRE02 (right
    front), TIRE03 (left rear) and TIRE04 (right rear); wheels in between keep their WHEEL names."""
    out = dict(groups)
    for side, front, rear in (("L", "TIRE01", "TIRE03"), ("R", "TIRE02", "TIRE04")):
        names = sorted(b for b, g, k in groups if re.match(rf"WHEEL{side}\d\d$", b))
        for old, new in ((names[0], front), (names[-1], rear)) if names else ():
            for key in [k for k in groups if k[0] == old]:
                out[(new, new, key[2])] = out.pop(key)
    return out


def number_wheels(groups):
    """Split '#' bones into one bone per wheel, numbered front to back on each side. The largest pieces
    (tyres, discs) seed the wheels; every smaller piece (bolts, hubs) joins the wheel whose axle it is
    nearest to, within that wheel's radius."""
    out = {}
    for (bone, group, kind), ps in groups.items():
        if not bone.endswith("#"):
            out[(bone, group, kind)] = ps
            continue
        stem = bone[:-1]
        wheels = []  # [centre, radius, pieces]
        rest = []
        for p in sorted(ps, key=lambda p: -max(p["extent"][0], p["extent"][2])):
            c = Vector(p["centre"])
            ex, ez = p["extent"][0], p["extent"][2]
            r = max(ex, ez) / 2
            same = [w for w in wheels if (w[0].y > 0) == (c.y > 0) and abs(w[0].y - c.y) < 2.0]
            best = min(same, key=lambda w: (w[0] - c).xz.length, default=None)
            if best and (best[0] - c).xz.length + r <= best[1] * 1.05:
                best[2].append(p)
            elif r > 0.8 and abs(ex - ez) < 0.2 * max(ex, ez):
                wheels.append([c, r, [p]])
            else:
                rest.append(p)  # track links, guards: they stay on the hull
        if rest:
            out.setdefault(("ROOTTRANSFORM", "HULL", "body"), []).extend(rest)
        for side, tag in ((1, "L"), (-1, "R")):
            mine = sorted([w for w in wheels if (w[0].y > 0) == (side > 0)], key=lambda w: -w[0].x)
            for i, w in enumerate(mine):
                name = f"{stem}{tag}{i + 1:02d}" if stem == "WHEEL" else f"{stem}{tag}" + (f"{i + 1:02d}" if i else "")
                out[(name, name, kind)] = w[2]
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


def cull_small(objs, size):
    """Drop loose islands smaller than `size` (bolt heads, rivets, handles): they cost triangles at game
    distance, and with a high-poly bake their look is already in the atlas."""
    for o in objs:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        seen, drop = set(), []
        for f in bm.faces:
            if f.index in seen:
                continue
            island, stack = [], [f]
            seen.add(f.index)
            while stack:
                g = stack.pop()
                island.append(g)
                for e in g.edges:
                    for h in e.link_faces:
                        if h.index not in seen:
                            seen.add(h.index)
                            stack.append(h)
            pts = [v.co for g in island for v in g.verts]
            ext = max(max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3))
            if ext < size:
                drop += island
        if drop and len(drop) < len(bm.faces):
            bmesh.ops.delete(bm, geom=drop, context="FACES")
            bm.to_mesh(o.data)
        bm.free()


def planar(objs, angle):
    """Merge coplanar faces (within `angle` degrees) without moving any vertex: flat armour plates become
    a few large polygons and the silhouette stays exact, so the later collapse has less to crush."""
    for o in objs:
        mod = o.modifiers.new("planar", "DECIMATE")
        mod.decimate_type = "DISSOLVE"
        mod.angle_limit = math.radians(angle)
        mod.delimit = {"MATERIAL", "SEAM"}
        tri = o.modifiers.new("tri", "TRIANGULATE")
        tri.quad_method = "BEAUTY"
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.ops.object.modifier_apply(modifier=tri.name)


def decimate(objs, budget, weights=None):
    """Collapse objs to about `budget` triangles. weights (object -> factor) keep more of the objects
    that read as round or thin at game distance (wheels, guns), which crumple first."""
    tris = [sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs]
    w = [(weights or {}).get(o.name, 1.0) for o in objs]
    lo, hi = 0.0, 1.0
    if sum(tris) <= budget:
        return
    for _ in range(40):
        ratio = (lo + hi) / 2
        if sum(min(1.0, wi * ratio) * n for wi, n in zip(w, tris)) > budget:
            hi = ratio
        else:
            lo = ratio
    for o, wi in zip(objs, w):
        if wi * lo >= 1.0:
            continue
        mod = o.modifiers.new("dec", "DECIMATE")
        mod.ratio = wi * lo
        mod.use_collapse_triangulate = True
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=mod.name)


def pivot_of(obj, bone, how=None):
    """Turrets turn about their base, guns elevate about their breech end, everything else about its
    centre; a spec's "pivots" ({bone: base, rear or centre}) overrides."""
    lo, hi = bounds([obj])
    c = (lo + hi) / 2
    how = how or ("base" if bone.startswith("TURRET") and not bone.startswith("TURRETEL") else
                  "rear" if bone in ("BARREL", "TURRETEL") else "centre")
    if how == "base":
        return Vector((c.x, c.y, lo.z))
    if how == "rear":
        return Vector((lo.x, c.y, c.z))
    return c


def bake_source(objs, size, damaged, burns, name, spec):
    """Bake source colour (through each object's original UVs) plus our weathering into a new atlas UV."""
    for o in objs:
        me = o.data
        if me.uv_layers[0].name != "Atlas":
            me.uv_layers[0].active_render = True
        me.uv_layers.active = me.uv_layers["Atlas"]
    image = bpy.data.images.new(name, size, size, alpha=False)
    image.colorspace_settings.name = "sRGB"
    done = {}
    for o in objs:
        for slot, mat in enumerate(o.data.materials):
            if mat is None:
                continue
            if mat.name not in done:
                done[mat.name] = weathered(mat, image, damaged, burns, spec)
            o.data.materials[slot] = done[mat.name]
    # Bake flat-shaded: the weathering finds edges and relief from the shading normal, and the smoothed
    # normals of a decimated mesh would read whole faces as worn edges. The game keeps the smooth ones.
    smooth = {o.name: [p.use_smooth for p in o.data.polygons] for o in objs}
    for o in objs:
        o.data.polygons.foreach_set("use_smooth", [False] * len(o.data.polygons))
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
    for o in objs:
        o.data.polygons.foreach_set("use_smooth", smooth[o.name])
    # The atlas is now the only UV map the game sees.
    for o in objs:
        me = o.data
        for layer in [l for l in me.uv_layers if l.name != "Atlas"]:
            me.uv_layers.remove(layer)
    return px


def finish_of(mat, spec):
    """A face's finish: set on the material by mark_rims ("name|rubber") or by the spec's finish rules on
    the source material's name; paint otherwise."""
    if "|" in mat.name:
        return mat.name.split("|")[-1]
    for pattern, finish in spec.get("finishes", ()):
        if re.search(pattern, mat.name, re.I):
            return finish
    return "paint"


def source_luminance(src):
    """Mean linear luminance of a source material's base colour (texture or value)."""
    bsdf = next((n for n in (src.node_tree.nodes if src.use_nodes else []) if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        c = np.array(src.diffuse_color[:3])
    else:
        sock = bsdf.inputs["Base Color"]
        c = np.array(sock.default_value[:3])
        node = sock.links[0].from_node if sock.links else None
        while node is not None and node.type != "TEX_IMAGE" and node.inputs and any(i.links for i in node.inputs):
            node = next(i for i in node.inputs if i.links).links[0].from_node
        if node is not None and node.type == "TEX_IMAGE" and node.image and node.image.size[0]:
            img = node.image
            px = np.empty(img.size[0] * img.size[1] * img.channels, np.float32)
            img.pixels.foreach_get(px)
            rgb = px.reshape(-1, img.channels)[::7, :3]
            if img.colorspace_settings.name == "sRGB" and not img.is_float:
                rgb = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
            c = rgb.mean(axis=0)
    return max(1e-3, float(c @ np.array([0.2126, 0.7152, 0.0722])))


def weathered(src, image, damaged, burns, spec):
    """Copy of a source material whose emission is its base colour (texture or value), repainted by finish,
    under blend.kit's weathering: occlusion, chips, dust, streaks and, damaged, soot. Paint is repainted
    into the unit's colour with the source's shading and detail kept as luminance, each material
    normalised by its own mean so plates from different textures come out the same colour; rubber and
    metal keep their own colour."""
    finish = finish_of(src, spec)
    tint = spec.get("tint")
    lum = source_luminance(src)

    def base(nt):
        out = repaint(nt)
        baked = spec.get("_highpoly")
        if baked:
            relief, out = highpoly_relief(nt, baked, spec.get("relief", 0.9)), occluded(nt, out, baked)
        else:
            relief = source_relief(src, nt, spec.get("relief", 0.7))
        if relief is None:
            return out
        m = nt.nodes.new("ShaderNodeMix")
        m.data_type, m.blend_type = "RGBA", "MULTIPLY"
        m.inputs[0].default_value = 1.0
        nt.links.new(out, m.inputs[6])
        nt.links.new(relief, m.inputs[7])
        return m.outputs[2]

    def repaint(nt):
        colour = source_colour(src, nt)
        if spec.get("procedural") and finish in ("paint", "canvas") and tint:
            # The source's own texture is too coarse to keep: flat paint, with all detail from the
            # high-poly bake and the weathering.
            rgb = nt.nodes.new("ShaderNodeRGB")
            rgb.outputs[0].default_value = kit.srgb(tint[0] if finish == "paint" else spec.get("canvas", (128, 116, 84)))
            return rgb.outputs[0]

        def node(kind, **inputs):
            n = nt.nodes.new(kind)
            for k_, v in inputs.items():
                setattr(n, k_, v)
            return n

        def mixc(fac, a, b, blend="MIX"):
            m = node("ShaderNodeMix", data_type="RGBA", blend_type=blend)
            m.inputs[0].default_value = fac
            for idx, val in ((6, a), (7, b)):
                if isinstance(val, tuple):
                    m.inputs[idx].default_value = val
                else:
                    nt.links.new(val, m.inputs[idx])
            return m.outputs[2]
        if finish in ("paint", "canvas") and tint:
            # detail = 1 + (luminance / mean - 1) * contrast: the source's panel shading and grime at reduced
            # contrast (its repeating detail shimmers at a distance otherwise, and plates the source painted
            # lighter or darker than the rest stand out).
            bw = node("ShaderNodeRGBToBW")
            nt.links.new(colour, bw.inputs[0])
            m = node("ShaderNodeMath", operation="MULTIPLY_ADD")
            nt.links.new(bw.outputs[0], m.inputs[0])
            contrast = spec.get("contrast", 0.5)
            m.inputs[1].default_value = contrast / lum
            m.inputs[2].default_value = 1.0 - contrast
            # Clamped, so whole plates the source painted much lighter or darker do not survive the repaint.
            hi_ = node("ShaderNodeMath", operation="MINIMUM")
            nt.links.new(m.outputs[0], hi_.inputs[0])
            hi_.inputs[1].default_value = 1.12
            lo_ = node("ShaderNodeMath", operation="MAXIMUM")
            nt.links.new(hi_.outputs[0], lo_.inputs[0])
            lo_.inputs[1].default_value = 0.82
            g3 = node("ShaderNodeCombineColor")
            for i in range(3):
                nt.links.new(lo_.outputs[0], g3.inputs[i])
            target = tint[0] if finish == "paint" else spec.get("canvas", (128, 116, 84))
            paint = mixc(1.0, g3.outputs[0], kit.srgb(target), "MULTIPLY")
            return mixc(tint[2], colour, paint)
        if finish == "rubber":
            return mixc(0.95, colour, kit.srgb((26, 25, 24)))
        if finish == "metal":
            return mixc(0.6, colour, kit.srgb((104, 100, 92)))
        if finish == "glass":
            return mixc(0.7, colour, kit.srgb((28, 34, 38)))
        return colour
    paint = tint[0] if tint else (166, 148, 106)
    mat = kit._paint_material(f"{src.name}_w", finish if finish != "canvas" else "canvas", [paint], image, damaged,
                              "solid", burns, source=True, base_colour=base,
                              dust_scale=(0.3 if finish in ("rubber", "glass") else 1.0) * spec.get("weathering", 1.0),
                              wear_scale=spec.get("weathering", 1.0))
    nt = mat.node_tree
    if os.environ.get("GX_RAW"):
        em = next(n for n in nt.nodes if n.type == "EMISSION")
        nt.links.new(source_colour(src, nt), em.inputs["Color"])
    # The bake writes into the active image node: make sure that is the atlas, not the source texture.
    tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE" and n.image == image)
    nt.nodes.active = tex
    mat["finish"] = finish
    return mat


def atlas_image(nt, image):
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = image
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "Atlas"
    nt.links.new(uvn.outputs[0], tex.inputs["Vector"])
    return tex


def highpoly_relief(nt, baked, strength):
    """Relief from the object-space normals baked off the high-poly source."""
    tex = atlas_image(nt, baked["normal"])
    unpack = nt.nodes.new("ShaderNodeVectorMath")
    unpack.operation = "MULTIPLY_ADD"
    nt.links.new(tex.outputs["Color"], unpack.inputs[0])
    unpack.inputs[1].default_value = (2.0, 2.0, 2.0)
    unpack.inputs[2].default_value = (-1.0, -1.0, -1.0)
    return relief_from(nt, unpack.outputs[0], strength)


def occluded(nt, colour, baked):
    """Colour darkened by the occlusion baked off the high-poly source (panel gaps, bolt rings, the
    shadowed sides of fittings), eased so open plates stay at full colour."""
    tex = atlas_image(nt, baked["ao"])
    ramp = nt.nodes.new("ShaderNodeMapRange")
    nt.links.new(tex.outputs["Color"], ramp.inputs["Value"])
    ramp.inputs["From Min"].default_value, ramp.inputs["From Max"].default_value = 0.2, 0.85
    ramp.inputs["To Min"].default_value, ramp.inputs["To Max"].default_value = 0.45, 1.0
    grey = nt.nodes.new("ShaderNodeCombineColor")
    for i in range(3):
        nt.links.new(ramp.outputs[0], grey.inputs[i])
    m = nt.nodes.new("ShaderNodeMix")
    m.data_type, m.blend_type = "RGBA", "MULTIPLY"
    m.inputs[0].default_value = 1.0
    nt.links.new(colour, m.inputs[6])
    nt.links.new(grey.outputs[0], m.inputs[7])
    return m.outputs[2]


def bake_highpoly(low, high, size, extrusion):
    """Object-space normals and occlusion of the full-resolution source pieces (high), baked through the
    decimated meshes' atlas UVs (low). Both are joined into temporary objects for the selected-to-active
    bake and removed afterwards; the low meshes themselves are untouched."""
    def merged(objs, name):
        copies = []
        for o in objs:
            c = o.copy()
            c.data = o.data.copy()
            bpy.context.scene.collection.objects.link(c)
            copies.append(c)
        bpy.ops.object.select_all(action="DESELECT")
        for c in copies:
            c.select_set(True)
        bpy.context.view_layer.objects.active = copies[0]
        if len(copies) > 1:
            bpy.ops.object.join()
        out = bpy.context.view_layer.objects.active
        out.name = name
        return out
    target = merged(low, "bake_low")
    target.data.uv_layers.active = target.data.uv_layers["Atlas"]
    source = merged(high, "bake_high")
    out = {}
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    for kind, samples in (("normal", 1), ("ao", 64)):
        img = bpy.data.images.new(f"hp_{kind}", size, size, alpha=False, float_buffer=True)
        img.colorspace_settings.name = "Non-Color"
        mat = bpy.data.materials.new(f"hp_{kind}")
        mat.use_nodes = True
        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = img
        mat.node_tree.nodes.active = node
        target.data.materials.clear()
        target.data.materials.append(mat)
        scene.cycles.samples = samples
        bpy.ops.object.select_all(action="DESELECT")
        source.select_set(True)
        target.select_set(True)
        bpy.context.view_layer.objects.active = target
        kwargs = dict(normal_space="OBJECT") if kind == "normal" else {}
        bpy.ops.object.bake(type="NORMAL" if kind == "normal" else "AO", use_selected_to_active=True,
                            cage_extrusion=extrusion, max_ray_distance=extrusion * 2.5, margin=6, use_clear=True,
                            **kwargs)
        out[kind] = img
    for o in (target, source, *high):
        bpy.data.objects.remove(o)
    return out


def source_relief(src, nt, strength):
    """Relief of the source's normal map, lit into the colour: 1 + strength x (N_map . L - N . L) under a
    light from above, clamped, as a grey socket; None when the source has no normal map. The game has no
    normal maps, so the bolts, weld seams and plate edges the source only painted into its normal map
    would be lost from the atlas otherwise."""
    bsdf = next((n for n in (src.node_tree.nodes if src.use_nodes else []) if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None or not bsdf.inputs["Normal"].links:
        return None
    nmap = bsdf.inputs["Normal"].links[0].from_node
    if nmap.type != "NORMAL_MAP" or not nmap.inputs["Color"].links:
        return None
    tex_src = nmap.inputs["Color"].links[0].from_node
    if tex_src.type != "TEX_IMAGE" or not tex_src.image:
        return None
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = tex_src.image
    tex.image.colorspace_settings.name = "Non-Color"
    uv_name = ""
    for o in bpy.context.scene.objects:
        if o.type == "MESH" and o.data.uv_layers and o.data.uv_layers[0].name != "Atlas":
            uv_name = o.data.uv_layers[0].name
            break
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = uv_name
    nt.links.new(uvn.outputs[0], tex.inputs["Vector"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.uv_map = uv_name
    nt.links.new(tex.outputs["Color"], nm.inputs["Color"])
    return relief_from(nt, nm.outputs[0], strength)


def relief_from(nt, normal, strength):
    """Grey socket 1 + strength x (normal . L - N . L), clamped: relief of a detailed normal lit into the
    colour against the flat-shaded face it lies on."""
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    light = nt.nodes.new("ShaderNodeCombineXYZ")
    for i, v in enumerate((0.35, 0.3, 0.89)):
        light.inputs[i].default_value = v
    dots = []
    for sock in (normal, geo.outputs["Normal"]):
        d = nt.nodes.new("ShaderNodeVectorMath")
        d.operation = "DOT_PRODUCT"
        nt.links.new(sock, d.inputs[0])
        nt.links.new(light.outputs[0], d.inputs[1])
        dots.append(d.outputs["Value"])
    diff = nt.nodes.new("ShaderNodeMath")
    diff.operation = "SUBTRACT"
    nt.links.new(dots[0], diff.inputs[0])
    nt.links.new(dots[1], diff.inputs[1])
    ma = nt.nodes.new("ShaderNodeMath")
    ma.operation = "MULTIPLY_ADD"
    nt.links.new(diff.outputs[0], ma.inputs[0])
    ma.inputs[1].default_value = strength
    ma.inputs[2].default_value = 1.0
    cl = nt.nodes.new("ShaderNodeClamp")
    nt.links.new(ma.outputs[0], cl.inputs["Value"])
    cl.inputs["Min"].default_value, cl.inputs["Max"].default_value = 0.65, 1.3
    grey = nt.nodes.new("ShaderNodeCombineColor")
    for i in range(3):
        nt.links.new(cl.outputs[0], grey.inputs[i])
    return grey.outputs[0]


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


def shadow_shell(objs, name, budget=300):
    """Convex hull of a bone's meshes, pulled 3% inside them: the stencil shadow caster for that bone."""
    bm = bmesh.new()
    for o in objs:
        for v in o.data.vertices:
            bm.verts.new(v.co)
    hull = bmesh.ops.convex_hull(bm, input=bm.verts)
    loose = {g for g in hull["geom_interior"] + hull["geom_unused"] if isinstance(g, bmesh.types.BMVert)}
    bmesh.ops.delete(bm, geom=list(loose), context="VERTS")
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


def in_box(c, box):
    x0, x1, y0, y1, z0, z1 = box
    return x0 <= c[0] <= x1 and y0 <= c[1] <= y1 and z0 <= c[2] <= z1


def mark_seams(parts, boxes, width=0.25):
    """Dark seams where separate plates meet (side skirts): a "seam" point attribute rising to 1 within
    `width` of both ends (along x) of every piece whose centre lies in one of the boxes."""
    for p in parts:
        if not any(in_box(p["centre"], b) for b in boxes):
            continue
        xs = [v.co.x for v in p.data.vertices]
        x0, x1 = min(xs), max(xs)
        w = [max(0.0, 1.0 - min(x - x0, x1 - x) / width) for x in xs]
        p.data.attributes.new("seam", "FLOAT", "POINT").data.foreach_set("value", w)


def battle_damage(groups, damage, step):
    """The damaged model's geometry: pieces in the "drop" boxes are torn off, pieces in the "bend" boxes
    ((box, degrees)) hang outward from their top edge."""
    for key, ps in groups.items():
        keep = []
        for p in ps:
            c = p["centre"]
            if any(in_box(c, b) for b in damage.get("drop", ())):
                step(f"torn off {p['src']} at {tuple(round(v, 1) for v in c)}")
                bpy.data.objects.remove(p)
                continue
            for box, deg in damage.get("bend", ()):
                if in_box(c, box):
                    # One hinge per box, along its top edge: sources built from loose faces would scatter
                    # if every face turned about its own top.
                    hinge = Vector((c[0], (box[2] + box[3]) / 2, box[5]))
                    rot = Matrix.Rotation(math.radians(deg if c[1] > 0 else -deg), 4, "X")
                    p.data.transform(Matrix.Translation(hinge) @ rot @ Matrix.Translation(-hinge))
                    step(f"bent {p['src']} at {tuple(round(v, 1) for v in c)}")
                    break
            keep.append(p)
        ps[:] = keep


def mark_rims(obj, rims):
    """Wheels: faces out at the rim (beyond ratio x radius from the axle) get their own finish, rubber
    tyres on road wheels, bare metal on sprocket teeth, through a "<material>|<finish>" copy."""
    for prefix, (finish, ratio) in rims.items():
        if not obj["bone"].startswith(prefix):
            continue
        lo, hi = bounds([obj])
        c = (lo + hi) / 2
        r = max(hi.x - lo.x, hi.z - lo.z) / 2
        me = obj.data
        copies = {}
        for poly in me.polygons:
            pc = poly.center
            if math.hypot(pc.x - c.x, pc.z - c.z) < ratio * r:
                continue
            src = me.materials[poly.material_index]
            if src is None:
                continue
            if src.name not in copies:
                m = bpy.data.materials.get(f"{src.name}|{finish}") or src.copy()
                m.name = f"{src.name}|{finish}"
                if m.name not in [x.name for x in me.materials if x]:
                    me.materials.append(m)
                copies[src.name] = [x.name for x in me.materials if x].index(m.name)
            poly.material_index = copies[src.name]


def track_path(circles, samples=12):
    """Inner face of a track band round the wheels [(x, z, r)]: the convex hull of the circles, from
    the sprocket over the top run to the idler and back along the road wheels' bottoms."""
    pts = []
    for x, z, r in circles:
        for i in range(samples):
            a = 2 * math.pi * i / samples
            pts.append((x + r * math.cos(a), z + r * math.sin(a)))
    pts = sorted(set((round(x, 4), round(z, 4)) for x, z in pts))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    # Long straight runs get intermediate points so the band bends smoothly where it leaves a wheel.
    out = []
    for i, a in enumerate(hull):
        b = hull[(i + 1) % len(hull)]
        n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 1.5))
        out += [(a[0] + (b[0] - a[0]) * t / n, a[1] + (b[1] - a[1]) * t / n) for t in range(n)]
    return out


def tracks(k, joined, strips, spec, step):
    """Replace the source's static track (its pieces were sorted onto the TRACK bone) with blend.kit's
    scrolling band, as wide as the source track and as thick as the gap under the road wheels."""
    cfg = spec.get("track", {})
    for side, tag in ((1, "L"), (-1, "R")):
        mine = [p for p in strips if (p["centre"][1] > 0) == (side > 0)]
        if not mine:
            continue
        lo, hi = bounds(mine)
        circles = []
        for (bone, group, kind), obj in joined.items():
            if kind != "body" or not re.match(rf"(WHEEL{tag}\d\d|SPROCKET{tag}|IDLER{tag})$", bone):
                continue
            blo, bhi = bounds([obj])
            r = max(bhi.x - blo.x, bhi.z - blo.z) / 2 * (cfg.get("sprocket", 0.9) if bone.startswith("SPROCKET") else 1.0)
            circles.append(((blo.x + bhi.x) / 2, (blo.z + bhi.z) / 2, r))
        thickness = max(0.25, min(z - r for _, z, r in circles) - lo.z)
        part, length = k.track_loop(f"TREADS{tag}", "ROOTTRANSFORM", track_path(circles), lo.y, hi.y,
                                    thickness=thickness, links=cfg.get("links", 3.0))
        part.obj["bone"], part.obj["group"], part.obj["kind"] = "ROOTTRANSFORM", f"TREADS{tag}", "tread"
        joined[("ROOTTRANSFORM", f"TREADS{tag}", "tread")] = part.obj
        step(f"track {tag}: {len(circles)} wheels, width {hi.y - lo.y:.2f}, thickness {thickness:.2f}, length {length:.0f}")
    for p in strips:
        bpy.data.objects.remove(p)


def split_finishes(joined, spec):
    """After the bake: each object's rubber, metal and canvas faces become their own mesh (own W3D
    material, so its own specular), named after the object's group with a suffix (WHEELL01_RUB): the
    engine finds wheels by their exact group name, so the extra mesh simply turns with the wheel bone."""
    for (bone, group, kind), obj in list(joined.items()):
        if kind != "body":
            continue
        me = obj.data
        finishes = [finish_of_baked(m) for m in me.materials]
        used = {finishes[p.material_index] for p in me.polygons}
        present = sorted(used - {"paint"})
        if "paint" not in used and present:
            # Nothing painted left (a wheel that is all tyre): the object itself takes the first finish and
            # keeps its group name, which the engine looks the wheel up by.
            main = present.pop(0)
            del joined[(bone, group, kind)]
            obj["kind"] = main
            joined[(bone, group, main)] = obj
            keep = main
        else:
            keep = "paint"
        for finish in present:
            part = obj.copy()
            part.data = me.copy()
            bpy.context.scene.collection.objects.link(part)
            bm = bmesh.new()
            bm.from_mesh(part.data)
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if finishes[f.material_index] != finish], context="FACES")
            bm.to_mesh(part.data)
            bm.free()
            sub = f"{group[:11]}_{finish[:3].upper()}"
            part.name = sub
            part["bone"], part["group"], part["kind"] = bone, sub, finish
            joined[(bone, sub, finish)] = part
        if present:
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if finishes[f.material_index] != keep], context="FACES")
            bm.to_mesh(me)
            bm.free()


def finish_of_baked(mat):
    return mat.get("finish", "paint") if mat else "paint"


def surface(objs, x, y):
    """Height of the topmost surface of objs above (x, y), or None."""
    from mathutils.bvhtree import BVHTree
    best = None
    for o in objs:
        me = o.data
        tree = BVHTree.FromPolygons([v.co for v in me.vertices], [p.vertices for p in me.polygons])
        hit = tree.ray_cast(Vector((x, y, 1000.0)), Vector((0, 0, -1)))
        if hit[0] is not None and (best is None or hit[0].z > best):
            best = hit[0].z
    return best


# Damage points in the vehicle's own frame: (u from the back 0 to the front 1, v across -1 to 1); the
# engine end (spec "engine": rear or front) sets where most of the smoke, fire and soot gather.
FX = [("SMOKE01", 0.0, -0.3), ("SMOKE02", 0.08, 0.35), ("SMOKE03", 0.5, 0.25),
      ("FIRE01", 0.02, 0.0), ("FIRE02", -0.03, -0.55), ("FIRE03", 0.55, -0.3)]
BURNS = [(0.02, 0.0, 0.14), (0.5, 0.65, 0.08), (0.62, -0.75, 0.08), (0.35, 0.85, 0.07), (0.8, 0.2, 0.06),
         (0.55, -0.3, 0.05)]


def damage_points(objs, spec):
    """Smoke and fire bones and burn marks on the top surface, for specs that do not place their own."""
    lo, hi = bounds(objs)
    length, half = hi.x - lo.x, (hi.y - lo.y) / 2
    front = spec.get("engine", "rear") == "front"

    def at(u, v):
        u = 0.12 + u if not front else 0.88 - u
        x, y = lo.x + length * min(0.98, max(0.02, u)), (lo.y + hi.y) / 2 + v * half * 0.9
        z = surface(objs, x, y)
        return (x, y, (z if z is not None else hi.z * 0.6) + 0.1)
    fx = {name: at(u, v) for name, u, v in FX}
    burns = [(at(u, v), r * length) for u, v, r in BURNS]
    return fx, burns


def build(path, spec, name, size, damaged=False):
    """Returns (Kit with bones, {(bone, group, kind): object}, body pixels)."""
    t0 = time.time()

    def step(msg):
        print(f"  [{name}] {msg} {time.time() - t0:.0f}s", flush=True)
    objs = load(path, spec)
    step(f"loaded {len(objs)} objects")
    parts = dedupe(pieces(objs, spec.get("split")))
    step(f"{len(parts)} pieces")
    groups = classify(parts, spec)
    if damaged and spec.get("damage"):
        battle_damage(groups, spec["damage"], step)
    if spec.get("find_wheels") is not None:
        groups = find_wheels(groups, spec["find_wheels"])
    groups = number_wheels(groups)
    if spec.get("tires"):
        groups = truck_tires(groups)
    step(f"{len(groups)} groups: {' '.join(sorted(b for b, g, k in groups if b != 'ROOTTRANSFORM'))}")
    mark_seams([p for ps in groups.values() for p in ps], spec.get("seams", ()))
    k = kit.Kit.__new__(kit.Kit)
    k.name, k.parts, k.cutters, k._n, k.damaged = name, [], [], 0, None
    k.bones = [("ROOTTRANSFORM", None, (0.0, 0.0, 0.0))]
    # Texel density per piece, as blend.kit does: small and thin pieces get less of the atlas.
    pid = 0
    for ps in groups.values():
        for p in ps:
            pid += 1
            mid = sorted(p["extent"])[1]
            n = len(p.data.polygons)
            p.data.attributes.new("dens", "FLOAT", "FACE").data.foreach_set("value", [min(1.0, max(0.1, mid / 1.5))] * n)
            p.data.attributes.new("pid", "INT", "FACE").data.foreach_set("value", [pid] * n)
    joined, strips = {}, []
    for (bone, group, kind), ps in sorted(groups.items()):
        if bone == "DROP":
            for p in ps:
                bpy.data.objects.remove(p)
            continue
        if bone == "TRACK":
            strips += ps
            continue
        obj = join(ps, f"{bone}_{group}")
        obj["bone"], obj["group"], obj["kind"] = bone, group, kind
        joined[(bone, group, kind)] = obj
    step("joined")
    high = []
    if spec.get("highpoly"):
        for (bone, group, kind), obj in joined.items():
            c = obj.copy()
            c.data = obj.data.copy()
            bpy.context.scene.collection.objects.link(c)
            c["bone"] = bone
            high.append(c)
    body_objs = [o for (b, g, kd), o in joined.items()]
    if spec.get("cull"):
        cull_small(body_objs, spec["cull"])
    if spec.get("planar"):
        planar(body_objs, spec["planar"])
        step(f"planar {sum(len(o.data.polygons) for o in body_objs)} triangles")
    decimate(list(joined.values()), spec.get("tris", 12000),
             {o.name: 3.0 for (b, g, kd), o in joined.items() if re.match(r"WHEEL|TIRE|SPROCKET|IDLER|BARREL", b)})
    step("decimated")
    for obj in joined.values():
        mark_rims(obj, spec.get("rims", {}))
    if strips:
        tracks(k, joined, strips, spec, step)
    droop = (spec.get("damage") or {}).get("droop") if damaged else None
    parents = spec.get("parents", {})
    for (bone, group, kind), obj in joined.items():
        if bone != "ROOTTRANSFORM" and bone not in [b for b, _, _ in k.bones]:
            parent = parents.get(bone, parents.get(re.sub(r"[LR]\d\d$", "#", bone), "ROOTTRANSFORM"))
            k.bones.append((bone, parent, tuple(pivot_of(obj, bone, spec.get("pivots", {}).get(bone)))))
    if droop:
        # A knocked-out tank's gun sags on its trunnions.
        pivot = Vector(next(p for b, _, p in k.bones if b == "BARREL"))
        rot = Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(droop), 4, "Y") @ Matrix.Translation(-pivot)
        for obj in [o for (bone, g, kd), o in joined.items() if bone == "BARREL"] + [h for h in high if h["bone"] == "BARREL"]:
            obj.data.transform(rot)
    # Points the damage effects use (smoke and fire), on both models; the retail Draw modules start their
    # really-damaged smoke on a random SMOKE* bone.
    body = [o for (b, g, kd), o in joined.items() if kd == "body"]
    fx, burns = damage_points(body, spec)
    for bone, p in spec.get("fx", fx).items():
        k.bones.append((bone, "ROOTTRANSFORM", p))
    # Muzzle points for the weapon effects, at the front (or ("PARENT", "rear")) end of the bone they ride on.
    for bone, parent in spec.get("muzzles", {}).items():
        parent, end = parent if isinstance(parent, tuple) else (parent, "front")
        ends = [o for (b, g, kd), o in joined.items() if b == parent and kd == "body"]
        if ends:
            lo, hi = bounds(ends)
            k.bones.append((bone, parent, (hi.x if end == "front" else lo.x, (lo.y + hi.y) / 2, (lo.z + hi.z) / 2)))
    # Parents before children.
    ordered, pending = k.bones[:1], k.bones[1:]
    while pending:
        ready = [b for b in pending if b[1] in [o[0] for o in ordered]] or pending[:1]
        ordered += ready
        pending = [b for b in pending if b not in ready]
    k.bones = ordered
    for bone in ("ROOTTRANSFORM", "TURRET", "BARREL"):
        hits = [o for (b, g, kd), o in joined.items() if b == bone and kd == "body"]
        if hits:
            shell = shadow_shell(hits, f"SHADOW{bone[:4]}")
            joined[(bone, f"SHADOW{bone[:4]}", "shadow")] = shell
    k.burns = (list(spec.get("burns", burns)) + [(c, r, "hit") for c, r in spec.get("hits", ())]) if damaged else None
    visible = [o for (b, g, kd), o in joined.items() if kd == "body"]
    for o in visible:
        # Only the source's first UV map is baked from; joined sources can carry up to Blender's limit of
        # eight, which leaves no room for the atlas.
        for layer in list(o.data.uv_layers)[1:]:
            o.data.uv_layers.remove(layer)
        o.data.uv_layers.new(name="Atlas")
        o.data.uv_layers.active = o.data.uv_layers["Atlas"]
    step("shadows")
    kit.unwrap(visible)
    step("unwrapped")
    spec.pop("_highpoly", None)
    if high:
        spec["_highpoly"] = bake_highpoly(visible, high, size, spec["highpoly"])
        step("high-poly normals and occlusion baked")
    px = bake_source(visible, size, damaged, k.burns, f"{name}_body", spec)
    split_finishes(joined, spec)
    # Custom normals for to_w3d.
    for (b, g, kd), o in joined.items():
        if kd == "shadow":
            continue
        me = o.data
        nrm = np.zeros(len(me.loops) * 3)
        me.corner_normals.foreach_get("vector", nrm)
        me.attributes.new("nrm", "FLOAT_VECTOR", "CORNER").data.foreach_set("vector", nrm)
    bpy.context.scene["bones"] = repr(k.bones)
    return k, joined, px
