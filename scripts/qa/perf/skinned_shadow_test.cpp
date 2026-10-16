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

// GeneralsX @feature Claude 16/10/2026 Regression test and microbenchmark for the skinned shadow geometry
// (Core/Libraries/Source/WWVegas/WW3D2/skinshadowgeometry.h). Builds without the engine:
//   scripts/qa/perf/run-skinned-shadow-test.sh
//
// A synthetic skinned tank (hull, turret and barrel on three bones, every face with its own vertices like
// exported W3D meshes, about 15k triangles) is posed with the turret and barrel turned. Checks:
//  1. The silhouette from the per-model topology (built once in the bind pose) equals the silhouette of a
//     full static rebuild of the posed mesh, edge for edge, and its volume has the same size.
//  2. Silhouette edges form closed loops on the closed mesh (every vertex has as many edges in as out).
//  3. The stencil volume is right: for ground points seen from an RTS camera, the signed count of volume
//     faces between the camera and the point (z-pass) is non zero exactly where a ray to the light hits the
//     tank.
//  4. The pose key ignores driving (translation) and catches a 0.5 degree turret turn; a volume rebuilt after
//     driving equals the old one relative to the root.
//  5. The vertex clustered proxy stays under its triangle cap and shades nearly the same ground points.
//  6. Terrain clipping to the light prism: clipped pieces stay inside the square and cover exactly its area
//     on flat ground (vertical and slanted light); texture coordinates of a caster point and of its shadow on
//     the ground are equal.
// Then times the per update work. Exit code 0 = pass.

#include "skinshadowgeometry.h"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <utility>
#include <vector>

namespace
{
	struct Vec3
	{
		float X, Y, Z;
	};

	Vec3 v3(float x, float y, float z) { Vec3 v = { x, y, z }; return v; }
	Vec3 sub(const Vec3 &a, const Vec3 &b) { return v3(a.X - b.X, a.Y - b.Y, a.Z - b.Z); }
	Vec3 add(const Vec3 &a, const Vec3 &b) { return v3(a.X + b.X, a.Y + b.Y, a.Z + b.Z); }
	Vec3 mul(const Vec3 &a, float s) { return v3(a.X * s, a.Y * s, a.Z * s); }
	float dot(const Vec3 &a, const Vec3 &b) { return a.X * b.X + a.Y * b.Y + a.Z * b.Z; }
	Vec3 cross(const Vec3 &a, const Vec3 &b) { return v3(a.Y * b.Z - a.Z * b.Y, a.Z * b.X - a.X * b.Z, a.X * b.Y - a.Y * b.X); }
	Vec3 normalize(const Vec3 &a) { const float l = std::sqrt(dot(a, a)); return mul(a, 1.0f / l); }

	/// 3x4 transform, rows of rotation | translation
	struct Mat34
	{
		float m[3][4];

		static Mat34 identity()
		{
			Mat34 r = {};
			r.m[0][0] = r.m[1][1] = r.m[2][2] = 1.0f;
			return r;
		}
		static Mat34 translation(const Vec3 &t)
		{
			Mat34 r = identity();
			r.m[0][3] = t.X; r.m[1][3] = t.Y; r.m[2][3] = t.Z;
			return r;
		}
		static Mat34 rotZ(float radians)
		{
			Mat34 r = identity();
			const float c = std::cos(radians), s = std::sin(radians);
			r.m[0][0] = c; r.m[0][1] = -s; r.m[1][0] = s; r.m[1][1] = c;
			return r;
		}
		static Mat34 rotY(float radians)
		{
			Mat34 r = identity();
			const float c = std::cos(radians), s = std::sin(radians);
			r.m[0][0] = c; r.m[0][2] = s; r.m[2][0] = -s; r.m[2][2] = c;
			return r;
		}
		Vec3 apply(const Vec3 &p) const
		{
			return v3(m[0][0] * p.X + m[0][1] * p.Y + m[0][2] * p.Z + m[0][3],
				m[1][0] * p.X + m[1][1] * p.Y + m[1][2] * p.Z + m[1][3],
				m[2][0] * p.X + m[2][1] * p.Y + m[2][2] * p.Z + m[2][3]);
		}
		Mat34 operator*(const Mat34 &b) const
		{
			Mat34 r = {};
			for (int i = 0; i < 3; ++i)
			{
				for (int j = 0; j < 4; ++j)
				{
					float s = (j == 3) ? m[i][3] : 0.0f;
					for (int k = 0; k < 3; ++k)
						s += m[i][k] * b.m[k][j];
					r.m[i][j] = s;
				}
			}
			return r;
		}
	};

