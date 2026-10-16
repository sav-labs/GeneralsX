"""Minimal W3D writer for GeneralsX content.

GeneralsX @feature Claude 15/10/2026 Writes the subset of the Westwood W3D format the
Zero Hour engine needs for a rigid unit: one hierarchy (bones), textured meshes attached
to bones, and an HLOD that ties them together. Layouts follow
GeneralsMD/Code/Libraries/Source/WWVegas/WW3D2/w3d_file.h and meshmdlio.cpp.
"""

import math
import struct

# Chunk ids (w3d_file.h)
MESH = 0x00000000
VERTICES = 0x00000002
VERTEX_NORMALS = 0x00000003
MESH_HEADER3 = 0x0000001F
TRIANGLES = 0x00000020
VERTEX_SHADE_INDICES = 0x00000022
MATERIAL_INFO = 0x00000028
SHADERS = 0x00000029
VERTEX_MATERIALS = 0x0000002A
VERTEX_MATERIAL = 0x0000002B
VERTEX_MATERIAL_NAME = 0x0000002C
VERTEX_MATERIAL_INFO = 0x0000002D
VERTEX_MAPPER_ARGS0 = 0x0000002E
TEXTURES = 0x00000030
TEXTURE = 0x00000031
TEXTURE_NAME = 0x00000032
MATERIAL_PASS = 0x00000038
VERTEX_MATERIAL_IDS = 0x00000039
SHADER_IDS = 0x0000003A
DCG = 0x0000003B
TEXTURE_STAGE = 0x00000048
TEXTURE_IDS = 0x00000049
STAGE_TEXCOORDS = 0x0000004A
HIERARCHY = 0x00000100
HIERARCHY_HEADER = 0x00000101
PIVOTS = 0x00000102
ANIMATION = 0x00000200
ANIMATION_HEADER = 0x00000201
ANIMATION_CHANNEL = 0x00000202
ANIM_CHANNEL_X = 0
ANIM_CHANNEL_Y = 1
ANIM_CHANNEL_Z = 2
ANIM_CHANNEL_Q = 6
HLOD = 0x00000700
HLOD_HEADER = 0x00000701
HLOD_LOD_ARRAY = 0x00000702
HLOD_SUB_OBJECT_ARRAY_HEADER = 0x00000703
HLOD_SUB_OBJECT = 0x00000704


def make_version(major, minor):
    return (major << 16) | minor


MESH_VERSION = make_version(4, 2)
HTREE_VERSION = make_version(4, 1)
HANIM_VERSION = make_version(4, 1)
HLOD_VERSION = make_version(1, 0)

MESH_FLAG_HIDDEN = 0x00001000
MESH_FLAG_TWO_SIDED = 0x00002000
MESH_FLAG_CAST_SHADOW = 0x00008000

VERTEX_CHANNEL_LOCATION = 0x1
VERTEX_CHANNEL_NORMAL = 0x2
VERTEX_CHANNEL_TEXCOORD = 0x4
VERTEX_CHANNEL_COLOR = 0x8
FACE_CHANNEL_FACE = 0x1

VERTMAT_MAPPING_LINEAR_OFFSET = 0x00040000

NAME_LEN = 16
NO_MAX_SCREEN_SIZE = 3.4028234663852886e38


def chunk(chunk_id, payload, has_children=False):
    size = len(payload)
    if has_children:
        size |= 0x80000000
    return struct.pack("<II", chunk_id, size) + payload


def wrapper(chunk_id, children):
    return chunk(chunk_id, b"".join(children), has_children=True)


def fixed_name(name, length=NAME_LEN):
    raw = name.encode("ascii")
    if len(raw) >= length:
        raise ValueError(f"W3D name '{name}' must be shorter than {length} characters")
    return raw + b"\0" * (length - len(raw))


def cstring(text):
    return text.encode("ascii") + b"\0"


class Shader:
    """W3dShaderStruct fields; defaults are an opaque, textured, lit surface."""

    def __init__(self, src_blend=1, dest_blend=0, depth_mask=1, alpha_test=0, texturing=1):
        self.src_blend = src_blend
        self.dest_blend = dest_blend
        self.depth_mask = depth_mask
        self.alpha_test = alpha_test
        self.texturing = texturing

    def pack(self):
        return struct.pack(
            "<16B",
            3,  # DepthCompare: pass LEQUAL
            self.depth_mask,
            0,  # ColorMask (obsolete)
            self.dest_blend,
            0,  # FogFunc (obsolete)
            1,  # PriGradient: modulate
            0,  # SecGradient
            self.src_blend,
            self.texturing,
            0, 0,  # DetailColorFunc, DetailAlphaFunc
            0,  # ShaderPreset (obsolete)
            self.alpha_test,
            0, 0,  # PostDetail funcs
            0,  # pad
        )


