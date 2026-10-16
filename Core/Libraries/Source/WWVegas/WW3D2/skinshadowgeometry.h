/*
**	Command & Conquer Generals Zero Hour(tm)
**	Copyright 2026 TheSuperHackers
**
**	This program is free software: you can redistribute it and/or modify
**	it under the terms of the GNU General Public License as published by
**	the Free Software Foundation, either version 3 of the License, or
**	(at your option) any later version.
**
**	This program is distributed in the hope that it will be useful,
**	but WITHOUT ANY WARRANTY; without even the implied warranty of
**	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
**	GNU General Public License for more details.
**
**	You should have received a copy of the GNU General Public License
**	along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/

// GeneralsX @feature Claude 16/10/2026 CPU geometry for shadows of skinned (and high poly) models.
//
// The W3D shadow volume code builds its silhouette tables once per model from the model's static vertices, so
// skin meshes (whose vertices only mean something after skinning) never cast a shadow volume. This header
// holds the pose independent parts used by W3DSkinnedShadow for both shadow routes:
//
//  - SkinShadowTopology: duplicate vertex groups and the edge to face table of a triangle mesh, built once per
//    model from one pose. A skinned mesh keeps its triangles, so the table stays valid for every later pose;
//    only the positions change.
//  - buildSilhouetteVolume: silhouette of the posed mesh from a light direction and the extruded sides of the
//    shadow volume (same face and edge rules as W3DVolumetricShadow::buildSilhouette), for the stencil route.
//  - buildClusterProxy: a vertex clustered stand-in with at most a given number of triangles, for very high
//    poly casters on the stencil route.
//  - SkinShadowPoseKey: detects that a pose changed by more than a tolerance, ignoring pure translation
//    (directional light), so shadows of units that only drive are not rebuilt.
//  - clipToLightPrism: clips terrain triangles to the square a projected shadow covers in light space, for
//    the projected texture route.
//
// Header only and free of engine types (any vector type with X, Y, Z float members works), so the regression
// test in scripts/qa/perf builds it without the engine. No transcendental math: square roots and
// normalisation stay with the caller. Rendering only; the game logic never reads any of this.

#pragma once

#include <algorithm>
#include <string.h>
#include <vector>

namespace SkinShadow
{

/// One mesh edge. v0 -> v1 runs in the winding of face f0; f1 is the face on the other side or -1 when the
/// edge is open (border, or shared by more than two faces or by faces of opposite winding).
struct Edge
{
	int v0;
	int v1;
	int f0;
	int f1;
};

namespace Detail
{
	struct VertexKey
	{
		unsigned int x, y, z;
		unsigned int group;
		int index;
		bool hasNaN;
	};

	inline unsigned int floatBits(float value)
	{
		if (value == 0.0f)
			return 0;	// +0 and -0 are the same position
		unsigned int bits;
		memcpy(&bits, &value, sizeof(bits));
		return bits;
	}

	inline bool vertexKeyLess(const VertexKey &a, const VertexKey &b)
	{
		if (a.hasNaN != b.hasNaN)
			return a.hasNaN < b.hasNaN;
		if (a.group != b.group)
			return a.group < b.group;
		if (a.x != b.x)
			return a.x < b.x;
		if (a.y != b.y)
			return a.y < b.y;
		if (a.z != b.z)
			return a.z < b.z;
		return a.index < b.index;
	}

	inline bool vertexKeySame(const VertexKey &a, const VertexKey &b)
	{
		return !a.hasNaN && !b.hasNaN && a.group == b.group && a.x == b.x && a.y == b.y && a.z == b.z;
	}

	struct HalfEdge
	{
		int lo, hi;		// sorted vertex pair, the key
		int a, b;		// direction in the face's winding
		int face;
	};

	inline bool halfEdgeLess(const HalfEdge &l, const HalfEdge &r)
	{
		if (l.lo != r.lo)
			return l.lo < r.lo;
		if (l.hi != r.hi)
			return l.hi < r.hi;
		return l.face < r.face;
	}

	template <class V3>
	inline void faceNormal(const V3 &p0, const V3 &p1, const V3 &p2, float n[3])
	{
		// Same orientation as W3DShadowGeometryMesh::buildPolygonNormal: cross(v1 - v2, v1 - v0)
		// equals cross(v1 - v0, v2 - v0). Not normalised; only its sign against the light is used.
		const float e1x = p1.X - p0.X, e1y = p1.Y - p0.Y, e1z = p1.Z - p0.Z;
		const float e2x = p2.X - p0.X, e2y = p2.Y - p0.Y, e2z = p2.Z - p0.Z;
		n[0] = e1y * e2z - e1z * e2y;
		n[1] = e1z * e2x - e1x * e2z;
		n[2] = e1x * e2y - e1y * e2x;
	}
}

/// Duplicate vertex groups and edge table of one triangle mesh. Built once per model; valid for every pose of
/// the same mesh because skinning moves vertices but never changes the triangles.
class SkinShadowTopology
{
public:
	SkinShadowTopology() : m_vertexCount(0) {}

	/// positions: one pose of the mesh; vertices that share a position in this pose are welded, like the shadow
	/// volume code does. groups (optional, one per vertex, e.g. the bone of each skin vertex): only vertices of
	/// the same group are welded, so vertices that touch in this pose but move apart in another stay apart.
	/// indices: three per triangle.
	template <class V3>
	void build(const V3 *positions, int vertexCount, const unsigned short *indices, int triangleCount,
		const unsigned short *groups = nullptr)
	{
		m_vertexCount = vertexCount;
		m_parent.assign(vertexCount > 0 ? vertexCount : 0, 0);
		m_triangles.clear();
		m_edges.clear();
		if (vertexCount <= 0 || triangleCount <= 0)
			return;

		// Weld vertices with bit-identical positions, each pointing at the lowest index of its group.
		std::vector<Detail::VertexKey> keys(vertexCount);
		for (int v = 0; v < vertexCount; ++v)
		{
			const V3 &p = positions[v];
			keys[v].x = Detail::floatBits(p.X);
			keys[v].y = Detail::floatBits(p.Y);
			keys[v].z = Detail::floatBits(p.Z);
			keys[v].group = groups ? groups[v] : 0;
			keys[v].index = v;
			keys[v].hasNaN = (p.X != p.X) || (p.Y != p.Y) || (p.Z != p.Z);
		}
		std::sort(keys.begin(), keys.end(), Detail::vertexKeyLess);
		int groupStart = 0;
		for (int s = 0; s < vertexCount; ++s)
		{
			if (s > 0 && Detail::vertexKeySame(keys[s - 1], keys[s]))
				m_parent[keys[s].index] = keys[groupStart].index;
			else
			{
				groupStart = s;
				m_parent[keys[s].index] = keys[s].index;
			}
		}

		// Triangles on welded vertices; triangles that collapse to a line or a point cast nothing.
		m_triangles.reserve(triangleCount * 3);
		for (int t = 0; t < triangleCount; ++t)
		{
			const int i0 = indices[t * 3 + 0], i1 = indices[t * 3 + 1], i2 = indices[t * 3 + 2];
			if (i0 >= vertexCount || i1 >= vertexCount || i2 >= vertexCount)
				continue;
			const int a = m_parent[i0], b = m_parent[i1], c = m_parent[i2];
			if (a == b || b == c || a == c)
				continue;
			m_triangles.push_back(a);
			m_triangles.push_back(b);
			m_triangles.push_back(c);
		}

		// Edge table: two faces of opposite winding share an edge; anything else is an open edge per face.
		const int faces = getTriangleCount();
		std::vector<Detail::HalfEdge> halfEdges(faces * 3);
		for (int f = 0; f < faces; ++f)
		{
			for (int k = 0; k < 3; ++k)
			{
				Detail::HalfEdge &h = halfEdges[f * 3 + k];
				h.a = m_triangles[f * 3 + k];
				h.b = m_triangles[f * 3 + (k + 1) % 3];
				h.lo = h.a < h.b ? h.a : h.b;
				h.hi = h.a < h.b ? h.b : h.a;
				h.face = f;
			}
		}
		std::sort(halfEdges.begin(), halfEdges.end(), Detail::halfEdgeLess);
		m_edges.reserve(halfEdges.size());
		size_t i = 0;
		while (i < halfEdges.size())
		{
			size_t j = i + 1;
			while (j < halfEdges.size() && halfEdges[j].lo == halfEdges[i].lo && halfEdges[j].hi == halfEdges[i].hi)
				++j;
			if (j - i == 2 && halfEdges[i].a == halfEdges[i + 1].b)
			{
				Edge e = { halfEdges[i].a, halfEdges[i].b, halfEdges[i].face, halfEdges[i + 1].face };
				m_edges.push_back(e);
			}
			else
			{
				for (size_t k = i; k < j; ++k)
				{
					Edge e = { halfEdges[k].a, halfEdges[k].b, halfEdges[k].face, -1 };
					m_edges.push_back(e);
				}
			}
			i = j;
		}
	}

	int getVertexCount() const { return m_vertexCount; }
	int getTriangleCount() const { return (int)(m_triangles.size() / 3); }
	int getEdgeCount() const { return (int)m_edges.size(); }
	int getOpenEdgeCount() const
	{
		int open = 0;
		for (size_t i = 0; i < m_edges.size(); ++i)
			if (m_edges[i].f1 < 0)
				++open;
		return open;
	}
	const int *getTriangles() const { return m_triangles.empty() ? nullptr : &m_triangles[0]; }
	const Edge *getEdges() const { return m_edges.empty() ? nullptr : &m_edges[0]; }
	const int *getParents() const { return m_parent.empty() ? nullptr : &m_parent[0]; }
	bool isEmpty() const { return m_triangles.empty(); }

private:
	int m_vertexCount;
	std::vector<int> m_parent;
	std::vector<int> m_triangles;
	std::vector<Edge> m_edges;
};

/// Scratch and output of buildSilhouetteVolume, kept per shadow so rebuilds do not allocate.
struct VolumeBuffers
{
	std::vector<unsigned char> lit;			///< per face: faces the light
	std::vector<int> remap;					///< per source vertex: output index + 1 of this build, 0 = not yet
	std::vector<float> vertices;			///< x, y, z relative to the origin; each silhouette vertex then its extrusion
	std::vector<unsigned short> indices;	///< triangle list
	int silhouetteEdges;

	VolumeBuffers() : silhouetteEdges(0) {}

	int getVertexCount() const { return (int)(vertices.size() / 3); }
	int getTriangleCount() const { return (int)(indices.size() / 3); }
};

/// Marks the faces of a posed mesh that face the light. lightDir points from the light into the scene.
template <class V3>
inline int classifyFaces(const SkinShadowTopology &topology, const V3 *positions, const float lightDir[3],
	std::vector<unsigned char> &lit)
{
	const int faces = topology.getTriangleCount();
	const int *tri = topology.getTriangles();
	lit.resize(faces);
	int litCount = 0;
	for (int f = 0; f < faces; ++f)
	{
		float n[3];
		Detail::faceNormal(positions[tri[f * 3]], positions[tri[f * 3 + 1]], positions[tri[f * 3 + 2]], n);
		// W3DVolumetricShadow::buildSilhouette: visible when dot(vertex - light, normal) < 0
		const bool isLit = n[0] * lightDir[0] + n[1] * lightDir[1] + n[2] * lightDir[2] < 0.0f;
		lit[f] = isLit ? 1 : 0;
		litCount += isLit ? 1 : 0;
	}
	return litCount;
}

/// Calls emit(a, b) for every silhouette edge of the posed mesh, a -> b in the winding of the lit face, with
/// the same rules as W3DVolumetricShadow: an edge between a lit and an unlit face, and every open edge of a lit
/// face. Returns the number of edges.
template <class EmitT>
inline int forEachSilhouetteEdge(const SkinShadowTopology &topology, const std::vector<unsigned char> &lit, EmitT &emit)
{
	const Edge *edges = topology.getEdges();
	const int edgeCount = topology.getEdgeCount();
	int count = 0;
	for (int i = 0; i < edgeCount; ++i)
	{
		const Edge &e = edges[i];
		const bool lit0 = lit[e.f0] != 0;
		if (e.f1 < 0)
		{
			if (lit0)
			{
				emit(e.v0, e.v1);
				++count;
			}
			continue;
		}
		const bool lit1 = lit[e.f1] != 0;
		if (lit0 && !lit1)
		{
			emit(e.v0, e.v1);
			++count;
		}
		else if (lit1 && !lit0)
		{
			emit(e.v1, e.v0);
			++count;
		}
	}
	return count;
}

namespace Detail
{
	template <class V3>
	struct VolumeEmitter
	{
		const V3 *positions;
		const float *origin;
		float extrude[3];
		VolumeBuffers *out;
		bool overflow;

		int vertexIndex(int v)
		{
			int &slot = out->remap[v];
			if (slot != 0)
				return slot - 1;
			const int index = out->getVertexCount();
			if (index + 2 > 65535)
			{
				overflow = true;
				return -1;
			}
			const V3 &p = positions[v];
			const float x = p.X - origin[0], y = p.Y - origin[1], z = p.Z - origin[2];
			out->vertices.push_back(x);
			out->vertices.push_back(y);
			out->vertices.push_back(z);
			out->vertices.push_back(x + extrude[0]);
			out->vertices.push_back(y + extrude[1]);
			out->vertices.push_back(z + extrude[2]);
			slot = index + 1;
			return index;
		}

		void operator()(int a, int b)
		{
			const int ia = vertexIndex(a);
			const int ib = vertexIndex(b);
			if (ia < 0 || ib < 0)
				return;
			// Same two triangles per edge as W3DVolumetricShadow::constructVolume:
			// (edge start, start extruded, edge end) and (edge end, start extruded, end extruded)
			out->indices.push_back((unsigned short)ia);
			out->indices.push_back((unsigned short)(ia + 1));
			out->indices.push_back((unsigned short)ib);
			out->indices.push_back((unsigned short)ib);
			out->indices.push_back((unsigned short)(ia + 1));
			out->indices.push_back((unsigned short)(ib + 1));
		}
	};
}

/// Builds the sides of the shadow volume of a posed mesh: every silhouette edge extruded by extrudeLength along
/// lightDir (normalised, from the light into the scene). Vertices are written relative to origin so the volume
/// can be drawn again after a pure translation. Appends to out (call out.vertices.clear() etc. per model), and
/// returns false if the 16 bit index range overflowed (the volume is then partial).
template <class V3>
inline bool buildSilhouetteVolume(const SkinShadowTopology &topology, const V3 *positions, const float lightDir[3],
	const float origin[3], float extrudeLength, VolumeBuffers &out)
{
	classifyFaces(topology, positions, lightDir, out.lit);
	out.remap.assign(topology.getVertexCount(), 0);
	Detail::VolumeEmitter<V3> emitter;
	emitter.positions = positions;
	emitter.origin = origin;
	emitter.extrude[0] = lightDir[0] * extrudeLength;
	emitter.extrude[1] = lightDir[1] * extrudeLength;
	emitter.extrude[2] = lightDir[2] * extrudeLength;
	emitter.out = &out;
	emitter.overflow = false;
	out.silhouetteEdges += forEachSilhouetteEdge(topology, out.lit, emitter);
	return !emitter.overflow;
}

/// Vertex clustered stand-in for a very high poly caster: welds all vertices that fall into the same cell of a
/// grid over the mesh's bounds onto the first vertex of the cell, drops collapsed and repeated triangles, and
/// coarsens the grid until at most maxTriangles remain. The result indexes the original vertices, so it follows
/// the skinning of the vertices it kept. Returns the triangle count (0 = the mesh is already small enough or
/// the proxy failed; use the full mesh).
template <class V3>
inline int buildClusterProxy(const V3 *positions, int vertexCount, const unsigned short *indices, int triangleCount,
	int maxTriangles, std::vector<unsigned short> &outIndices)
{
	outIndices.clear();
	if (vertexCount <= 0 || triangleCount <= maxTriangles || maxTriangles < 16)
		return 0;

	float lo[3] = { positions[0].X, positions[0].Y, positions[0].Z };
	float hi[3] = { lo[0], lo[1], lo[2] };
	for (int v = 1; v < vertexCount; ++v)
	{
		const float p[3] = { positions[v].X, positions[v].Y, positions[v].Z };
		for (int k = 0; k < 3; ++k)
		{
			if (p[k] < lo[k]) lo[k] = p[k];
			if (p[k] > hi[k]) hi[k] = p[k];
		}
	}
	float size = 0.0f;
	for (int k = 0; k < 3; ++k)
		if (hi[k] - lo[k] > size)
			size = hi[k] - lo[k];
	if (!(size > 0.0f))
		return 0;

	std::vector<long long> cellKey(vertexCount);
	std::vector<int> order(vertexCount);
	std::vector<int> representative(vertexCount);
	std::vector<unsigned long long> triKeys;
	std::vector<unsigned short> candidate;

	for (int cells = 128; cells >= 2; cells = cells * 3 / 4)
	{
		const float scale = (float)cells / size;
		for (int v = 0; v < vertexCount; ++v)
		{
			long long c[3];
			const float p[3] = { positions[v].X, positions[v].Y, positions[v].Z };
			for (int k = 0; k < 3; ++k)
			{
				long long cell = (long long)((p[k] - lo[k]) * scale);
				if (cell < 0) cell = 0;
				if (cell > cells) cell = cells;
				c[k] = cell;
			}
			cellKey[v] = (c[0] * 1024 + c[1]) * 1024 + c[2];
			order[v] = v;
		}
		std::sort(order.begin(), order.end(), [&cellKey](int a, int b) {
			return cellKey[a] != cellKey[b] ? cellKey[a] < cellKey[b] : a < b;
		});
		for (int s = 0; s < vertexCount; ++s)
		{
			if (s > 0 && cellKey[order[s]] == cellKey[order[s - 1]])
				representative[order[s]] = representative[order[s - 1]];
			else
				representative[order[s]] = order[s];
		}

		candidate.clear();
		triKeys.clear();
		for (int t = 0; t < triangleCount; ++t)
		{
			const int i0 = indices[t * 3], i1 = indices[t * 3 + 1], i2 = indices[t * 3 + 2];
			if (i0 >= vertexCount || i1 >= vertexCount || i2 >= vertexCount)
				continue;
			int a = representative[i0], b = representative[i1], c = representative[i2];
			if (a == b || b == c || a == c)
				continue;
			// Rotate so the smallest index comes first; the same triangle with the same winding then has one key.
			while (a > b || a > c)
			{
				const int keep = a;
				a = b;
				b = c;
				c = keep;
			}
			const unsigned long long key = ((unsigned long long)a << 32) | ((unsigned long long)b << 16) | (unsigned long long)c;
			triKeys.push_back(key);
		}
		std::sort(triKeys.begin(), triKeys.end());
		triKeys.erase(std::unique(triKeys.begin(), triKeys.end()), triKeys.end());
		if ((int)triKeys.size() <= maxTriangles)
		{
			for (size_t i = 0; i < triKeys.size(); ++i)
			{
				candidate.push_back((unsigned short)((triKeys[i] >> 32) & 0xffff));
				candidate.push_back((unsigned short)((triKeys[i] >> 16) & 0xffff));
				candidate.push_back((unsigned short)(triKeys[i] & 0xffff));
			}
			outIndices.swap(candidate);
			return (int)(outIndices.size() / 3);
		}
	}
	return 0;
}

/// Detects pose changes of a hierarchy for shadow updates. The caller gives 12 floats per pivot: the 3x3 part of
/// the pivot's world transform row by row, then its translation minus the root pivot's translation. Moving the
/// whole model (translation only) therefore keeps the key; turning it, animating a bone or moving a sub-object
/// changes it. Hidden flags of the caster meshes are compared as a separate mask.
class SkinShadowPoseKey
{
public:
	SkinShadowPoseKey() : m_valid(false), m_hiddenMask(0) {}

	void invalidate() { m_valid = false; }
	bool isValid() const { return m_valid; }

	/// True when the new key differs from the stored one by more than the tolerances (rotation entries are unit
	/// free, so epsRotation is roughly the angle in radians; epsPosition is in world units).
	bool differs(const float *entries, int count, unsigned long long hiddenMask, float epsRotation, float epsPosition) const
	{
		if (!m_valid || count != (int)m_entries.size() || hiddenMask != m_hiddenMask)
			return true;
		for (int i = 0; i < count; i += 12)
		{
			for (int k = 0; k < 9; ++k)
			{
				const float d = entries[i + k] - m_entries[i + k];
				if (d > epsRotation || d < -epsRotation)
					return true;
			}
			for (int k = 9; k < 12; ++k)
			{
				const float d = entries[i + k] - m_entries[i + k];
				if (d > epsPosition || d < -epsPosition)
					return true;
			}
		}
		return false;
	}

	void store(const float *entries, int count, unsigned long long hiddenMask)
	{
		m_entries.assign(entries, entries + count);
		m_hiddenMask = hiddenMask;
		m_valid = true;
	}

private:
	bool m_valid;
	unsigned long long m_hiddenMask;
	std::vector<float> m_entries;
};

/// Point of a polygon clipped to the light prism: world position and light space coordinates (a along U, b
/// along V, relative to the prism centre).
struct PrismVertex
{
	float p[3];
	float a;
	float b;
};

/// Clips a polygon against |a| <= limitA and |b| <= limitB (the square column of light a projected shadow
/// covers). in/out hold up to count + 4 vertices; returns the vertex count of the clipped polygon (0 when
/// nothing is left). Positions are interpolated linearly, so the result lies on the input plane.
inline int clipToLightPrism(const PrismVertex *in, int count, float limitA, float limitB, PrismVertex *out, PrismVertex *scratch)
{
	if (count <= 0)
		return 0;
	const PrismVertex *src = in;
	int srcCount = count;

	// planes +a, -a, +b, -b; the passes alternate between scratch and out and end in out
	for (int plane = 0; plane < 4; ++plane)
	{
		PrismVertex *dst = (plane & 1) ? out : scratch;
		int dstCount = 0;
		for (int i = 0; i < srcCount; ++i)
		{
			const PrismVertex &cur = src[i];
			const PrismVertex &next = src[(i + 1) % srcCount];
			float dc, dn;
			switch (plane)
			{
				case 0: dc = limitA - cur.a; dn = limitA - next.a; break;
				case 1: dc = cur.a + limitA; dn = next.a + limitA; break;
				case 2: dc = limitB - cur.b; dn = limitB - next.b; break;
				default: dc = cur.b + limitB; dn = next.b + limitB; break;
			}
			const bool curIn = dc >= 0.0f;
			const bool nextIn = dn >= 0.0f;
			if (curIn)
				dst[dstCount++] = cur;
			if (curIn != nextIn)
			{
				const float t = dc / (dc - dn);
				PrismVertex &v = dst[dstCount++];
				for (int k = 0; k < 3; ++k)
					v.p[k] = cur.p[k] + (next.p[k] - cur.p[k]) * t;
				v.a = cur.a + (next.a - cur.a) * t;
				v.b = cur.b + (next.b - cur.b) * t;
				// put the new vertex exactly on the plane
				switch (plane)
				{
					case 0: v.a = limitA; break;
					case 1: v.a = -limitA; break;
					case 2: v.b = limitB; break;
					default: v.b = -limitB; break;
				}
			}
		}
		src = dst;
		srcCount = dstCount;
		if (srcCount == 0)
			return 0;
	}
	return srcCount;
}

} // namespace SkinShadow