	/// W3D style rigid skin: every vertex belongs to one bone and is stored in that bone's bind space.
	struct SkinMesh
	{
		std::vector<Vec3> local;
		std::vector<unsigned short> bone;
		std::vector<unsigned short> indices;
	};

	struct Pose
	{
		Mat34 bones[3];
	};

	const Vec3 kTurretPivot = { 2.0f, 0.0f, 9.0f };
	const Vec3 kBarrelPivot = { 9.0f, 0.0f, 12.0f };

	void addQuadGrid(SkinMesh &mesh, int boneIndex, const Vec3 &bindOrigin, const Vec3 &corner, const Vec3 &edgeU,
		const Vec3 &edgeV, int n)
	{
		const int base = (int)mesh.local.size();
		for (int j = 0; j <= n; ++j)
		{
			for (int i = 0; i <= n; ++i)
			{
				const Vec3 p = add(corner, add(mul(edgeU, (float)i / n), mul(edgeV, (float)j / n)));
				mesh.local.push_back(sub(p, bindOrigin));
				mesh.bone.push_back((unsigned short)boneIndex);
			}
		}
		for (int j = 0; j < n; ++j)
		{
			for (int i = 0; i < n; ++i)
			{
				const int a = base + j * (n + 1) + i;
				const int b = a + 1;
				const int c = a + (n + 1);
				const int d = c + 1;
				const unsigned short tri[6] = { (unsigned short)a, (unsigned short)b, (unsigned short)d,
					(unsigned short)a, (unsigned short)d, (unsigned short)c };
				mesh.indices.insert(mesh.indices.end(), tri, tri + 6);
			}
		}
	}

	/// Closed box whose six faces have their own vertices (split at every box edge), outward winding.
	void addBox(SkinMesh &mesh, int boneIndex, const Vec3 &bindOrigin, const Vec3 &lo, const Vec3 &hi, int n)
	{
		const Vec3 dx = v3(hi.X - lo.X, 0, 0), dy = v3(0, hi.Y - lo.Y, 0), dz = v3(0, 0, hi.Z - lo.Z);
		addQuadGrid(mesh, boneIndex, bindOrigin, lo, dy, dx, n);							// bottom (-z)
		addQuadGrid(mesh, boneIndex, bindOrigin, add(lo, dz), dx, dy, n);					// top (+z)
		addQuadGrid(mesh, boneIndex, bindOrigin, lo, dx, dz, n);							// front (-y)
		addQuadGrid(mesh, boneIndex, bindOrigin, add(lo, dy), dz, dx, n);					// back (+y)
		addQuadGrid(mesh, boneIndex, bindOrigin, lo, dz, dy, n);							// left (-x)
		addQuadGrid(mesh, boneIndex, bindOrigin, add(lo, dx), dy, dz, n);					// right (+x)
	}

