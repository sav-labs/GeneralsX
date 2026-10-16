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

// GeneralsX @feature Claude 16/10/2026 Per pixel normal and gloss maps for unit and building models.
//
// A mesh texture "foo.tga" (or foo.dds) gets a normal map when "foo_n.dds" or "foo_n.tga" exists in the
// texture search paths (loose files or .big archives). The map is tangent space, OpenGL orientation (green
// = up, Y+), with the gloss / specular strength in its alpha channel.
//
// Meshes whose first pass uses such a texture get a tangent channel in their vertex buffer: one more 2 float
// texture coordinate set holding the tangent relative to a basis built from the vertex normal (see
// Pack_Tangent). CPU skinned meshes carry it in their (unused) second UV set, rotated by the vertex's bone
// every frame. Draws of those meshes use a vs.1.1 + ps.1.4 pair that rebuilds the fixed function lighting
// from the current device state (material, colour sources, lights, ambient, fog, stage 0 texture
// transform): the two strongest directional lights (sun and its first fill light) are applied per pixel
// with the normal map plus a specular highlight from the gloss, the remaining lights (effect / point lights
// and a third directional light) per vertex as before.
//
// Meshes without a _n texture keep their vertex format and the fixed function pipeline, so retail assets
// render exactly as before. Options.ini ModelNormalMaps = yes turns the feature on (default no), ModelSpecular
// (0..2, default 1) scales the highlight. Rendering only: nothing here is read by the game logic.

#pragma once

#include "WWLib/always.h"
#include "WWMath/vector3.h"
#include "WWMath/vector4.h"

class TextureClass;
class MeshModelClass;

class ModelNormalMapClass
{
public:
	static void Set_Enabled(bool onoff) { Enabled = onoff; }
	static bool Is_Enabled() { return Enabled; }
	/// Specular strength, 0 (none) .. 2; 1 is the default.
	static void Set_Specular(float strength);
	static float Get_Specular() { return Specular; }

	/// Normal map of a base texture, or null. Looked up once per texture; mesh_name is only used for the log.
	static TextureClass * Peek_Normal_Map(TextureClass * base, const char * mesh_name);

	/// TRUE when a rigid mesh model should get a tangent channel in its vertex buffer.
	static bool Mesh_Wants_Tangents(MeshModelClass * mmc);
	/// The FVF with one more 2 float texture coordinate set (the tangent channel) appended.
	static unsigned Add_Tangent_Channel(unsigned fvf);
	/// Writes the packed tangent of every vertex of a rigid mesh into texture coordinate set 'set' of a
	/// vertex array (stride in bytes, offset of that set in bytes).
	static void Write_Rigid_Tangents(MeshModelClass * mmc, unsigned char * vertices, unsigned stride, unsigned offset);

	/// Bind pose tangents (xyz, w = bitangent sign) of a skinned mesh model, or null when it is not normal
	/// mapped or needs its second UV set. Computed on first use.
	static const Vector4 * Peek_Skin_Tangents(MeshModelClass * mmc);
	/// Drops what is kept for a mesh model (it is being unregistered or deleted).
	static void Forget_Mesh(MeshModelClass * mmc);

	/// Packs a unit tangent into two floats relative to the basis the vertex shader builds from 'normal'
	/// (the normal exactly as it is in the vertex buffer). A negative bitangent sign doubles the length.
	static void Pack_Tangent(const Vector3 & normal, const Vector3 & tangent, float sign, float & a, float & b);

	/// Sets up the normal map shaders for the next draw from the current device state. Returns false and
	/// changes nothing when that state cannot be reproduced; the caller then draws with fixed function.
	static bool Begin(TextureClass * normal_map);
	/// Restores the fixed function state after a draw started with Begin.
	static void End();

	/// Releases the shaders and the kept tangents (device shutdown).
	static void Shutdown();

private:
	static bool Enabled;
	static float Specular;
};
