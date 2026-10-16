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

// FILE: W3DTerrainDetail.h ///////////////////////////////////////////////////
//
// GeneralsX @feature Claude 16/10/2026 Close-up terrain detail for the 3D height map.
//
// One ps.1.4 pixel shader replaces the retail terrain shaders (terrain*.pso) and adds, in the same single pass:
//  - Detail (Options.ini TerrainDetail, TerrainDetailStrength): a procedural, tileable 1024x1024 detail texture
//    mapped in world space (one repeat per 64 world units, turned against the cell grid) modulates the ground
//    colour. Its mip levels fade to neutral grey, so it fades out with distance on its own.
//  - Relief (TerrainRelief): when the 32 bit terrain atlas is built, a height field is derived from each texture
//    class's luminance, lit by the map's GlobalLighting lights and stored as a shade factor in the atlas alpha
//    channel (unused by the retail single pass shader). The shade is normalised to an average of 1 per texture
//    class and faded out in the smaller atlas mips, so the far view keeps the retail lighting.
//  - Soft blend (TerrainSoftBlend): the per vertex alpha between two terrain layers is reshaped with a world
//    space noise (detail texture alpha), giving irregular, natural edges instead of straight one-cell ramps.
// The three-texture blend tiles get the same treatment with a second shader.
//
// All options off, a device without ps.1.4 or a 16 bit atlas for relief keeps the retail path or retail values.
// Rendering only: nothing here is read by the game logic.

#pragma once

#include "Lib/BaseType.h"
#include "WW3D2/texture.h"
#include "d3dx8math.h"

class W3DTerrainDetail
{
public:
	/// Creates the pixel shaders and textures when an option asks for them and the device has ps.1.4.
	/// Returns TRUE when the detail terrain shader can be used.
	static Bool init();
	static void shutdown();
	static Bool isActive();

	/// TRUE when a new 32 bit terrain atlas should get relief in its alpha channel.
	static Bool wantsReliefInAtlas();
	/// Relief for one texture class: a square of size x size 32 bit texels at (x0, y0), wrapping at its edges.
	static void bakeReliefRegion(UnsignedByte *bits, Int pitchBytes, Int x0, Int y0, Int size);
	/// Fades the relief out in the smaller mips of a finished atlas and records which lights it was baked with.
	static void finishReliefAtlas(IDirect3DTexture8 *atlas, Bool baked);
	/// TRUE when the lights moved since the atlas relief was baked (time of day changed).
	static Bool reliefNeedsRebake();

	/// Sets up the terrain stages, constants and shader. cloud and lightMap may be null (white is used).
	/// The matrices are the texture transforms for camera space positions, viewInverse is the inverse view.
	static void apply(Bool extraBlendTiles, TextureClass *atlas, TextureClass *cloud, TextureClass *lightMap,
		const D3DXMATRIX *cloudMatrix, const D3DXMATRIX *lightMapMatrix, const D3DXMATRIX &viewInverse);
	static void reset();
};