OPAQUE = Shader()
ADDITIVE = Shader(src_blend=1, dest_blend=1, depth_mask=0)
ALPHA_BLEND = Shader(src_blend=2, dest_blend=5, depth_mask=0)


class Material:
    def __init__(self, name, texture, shader=OPAQUE, diffuse=(255, 255, 255), ambient=(255, 255, 255),
                 specular=(0, 0, 0), emissive=(0, 0, 0), shininess=1.0, scroll_mapper=False):
        self.name = name
        self.texture = texture
        self.shader = shader
        self.diffuse = diffuse
        self.ambient = ambient
        self.specular = specular
        self.emissive = emissive
        self.shininess = shininess
        self.scroll_mapper = scroll_mapper

    def vertex_material_chunk(self):
        attributes = VERTMAT_MAPPING_LINEAR_OFFSET if self.scroll_mapper else 0
        info = struct.pack("<I", attributes)
        for rgb in (self.ambient, self.diffuse, self.specular, self.emissive):
            info += struct.pack("<4B", rgb[0], rgb[1], rgb[2], 0)
        info += struct.pack("<3f", self.shininess, 1.0, 0.0)
        children = [chunk(VERTEX_MATERIAL_NAME, cstring(self.name)), chunk(VERTEX_MATERIAL_INFO, info)]
        if self.scroll_mapper:
            # W3DTankDraw drives the offset itself; the mapper only has to exist.
            children.append(chunk(VERTEX_MAPPER_ARGS0, cstring("UPerSec=0.0\r\nVPerSec=0.0")))
        return wrapper(VERTEX_MATERIAL, children)


class Mesh:
    """Triangle soup with per-vertex position, normal, uv and colour, in bone-local space."""

    def __init__(self, name, material, attributes=MESH_FLAG_CAST_SHADOW):
        self.name = name
        self.material = material
        self.attributes = attributes
        self.positions = []
        self.normals = []
        self.uvs = []
        self.colors = []
        self.triangles = []

    def add_vertex(self, position, normal, uv, color=(255, 255, 255, 255)):
        self.positions.append(tuple(float(c) for c in position))
        self.normals.append(tuple(float(c) for c in normal))
        self.uvs.append((float(uv[0]), float(uv[1])))
        self.colors.append(tuple(int(max(0, min(255, round(c)))) for c in color))
        return len(self.positions) - 1

    def add_triangle(self, a, b, c):
        self.triangles.append((a, b, c))

    def translate(self, offset):
        self.positions = [(p[0] - offset[0], p[1] - offset[1], p[2] - offset[2]) for p in self.positions]

    def pack(self, container):
        if not self.triangles:
            raise ValueError(f"mesh {self.name} has no triangles")
        xs, ys, zs = zip(*self.positions)
        bmin = (min(xs), min(ys), min(zs))
        bmax = (max(xs), max(ys), max(zs))
        center = tuple((lo + hi) * 0.5 for lo, hi in zip(bmin, bmax))
        radius = max(math.dist(center, p) for p in self.positions)

        header = struct.pack("<II", MESH_VERSION, self.attributes)
        header += fixed_name(self.name) + fixed_name(container)
        header += struct.pack(
            "<IIIIiII", len(self.triangles), len(self.positions), 1, 0, 0, 0, 0)
        header += struct.pack(
            "<II", VERTEX_CHANNEL_LOCATION | VERTEX_CHANNEL_NORMAL | VERTEX_CHANNEL_TEXCOORD | VERTEX_CHANNEL_COLOR,
            FACE_CHANNEL_FACE)
        header += struct.pack("<3f3f3ff", *bmin, *bmax, *center, radius)

        tris = b""
        for a, b, c in self.triangles:
            pa, pb, pc = self.positions[a], self.positions[b], self.positions[c]
            u = [pb[i] - pa[i] for i in range(3)]
            v = [pc[i] - pa[i] for i in range(3)]
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            length = math.sqrt(sum(x * x for x in n)) or 1.0
            n = tuple(x / length for x in n)
            dist = sum(n[i] * pa[i] for i in range(3))
            # Attributes: surface type 13 = default
            tris += struct.pack("<3II3ff", a, b, c, 13, *n, dist)

        material = self.material
        stage = wrapper(TEXTURE_STAGE, [
            chunk(TEXTURE_IDS, struct.pack("<I", 0)),
            chunk(STAGE_TEXCOORDS, b"".join(struct.pack("<2f", u, v) for u, v in self.uvs)),
        ])
        material_pass = wrapper(MATERIAL_PASS, [
            chunk(VERTEX_MATERIAL_IDS, struct.pack("<I", 0)),
            chunk(SHADER_IDS, struct.pack("<I", 0)),
            chunk(DCG, b"".join(struct.pack("<4B", *c) for c in self.colors)),
            stage,
        ])

        children = [
            chunk(MESH_HEADER3, header),
            chunk(VERTICES, b"".join(struct.pack("<3f", *p) for p in self.positions)),
            chunk(VERTEX_NORMALS, b"".join(struct.pack("<3f", *n) for n in self.normals)),
            chunk(TRIANGLES, tris),
            chunk(VERTEX_SHADE_INDICES, b"".join(struct.pack("<I", i) for i in range(len(self.positions)))),
            chunk(MATERIAL_INFO, struct.pack("<4I", 1, 1, 1, 1)),
            wrapper(VERTEX_MATERIALS, [material.vertex_material_chunk()]),
            chunk(SHADERS, material.shader.pack()),
            wrapper(TEXTURES, [wrapper(TEXTURE, [chunk(TEXTURE_NAME, cstring(material.texture))])]),
            material_pass,
        ]
        return wrapper(MESH, children)


