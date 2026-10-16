"""Blender-side modelling kit for detailed GeneralsX units.

GeneralsX @feature Claude 16/10/2026 Builds a unit from bevelled parts in Blender (bpy), lays every
painted part out in one texture atlas, bakes paint, ambient occlusion, worn edges, dust and soot into
that atlas with Cycles, and exports the result through w3d.py. Parts are grouped by bone and mesh
name, so moving pieces (wheels, hatches, sensors) get their own bones. Coordinates follow the engine:
+X forward, +Y left, +Z up, one unit per game distance unit.
"""

import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import w3d  # noqa: E402

# Finish of each kind of surface: base colour (sRGB 0-255), how much its edges wear, how much dust
# settles on it, and roughness for previews. "paint" takes the unit's own colours.
FINISHES = {
    "paint": ((176, 160, 118), 1.0, 1.0, 0.65),
    "metal": ((86, 86, 82), 0.6, 0.6, 0.45),
    "steel": ((122, 120, 114), 0.3, 0.4, 0.35),
    "rubber": ((34, 34, 33), 0.0, 1.2, 0.9),
    "dark": ((48, 50, 46), 0.4, 0.8, 0.7),
    "glass": ((22, 30, 34), 0.0, 0.2, 0.08),
    "lens": ((40, 70, 64), 0.0, 0.0, 0.05),
    "canvas": ((116, 108, 82), 0.0, 1.2, 0.95),
    "light": ((230, 226, 200), 0.0, 0.3, 0.1),
    "team": ((236, 236, 236), 0.7, 0.6, 0.6),
}


def srgb(c):
    """sRGB 0-255 -> linear 0-1 for Blender colour sockets."""
    out = []
    for v in c[:3]:
        v = v / 255.0
        out.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


class Part:
    def __init__(self, obj, bone, group, finish, damaged):
        self.obj = obj
        self.bone = bone
        self.group = group
        self.finish = finish
        self.damaged = damaged  # None: always; False: intact model only; True: damaged model only


