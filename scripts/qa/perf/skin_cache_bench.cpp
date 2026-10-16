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

// GeneralsX @performance Claude 16/10/2026 Regression test and microbenchmark for the skin cache
// (Core/Libraries/Source/WWVegas/WW3D2/skinposecache.h). Builds without the engine:
//   scripts/qa/perf/run-skin-cache-bench.sh
// A synthetic 15k triangle skin (8000 vertices, 24 bones, rigid one-bone-per-vertex like W3D skins) is drawn by
// 60 units for 300 frames in three phases: all idle, a third animated, all animated. The test checks that idle
// units hit the cache, that any moved bone used by the mesh misses, that a moved bone the mesh does not use
// still hits, and that cached vertices are bit-identical to freshly skinned ones. Exit code 0 = pass.

#include "skinposecache.h"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

namespace
{
	struct Vec3
	{
		float X, Y, Z;
	};

	struct Mat34
	{
		float Row[3][4];
	};

	struct Skeleton
	{
		std::vector<Mat34> Bones;
		const Mat34 &Get_Transform(int bone) const { return Bones[bone]; }
	};

	struct SkinModel
	{
		std::vector<Vec3> Vertices;
		std::vector<Vec3> Normals;
		std::vector<unsigned short> BoneLinks;
	};

	void Transform(const Mat34 &m, const Vec3 &v, Vec3 &out, bool translate)
	{
		const float w = translate ? 1.0f : 0.0f;
		out.X = m.Row[0][0] * v.X + m.Row[0][1] * v.Y + m.Row[0][2] * v.Z + m.Row[0][3] * w;
		out.Y = m.Row[1][0] * v.X + m.Row[1][1] * v.Y + m.Row[1][2] * v.Z + m.Row[1][3] * w;
		out.Z = m.Row[2][0] * v.X + m.Row[2][1] * v.Y + m.Row[2][2] * v.Z + m.Row[2][3] * w;
	}

	// Same shape as MeshGeometryClass::get_deformed_vertices: every vertex by its bone's world transform.
	void Skin(const SkinModel &model, const Skeleton &skeleton, Vec3 *verts, Vec3 *norms)
	{
		const size_t count = model.Vertices.size();
		for (size_t i = 0; i < count; ++i)
		{
			const Mat34 &m = skeleton.Get_Transform(model.BoneLinks[i]);
			Transform(m, model.Vertices[i], verts[i], true);
			Transform(m, model.Normals[i], norms[i], false);
		}
	}

	Mat34 MakeBone(float angle, float x, float y, float z)
	{
		Mat34 m;
		const float c = std::cos(angle);
		const float s = std::sin(angle);
		const float r[3][4] = { { c, -s, 0.0f, x }, { s, c, 0.0f, y }, { 0.0f, 0.0f, 1.0f, z } };
		std::memcpy(m.Row, r, sizeof(r));
		return m;
	}

	typedef SkinPoseCacheT<Mat34, Vec3> Cache;

	struct Unit
	{
		Skeleton Pose;
		Cache SkinCache;
		float Phase;
		bool Animated;
	};

	int g_failures = 0;

	void Check(bool condition, const char *what)
	{
		if (!condition)
		{
			std::printf("FAIL: %s\n", what);
			++g_failures;
		}
	}
}

