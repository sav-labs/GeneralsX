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

// GeneralsX @performance Claude 16/10/2026 Per instance cache of CPU skinned vertices.
//
// W3D skins are deformed on the CPU every time they are drawn: every vertex is transformed by the world
// transform of its bone (MeshGeometryClass::get_deformed_vertices). A 5-15k triangle unit model has 3-10k
// vertices, so a big battle spends most of its mesh time re-skinning units whose bones did not move (idle,
// garrisoned, waiting units and the same pose drawn twice in one frame for reflections or shadow textures).
//
// The cache keeps the deformed positions and normals of one mesh instance together with the bone
// transforms they were made from, limited to the bones the mesh's vertices actually use. When every one of
// those transforms is bit-for-bit equal, the stored vertices are exactly what skinning would produce, so the
// caller uses them and skips the transform. Rendering only; the game logic never reads skinned vertices.
//
// Header only, with the matrix and vector types as template parameters, so the regression test in
// scripts/qa/perf builds it without the engine.

#pragma once

#include <string.h>

template <class MatrixT, class VectorT>
class SkinPoseCacheT
{
public:
	SkinPoseCacheT() :
		ModelKey(nullptr),
		TreeKey(nullptr),
		VertexCount(0),
		BoneCount(0),
		Bones(nullptr),
		Pose(nullptr),
		Vertices(nullptr),
		Normals(nullptr),
		Valid(false),
		HasNormals(false)
	{
	}

	~SkinPoseCacheT()
	{
		Free();
	}

	/// Forget the stored pose; the next lookup misses.
	void Invalidate()
	{
		Valid = false;
	}

	/// Ties the cache to a model (any pointer that identifies the source vertices) and its vertex to bone
	/// links. Rebuilds the list of used bones and the storage when the model or its vertex count changes.
	void Bind(const void *model_key, const unsigned short *bone_links, int vertex_count)
	{
		if (model_key == ModelKey && vertex_count == VertexCount && Vertices != nullptr)
			return;

		Free();
		ModelKey = model_key;
		VertexCount = vertex_count;
		if (vertex_count <= 0 || bone_links == nullptr)
			return;

		int max_bone = 0;
		for (int i = 0; i < vertex_count; ++i)
		{
			if (bone_links[i] > max_bone)
				max_bone = bone_links[i];
		}
		unsigned char *used = new unsigned char[max_bone + 1];
		memset(used, 0, max_bone + 1);
		int count = 0;
		for (int i = 0; i < vertex_count; ++i)
		{
			if (!used[bone_links[i]])
			{
				used[bone_links[i]] = 1;
				++count;
			}
		}
		Bones = new unsigned short[count];
		BoneCount = 0;
		for (int b = 0; b <= max_bone; ++b)
		{
			if (used[b])
				Bones[BoneCount++] = (unsigned short)b;
		}
		delete [] used;

		Pose = new MatrixT[BoneCount];
		Vertices = new VectorT[vertex_count];
	}

	bool Is_Bound() const { return Vertices != nullptr; }

	/// True when the stored vertices were made from exactly the current transforms of the used bones.
	/// BoneSourceT needs Get_Transform(int) returning a MatrixT (HTreeClass does).
	template <class BoneSourceT>
	bool Matches(const void *tree_key, const BoneSourceT &bones, bool need_normals) const
	{
		if (!Valid || tree_key != TreeKey || (need_normals && !HasNormals))
			return false;
		for (int i = 0; i < BoneCount; ++i)
		{
			if (memcmp(&Pose[i], &bones.Get_Transform(Bones[i]), sizeof(MatrixT)) != 0)
				return false;
		}
		return true;
	}

	/// Storage the caller skins into on a miss, then calls Store_Pose.
	VectorT *Peek_Vertices() { return Vertices; }
	VectorT *Peek_Normals()
	{
		if (Normals == nullptr && VertexCount > 0)
			Normals = new VectorT[VertexCount];
		return Normals;
	}

	template <class BoneSourceT>
	void Store_Pose(const void *tree_key, const BoneSourceT &bones, bool has_normals)
	{
		TreeKey = tree_key;
		for (int i = 0; i < BoneCount; ++i)
			memcpy(&Pose[i], &bones.Get_Transform(Bones[i]), sizeof(MatrixT));
		HasNormals = has_normals;
		Valid = true;
	}

	int Get_Bone_Count() const { return BoneCount; }

private:
	void Free()
	{
		delete [] Bones;
		delete [] Pose;
		delete [] Vertices;
		delete [] Normals;
		Bones = nullptr;
		Pose = nullptr;
		Vertices = nullptr;
		Normals = nullptr;
		BoneCount = 0;
		ModelKey = nullptr;
		TreeKey = nullptr;
		VertexCount = 0;
		Valid = false;
		HasNormals = false;
	}

	SkinPoseCacheT(const SkinPoseCacheT &);
	SkinPoseCacheT &operator=(const SkinPoseCacheT &);

	const void *ModelKey;
	const void *TreeKey;
	int VertexCount;
	int BoneCount;
	unsigned short *Bones;
	MatrixT *Pose;
	VectorT *Vertices;
	VectorT *Normals;
	bool Valid;
	bool HasNormals;
};