class Bone:
    def __init__(self, name, parent, translation):
        self.name = name
        self.parent = parent
        self.translation = tuple(float(c) for c in translation)


class Model:
    """A hierarchy, its meshes and the HLOD that binds them, written as one .w3d file."""

    def __init__(self, name):
        self.name = name.upper()
        self.bones = [Bone("ROOTTRANSFORM", None, (0, 0, 0))]
        self.meshes = []  # (bone index, Mesh)
        self.spins = []  # (bone index, axis, revolutions per loop)
        self.tracks = []  # (bone index, channel type, one value or quaternion per frame)
        self.anim_frames = 0
        self.anim_rate = 30

    def add_spin(self, bone_name, axis, revolutions=1.0):
        """Loop that turns a bone about its local axis (rotors); written as the model's own animation."""
        self.spins.append((self.bone_index(bone_name), axis, revolutions))
        self.anim_frames = max(self.anim_frames, 17)

    def add_motion(self, bone_name, frames, offset=None, turn=None):
        """Keyed motion of one bone over `frames` frames, written as the model's own animation.
        offset(f) -> (dx, dy, dz) moves the bone from its rest pivot; turn(f) -> (axis, degrees) turns it
        about its own axis. WW3D applies both relative to the pivot, so frame values of zero are rest."""
        bone = self.bone_index(bone_name)
        if offset:
            values = [offset(f) for f in range(frames)]
            for axis, channel in enumerate((ANIM_CHANNEL_X, ANIM_CHANNEL_Y, ANIM_CHANNEL_Z)):
                if any(abs(v[axis]) > 1e-6 for v in values):
                    self.tracks.append((bone, channel, [(v[axis],) for v in values]))
        if turn:
            quats = []
            for f in range(frames):
                axis, degrees = turn(f)
                half = math.radians(degrees) / 2
                q = [0.0, 0.0, 0.0, math.cos(half)]
                q["xyz".index(axis)] = math.sin(half)
                quats.append(tuple(q))
            self.tracks.append((bone, ANIM_CHANNEL_Q, quats))
        self.anim_frames = max(self.anim_frames, frames)

    def bone_index(self, name):
        for i, bone in enumerate(self.bones):
            if bone.name == name:
                return i
        raise KeyError(name)

    def add_bone(self, name, parent, world_position):
        parent_index = self.bone_index(parent)
        parent_world = self.bone_world(parent_index)
        local = tuple(world_position[i] - parent_world[i] for i in range(3))
        self.bones.append(Bone(name, parent_index, local))
        return len(self.bones) - 1

    def bone_world(self, index):
        x = y = z = 0.0
        while index is not None:
            bone = self.bones[index]
            x += bone.translation[0]
            y += bone.translation[1]
            z += bone.translation[2]
            index = bone.parent
        return (x, y, z)

    def attach(self, bone_name, mesh):
        """Attach a mesh authored in model space; it is moved into the bone's space."""
        index = self.bone_index(bone_name)
        mesh.translate(self.bone_world(index))
        self.meshes.append((index, mesh))

    def pack(self):
        pivots = b""
        for bone in self.bones:
            parent = 0xFFFFFFFF if bone.parent is None else bone.parent
            pivots += fixed_name(bone.name) + struct.pack("<I3f3f4f", parent, *bone.translation, 0, 0, 0, 0, 0, 0, 1)
        hierarchy = wrapper(HIERARCHY, [
            chunk(HIERARCHY_HEADER, struct.pack("<I", HTREE_VERSION) + fixed_name(self.name)
                  + struct.pack("<I3f", len(self.bones), 0, 0, 0)),
            chunk(PIVOTS, pivots),
        ])

        meshes = [mesh.pack(self.name) for _, mesh in self.meshes]

        sub_objects = [
            chunk(HLOD_SUB_OBJECT, struct.pack("<I", bone) + fixed_name(f"{self.name}.{mesh.name}", NAME_LEN * 2))
            for bone, mesh in self.meshes
        ]
        hlod = wrapper(HLOD, [
            chunk(HLOD_HEADER, struct.pack("<II", HLOD_VERSION, 1) + fixed_name(self.name) + fixed_name(self.name)),
            wrapper(HLOD_LOD_ARRAY, [
                chunk(HLOD_SUB_OBJECT_ARRAY_HEADER, struct.pack("<If", len(sub_objects), NO_MAX_SCREEN_SIZE)),
                *sub_objects,
            ]),
        ])
        return hierarchy + b"".join(meshes) + hlod + self.pack_animation()

    def pack_animation(self):
        """Animation named MODEL.MODEL (what INI 'Animation = X.X' refers to): one Q channel per spin plus
        the keyed motion tracks, each held at its last value if shorter than the animation."""
        if not self.spins and not self.tracks:
            return b""
        frames = self.anim_frames
        channels = []
        for bone, axis, revolutions in self.spins:
            data = b""
            for f in range(frames):
                # Last key equals the first turned a whole number of times, so the loop is seamless.
                angle = 2 * math.pi * revolutions * f / (frames - 1)
                half = angle / 2
                q = [0.0, 0.0, 0.0, math.cos(half)]
                q["xyz".index(axis)] = math.sin(half)
                data += struct.pack("<4f", *q)
            channels.append(chunk(ANIMATION_CHANNEL, struct.pack("<6H", 0, frames - 1, 4, ANIM_CHANNEL_Q, bone, 0) + data))
        for bone, channel, values in self.tracks:
            values = values + [values[-1]] * (frames - len(values))
            width = len(values[0])
            data = b"".join(struct.pack(f"<{width}f", *v) for v in values)
            channels.append(chunk(ANIMATION_CHANNEL, struct.pack("<6H", 0, frames - 1, width, channel, bone, 0) + data))
        header = struct.pack("<I", HANIM_VERSION) + fixed_name(self.name) + fixed_name(self.name) + struct.pack("<II", frames, self.anim_rate)
        return wrapper(ANIMATION, [chunk(ANIMATION_HEADER, header), *channels])


