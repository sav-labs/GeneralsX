"""Primitive shapes for procedural W3D content.

GeneralsX @feature Claude 15/10/2026 Every shape is emitted as flat-shaded polygons (hard
edges, one normal per face) with box-projected UVs inside an atlas region, which suits the
angular armour of modern vehicles and keeps textures seamless without hand UV work.
Coordinates follow the engine: +X forward, +Y left, +Z up, one unit per game distance unit.
"""

import math


class Region:
    """A rectangle of a texture atlas plus the world size one texture repeat covers."""

    def __init__(self, u0, v0, u1, v1, world_size=24.0):
        self.u0, self.v0, self.u1, self.v1 = u0, v0, u1, v1
        self.world_size = world_size

    def map(self, s, t):
        # s, t are world-space planar coordinates; wrap them into the region.
        fs = (s / self.world_size) % 1.0
        ft = (t / self.world_size) % 1.0
        return (self.u0 + fs * (self.u1 - self.u0), self.v0 + ft * (self.v1 - self.v0))


FULL = Region(0.0, 0.0, 1.0, 1.0)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _normalize(v):
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / length, v[1] / length, v[2] / length)


def polygon_normal(points):
    # Newell's method: robust for any planar polygon.
    nx = ny = nz = 0.0
    for i, p in enumerate(points):
        q = points[(i + 1) % len(points)]
        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])
    return _normalize((nx, ny, nz))


def centroid(points):
    n = float(len(points))
    return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n, sum(p[2] for p in points) / n)


class ShadeFn:
    """Baked ambient occlusion: darker near the ground and on faces pointing down."""

    def __init__(self, ground=0.0, height=8.0, floor=0.62):
        self.ground = ground
        self.height = height
        self.floor = floor

    def __call__(self, position, normal):
        h = min(1.0, max(0.0, (position[2] - self.ground) / self.height))
        k = self.floor + (1.0 - self.floor) * h
        if normal[2] < -0.3:
            k *= 0.75
        k *= 0.92 + 0.08 * max(0.0, normal[2])
        v = 255 * min(1.0, k)
        return (v, v, v, 255)


class Builder:
    """Collects polygons into a w3d.Mesh."""

    def __init__(self, mesh, shade=None, uv_fn=None):
        self.mesh = mesh
        self.shade = shade or ShadeFn()
        # Optional fixed mapping (e.g. treads, where U must run along the hull on every face).
        self.uv_fn = uv_fn

    def polygon(self, points, region=FULL, flip=False, outward_from=None):
        points = [tuple(float(c) for c in p) for p in points]
        if flip:
            points.reverse()
        normal = polygon_normal(points)
        if outward_from is not None:
            # Convex parts: make the face point away from the part's centre (counter-clockwise
            # seen from outside, the winding the engine treats as front-facing).
            c = [sum(p[i] for p in points) / len(points) for i in range(3)]
            if sum(normal[i] * (c[i] - outward_from[i]) for i in range(3)) < 0:
                points.reverse()
                normal = (-normal[0], -normal[1], -normal[2])
        ax = max(range(3), key=lambda i: abs(normal[i]))
        # Planar projection on the two axes the face spans the most.
        if ax == 0:
            proj = lambda p: (p[1] * (1 if normal[0] > 0 else -1), p[2])
        elif ax == 1:
            proj = lambda p: (p[0] * (-1 if normal[1] > 0 else 1), p[2])
        else:
            proj = lambda p: (p[0], p[1])
        # U wraps freely (atlas regions span the full width and tile horizontally); V starts at the
        # face's lowest point so it stays inside the region's rows.
        t_min = min(proj(p)[1] for p in points)
        indices = []
        for p in points:
            s, t = proj(p)
            fs = s / region.world_size
            ft = min(0.98, (t - t_min) / region.world_size + 0.01)
            u = region.u0 + fs * (region.u1 - region.u0)
            v = region.v0 + ft * (region.v1 - region.v0)
            if self.uv_fn is not None:
                u, v = self.uv_fn(p)
                v = 1.0 - v
            indices.append(self.mesh.add_vertex(p, normal, (u, 1.0 - v), self.shade(p, normal)))
        for i in range(1, len(indices) - 1):
            self.mesh.add_triangle(indices[0], indices[i], indices[i + 1])

    def loft(self, bottom, top, region=FULL, cap_bottom=True, cap_top=True):
        """Join two convex rings with the same vertex count."""
        n = len(bottom)
        assert n == len(top)
        c = centroid(bottom + top)
        for i in range(n):
            j = (i + 1) % n
            self.polygon([bottom[i], bottom[j], top[j], top[i]], region, outward_from=c)
        if cap_top:
            self.polygon(top, region, outward_from=c)
        if cap_bottom:
            self.polygon(bottom, region, outward_from=c)

    def extrude_y(self, profile_xz, y0, y1, region=FULL):
        """Side profile in XZ (counter-clockwise seen from +Y) extruded between y0 < y1."""
        left = [(x, y1, z) for x, z in profile_xz]
        right = [(x, y0, z) for x, z in profile_xz]
        c = centroid(left + right)
        self.polygon(left, region, outward_from=c)
        self.polygon(right, region, outward_from=c)
        n = len(profile_xz)
        for i in range(n):
            j = (i + 1) % n
            self.polygon([right[i], right[j], left[j], left[i]], region, outward_from=c)

    def box(self, lo, hi, region=FULL):
        x0, y0, z0 = lo
        x1, y1, z1 = hi
        self.loft([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)],
                  [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], region)

    def cylinder_x(self, x0, x1, y, z, r0, r1=None, sides=12, region=FULL, caps=True):
        r1 = r0 if r1 is None else r1
        ring = lambda x, r: [(x, y + r * math.cos(a), z + r * math.sin(a))
                             for a in (2 * math.pi * k / sides for k in range(sides))]
        a, b = ring(x0, r0), ring(x1, r1)
        c = centroid(a + b)
        for i in range(sides):
            j = (i + 1) % sides
            self.polygon([a[i], b[i], b[j], a[j]], region, outward_from=c)
        if caps:
            self.polygon(a, region, outward_from=c)
            self.polygon(b, region, outward_from=c)

    def cylinder_y(self, x, y0, y1, z, r, sides=12, region=FULL):
        ring = lambda y: [(x + r * math.cos(a), y, z + r * math.sin(a))
                          for a in (2 * math.pi * k / sides for k in range(sides))]
        a, b = ring(y0), ring(y1)
        c = centroid(a + b)
        for i in range(sides):
            j = (i + 1) % sides
            self.polygon([a[i], a[j], b[j], b[i]], region, outward_from=c)
        self.polygon(a, region, outward_from=c)
        self.polygon(b, region, outward_from=c)

    def cylinder_z(self, x, y, z0, z1, r0, r1=None, sides=12, region=FULL):
        r1 = r0 if r1 is None else r1
        ring = lambda z, r: [(x + r * math.cos(a), y + r * math.sin(a), z)
                             for a in (2 * math.pi * k / sides for k in range(sides))]
        self.loft(ring(z0, r0), ring(z1, r1), region)