	/// Closed cylinder along z with separate cap vertices, outward winding.
	void addCylinder(SkinMesh &mesh, int boneIndex, const Vec3 &bindOrigin, const Vec3 &center, float radius, float height,
		int sides, int rings)
	{
		const int base = (int)mesh.local.size();
		for (int r = 0; r <= rings; ++r)
		{
			for (int s = 0; s < sides; ++s)
			{
				const float angle = 6.28318530718f * s / sides;
				const Vec3 p = v3(center.X + radius * std::cos(angle), center.Y + radius * std::sin(angle),
					center.Z + height * r / rings);
				mesh.local.push_back(sub(p, bindOrigin));
				mesh.bone.push_back((unsigned short)boneIndex);
			}
		}
		for (int r = 0; r < rings; ++r)
		{
			for (int s = 0; s < sides; ++s)
			{
				const int a = base + r * sides + s;
				const int b = base + r * sides + (s + 1) % sides;
				const int c = a + sides;
				const int d = b + sides;
				const unsigned short tri[6] = { (unsigned short)a, (unsigned short)b, (unsigned short)d,
					(unsigned short)a, (unsigned short)d, (unsigned short)c };
				mesh.indices.insert(mesh.indices.end(), tri, tri + 6);
			}
		}
		for (int cap = 0; cap < 2; ++cap)
		{
			const float z = center.Z + (cap ? height : 0.0f);
			const int mid = (int)mesh.local.size();
			mesh.local.push_back(sub(v3(center.X, center.Y, z), bindOrigin));
			mesh.bone.push_back((unsigned short)boneIndex);
			const int ring = (int)mesh.local.size();
			for (int s = 0; s < sides; ++s)
			{
				const float angle = 6.28318530718f * s / sides;
				mesh.local.push_back(sub(v3(center.X + radius * std::cos(angle), center.Y + radius * std::sin(angle), z), bindOrigin));
				mesh.bone.push_back((unsigned short)boneIndex);
			}
			for (int s = 0; s < sides; ++s)
			{
				const int a = ring + s, b = ring + (s + 1) % sides;
				if (cap)
				{
					const unsigned short tri[3] = { (unsigned short)mid, (unsigned short)a, (unsigned short)b };
					mesh.indices.insert(mesh.indices.end(), tri, tri + 3);
				}
				else
				{
					const unsigned short tri[3] = { (unsigned short)mid, (unsigned short)b, (unsigned short)a };
					mesh.indices.insert(mesh.indices.end(), tri, tri + 3);
				}
			}
		}
	}

	SkinMesh makeTank()
	{
		SkinMesh mesh;
		addBox(mesh, 0, v3(0, 0, 0), v3(-14, -7, 1), v3(14, 7, 8), 30);
		addCylinder(mesh, 1, kTurretPivot, v3(2, 0, 8), 6.0f, 5.0f, 64, 10);
		addBox(mesh, 2, kBarrelPivot, v3(8, -0.6f, 11.4f), v3(26, 0.6f, 12.6f), 12);
		return mesh;
	}

	Pose makePose(const Vec3 &position, float hullYaw, float turretYaw, float barrelPitch)
	{
		Pose pose;
		pose.bones[0] = Mat34::translation(position) * Mat34::rotZ(hullYaw);
		pose.bones[1] = pose.bones[0] * Mat34::translation(kTurretPivot) * Mat34::rotZ(turretYaw);
		pose.bones[2] = pose.bones[1] * Mat34::translation(sub(kBarrelPivot, kTurretPivot)) * Mat34::rotY(barrelPitch);
		return pose;
	}

	void deform(const SkinMesh &mesh, const Pose &pose, std::vector<Vec3> &out)
	{
		out.resize(mesh.local.size());
		for (size_t v = 0; v < mesh.local.size(); ++v)
			out[v] = pose.bones[mesh.bone[v]].apply(mesh.local[v]);
	}

	void poseKey(const Pose &pose, std::vector<float> &entries)
	{
		entries.clear();
		for (int b = 0; b < 3; ++b)
		{
			for (int i = 0; i < 3; ++i)
				for (int j = 0; j < 3; ++j)
					entries.push_back(pose.bones[b].m[i][j]);
			for (int i = 0; i < 3; ++i)
				entries.push_back(pose.bones[b].m[i][3] - pose.bones[0].m[i][3]);
		}
	}

	typedef std::pair<std::vector<float>, std::vector<float> > PositionEdge;