int main(int argc, char **argv)
{
	const int kVertices = 8000;    // about 15k triangles
	const int kBones = 24;
	const int kUnusedBone = kBones; // a bone in the tree that no vertex uses (a turret or muzzle helper)
	const int kUnits = argc > 1 ? std::atoi(argv[1]) : 60;
	const int kFrames = 300;

	SkinModel model;
	model.Vertices.resize(kVertices);
	model.Normals.resize(kVertices);
	model.BoneLinks.resize(kVertices);
	std::srand(1234);
	for (int i = 0; i < kVertices; ++i)
	{
		model.Vertices[i].X = (float)(std::rand() % 2000) * 0.01f - 10.0f;
		model.Vertices[i].Y = (float)(std::rand() % 2000) * 0.01f - 10.0f;
		model.Vertices[i].Z = (float)(std::rand() % 1000) * 0.01f;
		model.Normals[i].X = 0.0f;
		model.Normals[i].Y = 0.0f;
		model.Normals[i].Z = 1.0f;
		model.BoneLinks[i] = (unsigned short)((i * kBones) / kVertices);	// sorted by bone, as W3D exports them
	}

	std::vector<Unit> units(kUnits);
	for (int u = 0; u < kUnits; ++u)
	{
		units[u].Pose.Bones.resize(kBones + 1);
		for (int b = 0; b <= kBones; ++b)
			units[u].Pose.Bones[b] = MakeBone(0.1f * b, (float)u * 30.0f, 0.0f, 0.0f);
		units[u].Phase = 0.0f;
		units[u].Animated = false;
	}

	std::vector<Vec3> scratchVerts(kVertices);
	std::vector<Vec3> scratchNorms(kVertices);

	// Correctness: hit, miss on a used bone, hit on an unused bone, bit-identical output.
	{
		Unit &unit = units[0];
		unit.SkinCache.Bind(&model, &model.BoneLinks[0], kVertices);
		Check(unit.SkinCache.Get_Bone_Count() == kBones, "used bone list has every linked bone and nothing else");
		Check(!unit.SkinCache.Matches(&unit.Pose, unit.Pose, true), "empty cache misses");
		Skin(model, unit.Pose, unit.SkinCache.Peek_Vertices(), unit.SkinCache.Peek_Normals());
		unit.SkinCache.Store_Pose(&unit.Pose, unit.Pose, true);
		Check(unit.SkinCache.Matches(&unit.Pose, unit.Pose, true), "same pose hits");

		unit.Pose.Bones[kUnusedBone] = MakeBone(1.0f, 5.0f, 5.0f, 5.0f);
		Check(unit.SkinCache.Matches(&unit.Pose, unit.Pose, true), "moving a bone no vertex uses still hits");

		unit.Pose.Bones[kBones / 2].Row[1][3] += 0.001f;
		Check(!unit.SkinCache.Matches(&unit.Pose, unit.Pose, true), "moving a used bone misses");
		Skin(model, unit.Pose, unit.SkinCache.Peek_Vertices(), unit.SkinCache.Peek_Normals());
		unit.SkinCache.Store_Pose(&unit.Pose, unit.Pose, true);

		Skin(model, unit.Pose, &scratchVerts[0], &scratchNorms[0]);
		Check(std::memcmp(&scratchVerts[0], unit.SkinCache.Peek_Vertices(), sizeof(Vec3) * kVertices) == 0,
			"cached positions are bit-identical to skinning again");
		Check(std::memcmp(&scratchNorms[0], unit.SkinCache.Peek_Normals(), sizeof(Vec3) * kVertices) == 0,
			"cached normals are bit-identical to skinning again");

		Check(!unit.SkinCache.Matches(&units[1].Pose, unit.Pose, true), "another skeleton misses");
		unit.SkinCache.Invalidate();
		Check(!unit.SkinCache.Matches(&unit.Pose, unit.Pose, true), "invalidated cache misses");

		SkinModel other = model;
		unit.SkinCache.Bind(&other, &other.BoneLinks[0], kVertices);
		Check(!unit.SkinCache.Matches(&unit.Pose, unit.Pose, true), "binding another model resets the cache");
	}

	// Benchmark: per frame every unit is drawn; animated units move their bones every frame.
	struct Phase
	{
		const char *name;
		int animatedEvery;	// 0 = none, 3 = a third, 1 = all
	};
	const Phase phases[] = { { "idle", 0 }, { "third animated", 3 }, { "all animated", 1 } };

	double uncachedMs = 0.0;
	for (int p = 0; p < 3; ++p)
	{
		for (int u = 0; u < kUnits; ++u)
		{
			units[u].Animated = phases[p].animatedEvery != 0 && (u % phases[p].animatedEvery) == 0;
			units[u].SkinCache.Invalidate();
		}

		long hits = 0;
		long misses = 0;
		volatile float sink = 0.0f;
		const auto start = std::chrono::steady_clock::now();
		for (int frame = 0; frame < kFrames; ++frame)
		{
			for (int u = 0; u < kUnits; ++u)
			{
				Unit &unit = units[u];
				if (unit.Animated)
				{
					unit.Phase += 0.05f;
					for (int b = 0; b < kBones; ++b)
						unit.Pose.Bones[b] = MakeBone(0.1f * b + std::sin(unit.Phase + b), (float)u * 30.0f, 0.0f, 0.0f);
				}
				unit.SkinCache.Bind(&model, &model.BoneLinks[0], kVertices);
				if (unit.SkinCache.Matches(&unit.Pose, unit.Pose, true))
				{
					++hits;
				}
				else
				{
					++misses;
					Skin(model, unit.Pose, unit.SkinCache.Peek_Vertices(), unit.SkinCache.Peek_Normals());
					unit.SkinCache.Store_Pose(&unit.Pose, unit.Pose, true);
				}
				sink = sink + unit.SkinCache.Peek_Vertices()[frame % kVertices].X;
			}
		}
		const double cachedMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count();

		// The same work without the cache: skin every unit every frame.
		const auto startRaw = std::chrono::steady_clock::now();
		for (int frame = 0; frame < kFrames; ++frame)
		{
			for (int u = 0; u < kUnits; ++u)
			{
				Skin(model, units[u].Pose, &scratchVerts[0], &scratchNorms[0]);
				sink = sink + scratchVerts[frame % kVertices].X;
			}
		}
		uncachedMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - startRaw).count();

		std::printf("%-15s units=%d frames=%d hits=%ld misses=%ld  cached %.3f ms/frame  uncached %.3f ms/frame  (%.1fx)\n",
			phases[p].name, kUnits, kFrames, hits, misses, cachedMs / kFrames, uncachedMs / kFrames,
			cachedMs > 0.0 ? uncachedMs / cachedMs : 0.0);

		int animatedUnits = 0;
		for (int u = 0; u < kUnits; ++u)
			animatedUnits += units[u].Animated ? 1 : 0;
		const long expectedMisses = (long)animatedUnits * kFrames + (kUnits - animatedUnits);
		Check(misses == expectedMisses, "misses are exactly the first frame of idle units plus every animated frame");
		Check(hits + misses == (long)kUnits * kFrames, "every draw is a hit or a miss");
		(void)sink;
	}

	if (g_failures == 0)
		std::printf("PASS\n");
	return g_failures == 0 ? 0 : 1;
}