def pack_clip(hierarchy, name, frames, tracks, rate=30):
    """A standalone animation HIERARCHY.NAME, saved as NAME.w3d (the asset manager loads an animation
    from the file named after the part behind the dot). tracks: (pivot index, channel type, one tuple
    per frame), the same layout Model.add_motion keeps."""
    channels = []
    for bone, channel, values in tracks:
        width = len(values[0])
        data = b"".join(struct.pack(f"<{width}f", *v) for v in values)
        channels.append(chunk(ANIMATION_CHANNEL, struct.pack("<6H", 0, frames - 1, width, channel, bone, 0) + data))
    header = struct.pack("<I", HANIM_VERSION) + fixed_name(name) + fixed_name(hierarchy) + struct.pack("<II", frames, rate)
    return wrapper(ANIMATION, [chunk(ANIMATION_HEADER, header), *channels])


def read_chunks(data, offset=0, end=None):
    """Parse a chunk tree back; used by the self-test to validate written files."""
    end = len(data) if end is None else end
    out = []
    while offset < end:
        chunk_id, size = struct.unpack_from("<II", data, offset)
        has_children = bool(size & 0x80000000)
        size &= 0x7FFFFFFF
        start = offset + 8
        if start + size > end:
            raise ValueError(f"chunk 0x{chunk_id:x} at {offset} overruns its parent")
        children = read_chunks(data, start, start + size) if has_children else None
        out.append((chunk_id, data[start:start + size], children))
        offset = start + size
    return out