	struct EdgeCollector
	{
		const std::vector<Vec3> *positions;
		std::set<std::vector<float> > edges;
		std::vector<int> inDegree, outDegree;

		void operator()(int a, int b)
		{
			const Vec3 &pa = (*positions)[a];
			const Vec3 &pb = (*positions)[b];
			std::vector<float> key;
			key.push_back(pa.X); key.push_back(pa.Y); key.push_back(pa.Z);
			key.push_back(pb.X); key.push_back(pb.Y); key.push_back(pb.Z);
			edges.insert(key);
			if ((int)outDegree.size() <= a) outDegree.resize(a + 1, 0);
			if ((int)inDegree.size() <= b) inDegree.resize(b + 1, 0);
			outDegree[a]++;
			inDegree[b]++;
		}
	};

	/// Moller-Trumbore; returns the ray parameter or -1.
	float intersect(const Vec3 &origin, const Vec3 &dir, const Vec3 &a, const Vec3 &b, const Vec3 &c)
	{
		const Vec3 e1 = sub(b, a), e2 = sub(c, a);
		const Vec3 p = cross(dir, e2);
		const float det = dot(e1, p);
		if (std::fabs(det) < 1e-9f)
			return -1.0f;
		const float inv = 1.0f / det;
		const Vec3 s = sub(origin, a);
		const float u = dot(s, p) * inv;
		if (u < 0.0f || u > 1.0f)
			return -1.0f;
		const Vec3 q = cross(s, e1);
		const float v = dot(dir, q) * inv;
		if (v < 0.0f || u + v > 1.0f)
			return -1.0f;
		const float t = dot(e2, q) * inv;
		return t;
	}

	bool rayHitsMesh(const Vec3 &origin, const Vec3 &dir, float maxT, const std::vector<Vec3> &positions,
		const std::vector<unsigned short> &indices)
	{
		for (size_t t = 0; t + 2 < indices.size(); t += 3)
		{
			const float hit = intersect(origin, dir, positions[indices[t]], positions[indices[t + 1]], positions[indices[t + 2]]);
			if (hit > 1e-4f && hit < maxT)
				return true;
		}
		return false;
	}

	/// z-pass stencil count of the volume along camera -> point (only faces in front of the point count).
	int stencilCount(const Vec3 &camera, const Vec3 &point, const SkinShadow::VolumeBuffers &volume, const Vec3 &origin)
	{
		const Vec3 dir = sub(point, camera);
		int count = 0;
		const std::vector<float> &v = volume.vertices;
		for (size_t t = 0; t + 2 < volume.indices.size(); t += 3)
		{
			const int i0 = volume.indices[t], i1 = volume.indices[t + 1], i2 = volume.indices[t + 2];
			const Vec3 a = add(v3(v[i0 * 3], v[i0 * 3 + 1], v[i0 * 3 + 2]), origin);
			const Vec3 b = add(v3(v[i1 * 3], v[i1 * 3 + 1], v[i1 * 3 + 2]), origin);
			const Vec3 c = add(v3(v[i2 * 3], v[i2 * 3 + 1], v[i2 * 3 + 2]), origin);
			const float hit = intersect(camera, dir, a, b, c);
			if (hit > 0.0f && hit < 1.0f - 1e-5f)
				count += dot(cross(sub(b, a), sub(c, a)), dir) < 0.0f ? 1 : -1;
		}
		return count;
	}

	int s_failures = 0;

	void check(bool ok, const char *what)
	{
		printf("  %s %s\n", ok ? "ok  " : "FAIL", what);
		if (!ok)
			++s_failures;
	}

	double nowUs()
	{
		using namespace std::chrono;
		return duration<double, std::micro>(steady_clock::now().time_since_epoch()).count();
	}

	/// Ground points seen from the camera: count of matches between "stencil says shadow" and "ray to light hits
	/// the caster", over the points whose view is not blocked by the caster.
	struct ShadowSampleResult
	{
		int samples;
		int shadowed;
		int mismatches;
	};