class Kit:
    """Collects parts. bone/group/finish/damaged set the defaults for the parts that follow."""

    def __init__(self, name):
        reset()
        self.name = name
        self.parts = []
        self.bones = [("ROOTTRANSFORM", None, (0.0, 0.0, 0.0))]
        self.bone = "ROOTTRANSFORM"
        self.group = "HULL"
        self.finish = "paint"
        self.damaged = None
        self.cutters = []
        self._n = 0

    # --- bones -------------------------------------------------------------------------------
    def add_bone(self, name, parent, pivot):
        self.bones.append((name.upper(), parent.upper(), tuple(float(c) for c in pivot)))

    def bone_pivot(self, name):
        for bone, _, pivot in self.bones:
            if bone == name.upper():
                return Vector(pivot)
        raise KeyError(name)

    def at(self, bone=None, group=None, finish=None, damaged="keep"):
        """Context: kit.at(bone=..., group=...) then add parts."""
        if bone is not None:
            self.bone = bone.upper()
        if group is not None:
            self.group = group.upper()
        if finish is not None:
            self.finish = finish
        if damaged != "keep":
            self.damaged = damaged
        return self

    # --- object plumbing ---------------------------------------------------------------------
    def _object(self, bm, bevel, segments, angle, finish, smooth_all=False):
        self._n += 1
        mesh = bpy.data.meshes.new(f"p{self._n}")
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new(f"p{self._n}", mesh)
        bpy.context.scene.collection.objects.link(obj)
        for poly in mesh.polygons:
            poly.use_smooth = True
        if bevel > 0:
            mod = obj.modifiers.new("bevel", "BEVEL")
            mod.width = bevel
            mod.segments = segments
            mod.limit_method = "ANGLE"
            mod.angle_limit = math.radians(angle)
            mod.harden_normals = True
            mod.miter_outer = "MITER_ARC"
            mod.use_clamp_overlap = True
        if not smooth_all:
            obj.modifiers.new("smooth", "WEIGHTED_NORMAL").keep_sharp = True
            # Sharp edges where the bevel does not reach, so flat faces stay flat.
            bm2 = bmesh.new()
            bm2.from_mesh(mesh)
            for e in bm2.edges:
                if len(e.link_faces) == 2 and e.calc_face_angle(0) > math.radians(angle):
                    e.smooth = False
            bm2.to_mesh(mesh)
            bm2.free()
        part = Part(obj, self.bone, self.group, finish or self.finish, self.damaged)
        self.parts.append(part)
        return part

    # --- primitives --------------------------------------------------------------------------
    def box(self, p0, p1, bevel=0.12, segments=2, finish=None, angle=30):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        lo, hi = Vector(p0), Vector(p1)
        size = hi - lo
        centre = (hi + lo) / 2
        for v in bm.verts:
            v.co = Vector((v.co.x * size.x, v.co.y * size.y, v.co.z * size.z)) + centre
        smallest = min(abs(size.x), abs(size.y), abs(size.z))
        bevel = min(bevel, 0.45 * smallest)
        if smallest < 0.5 or max(abs(size.x), abs(size.y), abs(size.z)) < 1.0:
            segments = 1  # small parts: one chamfer is all that reads at game distance
        if smallest < 0.1:
            bevel = 0
        return self._object(bm, bevel, segments, angle, finish)

    def prism(self, profile, y0, y1, bevel=0.12, segments=2, finish=None, angle=30, axis="y"):
        """Extrude a side profile [(x, z)] from y0 to y1 (axis "y"), or a plan [(x, y)] from z0 to z1
        (axis "z"), or a front profile [(y, z)] from x0 to x1 (axis "x")."""
        bm = bmesh.new()

        def v3(a, b, c):
            if axis == "y":
                return (a, c, b)
            if axis == "z":
                return (a, b, c)
            return (c, a, b)

        ring0 = [bm.verts.new(v3(a, b, y0)) for a, b in profile]
        ring1 = [bm.verts.new(v3(a, b, y1)) for a, b in profile]
        bm.faces.new(ring0)
        bm.faces.new(list(reversed(ring1)))
        n = len(profile)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((ring0[i], ring0[j], ring1[j], ring1[i]))
        span = abs(y1 - y0)
        bevel = min(bevel, 0.45 * span)
        return self._object(bm, bevel, segments, angle, finish)

    def loft(self, bottom, top, bevel=0.12, segments=2, finish=None, angle=30):
        """Solid between two rings of (x, y, z) points with the same count (a turret, a cab)."""
        bm = bmesh.new()
        r0 = [bm.verts.new(p) for p in bottom]
        r1 = [bm.verts.new(p) for p in top]
        bm.faces.new(list(reversed(r0)))
        bm.faces.new(r1)
        n = len(bottom)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
        return self._object(bm, bevel, segments, angle, finish)

    def cyl(self, centre, axis, radius, length, sides=None, radius2=None, bevel=0.06, segments=2, finish=None,
            caps=True, angle=40):
        """Cylinder (or cone with radius2) centred on `centre` along axis "x", "y" or "z"."""
        if sides is None:
            sides = max(8, min(24, int(7 + max(radius, radius2 or 0) * 14)))
        if radius < 0.5:
            segments = 1
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=sides, radius1=radius,
                              radius2=radius if radius2 is None else radius2, depth=length)
        rot = {"x": Matrix.Rotation(math.radians(90), 4, "Y"), "y": Matrix.Rotation(math.radians(-90), 4, "X"),
               "z": Matrix.Identity(4)}[axis]
        bmesh.ops.transform(bm, matrix=Matrix.Translation(Vector(centre)) @ rot, verts=bm.verts)
        bevel = min(bevel, 0.4 * min(radius, length))
        if radius < 0.1 or length < 0.05:
            bevel = 0
        return self._object(bm, bevel, segments, angle, finish)

    def tube(self, points, radius, sides=8, finish=None, closed=False):
        """Bent rod through points (rails, handles, antenna bases)."""
        self._n += 1
        curve = bpy.data.curves.new(f"c{self._n}", "CURVE")
        curve.dimensions = "3D"
        curve.bevel_depth = radius
        curve.bevel_resolution = 1 if radius >= 0.08 else 0
        spline = curve.splines.new("POLY")
        spline.points.add(len(points) - 1)
        for p, q in zip(spline.points, points):
            p.co = (*q, 1.0)
        spline.use_cyclic_u = closed
        curve.use_fill_caps = True
        obj = bpy.data.objects.new(f"c{self._n}", curve)
        bpy.context.scene.collection.objects.link(obj)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
        bpy.data.objects.remove(obj)
        bm = bmesh.new()
        bm.from_mesh(mesh)
        return self._object(bm, 0, 1, 40, finish, smooth_all=True)

    def bolts(self, centres, axis, radius=0.12, height=0.08, finish=None):
        """Hex bolt heads with a small chamfer, so they catch light instead of reading as dots."""
        for c in centres:
            self.cyl(c, axis, radius, height, sides=6, bevel=0.025, segments=1, finish=finish, angle=20)

    def wheel(self, centre, radius, width, spokes=6, finish_tyre="rubber", holes=True, bolts=6, side=1, detail=True):
        """Road wheel along Y: rubber tyre, dished rim, hub and bolts on the face that points to `side`
        (+1 left, -1 right). detail=False is the hidden inner half of a dual wheel: tyre and disc only."""
        x, y, z = centre
        s = 1 if side > 0 else -1
        face = y + s * width / 2
        if not detail:
            self.cyl(centre, "y", radius, width, sides=20, bevel=0, finish=finish_tyre)
            return
        self.cyl(centre, "y", radius, width, sides=20, bevel=0.1, segments=1, finish=finish_tyre)
        self.cyl((x, face + s * 0.02, z), "y", radius * 0.8, 0.06, sides=20, bevel=0, finish="paint")
        self.cyl((x, face + s * 0.08, z), "y", radius * 0.36, 0.12, sides=12, radius2=radius * 0.3, bevel=0, finish="paint")
        self.cyl((x, face + s * 0.15, z), "y", radius * 0.13, 0.06, sides=8, bevel=0, finish="steel")
        for k in range(bolts):
            a = 2 * math.pi * k / bolts
            self.cyl((x + math.cos(a) * radius * 0.24, face + s * 0.14, z + math.sin(a) * radius * 0.24), "y",
                     0.05, 0.06, sides=6, bevel=0, finish="steel")
        if holes:
            for k in range(spokes):
                a = 2 * math.pi * (k + 0.5) / spokes
                self.cyl((x + math.cos(a) * radius * 0.56, face + s * 0.045, z + math.sin(a) * radius * 0.56), "y",
                         radius * 0.13, 0.02, sides=8, bevel=0, finish="dark", caps=True)

    def grille(self, x0, x1, y0, y1, z, slats, axis="x", depth=0.18, finish="dark", width=None):
        """Row of louvres on a deck: a dark well with slats across it."""
        self.box((x0, y0, z - depth), (x1, y1, z + 0.02), bevel=0.03, finish="dark")
        if axis == "x":
            pitch = (x1 - x0) / slats
            w = width or pitch * 0.45
            for k in range(slats):
                cx = x0 + pitch * (k + 0.5)
                self.box((cx - w / 2, y0 + 0.05, z - depth * 0.6), (cx + w / 2, y1 - 0.05, z + 0.05), bevel=0.02,
                         finish=finish)
        else:
            pitch = (y1 - y0) / slats
            w = width or pitch * 0.45
            for k in range(slats):
                cy = y0 + pitch * (k + 0.5)
                self.box((x0 + 0.05, cy - w / 2, z - depth * 0.6), (x1 - 0.05, cy + w / 2, z + 0.05), bevel=0.02,
                         finish=finish)

    # Track cross-section seen along the band: (across 0-1, height above the inner face as a fraction of
    # the thickness). End connectors stand proud at both edges and in the middle, rubber pads between.
    TRACK_PROFILE = [(0.0, 0.18), (0.0, 0.88), (0.06, 1.0), (0.13, 1.0), (0.16, 0.84), (0.41, 0.84), (0.44, 0.94),
                     (0.56, 0.94), (0.59, 0.84), (0.84, 0.84), (0.87, 1.0), (0.94, 1.0), (1.0, 0.88), (1.0, 0.18),
                     (0.94, 0.0), (0.06, 0.0)]

    def track_loop(self, group, bone, path, y0, y1, thickness=0.45, links=0.9, closed=True):
        """Closed track band around the running gear, extruded from TRACK_PROFILE along path [(x, z)] (the
        inner face, clockwise seen from the left). U runs along the band in game units / `links`, so
        W3DTankDraw can scroll it; the profile is the same all round, so scrolling never slides texture
        over relief. V: outer face 0.5-1, sides 0.4-0.5, inner face 0-0.4. An open band (closed=False, a
        thrown track) gets its ends capped. Returns (Part, length)."""
        pts = [Vector((x, 0, z)) for x, z in path]
        n = len(pts)
        normals = []
        for i in range(n):
            a = pts[i - 1] if closed or i > 0 else pts[i]
            c = pts[(i + 1) % n] if closed or i < n - 1 else pts[i]
            t = (c - a).normalized()
            normals.append(Vector((t.z, 0, -t.x)))
        area = sum(pts[i].x * pts[(i + 1) % n].z - pts[(i + 1) % n].x * pts[i].z for i in range(n))
        if area < 0:
            normals = [-v for v in normals]
        prof = self.TRACK_PROFILE
        m = len(prof)
        bm = bmesh.new()
        uv_layer = bm.loops.layers.uv.new("UVMap")
        rings = []
        for p, nrm in zip(pts, normals):
            ring = []
            for w, h in prof:
                q = p + nrm * (h * thickness)
                ring.append(bm.verts.new((q.x, y0 + (y1 - y0) * w, q.z)))
            rings.append(ring)
        dist = [0.0]
        for i in range(1, n + 1):
            dist.append(dist[-1] + (pts[i % n] - pts[i - 1]).length)
        length = dist[-1]
        for i in range(n if closed else n - 1):
            j = (i + 1) % n
            u0, u1 = dist[i] / links, dist[i + 1] / links
            for k in range(m):
                k2 = (k + 1) % m
                f = bm.faces.new((rings[i][k], rings[j][k], rings[j][k2], rings[i][k2]))
                (wa, ha), (wb, hb) = prof[k], prof[k2]

                def v_of(w, h, wa=wa, ha=ha, wb=wb, hb=hb):
                    if min(ha, hb) >= 0.8:
                        return 0.5 + 0.5 * w
                    if max(ha, hb) <= 0.05:
                        return 0.4 * w
                    return 0.4 + 0.1 * h
                va, vb = v_of(wa, ha), v_of(wb, hb)
                for loop, (uu, vv) in zip(f.loops, ((u0, va), (u1, va), (u1, vb), (u0, vb))):
                    loop[uv_layer].uv = (uu, vv)
        if not closed:
            for ring in (rings[0], rings[-1][::-1]):
                f = bm.faces.new(ring[::-1])
                for loop in f.loops:
                    loop[uv_layer].uv = (0.0, 0.45)
        # Hard corners across the profile, smooth along the band.
        bm.verts.index_update()
        for e in bm.edges:
            a, b = e.verts
            if a.index % m == b.index % m:  # runs along the band
                e.smooth = False
        self._n += 1
        mesh = bpy.data.meshes.new(f"t{self._n}")
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new(f"t{self._n}", mesh)
        bpy.context.scene.collection.objects.link(obj)
        for poly in mesh.polygons:
            poly.use_smooth = True
        part = Part(obj, bone.upper(), group.upper(), "tread", self.damaged)
        self.parts.append(part)
        return part, length

    def cut(self, part, centre, axis, radius, depth, sides=10, jag=0.25):
        """Punch a ragged hole through a part (battle damage): a boolean with a jagged cylinder."""
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=sides, radius1=radius, radius2=radius,
                              depth=depth)
        for k, v in enumerate(bm.verts):
            scale = 1.0 + jag * math.sin(k * 2.4 + radius * 7.0)
            v.co.x *= scale
            v.co.y *= scale
        rot = {"x": Matrix.Rotation(math.radians(90), 4, "Y"), "y": Matrix.Rotation(math.radians(-90), 4, "X"),
               "z": Matrix.Identity(4)}[axis]
        bmesh.ops.transform(bm, matrix=Matrix.Translation(Vector(centre)) @ rot, verts=bm.verts)
        self._n += 1
        mesh = bpy.data.meshes.new(f"cut{self._n}")
        bm.to_mesh(mesh)
        bm.free()
        cutter = bpy.data.objects.new(f"cut{self._n}", mesh)
        bpy.context.scene.collection.objects.link(cutter)
        cutter.hide_render = True
        self.cutters.append(cutter)
        mod = part.obj.modifiers.new("hole", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.object = cutter
        part.obj.modifiers.move(len(part.obj.modifiers) - 1, 0)

    def weld(self, points, radius=0.06):
        """Weld bead along a plate joint."""
        return self.tube(points, radius, finish="paint")


# --- baking ----------------------------------------------------------------------------------
def _paint_material(name, finish, palette, image, damaged, pattern, burns=None, source=False, base_colour=None,
                    dust_scale=1.0):
    """Shader whose emission is the finished albedo: paint (camouflage or solid with mottling), ambient
    occlusion, worn edges, dust from below, vertical streaks and, for the damaged model, soot.
    base_colour(node_tree) -> socket replaces the paint colour (a source model's own texture)."""
    base, wear, dust, rough = FINISHES[finish]
    dust *= dust_scale
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    N = nt.nodes.new
    L = nt.links.new

    def math_node(op, a=None, b=None, clamp=False):
        m = N("ShaderNodeMath")
        m.operation = op
        m.use_clamp = clamp
        for idx, val in ((0, a), (1, b)):
            if val is None:
                continue
            if isinstance(val, (int, float)):
                m.inputs[idx].default_value = val
            else:
                L(val, m.inputs[idx])
        return m.outputs[0]

    def mix(fac, a, b):
        m = N("ShaderNodeMix")
        m.data_type = "RGBA"
        m.blend_type = "MIX"
        if isinstance(fac, (int, float)):
            m.inputs[0].default_value = fac
        else:
            L(fac, m.inputs[0])
        for idx, val in ((6, a), (7, b)):
            if isinstance(val, tuple):
                m.inputs[idx].default_value = val
            else:
                L(val, m.inputs[idx])
        return m.outputs[2]

    def multiply(a, b):
        m = N("ShaderNodeMix")
        m.data_type = "RGBA"
        m.blend_type = "MULTIPLY"
        m.inputs[0].default_value = 1.0
        for idx, val in ((6, a), (7, b)):
            if isinstance(val, tuple):
                m.inputs[idx].default_value = val
            else:
                L(val, m.inputs[idx])
        return m.outputs[2]

    def noise(scale, detail=4.0, coords=None, stretch=None, w=0.0):
        n = N("ShaderNodeTexNoise")
        n.noise_dimensions = "4D"
        n.inputs["W"].default_value = w
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        if stretch is not None:
            sep = N("ShaderNodeVectorMath")
            sep.operation = "MULTIPLY"
            L(coords, sep.inputs[0])
            sep.inputs[1].default_value = stretch
            L(sep.outputs[0], n.inputs["Vector"])
        elif coords is not None:
            L(coords, n.inputs["Vector"])
        return n.outputs["Fac"]

    def ramp(fac, lo, hi):
        """Smooth step of fac between lo and hi."""
        m = N("ShaderNodeMapRange")
        m.interpolation_type = "SMOOTHSTEP"
        L(fac, m.inputs["Value"])
        m.inputs["From Min"].default_value = lo
        m.inputs["From Max"].default_value = hi
        return m.outputs["Result"]

    tc = N("ShaderNodeTexCoord")
    coords = tc.outputs["Object"]
    geo = N("ShaderNodeNewGeometry")

    if base_colour is not None:
        col = base_colour(nt)
    elif finish == "paint":
        colour = srgb(palette[0])
        if pattern == "camo" and len(palette) > 2:
            n1 = noise(0.07, 2.0, coords, w=1.3)
            n2 = noise(0.08, 2.0, coords, w=7.1)
            c2 = mix(ramp(n1, 0.53, 0.55), colour, srgb(palette[1]))
            col = mix(ramp(n2, 0.56, 0.58), c2, srgb(palette[2]))
        else:
            col = mix(ramp(noise(0.25, 3.0, coords, w=3.0), 0.3, 0.7), srgb(palette[0]),
                      srgb(tuple(int(c * 0.9) for c in palette[0])))
    else:
        col = srgb(base)
        col = mix(0.5, col, col)
    # Mottling (not over a source model's own painted texture, where it reads as camouflage).
    mott = math_node("ADD", math_node("MULTIPLY", noise(1.6, 6.0, coords, w=2.0), 0.3), 0.85)
    mott = math_node("MULTIPLY", mott, math_node("ADD", math_node("MULTIPLY", noise(0.05, 2.0, coords, w=8.0), 0.2), 0.9))
    gray = N("ShaderNodeCombineColor")
    for i in range(3):
        L(mott, gray.inputs[i])
    if not source:
        col = multiply(col, gray.outputs[0])
    if finish == "paint" and not source:
        col = mix(math_node("MULTIPLY", ramp(noise(0.12, 3.0, coords, w=21.0), 0.4, 0.75), 0.35), col,
                  multiply(col, (0.86, 0.92, 0.84, 1.0)))

    # Worn edges: where the bevelled normal departs from the face normal.
    bev = N("ShaderNodeBevel")
    bev.samples = 8
    bev.inputs["Radius"].default_value = 0.1
    dot = N("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    L(bev.outputs[0], dot.inputs[0])
    L(geo.outputs["Normal"], dot.inputs[1])
    edge = ramp(math_node("SUBTRACT", 1.0, dot.outputs["Value"]), 0.008, 0.05)
    chip = ramp(noise(3.0, 8.0, coords, w=5.0), 0.38, 0.62)
    edge = math_node("MULTIPLY", edge, chip)
    edge = math_node("MULTIPLY", edge, wear)
    lighter = multiply(col, (1.65, 1.6, 1.5, 1.0))
    col = mix(math_node("MULTIPLY", edge, 0.9), col, lighter)
    bare = ramp(math_node("MULTIPLY", edge, noise(6.0, 4.0, coords, w=9.0)), 0.32, 0.4)
    col = mix(bare, col, srgb((96, 94, 88)))

    # Paint chipped off in larger flakes along edges and where crews climb: a ring of dark primer, then
    # bare steel, some of it rusting.
    bev2 = N("ShaderNodeBevel")
    bev2.samples = 8
    bev2.inputs["Radius"].default_value = 0.3
    dot2 = N("ShaderNodeVectorMath")
    dot2.operation = "DOT_PRODUCT"
    L(bev2.outputs[0], dot2.inputs[0])
    L(geo.outputs["Normal"], dot2.inputs[1])
    wide = ramp(math_node("SUBTRACT", 1.0, dot2.outputs["Value"]), 0.004, 0.04)
    flakes = noise(1.1, 9.0, coords, w=31.0)
    flake = math_node("ADD", math_node("MULTIPLY", wide, 0.55), math_node("MULTIPLY", flakes, 0.75))
    flake = math_node("MULTIPLY", flake, min(1.0, wear * 1.2))
    primer = ramp(flake, 0.74, 0.76)
    steel = ramp(flake, 0.8, 0.82)
    col = mix(math_node("MULTIPLY", primer, 0.9), col, srgb((74, 70, 52)))
    rusty = ramp(noise(2.5, 6.0, coords, w=33.0), 0.45, 0.7)
    metal_col = mix(rusty, srgb((128, 126, 118)), srgb((112, 64, 34)))
    col = mix(steel, col, metal_col)

    # Per-part shade: neighbouring plates and boxes never match exactly.
    attr = N("ShaderNodeAttribute")
    attr.attribute_type = "GEOMETRY"
    attr.attribute_name = "pid"
    wn = N("ShaderNodeTexWhiteNoise")
    wn.noise_dimensions = "1D"
    L(attr.outputs["Fac"], wn.inputs["W"])
    tint = math_node("ADD", math_node("MULTIPLY", wn.outputs["Value"], 0.08 if source else 0.14), 0.96 if source else 0.93)
    g3 = N("ShaderNodeCombineColor")
    for i in range(3):
        L(tint, g3.inputs[i])
    col = multiply(col, g3.outputs[0])
    # Dark seams where separate plates meet (the "seam" point attribute, see import_src.mark_seams).
    sa = N("ShaderNodeAttribute")
    sa.attribute_type = "GEOMETRY"
    sa.attribute_name = "seam"
    col = mix(math_node("MULTIPLY", sa.outputs["Fac"], 0.7, clamp=True), col, srgb((30, 27, 22)))

    # Ambient occlusion.
    ao = N("ShaderNodeAmbientOcclusion")
    ao.samples = 24
    # A source model is far busier than our procedural ones: at 2.5 units nearly every face is occluded.
    ao.inputs["Distance"].default_value = 1.2 if source else 2.5
    occl = ao.outputs["AO"]
    shade = ramp(occl, 0.0, 1.0)
    shade = math_node("ADD", math_node("MULTIPLY", shade, 0.72), 0.28)
    ao2 = N("ShaderNodeAmbientOcclusion")
    ao2.samples = 16
    ao2.inputs["Distance"].default_value = 0.3 if source else 0.45
    shade = math_node("MULTIPLY", shade, math_node("ADD", math_node("MULTIPLY", ao2.outputs["AO"], 0.45), 0.55))
    g2 = N("ShaderNodeCombineColor")
    for i in range(3):
        L(shade, g2.inputs[i])
    col = multiply(col, g2.outputs[0])

    # Dust: low on the vehicle, in cavities and on upward faces, broken up by noise.
    sep = N("ShaderNodeSeparateXYZ")
    L(tc.outputs["Object"], sep.inputs[0])
    low = math_node("SUBTRACT", 1.0, ramp(sep.outputs["Z"], 0.5, 4.5 if source else 5.5))
    nz = N("ShaderNodeSeparateXYZ")
    L(geo.outputs["Normal"], nz.inputs[0])
    up = ramp(nz.outputs["Z"], 0.6, 1.0)
    cav = math_node("SUBTRACT", 1.0, occl)
    amount = math_node("ADD", math_node("MULTIPLY", low, 0.75), math_node("MULTIPLY", math_node("MULTIPLY", up, cav), 1.4))
    amount = math_node("MULTIPLY", amount, ramp(noise(3.0 if source else 0.9, 6.0, coords, w=4.0), 0.3, 0.75))
    amount = math_node("MULTIPLY", amount, dust * 1.1, clamp=True)
    col = mix(amount, col, srgb((128, 108, 78)))
    grime = math_node("MULTIPLY", math_node("MULTIPLY", cav, cav), (0.5 if source else 0.9) * min(1.0, dust), clamp=True)
    col = mix(grime, col, srgb((62, 52, 40)))

    # Dust lying in patches on upward faces.
    # Source models: no large patches (they read as winter camouflage), only fine dust in the low parts.
    patches = math_node("MULTIPLY", up, ramp(noise(2.5 if source else 0.18, 5.0, coords, w=15.0), 0.45, 0.65))
    if source:
        patches = math_node("MULTIPLY", patches, low)
    col = mix(math_node("MULTIPLY", patches, (0.4 if source else 0.7) * min(1.0, dust), clamp=True), col,
              srgb((176, 156, 120) if source else (198, 184, 150)))

    # Mud thrown up by the running gear on the lowest parts.
    low2 = math_node("SUBTRACT", 1.0, ramp(sep.outputs["Z"], 0.4, 3.6))
    mud = math_node("MULTIPLY", low2, ramp(noise(2.2 if source else 0.7, 6.0, coords, w=14.0), 0.35, 0.6))
    col = mix(math_node("MULTIPLY", mud, 1.0 * min(1.0, dust), clamp=True), col, srgb((92, 76, 56)))

    # Streaks running down vertical faces.
    vert = math_node("SUBTRACT", 1.0, ramp(math_node("ABSOLUTE", nz.outputs["Z"]), 0.2, 0.6))
    streak = ramp(noise(3.5 if source else 2.0, 2.0, coords, stretch=(1.0, 1.0, 0.05), w=6.0), 0.58, 0.72)
    streak = math_node("MULTIPLY", math_node("MULTIPLY", streak, vert), 0.85 * min(1.0, dust))
    col = mix(streak, col, srgb((70, 62, 50)))

    # Rust weeping from bolts and seams down vertical faces, oil and fuel stains on the engine deck.
    rust = ramp(noise(3.0, 3.0, coords, stretch=(1.0, 1.0, 0.08), w=17.0), 0.62, 0.74)
    rust = math_node("MULTIPLY", math_node("MULTIPLY", rust, vert), math_node("ADD", math_node("MULTIPLY", cav, 1.5), 0.25))
    col = mix(math_node("MULTIPLY", rust, 0.55 * min(1.0, wear), clamp=True), col, srgb((118, 70, 38)))
    rear = math_node("SUBTRACT", 1.0, ramp(sep.outputs["X"], -6.0, -2.0))
    oil = math_node("MULTIPLY", math_node("MULTIPLY", rear, up), ramp(noise(0.6, 5.0, coords, w=41.0), 0.55, 0.62))
    col = mix(math_node("MULTIPLY", oil, 0.75 * min(1.0, dust), clamp=True), col, srgb((38, 33, 26)))

    if damaged:
        # The whole vehicle is smoke-stained and about 45% darker; around each hit and fire (burns: [(centre,
        # radius)]) the paint is scorched dark brown, then soot black. Rust only on the ragged fringe.
        col = multiply(col, (0.55, 0.54, 0.52, 1.0))
        # Burns are ragged blobs, not rings: warp the position by a noise vector before measuring.
        nv = N("ShaderNodeTexNoise")
        nv.inputs["Scale"].default_value = 0.35
        nv.inputs["Detail"].default_value = 4.0
        L(coords, nv.inputs["Vector"])
        cen = N("ShaderNodeVectorMath")
        cen.operation = "SUBTRACT"
        L(nv.outputs["Color"], cen.inputs[0])
        cen.inputs[1].default_value = (0.5, 0.5, 0.5)
        amp = N("ShaderNodeVectorMath")
        amp.operation = "SCALE"
        L(cen.outputs[0], amp.inputs[0])
        amp.inputs["Scale"].default_value = 5.0
        wp = N("ShaderNodeVectorMath")
        wp.operation = "ADD"
        L(coords, wp.inputs[0])
        L(amp.outputs[0], wp.inputs[1])
        warped = wp.outputs[0]
        heat = None
        for centre, radius in burns or ():
            off = N("ShaderNodeVectorMath")
            off.operation = "SUBTRACT"
            L(warped, off.inputs[0])
            off.inputs[1].default_value = centre
            sq = N("ShaderNodeVectorMath")
            sq.operation = "MULTIPLY"
            L(off.outputs[0], sq.inputs[0])
            sq.inputs[1].default_value = (1.0 / radius, 1.0 / radius, 0.8 / radius)
            ln = N("ShaderNodeVectorMath")
            ln.operation = "LENGTH"
            L(sq.outputs[0], ln.inputs[0])
            h = math_node("SUBTRACT", 1.0, ln.outputs["Value"])
            heat = h if heat is None else math_node("MAXIMUM", heat, h)
        if heat is None:
            heat = noise(0.22, 5.0, coords, w=11.0)
        heat = math_node("ADD", heat, math_node("MULTIPLY", math_node("SUBTRACT", noise(1.8, 6.0, coords, w=12.0), 0.5),
                                                0.5))
        # Rust on the fringe of each burn, broken up so it never closes into a ring.
        fringe = math_node("MULTIPLY", ramp(heat, 0.0, 0.05), math_node("SUBTRACT", 1.0, ramp(heat, 0.08, 0.14)))
        fringe = math_node("MULTIPLY", fringe, ramp(noise(4.0, 6.0, coords, w=13.0), 0.5, 0.65))
        col = mix(math_node("MULTIPLY", fringe, 0.6, clamp=True), col, srgb((84, 50, 30)))
        cr = N("ShaderNodeValToRGB")
        L(heat, cr.inputs["Fac"])
        el = cr.color_ramp.elements
        # The transparent end has the scorch colour too, so the fade is only in alpha (no light rim).
        el[0].position, el[0].color = 0.0, (*srgb((62, 50, 38))[:3], 0.0)
        el[1].position, el[1].color = 0.82, srgb((11, 10, 9))
        for pos, c in ((0.07, (62, 50, 38)), (0.16, (44, 36, 29)), (0.3, (30, 26, 22)), (0.5, (19, 17, 15))):
            e = el.new(pos)
            e.color = srgb(c)
        el[0].alpha = 0.0
        for e in list(el)[1:]:
            e.alpha = 1.0
        col = mix(cr.outputs["Alpha"], col, cr.outputs["Color"])
        soot = ramp(noise(1.2, 5.0, coords, w=19.0), 0.45, 0.62)
        col = mix(math_node("MULTIPLY", math_node("MULTIPLY", soot, up), 0.55, clamp=True), col, srgb((20, 18, 16)))

    # Relief baked into the albedo (the game has no normal maps): cast and rolled steel pitting and small
    # dents, lit from the upper left like the game's sun.
    height = math_node("ADD", math_node("MULTIPLY", noise(9.0, 6.0, coords, w=43.0), 0.6),
                       math_node("MULTIPLY", noise(1.2, 3.0, coords, w=44.0), 0.4))
    if damaged:
        height = math_node("ADD", height, math_node("MULTIPLY", noise(0.8, 4.0, coords, w=45.0), 1.2))
    bump = N("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35 if finish in ("paint", "metal", "steel", "team") else 0.15
    bump.inputs["Distance"].default_value = 0.05
    L(height, bump.inputs["Height"])
    light = (-0.45, 0.35, 0.82)
    lit = []
    for nrm in (bump.outputs["Normal"], geo.outputs["Normal"]):
        d = N("ShaderNodeVectorMath")
        d.operation = "DOT_PRODUCT"
        L(nrm, d.inputs[0])
        d.inputs[1].default_value = light
        lit.append(d.outputs["Value"])
    relief = math_node("ADD", math_node("MULTIPLY", math_node("SUBTRACT", lit[0], lit[1]), 1.6), 1.0)
    g4 = N("ShaderNodeCombineColor")
    for i in range(3):
        L(relief, g4.inputs[i])
    col = multiply(col, g4.outputs[0])

    em = N("ShaderNodeEmission")
    L(col, em.inputs["Color"])
    out = N("ShaderNodeOutputMaterial")
    L(em.outputs[0], out.inputs["Surface"])
    tex = N("ShaderNodeTexImage")
    tex.image = image
    nt.nodes.active = tex
    mat["rough"] = rough
    return mat


def _join(objs, name):
    """Apply modifiers and join objects into one mesh object."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    for obj in objs:
        mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), preserve_all_data_layers=True,
                                               depsgraph=depsgraph)
        mesh.transform(obj.matrix_world)
        bm.from_mesh(mesh)
        bpy.data.meshes.remove(mesh)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _mesh_with_normals(obj):
    """Evaluated mesh with custom (hardened/weighted) normals kept."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), preserve_all_data_layers=True,
                                           depsgraph=depsgraph)


def finalize(kit, damaged=False):
    """Turn the parts into one object per (bone, mesh): applied modifiers, finish per face (material
    slot). Returns {(bone, group, kind): object}, kind is "body", "team" or "tread"."""
    groups = {}
    for part in kit.parts:
        if part.damaged is not None and part.damaged != damaged:
            continue
        kind = part.finish if part.finish in ("tread", "team", "shadow") else "body"
        groups.setdefault((part.bone, part.group, kind), []).append(part)
    out = {}
    finishes = list(FINISHES)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for key, parts in groups.items():
        bm = bmesh.new()
        for part in parts:
            mesh = bpy.data.meshes.new_from_object(part.obj.evaluated_get(depsgraph), preserve_all_data_layers=True,
                                                   depsgraph=depsgraph)
            mesh.transform(part.obj.matrix_world)
            # Finish index on every face, through the material index.
            idx = finishes.index(part.finish) if part.finish in finishes else 0
            for poly in mesh.polygons:
                poly.material_index = idx
            # Texel density weight: small parts and plain finishes get less of the atlas.
            # Judged by the middle dimension, so long thin welds, rails and cables stay thin in the atlas too.
            mid = sorted(part.obj.dimensions)[1]
            weight = min(1.0, max(0.12, mid / 1.2))
            if part.finish in ("rubber", "dark", "glass", "lens", "steel"):
                weight *= 0.5
            dens = mesh.attributes.new("dens", "FLOAT", "FACE")
            dens.data.foreach_set("value", [weight] * len(mesh.polygons))
            pid = mesh.attributes.new("pid", "INT", "FACE")
            pid.data.foreach_set("value", [kit.parts.index(part)] * len(mesh.polygons))
            # Keep custom normals: store them as a corner attribute so bmesh merging keeps them.
            normals = np.zeros(len(mesh.loops) * 3)
            mesh.corner_normals.foreach_get("vector", normals)
            attr = mesh.attributes.new("nrm", "FLOAT_VECTOR", "CORNER")
            attr.data.foreach_set("vector", normals)
            bm.from_mesh(mesh)
            bpy.data.meshes.remove(mesh)
        name = f"{key[0][:6]}_{key[1]}_{key[2]}"
        mesh = bpy.data.meshes.new(name)
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj["bone"], obj["group"], obj["kind"] = key
        out[key] = obj
    bpy.context.scene["bones"] = repr(kit.bones)
    for part in kit.parts:
        bpy.data.objects.remove(part.obj)
    for cutter in kit.cutters:
        bpy.data.objects.remove(cutter)
    kit.cutters = []
    return out


def unwrap(objs, margin=0.004):
    """One shared atlas for all objects: angle-based islands packed together at even texel density."""
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objs:
        obj.select_set(True)
        if not obj.data.uv_layers:
            obj.data.uv_layers.new(name="UVMap")
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(50), island_margin=margin, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode="OBJECT")
    # Shrink the islands of each part by its density weight, about the part's own UV centre.
    for obj in objs:
        me = obj.data
        if not me.uv_layers:
            # Shadow casters sit inside the hull and are never seen: one texel of the atlas's dark margin.
            layer = me.uv_layers.new(name="UVMap")
            for d in layer.data:
                d.uv = (0.0005, 0.0005)
        uv = me.uv_layers.active.data
        dens = me.attributes.get("dens")
        pid = me.attributes.get("pid")
        if not dens or not pid:
            continue
        loops = {}
        for poly in me.polygons:
            loops.setdefault(pid.data[poly.index].value, (dens.data[poly.index].value, []))[1].extend(poly.loop_indices)
        for weight, idx in loops.values():
            if weight >= 0.999:
                continue
            cu = sum(uv[i].uv[0] for i in idx) / len(idx)
            cv = sum(uv[i].uv[1] for i in idx) / len(idx)
            for i in idx:
                u, v = uv[i].uv
                uv[i].uv = (cu + (u - cu) * weight, cv + (v - cv) * weight)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=margin * 0.6, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")


def bake(objs, palette, size, damaged, pattern, name, burns=None):
    """Bake the finished albedo of objs into a new image."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 48
    scene.cycles.use_denoising = False
    scene.render.bake.margin = 6
    image = bpy.data.images.new(name, size, size, alpha=False)
    image.colorspace_settings.name = "sRGB"
    mats = []
    for finish in FINISHES:
        mats.append(_paint_material(f"{name}_{finish}", finish, palette, image, damaged, pattern, burns))
    for obj in objs:
        obj.data.materials.clear()
        for m in mats:
            obj.data.materials.append(m)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objs:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.bake(type="EMIT", margin=6, use_clear=True)
    px = np.array(image.pixels[:]).reshape(size, size, 4)
    return image, px


def to_w3d(kit, objects, model_name, textures, materials):
    """Export finalized objects into a w3d.Model. textures: kind -> texture file name; materials:
    kind -> w3d.Material."""
    model = w3d.Model(model_name)
    for bone, parent, pivot in kit.bones[1:]:
        model.add_bone(bone, parent, pivot)
    for (bone, group, kind), obj in sorted(objects.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        mesh_name = group if kind != "team" else group  # group names carry HOUSECOLOR for team parts
        me = obj.data
        me.calc_loop_triangles()
        if not me.uv_layers:
            # Shadow casters sit inside the hull and are never seen: one texel of the atlas's dark margin.
            layer = me.uv_layers.new(name="UVMap")
            for d in layer.data:
                d.uv = (0.0005, 0.0005)
        uv = me.uv_layers.active.data
        nrm = me.attributes.get("nrm")
        m = w3d.Mesh(mesh_name, materials[kind])
        index = {}
        for tri in me.loop_triangles:
            ids = []
            for li in tri.loops:
                vi = me.loops[li].vertex_index
                p = tuple(round(c, 5) for c in me.vertices[vi].co)
                n = tuple(round(c, 4) for c in (nrm.data[li].vector if nrm else me.loops[li].normal))
                u = tuple(round(c, 5) for c in uv[li].uv)
                key = (p, n, u)
                if key not in index:
                    index[key] = m.add_vertex(p, n, u)
                ids.append(index[key])
            m.add_triangle(*ids)
        model.attach(bone, m)
    return model


def save_image(px, path):
    from PIL import Image
    arr = (np.clip(px[::-1, :, :3], 0, 1) * 255 + 0.5).astype(np.uint8)  # byte image: already sRGB
    Image.fromarray(arr, "RGB").save(path)
    return arr