	ShadowSampleResult sampleGround(const Vec3 &camera, const Vec3 &lightDir, const std::vector<Vec3> &posed,
		const std::vector<unsigned short> &casterIndices, const std::vector<unsigned short> &referenceIndices,
		const SkinShadow::VolumeBuffers &volume, const Vec3 &origin, const Vec3 &center)
	{
		ShadowSampleResult r = { 0, 0, 0 };
		const Vec3 toLight = mul(lightDir, -1.0f);
		for (int j = -30; j <= 30; ++j)
		{
			for (int i = -30; i <= 30; ++i)
			{
				const Vec3 ground = v3(center.X + i * 0.9f, center.Y + j * 0.9f, 0.0f);
				const Vec3 view = sub(ground, camera);
				if (rayHitsMesh(camera, view, 1.0f - 1e-4f, posed, casterIndices))
					continue;	// the pixel shows the tank, not the ground
				const bool inShadow = rayHitsMesh(ground, toLight, 1e6f, posed, referenceIndices);
				const int count = stencilCount(camera, ground, volume, origin);
				++r.samples;
				r.shadowed += inShadow ? 1 : 0;
				if ((count != 0) != inShadow)
					++r.mismatches;
			}
		}
		return r;
	}
}

int main()
{
	const SkinMesh tank = makeTank();
	const int triangles = (int)(tank.indices.size() / 3);
	printf("skinned shadow test: synthetic tank with %d triangles, %d vertices, 3 bones\n", triangles, (int)tank.local.size());

	const Vec3 lightDir = normalize(v3(-0.45f, 0.3f, -0.84f));	// from the light into the scene
	const float light[3] = { lightDir.X, lightDir.Y, lightDir.Z };
	const Vec3 position = v3(512.0f, 300.0f, 0.0f);

	// Topology once per model, from the bind pose (identity root).
	std::vector<Vec3> bindPosed;
	deform(tank, makePose(v3(0, 0, 0), 0, 0, 0), bindPosed);
	SkinShadow::SkinShadowTopology topology;
	topology.build(&bindPosed[0], (int)bindPosed.size(), &tank.indices[0], triangles, &tank.bone[0]);
	printf("  topology: %d faces, %d edges, %d open\n", topology.getTriangleCount(), topology.getEdgeCount(), topology.getOpenEdgeCount());
	check(topology.getOpenEdgeCount() == 0, "split vertices are welded: the closed tank has no open edges");

	const Pose pose = makePose(position, 0.35f, 0.7f, -0.12f);
	std::vector<Vec3> posed;
	deform(tank, pose, posed);

	// 1. per-model topology against a static rebuild of the posed mesh
	{
		SkinShadow::SkinShadowTopology rebuilt;
		rebuilt.build(&posed[0], (int)posed.size(), &tank.indices[0], triangles, &tank.bone[0]);
		std::vector<unsigned char> litA, litB;
		SkinShadow::classifyFaces(topology, &posed[0], light, litA);
		SkinShadow::classifyFaces(rebuilt, &posed[0], light, litB);
		EdgeCollector a, b;
		a.positions = &posed;
		b.positions = &posed;
		const int countA = SkinShadow::forEachSilhouetteEdge(topology, litA, a);
		const int countB = SkinShadow::forEachSilhouetteEdge(rebuilt, litB, b);
		printf("  silhouette: %d edges (bind pose topology), %d edges (static rebuild)\n", countA, countB);
		check(countA == countB && a.edges == b.edges, "silhouette of the posed skin equals the static rebuild, edge for edge");

		bool balanced = true;
		const size_t n = a.inDegree.size() > a.outDegree.size() ? a.inDegree.size() : a.outDegree.size();
		a.inDegree.resize(n, 0);
		a.outDegree.resize(n, 0);
		for (size_t v = 0; v < n; ++v)
			if (a.inDegree[v] != a.outDegree[v])
				balanced = false;
		check(balanced, "silhouette edges form closed loops");

		SkinShadow::VolumeBuffers volA, volB;
		const float origin[3] = { position.X, position.Y, position.Z };
		SkinShadow::buildSilhouetteVolume(topology, &posed[0], light, origin, 60.0f, volA);
		SkinShadow::buildSilhouetteVolume(rebuilt, &posed[0], light, origin, 60.0f, volB);
		check(volA.getVertexCount() == volB.getVertexCount() && volA.getTriangleCount() == volB.getTriangleCount(),
			"volume of the posed skin has the size of the static rebuild's volume");
	}

	// 3. stencil volume against ray casts to the light
	SkinShadow::VolumeBuffers volume;
	{
		const float origin[3] = { position.X, position.Y, position.Z };
		const bool complete = SkinShadow::buildSilhouetteVolume(topology, &posed[0], light, origin, 60.0f, volume);
		check(complete, "volume fits 16 bit indices");
		printf("  volume: %d silhouette edges, %d vertices, %d triangles\n", volume.silhouetteEdges, volume.getVertexCount(), volume.getTriangleCount());
		const Vec3 camera = v3(position.X - 160.0f, position.Y + 140.0f, 260.0f);
		const ShadowSampleResult r = sampleGround(camera, lightDir, posed, tank.indices, tank.indices, volume, position, position);
		printf("  stencil: %d visible ground samples, %d in shadow, %d mismatches\n", r.samples, r.shadowed, r.mismatches);
		check(r.shadowed > 100 && r.mismatches <= r.samples / 200, "z-pass count marks exactly the ground points the tank shades");
	}

	// 4. pose key: translation only keeps the key and the volume; a small turret turn changes it
	{
		std::vector<float> key, moved, turned;
		poseKey(pose, key);
		poseKey(makePose(add(position, v3(37.5f, -12.25f, 3.0f)), 0.35f, 0.7f, -0.12f), moved);
		poseKey(makePose(position, 0.35f, 0.7f + 0.5f * 3.14159265f / 180.0f, -0.12f), turned);
		SkinShadow::SkinShadowPoseKey poseKeyState;
		poseKeyState.store(&key[0], (int)key.size(), 0);
		check(!poseKeyState.differs(&moved[0], (int)moved.size(), 0, 0.002f, 0.02f), "pose key ignores driving");
		check(poseKeyState.differs(&turned[0], (int)turned.size(), 0, 0.002f, 0.02f), "pose key catches a 0.5 degree turret turn");
		check(poseKeyState.differs(&key[0], (int)key.size(), 1, 0.002f, 0.02f), "pose key catches a hidden sub-object");

		const Vec3 newPosition = add(position, v3(37.5f, -12.25f, 3.0f));
		std::vector<Vec3> movedPosed;
		deform(tank, makePose(newPosition, 0.35f, 0.7f, -0.12f), movedPosed);
		SkinShadow::VolumeBuffers movedVolume;
		const float origin[3] = { newPosition.X, newPosition.Y, newPosition.Z };
		SkinShadow::buildSilhouetteVolume(topology, &movedPosed[0], light, origin, 60.0f, movedVolume);
		float maxDiff = 0.0f;
		bool sameShape = movedVolume.vertices.size() == volume.vertices.size() && movedVolume.indices == volume.indices;
		for (size_t i = 0; sameShape && i < volume.vertices.size(); ++i)
			maxDiff = std::fmax(maxDiff, std::fabs(movedVolume.vertices[i] - volume.vertices[i]));
		printf("  translated volume: largest difference %.6f units\n", maxDiff);
		check(sameShape && maxDiff < 1e-3f, "volume relative to the root does not change when the unit only drives");
	}

	// 5. clustered proxy
	{
		std::vector<unsigned short> proxy;
		const int proxyTriangles = SkinShadow::buildClusterProxy(&bindPosed[0], (int)bindPosed.size(), &tank.indices[0], triangles, 4000, proxy);
		printf("  proxy: %d triangles (cap 4000)\n", proxyTriangles);
		check(proxyTriangles > 500 && proxyTriangles <= 4000, "proxy is under the cap and not empty");
		SkinShadow::SkinShadowTopology proxyTopology;
		proxyTopology.build(&bindPosed[0], (int)bindPosed.size(), &proxy[0], proxyTriangles, &tank.bone[0]);
		SkinShadow::VolumeBuffers proxyVolume;
		const float origin[3] = { position.X, position.Y, position.Z };
		SkinShadow::buildSilhouetteVolume(proxyTopology, &posed[0], light, origin, 60.0f, proxyVolume);
		const Vec3 camera = v3(position.X - 160.0f, position.Y + 140.0f, 260.0f);
		const ShadowSampleResult r = sampleGround(camera, lightDir, posed, tank.indices, tank.indices, proxyVolume, position, position);
		printf("  proxy stencil: %d samples, %d mismatches against the full tank, %d edges, %d open\n", r.samples, r.mismatches,
			proxyVolume.silhouetteEdges, proxyTopology.getOpenEdgeCount());
		check(r.mismatches <= r.samples / 20, "proxy shades at least 95% of the samples like the full mesh");
	}

	// 6. terrain clipping and projected texture coordinates
	{
		const float half = 20.0f;
		const Vec3 lights[2] = { v3(0.0f, 0.0f, -1.0f), lightDir };
		for (int l = 0; l < 2; ++l)
		{
			const Vec3 d = lights[l];
			const Vec3 u = normalize(cross(d, v3(0, 0, 1)).X == 0.0f && cross(d, v3(0, 0, 1)).Y == 0.0f ? v3(1, 0, 0) : cross(d, v3(0, 0, 1)));
			const Vec3 v = cross(u, d);
			const Vec3 center = v3(100.0f, 100.0f, 25.0f);
			double area = 0.0;
			bool inside = true;
			for (int j = -20; j < 20; ++j)
			{
				for (int i = -20; i < 20; ++i)
				{
					const Vec3 cell[4] = { v3(100.0f + i * 10.0f, 100.0f + j * 10.0f, 0), v3(100.0f + (i + 1) * 10.0f, 100.0f + j * 10.0f, 0),
						v3(100.0f + (i + 1) * 10.0f, 100.0f + (j + 1) * 10.0f, 0), v3(100.0f + i * 10.0f, 100.0f + (j + 1) * 10.0f, 0) };
					const int tris[2][3] = { { 0, 1, 2 }, { 0, 2, 3 } };
					for (int t = 0; t < 2; ++t)
					{
						SkinShadow::PrismVertex in[3], out[8], scratch[8];
						for (int k = 0; k < 3; ++k)
						{
							const Vec3 &p = cell[tris[t][k]];
							in[k].p[0] = p.X; in[k].p[1] = p.Y; in[k].p[2] = p.Z;
							in[k].a = dot(sub(p, center), u);
							in[k].b = dot(sub(p, center), v);
						}
						const int n = SkinShadow::clipToLightPrism(in, 3, half, half, out, scratch);
						for (int k = 0; k < n; ++k)
							if (std::fabs(out[k].a) > half + 1e-3f || std::fabs(out[k].b) > half + 1e-3f)
								inside = false;
						for (int k = 1; k + 1 < n; ++k)
						{
							const Vec3 a = v3(out[0].p[0], out[0].p[1], out[0].p[2]);
							const Vec3 b = v3(out[k].p[0], out[k].p[1], out[k].p[2]);
							const Vec3 c = v3(out[k + 1].p[0], out[k + 1].p[1], out[k + 1].p[2]);
							area += 0.5 * std::fabs(cross(sub(b, a), sub(c, a)).Z);
						}
					}
				}
			}
			const double expected = (2.0 * half) * (2.0 * half) / std::fabs(d.Z);
			printf("  clip (light %d): area %.3f, expected %.3f\n", l, area, expected);
			check(inside && std::fabs(area - expected) < expected * 1e-4, "clipped terrain covers exactly the light square on the ground");

			// a caster point and its shadow on the ground get the same texture coordinates
			const Vec3 caster = v3(110.0f, 95.0f, 14.0f);
			const float t = -caster.Z / d.Z;
			const Vec3 shadow = add(caster, mul(d, t));
			const float da = dot(sub(caster, center), u) - dot(sub(shadow, center), u);
			const float db = dot(sub(caster, center), v) - dot(sub(shadow, center), v);
			check(std::fabs(da) < 1e-4f && std::fabs(db) < 1e-4f, "shadow of a point has the point's light space coordinates");
		}
	}

	// timings
	{
		const int runs = 200;
		double start = nowUs();
		for (int i = 0; i < 20; ++i)
		{
			SkinShadow::SkinShadowTopology t;
			t.build(&bindPosed[0], (int)bindPosed.size(), &tank.indices[0], triangles, &tank.bone[0]);
		}
		const double topologyUs = (nowUs() - start) / 20.0;

		SkinShadow::VolumeBuffers buffers;
		start = nowUs();
		for (int i = 0; i < runs; ++i)
		{
			buffers.vertices.clear();
			buffers.indices.clear();
			buffers.silhouetteEdges = 0;
			const float origin[3] = { position.X, position.Y, position.Z };
			SkinShadow::buildSilhouetteVolume(topology, &posed[0], light, origin, 60.0f, buffers);
		}
		const double volumeUs = (nowUs() - start) / runs;

		std::vector<unsigned short> proxy;
		start = nowUs();
		const int proxyTriangles = SkinShadow::buildClusterProxy(&bindPosed[0], (int)bindPosed.size(), &tank.indices[0], triangles, 4000, proxy);
		const double proxyUs = nowUs() - start;
		SkinShadow::SkinShadowTopology proxyTopology;
		proxyTopology.build(&bindPosed[0], (int)bindPosed.size(), &proxy[0], proxyTriangles, &tank.bone[0]);
		start = nowUs();
		for (int i = 0; i < runs; ++i)
		{
			buffers.vertices.clear();
			buffers.indices.clear();
			const float origin[3] = { position.X, position.Y, position.Z };
			SkinShadow::buildSilhouetteVolume(proxyTopology, &posed[0], light, origin, 60.0f, buffers);
		}
		const double proxyVolumeUs = (nowUs() - start) / runs;

		std::vector<Vec3> scratch;
		start = nowUs();
		for (int i = 0; i < runs; ++i)
			deform(tank, pose, scratch);
		const double skinUs = (nowUs() - start) / runs;

		std::vector<float> key;
		poseKey(pose, key);
		SkinShadow::SkinShadowPoseKey state;
		state.store(&key[0], (int)key.size(), 0);
		std::vector<float> key40(40 * 12);
		for (size_t i = 0; i < key40.size(); ++i)
			key40[i] = key[i % key.size()];
		state.store(&key40[0], (int)key40.size(), 0);
		volatile int changed = 0;
		start = nowUs();
		for (int i = 0; i < 100000; ++i)
			changed += state.differs(&key40[0], (int)key40.size(), 0, 0.002f, 0.02f) ? 1 : 0;
		const double keyUs = (nowUs() - start) / 100000.0;

		printf("timings for a %d triangle skin:\n", triangles);
		printf("  topology build (once per model):       %8.1f us\n", topologyUs);
		printf("  CPU skinning (reference, per pose):     %8.1f us\n", skinUs);
		printf("  stencil volume rebuild (per update):    %8.1f us\n", volumeUs);
		printf("  proxy build (once per model):           %8.1f us\n", proxyUs);
		printf("  stencil volume rebuild of 4k proxy:     %8.1f us\n", proxyVolumeUs);
		printf("  pose key check, 40 bones (per frame):   %8.3f us\n", keyUs);
	}

	printf("%s (%d failures)\n", s_failures == 0 ? "PASS" : "FAIL", s_failures);
	return s_failures == 0 ? 0 : 1;
}
