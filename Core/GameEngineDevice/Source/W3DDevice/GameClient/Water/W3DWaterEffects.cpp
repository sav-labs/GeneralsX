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

// FILE: W3DWaterEffects.cpp //////////////////////////////////////////////////////////////////////
// GeneralsX @feature Claude 16/10/2026 Modern water effects for standing water and rivers.
//
// Retail Zero Hour draws standing water and rivers as flat translucent polygons: no reflections, and a hard
// line where the water plane cuts the terrain. This file adds, all render only and all fixed function so it
// runs on every D3D8 device and through DXVK:
//
//  1. Planar reflections (Options.ini WaterReflections = Off | Sky | Full, WaterReflectionScale). Before the
//     main scene, the water plane in view is found and the scene is drawn mirrored across it into a texture of
//     WaterReflectionScale times the 3D view size. Only the part of the screen the water covers is drawn, the
//     camera's near plane is tilted onto the water plane (oblique clipping) so the lake bed and anything under
//     the water stay out of the mirror, and a static camera refreshes the mirror every other frame. The water
//     then blends the texture in with a projective texture stage; the blend follows a Fresnel curve over the
//     view angle (stronger at grazing angles), so the far side of a lake reflects more than the shore below
//     the camera. Sky draws only the cloud layer into the mirror.
//  2. Shoreline foam and a soft shoreline (Options.ini ShoreFoam). When a map loads, the water depth (water
//     plane height minus terrain height) is sampled at twice the height map resolution into a texture that
//     covers the map: its alpha fades the water in over the first few units of depth, so the shore no longer
//     ends in a hard cut, and its colour holds a foam band along the waterline. A foam pass draws two
//     slowly drifting layers of an original procedural foam pattern through that band.
//  3. Waves (Options.ini WaterWaves). A looping du/dv animation made of two wave layers that travel in
//     different directions perturbs the reflection and the foam through a bump environment map stage.
//
// All textures are generated at start up; nothing is loaded from the retail archives. The retail water
// passes are unchanged, the effects are extra passes over the same polygons, and WaterReflections = Off,
// ShoreFoam = no and WaterWaves = no give the retail picture.
///////////////////////////////////////////////////////////////////////////////////////////////////

#include "W3DDevice/GameClient/W3DWater.h"
#include "W3DDevice/GameClient/HeightMap.h"
#include "W3DDevice/GameClient/W3DShroud.h"
#include "W3DDevice/GameClient/W3DShaderManager.h"
#include "W3DDevice/GameClient/W3DPoly.h"
#include "W3DDevice/GameClient/WorldHeightMap.h"
#include "WW3D2/camera.h"
#include "WW3D2/dx8caps.h"
#include "WW3D2/dx8wrapper.h"
#include "WW3D2/scene.h"
#include "WW3D2/texture.h"
#include "WW3D2/vertmaterial.h"
#include "WW3D2/ww3d.h"
#include "WWMath/plane.h"
#include "d3dx8math.h"

#include "Common/GameCommon.h"
#include "Common/GlobalData.h"
#include "Common/MapObject.h"
#include "Common/OptionPreferences.h"
#include "Common/PerfStats.h"
#include "GameClient/Water.h"
#include "GameLogic/PolygonTrigger.h"

#include <math.h>
#include <stdint.h>
#include <string.h>
#include <vector>
#include <algorithm>

namespace
{
	// Texture sizes of the generated textures.
	const Int FRESNEL_TEXTURE_SIZE = 64;
	const Int FOAM_TEXTURE_SIZE = 256;
	const Int WAVE_TEXTURE_SIZE = 64;
	const Int SHORE_TEXTURE_MAX = 2048;

	// The shore texture samples the water depth at twice the height map resolution.
	const Real SHORE_TEXEL_WORLD = MAP_XY_FACTOR * 0.5f;
	// Water fades in over this many world units of depth (the soft shoreline).
	const Real SOFT_SHORE_DEPTH = 5.0f;
	// The foam band: it rises over the first FOAM_RISE_DEPTH units of depth, holds, then fades out between
	// FOAM_FADE_START and FOAM_FADE_END units.
	const Real FOAM_RISE_DEPTH = 0.8f;
	const Real FOAM_FADE_START = 1.5f;
	const Real FOAM_FADE_END = 7.0f;
	// The shore texture is rebuilt at most once a second while scripts move the water.
	const Int SHORE_REBUILD_INTERVAL_MS = 1000;

	// World units covered by one repeat of the foam and wave textures.
	const Real FOAM_TILE_WORLD = 110.0f;
	const Real WAVE_TILE_WORLD = 64.0f;
	// Bump environment map scale: offset of the reflection texture coordinates (a fraction of the screen) and
	// of the foam texture coordinates at the steepest wave slope.
	const Real WAVE_REFLECTION_DISTORTION = 0.012f;
	const Real WAVE_FOAM_DISTORTION = 0.05f;
	// Wave animation frames per second; WATER_WAVE_FRAMES frames make one loop.
	const Real WAVE_FRAMES_PER_SECOND = 10.0f;

	// Fresnel curve of the reflection: F(c) = FRESNEL_MIN + FRESNEL_RANGE * (1 - c)^FRESNEL_POWER over the cosine
	// c of the angle between the view ray and the water normal. Retail camera angles give c from about 0.3
	// (top of the screen) to 0.8 (bottom), so the reflection runs from about 0.4 down to 0.15.
	const Real FRESNEL_MIN = 0.12f;
	const Real FRESNEL_RANGE = 0.6f;
	const Real FRESNEL_POWER = 2.0f;
	// Strength of the sky only reflection, which has no scene to anchor it and reads better a little weaker.
	const Real SKY_REFLECTION_STRENGTH = 0.8f;
	// Water whose height differs from the mirrored plane by this much gets no reflection (it fades out
	// linearly before that), since its reflection would be offset by twice the difference.
	const Real REFLECTION_HEIGHT_FADE = 24.0f;
	// The mirror keeps geometry from this far below the water plane, so objects standing in the water
	// still meet their reflection.
	const Real REFLECTION_CLIP_BIAS = 1.0f;
	// Screen margin (in normalized device units) drawn around the water so the wave distortion never
	// samples outside the drawn part of the reflection texture.
	const Real REFLECTION_SCREEN_MARGIN = 0.06f;
	// The cloud layer reflected in the water floats this high above it (well inside the far clip plane).
	const Real REFLECTION_SKY_HEIGHT = 150.0f;
	const Real REFLECTION_SKY_SIZE = 6000.0f;
	// A static camera refreshes the reflection every this many frames.
	const Int REFLECTION_STATIC_INTERVAL = 2;

	// Colour of the foam before the time of day lighting, and its overall strength.
	const Real FOAM_STRENGTH = 0.75f;

	inline Real smoothStep(Real edge0, Real edge1, Real x)
	{
		Real t = (x - edge0) / (edge1 - edge0);
		if (t < 0.0f) t = 0.0f;
		if (t > 1.0f) t = 1.0f;
		return t * t * (3.0f - 2.0f * t);
	}

	inline Real clamp01(Real x)
	{
		return x < 0.0f ? 0.0f : (x > 1.0f ? 1.0f : x);
	}

	inline DWORD floatToDword(Real f)
	{
		DWORD d;
		memcpy(&d, &f, sizeof(d));
		return d;
	}

	// Integer hash for the procedural textures (deterministic on every platform).
	inline UnsignedInt hashCell(Int x, Int y, UnsignedInt seed)
	{
		UnsignedInt h = (UnsignedInt)x * 374761393u + (UnsignedInt)y * 668265263u + seed * 2246822519u;
		h = (h ^ (h >> 13)) * 1274126177u;
		return h ^ (h >> 16);
	}

	inline Real hashUnit(Int x, Int y, UnsignedInt seed)
	{
		return (Real)(hashCell(x, y, seed) & 0xffffff) / 16777216.0f;
	}

	inline Int wrapIndex(Int i, Int period)
	{
		i %= period;
		return i < 0 ? i + period : i;
	}

	// Tiling value noise with the given number of cells across the unit square.
	Real tileValueNoise(Real u, Real v, Int period, UnsignedInt seed)
	{
		const Real x = u * period;
		const Real y = v * period;
		const Int x0 = (Int)floorf(x);
		const Int y0 = (Int)floorf(y);
		const Real fx = smoothStep(0.0f, 1.0f, x - x0);
		const Real fy = smoothStep(0.0f, 1.0f, y - y0);
		const Real a = hashUnit(wrapIndex(x0, period), wrapIndex(y0, period), seed);
		const Real b = hashUnit(wrapIndex(x0 + 1, period), wrapIndex(y0, period), seed);
		const Real c = hashUnit(wrapIndex(x0, period), wrapIndex(y0 + 1, period), seed);
		const Real d = hashUnit(wrapIndex(x0 + 1, period), wrapIndex(y0 + 1, period), seed);
		return (a + (b - a) * fx) * (1.0f - fy) + (c + (d - c) * fx) * fy;
	}

	// Tiling cellular noise: distance to the nearest (f1) and second nearest (f2) feature point, in cells.
	void tileCellNoise(Real u, Real v, Int period, UnsignedInt seed, Real *f1, Real *f2)
	{
		const Real x = u * period;
		const Real y = v * period;
		const Int cx = (Int)floorf(x);
		const Int cy = (Int)floorf(y);
		Real d1 = 1.0e9f;
		Real d2 = 1.0e9f;
		for (Int j = -1; j <= 1; ++j)
		{
			for (Int i = -1; i <= 1; ++i)
			{
				const Int gx = cx + i;
				const Int gy = cy + j;
				const Int wx = wrapIndex(gx, period);
				const Int wy = wrapIndex(gy, period);
				const Real px = gx + 0.15f + 0.7f * hashUnit(wx, wy, seed);
				const Real py = gy + 0.15f + 0.7f * hashUnit(wx, wy, seed + 17u);
				const Real d = sqrtf((px - x) * (px - x) + (py - y) * (py - y));
				if (d < d1)
				{
					d2 = d1;
					d1 = d;
				}
				else if (d < d2)
				{
					d2 = d;
				}
			}
		}
		*f1 = d1;
		*f2 = d2;
	}

	inline Real wrapUnit(Real x)
	{
		return x - floorf(x);
	}

	// Foam pattern at texture coordinate (u, v) in [0, 1): a lace of thin, curving filaments (the borders of a
	// domain warped cellular pattern, of varying width) over soft patches, with small bubbles punched in.
	Real foamPattern(Real u, Real v)
	{
		const Real wu = u + 0.06f * (tileValueNoise(u, v, 7, 41u) - 0.5f) + 0.03f * (tileValueNoise(u, v, 17, 45u) - 0.5f);
		const Real wv = v + 0.06f * (tileValueNoise(u, v, 7, 43u) - 0.5f) + 0.03f * (tileValueNoise(u, v, 17, 47u) - 0.5f);
		const Real fbm = 0.5f * tileValueNoise(u, v, 4, 5u) + 0.3f * tileValueNoise(u, v, 8, 7u) + 0.2f * tileValueNoise(u, v, 16, 13u);
		Real g1, g2;
		tileCellNoise(wrapUnit(wu), wrapUnit(wv), 10, 23u, &g1, &g2);
		const Real widthNoise = tileValueNoise(u, v, 8, 51u);
		const Real lace = 1.0f - smoothStep(0.0f, 0.05f + 0.30f * widthNoise * widthNoise, g2 - g1);
		Real f1, f2;
		tileCellNoise(u, v, 28, 11u, &f1, &f2);
		const Real bubbles = smoothStep(0.08f, 0.38f, f1 + 0.3f * (tileValueNoise(u, v, 28, 61u) - 0.5f));
		const Real patch = smoothStep(0.30f, 0.72f, fbm);
		const Real value = (0.5f * lace + 0.6f * patch) * (0.85f + 0.15f * bubbles) + 0.05f;
		return clamp01(value);
	}

	// Height of the wave field at (u, v) in [0, 1) and animation phase t in [0, 1). Each layer is a sum of
	// sines with integer wave numbers (so the texture tiles) and integer temporal frequencies (so the
	// animation loops). Layer A travels roughly east, layer B roughly north-west.
	struct WaveComponent { Int kx, ky, cycles; Real amplitude, phase; };
	const WaveComponent WAVE_COMPONENTS[] =
	{
		// layer A
		{ 3, 1, 1, 1.00f, 0.0f },
		{ 5, 2, 2, 0.55f, 1.3f },
		{ 7, -1, 3, 0.35f, 2.1f },
		// layer B
		{ -1, 4, 1, 0.80f, 0.7f },
		{ -3, 5, 2, 0.45f, 2.9f },
		{ -2, 9, 3, 0.25f, 4.4f },
	};

	void waveSlope(Real u, Real v, Real t, Real *du, Real *dv)
	{
		const Real twoPi = 2.0f * PI;
		Real sx = 0.0f;
		Real sy = 0.0f;
		Real norm = 0.0f;
		for (Int i = 0; i < (Int)(sizeof(WAVE_COMPONENTS) / sizeof(WAVE_COMPONENTS[0])); ++i)
		{
			const WaveComponent &w = WAVE_COMPONENTS[i];
			const Real arg = twoPi * (w.kx * u + w.ky * v - w.cycles * t) + w.phase;
			// The slope grows with the wave number; divide it out partly so short waves stay subtle.
			const Real k = sqrtf((Real)(w.kx * w.kx + w.ky * w.ky));
			const Real c = w.amplitude * cosf(arg) / sqrtf(k);
			sx += c * w.kx;
			sy += c * w.ky;
			norm += w.amplitude * sqrtf(k);
		}
		*du = sx / norm * 2.2f;
		*dv = sy / norm * 2.2f;
	}

	// Combines a 4x4 D3D matrix (row vector convention, m[row][col]) with another: out = a * b.
	void multiplyD3D(Real out[4][4], const Real a[4][4], const Real b[4][4])
	{
		Real r[4][4];
		for (Int i = 0; i < 4; ++i)
			for (Int j = 0; j < 4; ++j)
				r[i][j] = a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j] + a[i][3] * b[3][j];
		memcpy(out, r, sizeof(r));
	}

	void setTextureTransform(Int stage, const Real m[4][4])
	{
		Matrix4x4 tm;
		memcpy(&tm, m, sizeof(Real) * 16);
		DX8Wrapper::_Set_DX8_Transform((D3DTRANSFORMSTATETYPE)(D3DTS_TEXTURE0 + stage), tm);
	}

	void setStageOps(Int stage, DWORD colorOp, DWORD colorArg1, DWORD colorArg2, DWORD alphaOp, DWORD alphaArg1, DWORD alphaArg2)
	{
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_COLOROP, colorOp);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_COLORARG1, colorArg1);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_COLORARG2, colorArg2);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_ALPHAOP, alphaOp);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_ALPHAARG1, alphaArg1);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_ALPHAARG2, alphaArg2);
	}

	void setStageSampler(Int stage, Bool wrap, Bool mipmaps)
	{
		const DWORD address = wrap ? D3DTADDRESS_WRAP : D3DTADDRESS_CLAMP;
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_ADDRESSU, address);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_ADDRESSV, address);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_MINFILTER, D3DTEXF_LINEAR);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_MAGFILTER, D3DTEXF_LINEAR);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_MIPFILTER, mipmaps ? D3DTEXF_LINEAR : D3DTEXF_NONE);
	}

	// Camera space position to world, then to texture space with a 2D rotation, scale and offset.
	void setWorldTexGenMatrix(Int stage, const Real invView[4][4], Real scaleX, Real scaleY, Real offsetU, Real offsetV, Real rotation)
	{
		const Real c = cosf(rotation);
		const Real s = sinf(rotation);
		Real affine[4][4] =
		{
			{ c * scaleX, s * scaleY, 0.0f, 0.0f },
			{ -s * scaleX, c * scaleY, 0.0f, 0.0f },
			{ 0.0f, 0.0f, 1.0f, 0.0f },
			{ offsetU, offsetV, 0.0f, 1.0f },
		};
		Real m[4][4];
		multiplyD3D(m, invView, affine);
		setTextureTransform(stage, m);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_TEXCOORDINDEX, D3DTSS_TCI_CAMERASPACEPOSITION);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_TEXTURETRANSFORMFLAGS, D3DTTFF_COUNT2);
	}

	void getInverseView(Real out[4][4])
	{
		Matrix4x4 view;
		DX8Wrapper::_Get_DX8_Transform(D3DTS_VIEW, view);
		D3DXMATRIX inv;
		float det;
		D3DXMatrixInverse(&inv, &det, (D3DXMATRIX *)&view);
		memcpy(out, &inv, sizeof(Real) * 16);
	}

	LPDIRECT3DTEXTURE8 createManagedTexture(Int width, Int height, Int levels, D3DFORMAT format)
	{
		IDirect3DDevice8 *device = DX8Wrapper::_Get_D3D_Device8();
		if (device == nullptr)
			return nullptr;
		LPDIRECT3DTEXTURE8 texture = nullptr;
		if (FAILED(device->CreateTexture(width, height, levels, 0, format, D3DPOOL_MANAGED, &texture)))
			return nullptr;
		return texture;
	}

	Int mipLevelCount(Int size)
	{
		Int levels = 1;
		while (size > 1)
		{
			size >>= 1;
			++levels;
		}
		return levels;
	}

	// Writes an A8R8G8B8 level from a float alpha/grey image and box filters it into the following levels.
	Bool fillGreyAlphaTexture(LPDIRECT3DTEXTURE8 texture, Int size, const std::vector<Real> &grey, const std::vector<Real> &alpha)
	{
		std::vector<Real> g(grey);
		std::vector<Real> a(alpha);
		const Int levels = (Int)texture->GetLevelCount();
		Int levelSize = size;
		for (Int level = 0; level < levels; ++level)
		{
			D3DLOCKED_RECT rect;
			if (FAILED(texture->LockRect(level, &rect, nullptr, 0)))
				return FALSE;
			for (Int y = 0; y < levelSize; ++y)
			{
				UnsignedInt *row = (UnsignedInt *)((UnsignedByte *)rect.pBits + y * rect.Pitch);
				for (Int x = 0; x < levelSize; ++x)
				{
					const UnsignedInt gv = (UnsignedInt)(clamp01(g[y * levelSize + x]) * 255.0f + 0.5f);
					const UnsignedInt av = (UnsignedInt)(clamp01(a[y * levelSize + x]) * 255.0f + 0.5f);
					row[x] = (av << 24) | (gv << 16) | (gv << 8) | gv;
				}
			}
			texture->UnlockRect(level);

			if (levelSize == 1)
				break;
			const Int next = levelSize / 2;
			std::vector<Real> ng(next * next);
			std::vector<Real> na(next * next);
			for (Int y = 0; y < next; ++y)
			{
				for (Int x = 0; x < next; ++x)
				{
					const Int i0 = (2 * y) * levelSize + 2 * x;
					const Int i1 = i0 + levelSize;
					ng[y * next + x] = 0.25f * (g[i0] + g[i0 + 1] + g[i1] + g[i1 + 1]);
					na[y * next + x] = 0.25f * (a[i0] + a[i0 + 1] + a[i1] + a[i1 + 1]);
				}
			}
			g.swap(ng);
			a.swap(na);
			levelSize = next;
		}
		return TRUE;
	}

	// Writes a V8U8 du/dv level from float slopes in [-1, 1] and box filters it into the following levels.
	Bool fillWaveTexture(LPDIRECT3DTEXTURE8 texture, Int size, const std::vector<Real> &du, const std::vector<Real> &dv)
	{
		std::vector<Real> u(du);
		std::vector<Real> v(dv);
		const Int levels = (Int)texture->GetLevelCount();
		Int levelSize = size;
		for (Int level = 0; level < levels; ++level)
		{
			D3DLOCKED_RECT rect;
			if (FAILED(texture->LockRect(level, &rect, nullptr, 0)))
				return FALSE;
			for (Int y = 0; y < levelSize; ++y)
			{
				signed char *row = (signed char *)((UnsignedByte *)rect.pBits + y * rect.Pitch);
				for (Int x = 0; x < levelSize; ++x)
				{
					Real cu = u[y * levelSize + x];
					Real cv = v[y * levelSize + x];
					cu = cu < -1.0f ? -1.0f : (cu > 1.0f ? 1.0f : cu);
					cv = cv < -1.0f ? -1.0f : (cv > 1.0f ? 1.0f : cv);
					// D3DFMT_V8U8: U in the low byte, V in the high byte.
					row[2 * x] = (signed char)(Int)floorf(cu * 127.0f + 0.5f);
					row[2 * x + 1] = (signed char)(Int)floorf(cv * 127.0f + 0.5f);
				}
			}
			texture->UnlockRect(level);

			if (levelSize == 1)
				break;
			const Int next = levelSize / 2;
			std::vector<Real> nu(next * next);
			std::vector<Real> nv(next * next);
			for (Int y = 0; y < next; ++y)
			{
				for (Int x = 0; x < next; ++x)
				{
					const Int i0 = (2 * y) * levelSize + 2 * x;
					const Int i1 = i0 + levelSize;
					nu[y * next + x] = 0.25f * (u[i0] + u[i0 + 1] + u[i1] + u[i1 + 1]);
					nv[y * next + x] = 0.25f * (v[i0] + v[i0 + 1] + v[i1] + v[i1 + 1]);
				}
			}
			u.swap(nu);
			v.swap(nv);
			levelSize = next;
		}
		return TRUE;
	}

	UnsignedInt hashCombine(UnsignedInt h, UnsignedInt value)
	{
		h ^= value + 0x9e3779b9u + (h << 6) + (h >> 2);
		return h;
	}

	// Terrain height at a world position, interpolated over the same triangles the terrain draws.
	Real sampleTerrainHeight(WorldHeightMap *map, Real x, Real y)
	{
		const Int border = map->getBorderSizeInline();
		const Int width = map->getXExtent();
		const Int height = map->getYExtent();
		const UnsignedByte *data = map->getDataPtr();

		Real gx = x / MAP_XY_FACTOR + border;
		Real gy = y / MAP_XY_FACTOR + border;
		if (gx < 0.0f) gx = 0.0f;
		if (gy < 0.0f) gy = 0.0f;
		if (gx > width - 1.001f) gx = width - 1.001f;
		if (gy > height - 1.001f) gy = height - 1.001f;
		const Int ix = (Int)gx;
		const Int iy = (Int)gy;
		const Real fx = gx - ix;
		const Real fy = gy - iy;
		const Int idx = ix + iy * width;
		const Real p0 = data[idx];
		const Real p2 = data[idx + width + 1];
		Real h;
		if (fy > fx)
		{
			const Real p3 = data[idx + width];
			h = p3 + (1.0f - fy) * (p0 - p3) + fx * (p2 - p3);
		}
		else
		{
			const Real p1 = data[idx + 1];
			h = p1 + fy * (p2 - p1) + (1.0f - fx) * (p0 - p1);
		}
		return h * MAP_HEIGHT_SCALE;
	}
}

Bool WaterRenderObjClass::s_drawingEffectReflection = FALSE;

//-------------------------------------------------------------------------------------------------
/** Options and generated textures. Called from init(). */
//-------------------------------------------------------------------------------------------------
void WaterRenderObjClass::initWaterEffects()
{
	// The World Builder has no scene to reflect and keeps the retail look.
	if (m_parentScene == nullptr)
	{
		m_effects.reflections = WATER_REFLECTIONS_OFF;
		m_effects.shoreFoam = FALSE;
		m_effects.waves = FALSE;
		m_effectsSupported = FALSE;
		return;
	}

	OptionPreferences prefs;
	m_effects.reflections = prefs.getWaterReflections();
	m_effects.reflectionScale = prefs.getWaterReflectionScale();
	m_effects.shoreFoam = prefs.getShoreFoamEnabled();
	m_effects.waves = prefs.getWaterWavesEnabled();

	m_effectsSupported = createWaterEffectTextures();

	static const char *const reflectionNames[] = { "Off", "Sky", "Full" };
	fprintf(stderr, "[WATER] reflections=%s scale=%.2f shore_foam=%s waves=%s%s\n",
		reflectionNames[m_effects.reflections], m_effects.reflectionScale,
		m_effects.shoreFoam ? "yes" : "no", m_effects.waves ? "yes" : "no",
		m_effectsSupported ? "" : " (not supported by the device, retail water)");
	fflush(stderr);
}

//-------------------------------------------------------------------------------------------------
/** Creates the Fresnel curve, foam and wave textures. Returns false when the device cannot draw the
	* effects (fewer than five texture stages); waves alone are dropped without bump mapping. */
//-------------------------------------------------------------------------------------------------
Bool WaterRenderObjClass::createWaterEffectTextures()
{
	if (m_effects.reflections == WATER_REFLECTIONS_OFF && !m_effects.shoreFoam)
		return TRUE;

	if (DX8Wrapper::_Get_D3D_Device8() == nullptr || DX8Wrapper::Get_Current_Caps() == nullptr)
		return FALSE;

	const DX8Caps *caps = DX8Wrapper::Get_Current_Caps();
	if (caps->Get_Max_Textures_Per_Pass() < 5)
		return FALSE;

	if (m_effects.waves && (!caps->Support_Bump_Envmap() || !caps->Support_Texture_Format(WW3D_FORMAT_U8V8)))
	{
		fprintf(stderr, "[WATER] no bump environment mapping, WaterWaves off\n");
		fflush(stderr);
		m_effects.waves = FALSE;
	}

	// Fresnel curve: alpha over the cosine of the view angle, white colour.
	if (m_effectFresnelTexture == nullptr)
	{
		m_effectFresnelTexture = createManagedTexture(FRESNEL_TEXTURE_SIZE, 1, 1, D3DFMT_A8R8G8B8);
		if (m_effectFresnelTexture == nullptr)
			return FALSE;
		std::vector<Real> grey(FRESNEL_TEXTURE_SIZE, 1.0f);
		std::vector<Real> alpha(FRESNEL_TEXTURE_SIZE);
		for (Int i = 0; i < FRESNEL_TEXTURE_SIZE; ++i)
		{
			const Real c = ((Real)i + 0.5f) / FRESNEL_TEXTURE_SIZE;
			alpha[i] = clamp01(FRESNEL_MIN + FRESNEL_RANGE * powf(1.0f - c, FRESNEL_POWER));
		}
		D3DLOCKED_RECT rect;
		if (FAILED(m_effectFresnelTexture->LockRect(0, &rect, nullptr, 0)))
			return FALSE;
		UnsignedInt *row = (UnsignedInt *)rect.pBits;
		for (Int i = 0; i < FRESNEL_TEXTURE_SIZE; ++i)
			row[i] = ((UnsignedInt)(alpha[i] * 255.0f + 0.5f) << 24) | 0x00ffffff;
		m_effectFresnelTexture->UnlockRect(0);
	}

	// Foam pattern with mip maps.
	if (m_effectFoamTexture == nullptr && m_effects.shoreFoam)
	{
		m_effectFoamTexture = createManagedTexture(FOAM_TEXTURE_SIZE, FOAM_TEXTURE_SIZE, mipLevelCount(FOAM_TEXTURE_SIZE), D3DFMT_A8R8G8B8);
		if (m_effectFoamTexture == nullptr)
			return FALSE;
		std::vector<Real> grey(FOAM_TEXTURE_SIZE * FOAM_TEXTURE_SIZE);
		for (Int y = 0; y < FOAM_TEXTURE_SIZE; ++y)
			for (Int x = 0; x < FOAM_TEXTURE_SIZE; ++x)
				grey[y * FOAM_TEXTURE_SIZE + x] = foamPattern(((Real)x + 0.5f) / FOAM_TEXTURE_SIZE, ((Real)y + 0.5f) / FOAM_TEXTURE_SIZE);
		if (!fillGreyAlphaTexture(m_effectFoamTexture, FOAM_TEXTURE_SIZE, grey, grey))
			return FALSE;
	}

	// Looping du/dv wave animation.
	if (m_effects.waves && m_effectWaveTexture[0] == nullptr)
	{
		std::vector<Real> du(WAVE_TEXTURE_SIZE * WAVE_TEXTURE_SIZE);
		std::vector<Real> dv(WAVE_TEXTURE_SIZE * WAVE_TEXTURE_SIZE);
		for (Int frame = 0; frame < WATER_WAVE_FRAMES; ++frame)
		{
			m_effectWaveTexture[frame] = createManagedTexture(WAVE_TEXTURE_SIZE, WAVE_TEXTURE_SIZE, mipLevelCount(WAVE_TEXTURE_SIZE), D3DFMT_V8U8);
			if (m_effectWaveTexture[frame] == nullptr)
			{
				fprintf(stderr, "[WATER] cannot create V8U8 textures, WaterWaves off\n");
				fflush(stderr);
				m_effects.waves = FALSE;
				break;
			}
			const Real t = (Real)frame / (Real)WATER_WAVE_FRAMES;
			for (Int y = 0; y < WAVE_TEXTURE_SIZE; ++y)
				for (Int x = 0; x < WAVE_TEXTURE_SIZE; ++x)
					waveSlope(((Real)x + 0.5f) / WAVE_TEXTURE_SIZE, ((Real)y + 0.5f) / WAVE_TEXTURE_SIZE, t,
						&du[y * WAVE_TEXTURE_SIZE + x], &dv[y * WAVE_TEXTURE_SIZE + x]);
			if (!fillWaveTexture(m_effectWaveTexture[frame], WAVE_TEXTURE_SIZE, du, dv))
			{
				m_effects.waves = FALSE;
				break;
			}
		}
	}

	return TRUE;
}

//-------------------------------------------------------------------------------------------------
/** Releases the reflection render target (device reset) */
//-------------------------------------------------------------------------------------------------
void WaterRenderObjClass::releaseWaterEffectTargets()
{
	REF_PTR_RELEASE(m_effectReflectionTexture);
	m_effectReflectionValid = FALSE;
}

//-------------------------------------------------------------------------------------------------
/** Releases every effect texture (destructor) */
//-------------------------------------------------------------------------------------------------
void WaterRenderObjClass::releaseWaterEffects()
{
	releaseWaterEffectTargets();
	SAFE_RELEASE(m_effectFresnelTexture);
	SAFE_RELEASE(m_effectFoamTexture);
	SAFE_RELEASE(m_effectShoreTexture);
	for (Int i = 0; i < WATER_WAVE_FRAMES; ++i)
		SAFE_RELEASE(m_effectWaveTexture[i]);
	m_effectShoreSignature = 0;
}

Bool WaterRenderObjClass::shoreEffectsActive() const
{
	return m_effectsSupported && m_effects.shoreFoam && m_effectShoreTexture != nullptr && m_effectFoamTexture != nullptr;
}

Bool WaterRenderObjClass::reflectionEffectsActive() const
{
	return m_effectsSupported && m_effects.reflections != WATER_REFLECTIONS_OFF && m_effectFresnelTexture != nullptr;
}

//-------------------------------------------------------------------------------------------------
/** Finds the water in view: the screen rectangle (normalized device coordinates) that all visible water
	* polygons cover, and the height of the one that covers most of the screen, which the reflection mirrors
	* across. Returns false when no water is visible. */
//-------------------------------------------------------------------------------------------------
Bool WaterRenderObjClass::findWaterReflectionPlane(CameraClass *cam, Real *level, Vector2 *ndcMin, Vector2 *ndcMax)
{
	const FrustumClass &frustum = cam->Get_Frustum();
	Bool found = FALSE;
	Real bestArea = -1.0f;
	ClipPolyClass poly0;
	ClipPolyClass poly1;

	for (PolygonTrigger *trig = PolygonTrigger::getFirstPolygonTrigger(); trig; trig = trig->getNext())
	{
		if (!trig->isWaterArea() || trig->getNumPoints() < 3)
			continue;

		poly0.Reset();
		for (Int i = 0; i < trig->getNumPoints(); ++i)
		{
			const ICoord3D *pt = trig->getPoint(i);
			poly0.Add_Vertex(Vector3((Real)pt->x, (Real)pt->y, (Real)pt->z));
		}
		poly0.Clip(frustum.Planes[0], poly1);
		poly1.Clip(frustum.Planes[1], poly0);
		poly0.Clip(frustum.Planes[2], poly1);
		poly1.Clip(frustum.Planes[3], poly0);
		poly0.Clip(frustum.Planes[4], poly1);
		poly1.Clip(frustum.Planes[5], poly0);

		const Int count = poly0.Verts.Count();
		if (count < 3)
			continue;

		Vector2 polyMin(1.0f, 1.0f);
		Vector2 polyMax(-1.0f, -1.0f);
		Int projected = 0;
		for (Int i = 0; i < count; ++i)
		{
			Vector3 ndc;
			if (cam->Project(ndc, poly0.Verts[i]) == CameraClass::OUTSIDE_NEAR_CLIP)
				continue;
			const Real x = ndc.X < -1.0f ? -1.0f : (ndc.X > 1.0f ? 1.0f : ndc.X);
			const Real y = ndc.Y < -1.0f ? -1.0f : (ndc.Y > 1.0f ? 1.0f : ndc.Y);
			polyMin.X = std::min(polyMin.X, x);
			polyMin.Y = std::min(polyMin.Y, y);
			polyMax.X = std::max(polyMax.X, x);
			polyMax.Y = std::max(polyMax.Y, y);
			++projected;
		}
		if (projected < 3 || polyMax.X <= polyMin.X || polyMax.Y <= polyMin.Y)
			continue;

		const Real area = (polyMax.X - polyMin.X) * (polyMax.Y - polyMin.Y);
		if (!found)
		{
			*ndcMin = polyMin;
			*ndcMax = polyMax;
		}
		else
		{
			ndcMin->X = std::min(ndcMin->X, polyMin.X);
			ndcMin->Y = std::min(ndcMin->Y, polyMin.Y);
			ndcMax->X = std::max(ndcMax->X, polyMax.X);
			ndcMax->Y = std::max(ndcMax->Y, polyMax.Y);
		}
		if (area > bestArea)
		{
			bestArea = area;
			*level = (Real)trig->getPoint(0)->z;
		}
		found = TRUE;
	}

	return found;
}

//-------------------------------------------------------------------------------------------------
/** Draws the cloud layer of the current time of day as a plane high above the water, centred under the
	* camera with world anchored texture coordinates. It fills the background of the reflection. */
//-------------------------------------------------------------------------------------------------
void WaterRenderObjClass::renderWaterReflectionSky(const Vector3 &cameraPos, Real level)
{
	Setting *setting = &m_settings[m_tod];
	if (setting->skyTexture == nullptr)
		return;

	VertexMaterialClass *vmat = VertexMaterialClass::Get_Preset(VertexMaterialClass::PRELIT_DIFFUSE);
	DX8Wrapper::Set_Material(vmat);
	REF_PTR_RELEASE(vmat);

	ShaderClass shader = ShaderClass::_PresetOpaqueShader;
	shader.Set_Cull_Mode(ShaderClass::CULL_MODE_DISABLE);
	shader.Set_Depth_Compare(ShaderClass::PASS_ALWAYS);
	shader.Set_Depth_Mask(ShaderClass::DEPTH_WRITE_DISABLE);
	DX8Wrapper::Set_Shader(shader);
	DX8Wrapper::Set_Texture(0, setting->skyTexture);
	DX8Wrapper::Set_Texture(1, nullptr);

	// The retail cloud layer floats 30 units above the sea; this one is higher, so its texture repeats less
	// often to keep the clouds about the same size on screen.
	const Real texelsPerUnit = setting->skyTexelsPerUnit * 0.5f;
	const Real scroll = m_effectTime * 1000.0f;
	const Real u0 = setting->uScrollPerMs * texelsPerUnit * scroll;
	const Real v0 = setting->vScrollPerMs * texelsPerUnit * scroll;
	const Real cx = cameraPos.X;
	const Real cy = cameraPos.Y;
	const Real z = level + REFLECTION_SKY_HEIGHT;
	const Real size = REFLECTION_SKY_SIZE;

	DynamicVBAccessClass vb_access(BUFFER_TYPE_DYNAMIC_DX8, dynamic_fvf_type, 4);
	{
		DynamicVBAccessClass::WriteLockClass lock(&vb_access);
		VertexFormatXYZNDUV2 *verts = lock.Get_Formatted_Vertex_Array();
		if (verts == nullptr)
			return;
		const Real xs[4] = { cx - size, cx + size, cx + size, cx - size };
		const Real ys[4] = { cy + size, cy + size, cy - size, cy - size };
		const DWORD colors[4] = { setting->vertex01Diffuse, setting->vertex11Diffuse, setting->vertex10Diffuse, setting->vertex00Diffuse };
		for (Int i = 0; i < 4; ++i)
		{
			verts[i].x = xs[i];
			verts[i].y = ys[i];
			verts[i].z = z;
			verts[i].nx = 0.0f;
			verts[i].ny = 0.0f;
			verts[i].nz = -1.0f;
			verts[i].diffuse = colors[i] | 0xff000000;
			verts[i].u1 = xs[i] * texelsPerUnit + u0;
			verts[i].v1 = ys[i] * texelsPerUnit + v0;
			verts[i].u2 = 0.0f;
			verts[i].v2 = 0.0f;
		}
	}

	DX8Wrapper::Set_Index_Buffer(m_indexBuffer, 0);
	DX8Wrapper::Set_Vertex_Buffer(vb_access);
	DX8Wrapper::Set_Transform(D3DTS_WORLD, Matrix3D(1));
	DX8Wrapper::Draw_Triangles(0, 2, 0, 4);
}

//-------------------------------------------------------------------------------------------------
/** Renders the mirrored scene for standing water and rivers into the reflection texture. Called before the
	* main scene, like the retail sea reflection. */
//-------------------------------------------------------------------------------------------------
void WaterRenderObjClass::renderWaterReflection(CameraClass *cam)
{
	if (!reflectionEffectsActive() || cam == nullptr || m_parentScene == nullptr)
		return;
	if (TheTerrainRenderObject == nullptr || TheTerrainRenderObject->getMap() == nullptr)
		return;
#ifdef EXTENDED_STATS
	if (DX8Wrapper::stats.m_disableWater)
		return;
#endif

	Real level = 0.0f;
	Vector2 ndcMin, ndcMax;
	if (!findWaterReflectionPlane(cam, &level, &ndcMin, &ndcMax))
	{
		m_effectReflectionValid = FALSE;
		return;
	}

	// A static camera refreshes the reflection every other frame; a moving one every frame.
	const Matrix3D &cameraTransform = cam->Get_Transform();
	const Bool cameraMoved = !m_effectReflectionValid || level != m_effectReflectionLevel ||
		memcmp(&cameraTransform, &m_effectReflectionCamera, sizeof(Matrix3D)) != 0;
	++m_effectReflectionAge;
	if (!cameraMoved && m_effectReflectionAge < REFLECTION_STATIC_INTERVAL)
		return;

	PERF_STATS_SCOPE(SECTION_WATER_REFLECTION);

	// Reflection texture: WaterReflectionScale times the depth buffer, which matches the 3D view.
	if (m_effectReflectionTexture == nullptr)
	{
		IDirect3DDevice8 *device = DX8Wrapper::_Get_D3D_Device8();
		IDirect3DSurface8 *depth = nullptr;
		if (device == nullptr || FAILED(device->GetDepthStencilSurface(&depth)) || depth == nullptr)
			return;
		D3DSURFACE_DESC desc;
		const HRESULT hr = depth->GetDesc(&desc);
		depth->Release();
		if (FAILED(hr))
			return;
		m_effectReflectionWidth = std::max(64, (Int)(desc.Width * m_effects.reflectionScale + 0.5f));
		m_effectReflectionHeight = std::max(64, (Int)(desc.Height * m_effects.reflectionScale + 0.5f));
		WW3DFormat format = WW3D_FORMAT_X8R8G8B8;
		if (!DX8Wrapper::Get_Current_Caps()->Support_Render_To_Texture_Format(format))
			format = WW3D_FORMAT_A8R8G8B8;
		m_effectReflectionTexture = NEW_REF(TextureClass, (m_effectReflectionWidth, m_effectReflectionHeight, format,
			MIP_LEVELS_1, TextureClass::POOL_DEFAULT, true));
		if (m_effectReflectionTexture->Peek_D3D_Base_Texture() == nullptr)
		{
			REF_PTR_RELEASE(m_effectReflectionTexture);
			fprintf(stderr, "[WATER] cannot create the %dx%d reflection texture, reflections off\n",
				m_effectReflectionWidth, m_effectReflectionHeight);
			fflush(stderr);
			m_effects.reflections = WATER_REFLECTIONS_OFF;
			return;
		}
		fprintf(stderr, "[WATER] reflection texture %dx%d\n", m_effectReflectionWidth, m_effectReflectionHeight);
		fflush(stderr);
	}

	// Draw only the part of the screen the water covers, plus a margin for the wave distortion.
	ndcMin.X = std::max(-1.0f, ndcMin.X - REFLECTION_SCREEN_MARGIN);
	ndcMin.Y = std::max(-1.0f, ndcMin.Y - REFLECTION_SCREEN_MARGIN);
	ndcMax.X = std::min(1.0f, ndcMax.X + REFLECTION_SCREEN_MARGIN);
	ndcMax.Y = std::min(1.0f, ndcMax.Y + REFLECTION_SCREEN_MARGIN);

	// Mirror the camera across the water plane (as the retail sea does).
	const Matrix3D oldTransform = cam->Get_Transform();
	Vector2 oldViewportMin, oldViewportMax, oldPlaneMin, oldPlaneMax;
	cam->Get_Viewport(oldViewportMin, oldViewportMax);
	cam->Get_View_Plane(oldPlaneMin, oldPlaneMax);
	float oldJitterX, oldJitterY;
	cam->Get_Projection_Jitter(oldJitterX, oldJitterY);

	Matrix4x4 full4(oldTransform);
	Matrix4x4 full(full4.Transpose());
	const Vector3 normal(0.0f, 0.0f, 1.0f);
	Vector3 axes[3];
	for (Int i = 0; i < 3; ++i)
	{
		const Vector3 &axis = (Vector3 &)full[i];
		axes[i] = axis - (2.0f * Vector3::Dot_Product(axis, normal)) * normal;
	}
	const Vector3 &position = (Vector3 &)full[3];
	const Real distance = Vector3::Dot_Product(position, normal) - level;
	const Vector3 mirroredPosition = position - (2.0f * distance) * normal;
	Matrix3D mirrored(axes[0], axes[1], axes[2], mirroredPosition);

	// Screen sub rectangle: the viewport is in [0, 1] with y down, the view plane and NDC have y up.
	const Real ux0 = (ndcMin.X + 1.0f) * 0.5f;
	const Real ux1 = (ndcMax.X + 1.0f) * 0.5f;
	const Real uy0 = (ndcMin.Y + 1.0f) * 0.5f;
	const Real uy1 = (ndcMax.Y + 1.0f) * 0.5f;
	const Vector2 viewportMin(ux0, 1.0f - uy1);
	const Vector2 viewportMax(ux1, 1.0f - uy0);
	const Vector2 planeSize(oldPlaneMax.X - oldPlaneMin.X, oldPlaneMax.Y - oldPlaneMin.Y);
	const Vector2 planeMin(oldPlaneMin.X + ux0 * planeSize.X, oldPlaneMin.Y + uy0 * planeSize.Y);
	const Vector2 planeMax(oldPlaneMin.X + ux1 * planeSize.X, oldPlaneMin.Y + uy1 * planeSize.Y);

	DX8Wrapper::Set_Render_Target_With_Z(m_effectReflectionTexture);

	// Clear to the horizon colour of the sky; the cloud layer covers it where it is visible.
	const DWORD skyColor = m_settings[m_tod].vertex00Diffuse;
	const Vector3 clearColor(((skyColor >> 16) & 0xff) / 255.0f, ((skyColor >> 8) & 0xff) / 255.0f, (skyColor & 0xff) / 255.0f);
	if (WW3D::Begin_Offscreen_Render(true, true, clearColor) == WW3D_ERROR_OK)
	{
		cam->Set_Transform(mirrored);
		cam->Set_Viewport(viewportMin, viewportMax);
		cam->Set_View_Plane(planeMin, planeMax);
		cam->Set_Projection_Jitter(0.0f, 0.0f);
		cam->Set_Oblique_Clip_Plane(Vector4(0.0f, 0.0f, 1.0f, -(level - REFLECTION_CLIP_BIAS)));
		cam->Apply();

		// Mirrored geometry has its winding reversed.
		ShaderClass::Invert_Backface_Culling(true);

		renderWaterReflectionSky(position, level);
		if (m_effects.reflections == WATER_REFLECTIONS_FULL)
		{
			s_drawingEffectReflection = TRUE;
			WW3D::Render(m_parentScene, cam);
			s_drawingEffectReflection = FALSE;
		}

		ShaderClass::Invert_Backface_Culling(false);

		cam->Clear_Oblique_Clip_Plane();
		cam->Set_Projection_Jitter(oldJitterX, oldJitterY);
		cam->Set_View_Plane(oldPlaneMin, oldPlaneMax);
		cam->Set_Viewport(oldViewportMin, oldViewportMax);
		cam->Set_Transform(oldTransform);

		WW3D::End_Offscreen_Render();

		m_effectReflectionValid = TRUE;
		m_effectReflectionLevel = level;
		m_effectReflectionCamera = oldTransform;
		m_effectReflectionAge = 0;
	}

	DX8Wrapper::Set_Render_Target((IDirect3DSurface8 *)nullptr);
	cam->Apply();
}

//-------------------------------------------------------------------------------------------------
/** Builds the shore texture from the water depth: alpha fades the water in over the first SOFT_SHORE_DEPTH
	* units, the colour holds the foam band. Texels outside all water polygons count as deep water. Rebuilt
	* when the map or a water polygon changes (scripts can raise or lower the water). */
//-------------------------------------------------------------------------------------------------
void WaterRenderObjClass::updateShoreTexture()
{
	if (!m_effectsSupported || !m_effects.shoreFoam)
		return;
	if (TheTerrainRenderObject == nullptr)
		return;
	WorldHeightMap *map = TheTerrainRenderObject->getMap();
	if (map == nullptr || map->getDataPtr() == nullptr || map->getXExtent() < 2 || map->getYExtent() < 2)
		return;

	// Signature of the map and its water polygons.
	UnsignedInt signature = 2166136261u;
	signature = hashCombine(signature, (UnsignedInt)(uintptr_t)map);
	signature = hashCombine(signature, (UnsignedInt)map->getXExtent());
	signature = hashCombine(signature, (UnsignedInt)map->getYExtent());
	signature = hashCombine(signature, (UnsignedInt)map->getBorderSizeInline());
	Int waterPolygons = 0;
	for (PolygonTrigger *trig = PolygonTrigger::getFirstPolygonTrigger(); trig; trig = trig->getNext())
	{
		if (!trig->isWaterArea())
			continue;
		++waterPolygons;
		signature = hashCombine(signature, (UnsignedInt)trig->getNumPoints());
		for (Int i = 0; i < trig->getNumPoints(); ++i)
		{
			const ICoord3D *pt = trig->getPoint(i);
			signature = hashCombine(signature, (UnsignedInt)pt->x);
			signature = hashCombine(signature, (UnsignedInt)pt->y);
			signature = hashCombine(signature, (UnsignedInt)pt->z);
		}
	}
	if (waterPolygons == 0)
		return;
	if (signature == m_effectShoreSignature && m_effectShoreTexture != nullptr)
		return;
	const Int now = (Int)timeGetTime();
	if (m_effectShoreTexture != nullptr && now - m_effectShoreBuildTime < SHORE_REBUILD_INTERVAL_MS)
		return;
	m_effectShoreBuildTime = now;

	const Int border = map->getBorderSizeInline();
	const Real originX = -border * MAP_XY_FACTOR;
	const Real originY = -border * MAP_XY_FACTOR;
	const Real sizeX = (map->getXExtent() - 1) * MAP_XY_FACTOR;
	const Real sizeY = (map->getYExtent() - 1) * MAP_XY_FACTOR;
	Int width = 64;
	while (width < SHORE_TEXTURE_MAX && width * SHORE_TEXEL_WORLD < sizeX)
		width *= 2;
	Int height = 64;
	while (height < SHORE_TEXTURE_MAX && height * SHORE_TEXEL_WORLD < sizeY)
		height *= 2;
	const Real texelX = sizeX / width;
	const Real texelY = sizeY / height;

	// Water height of each texel: scanline fill of every water polygon, the highest water wins (as in
	// getWaterHeight). A large negative value marks dry texels.
	const Real DRY = -1.0e9f;
	std::vector<Real> water(width * height, DRY);
	std::vector<Real> crossings;
	for (PolygonTrigger *trig = PolygonTrigger::getFirstPolygonTrigger(); trig; trig = trig->getNext())
	{
		const Int count = trig->getNumPoints();
		if (!trig->isWaterArea() || count < 3)
			continue;
		// Standing water is flat; a river may slope, and its highest point keeps the depth from ever reading
		// shallower than it is (which would fade out water that should be there).
		Real z = (Real)trig->getPoint(0)->z;
		Real minY = 1.0e9f;
		Real maxY = -1.0e9f;
		for (Int i = 0; i < count; ++i)
		{
			z = std::max(z, (Real)trig->getPoint(i)->z);
			minY = std::min(minY, (Real)trig->getPoint(i)->y);
			maxY = std::max(maxY, (Real)trig->getPoint(i)->y);
		}
		const Int row0 = std::max(0, (Int)floorf((minY - originY) / texelY - 0.5f));
		const Int row1 = std::min(height - 1, (Int)ceilf((maxY - originY) / texelY - 0.5f));
		for (Int row = row0; row <= row1; ++row)
		{
			const Real y = originY + (row + 0.5f) * texelY;
			crossings.clear();
			for (Int i = 0; i < count; ++i)
			{
				const ICoord3D *a = trig->getPoint(i);
				const ICoord3D *b = trig->getPoint((i + 1) % count);
				const Real ay = (Real)a->y;
				const Real by = (Real)b->y;
				if ((ay <= y && by > y) || (by <= y && ay > y))
					crossings.push_back((Real)a->x + (y - ay) / (by - ay) * (Real)(b->x - a->x));
			}
			std::sort(crossings.begin(), crossings.end());
			for (size_t i = 0; i + 1 < crossings.size(); i += 2)
			{
				const Int col0 = std::max(0, (Int)ceilf((crossings[i] - originX) / texelX - 0.5f));
				const Int col1 = std::min(width - 1, (Int)floorf((crossings[i + 1] - originX) / texelX - 0.5f));
				Real *dst = &water[row * width];
				for (Int col = col0; col <= col1; ++col)
					dst[col] = std::max(dst[col], z);
			}
		}
	}

	if (m_effectShoreTexture == nullptr || m_effectShoreWidth != width || m_effectShoreHeight != height)
	{
		SAFE_RELEASE(m_effectShoreTexture);
		m_effectShoreTexture = createManagedTexture(width, height, 1, D3DFMT_A8R8G8B8);
		if (m_effectShoreTexture == nullptr)
			return;
		m_effectShoreWidth = width;
		m_effectShoreHeight = height;
	}

	D3DLOCKED_RECT rect;
	if (FAILED(m_effectShoreTexture->LockRect(0, &rect, nullptr, 0)))
		return;
	for (Int row = 0; row < height; ++row)
	{
		UnsignedInt *dst = (UnsignedInt *)((UnsignedByte *)rect.pBits + row * rect.Pitch);
		const Real y = originY + (row + 0.5f) * texelY;
		for (Int col = 0; col < width; ++col)
		{
			const Real waterZ = water[row * width + col];
			if (waterZ == DRY)
			{
				dst[col] = 0xff000000;	// deep water: opaque, no foam
				continue;
			}
			const Real x = originX + (col + 0.5f) * texelX;
			const Real depth = waterZ - sampleTerrainHeight(map, x, y);
			const Real alpha = smoothStep(0.0f, SOFT_SHORE_DEPTH, depth);
			const Real foam = smoothStep(0.0f, FOAM_RISE_DEPTH, depth) * (1.0f - smoothStep(FOAM_FADE_START, FOAM_FADE_END, depth));
			const UnsignedInt a = (UnsignedInt)(alpha * 255.0f + 0.5f);
			const UnsignedInt f = (UnsignedInt)(foam * 255.0f + 0.5f);
			dst[col] = (a << 24) | (f << 16) | (f << 8) | f;
		}
	}
	m_effectShoreTexture->UnlockRect(0);

	m_effectShoreOriginX = originX;
	m_effectShoreOriginY = originY;
	m_effectShoreSizeX = sizeX;
	m_effectShoreSizeY = sizeY;
	m_effectShoreSignature = signature;
	fprintf(stderr, "[WATER] shore texture %dx%d for %d water areas\n", width, height, waterPolygons);
	fflush(stderr);
}

//-------------------------------------------------------------------------------------------------
/** Projects a world space texture onto the stage: texture coordinates from the camera space position. */
//-------------------------------------------------------------------------------------------------
void WaterRenderObjClass::setWorldTexGen(Int stage, Real scaleX, Real scaleY, Real offsetX, Real offsetY, Real rotation)
{
	Real invView[4][4];
	getInverseView(invView);
	setWorldTexGenMatrix(stage, invView, scaleX, scaleY, offsetX, offsetY, rotation);
}

//-------------------------------------------------------------------------------------------------
/** Soft shoreline: the shore texture's alpha multiplies the alpha of the base water pass on the given (free)
	* stage. Call after the water shader is set up and before the draw; endSoftShore() after it. */
//-------------------------------------------------------------------------------------------------
void WaterRenderObjClass::beginSoftShore(Int stage)
{
	if (!shoreEffectsActive() || !m_effectLayer)
		return;

	// Keep W3D's view of the stage (no texture) in line with the device.
	DX8Wrapper::Set_Texture(stage, nullptr);
	DX8Wrapper::Apply_Render_State_Changes();

	DX8Wrapper::Set_DX8_Texture(stage, m_effectShoreTexture);
	setStageSampler(stage, FALSE, FALSE);
	setWorldTexGen(stage, 1.0f / m_effectShoreSizeX, 1.0f / m_effectShoreSizeY,
		-m_effectShoreOriginX / m_effectShoreSizeX, -m_effectShoreOriginY / m_effectShoreSizeY, 0.0f);
	setStageOps(stage, D3DTOP_SELECTARG2, D3DTA_TEXTURE, D3DTA_CURRENT, D3DTOP_MODULATE, D3DTA_TEXTURE, D3DTA_CURRENT);
	DX8Wrapper::Set_DX8_Texture_Stage_State(stage + 1, D3DTSS_COLOROP, D3DTOP_DISABLE);
	DX8Wrapper::Set_DX8_Texture_Stage_State(stage + 1, D3DTSS_ALPHAOP, D3DTOP_DISABLE);
}

void WaterRenderObjClass::endSoftShore(Int stage)
{
	if (!shoreEffectsActive() || !m_effectLayer)
		return;

	DX8Wrapper::Set_DX8_Texture(stage, nullptr);
	DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_COLOROP, D3DTOP_DISABLE);
	DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_ALPHAOP, D3DTOP_DISABLE);
	DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_TEXCOORDINDEX, stage);
	DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_TEXTURETRANSFORMFLAGS, D3DTTFF_DISABLE);
	ShaderClass::Invalidate();
}

//-------------------------------------------------------------------------------------------------
/** Puts stages 0..lastStage back into the state W3D expects after the effect passes. */
//-------------------------------------------------------------------------------------------------
void WaterRenderObjClass::resetWaterEffectStages(Int lastStage)
{
	for (Int stage = 0; stage <= lastStage; ++stage)
	{
		DX8Wrapper::Set_DX8_Texture(stage, nullptr);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_TEXCOORDINDEX, stage);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_TEXTURETRANSFORMFLAGS, D3DTTFF_DISABLE);
		if (stage >= 2)
		{
			DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_COLOROP, D3DTOP_DISABLE);
			DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_ALPHAOP, D3DTOP_DISABLE);
		}
	}
	ShaderClass::Invalidate();
}

//-------------------------------------------------------------------------------------------------
/** Draws the reflection and foam passes over the water polygons that are bound (vertex and index buffer of
	* the water draw that just happened). waterZ is the height of these polygons. Each pass applies the shroud
	* itself, so call this after the retail passes, shroud included. */
//-------------------------------------------------------------------------------------------------
void WaterRenderObjClass::drawWaterEffectPasses(Int vertexCount, Int polygonCount, Real waterZ)
{
	if (!m_effectLayer || vertexCount <= 0 || polygonCount <= 0)
		return;

	const Bool doReflection = reflectionEffectsActive() && m_effectReflectionValid && m_effectReflectionTexture != nullptr;
	const Bool doFoam = shoreEffectsActive();
	if (!doReflection && !doFoam)
		return;

	Real reflectionStrength = 1.0f - fabsf(waterZ - m_effectReflectionLevel) / REFLECTION_HEIGHT_FADE;
	if (m_effects.reflections == WATER_REFLECTIONS_SKY)
		reflectionStrength *= SKY_REFLECTION_STRENGTH;
	const Bool reflect = doReflection && reflectionStrength > 0.01f;
	if (!reflect && !doFoam)
		return;

	W3DShroud *shroud = TheTerrainRenderObject ? TheTerrainRenderObject->getShroud() : nullptr;
	const Bool waves = m_effects.waves && m_effectWaveTexture[0] != nullptr;
	LPDIRECT3DTEXTURE8 waveTexture = waves ? m_effectWaveTexture[((Int)(m_effectTime * WAVE_FRAMES_PER_SECOND)) % WATER_WAVE_FRAMES] : nullptr;
	// Slow drift of the wave field on top of its animation, wrapped to keep the texture matrix precise.
	const Real waveDrift = fmodf(m_effectTime * 0.011f, 1.0f);
	const Real foamDriftA = fmodf(m_effectTime * 0.006f, 1.0f);
	const Real foamDriftB = fmodf(m_effectTime * 0.0045f, 1.0f);

	VertexMaterialClass *vmat = VertexMaterialClass::Get_Preset(VertexMaterialClass::PRELIT_DIFFUSE);
	DX8Wrapper::Set_Material(vmat);
	REF_PTR_RELEASE(vmat);

	// Foam takes the lighting of the time of day.
	Real lightR = TheGlobalData->m_terrainAmbient[0].red;
	Real lightG = TheGlobalData->m_terrainAmbient[0].green;
	Real lightB = TheGlobalData->m_terrainAmbient[0].blue;
	for (Int lightIndex = 0; lightIndex < TheGlobalData->m_numGlobalLights; ++lightIndex)
	{
		const Real nDotL = -TheGlobalData->m_terrainLightPos[lightIndex].z;
		if (nDotL > 0.0f)
		{
			lightR += nDotL * TheGlobalData->m_terrainDiffuse[lightIndex].red;
			lightG += nDotL * TheGlobalData->m_terrainDiffuse[lightIndex].green;
			lightB += nDotL * TheGlobalData->m_terrainDiffuse[lightIndex].blue;
		}
	}

	for (Int pass = 0; pass < 2; ++pass)
	{
		const Bool reflectionPass = pass == 0;
		if (reflectionPass ? !reflect : !doFoam)
			continue;

		ShaderClass shader = ShaderClass::_PresetAlphaShader;
		shader.Set_Depth_Mask(ShaderClass::DEPTH_WRITE_DISABLE);
		shader.Set_Depth_Compare(ShaderClass::PASS_LEQUAL);
		shader.Set_Cull_Mode(ShaderClass::CULL_MODE_DISABLE);
		if (!reflectionPass)
		{
			// Screen blend: the foam brightens the water without ever going past white.
			shader.Set_Src_Blend_Func(ShaderClass::SRCBLEND_ONE);
			shader.Set_Dst_Blend_Func(ShaderClass::DSTBLEND_ONE_MINUS_SRC_COLOR);
		}
		DX8Wrapper::Set_Shader(shader);
		for (Int stage = 0; stage < 2; ++stage)
			DX8Wrapper::Set_Texture(stage, nullptr);
		DX8Wrapper::Apply_Render_State_Changes();

		Int stage = 0;
		Int shroudStage = -1;
		Real invView[4][4];
		getInverseView(invView);

		if (waves)
		{
			// Bump environment map stage: perturbs the texture coordinates of the next stage.
			const Real amount = reflectionPass ? WAVE_REFLECTION_DISTORTION : WAVE_FOAM_DISTORTION;
			DX8Wrapper::Set_DX8_Texture(stage, waveTexture);
			setStageSampler(stage, TRUE, TRUE);
			setWorldTexGenMatrix(stage, invView, 1.0f / WAVE_TILE_WORLD, 1.0f / WAVE_TILE_WORLD, waveDrift, 0.37f * waveDrift, 0.0f);
			setStageOps(stage, D3DTOP_BUMPENVMAP, D3DTA_TEXTURE, D3DTA_CURRENT, D3DTOP_SELECTARG1, D3DTA_TFACTOR, D3DTA_CURRENT);
			DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_BUMPENVMAT00, floatToDword(amount));
			DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_BUMPENVMAT01, floatToDword(0.0f));
			DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_BUMPENVMAT10, floatToDword(0.0f));
			DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_BUMPENVMAT11, floatToDword(amount));
			++stage;
		}

		if (reflectionPass)
		{
			// Reflection texture, projected with the camera: camera space -> clip space -> [0, 1] screen
			// coordinates, divided by w per pixel.
			Matrix4x4 projection;
			DX8Wrapper::_Get_DX8_Transform(D3DTS_PROJECTION, projection);
			Real proj[4][4];
			memcpy(proj, &projection, sizeof(proj));
			const Real bias[4][4] =
			{
				{ 0.5f, 0.0f, 0.0f, 0.0f },
				{ 0.0f, -0.5f, 0.0f, 0.0f },
				{ 0.0f, 0.0f, 0.0f, 0.0f },
				{ 0.5f, 0.5f, 1.0f, 1.0f },
			};
			Real texProj[4][4];
			multiplyD3D(texProj, proj, bias);
			DX8Wrapper::Set_DX8_Texture(stage, m_effectReflectionTexture->Peek_D3D_Texture());
			setStageSampler(stage, FALSE, FALSE);
			setTextureTransform(stage, texProj);
			DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_TEXCOORDINDEX, D3DTSS_TCI_CAMERASPACEPOSITION);
			DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_TEXTURETRANSFORMFLAGS, D3DTTFF_COUNT3 | D3DTTFF_PROJECTED);
			setStageOps(stage, D3DTOP_SELECTARG1, D3DTA_TEXTURE, D3DTA_CURRENT,
				waves ? D3DTOP_SELECTARG2 : D3DTOP_SELECTARG1, D3DTA_TFACTOR, D3DTA_CURRENT);
			++stage;

			// Fresnel: the reflection vector dotted with the water normal is the cosine of the view angle.
			Matrix4x4 view;
			DX8Wrapper::_Get_DX8_Transform(D3DTS_VIEW, view);
			Vector3 n(view[2][0], view[2][1], view[2][2]);
			n.Normalize();
			const Real fresnel[4][4] =
			{
				{ n.X, 0.0f, 0.0f, 0.0f },
				{ n.Y, 0.0f, 0.0f, 0.0f },
				{ n.Z, 0.0f, 0.0f, 0.0f },
				{ 0.0f, 0.5f, 0.0f, 1.0f },
			};
			DX8Wrapper::Set_DX8_Texture(stage, m_effectFresnelTexture);
			setStageSampler(stage, FALSE, FALSE);
			setTextureTransform(stage, fresnel);
			DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_TEXCOORDINDEX, D3DTSS_TCI_CAMERASPACEREFLECTIONVECTOR);
			DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_TEXTURETRANSFORMFLAGS, D3DTTFF_COUNT2);
			setStageOps(stage, D3DTOP_SELECTARG2, D3DTA_TEXTURE, D3DTA_CURRENT, D3DTOP_MODULATE, D3DTA_TEXTURE, D3DTA_CURRENT);
			++stage;

			const UnsignedInt strength = (UnsignedInt)(clamp01(reflectionStrength) * 255.0f + 0.5f);
			DX8Wrapper::Set_DX8_Render_State(D3DRS_TEXTUREFACTOR, (strength << 24) | 0x00ffffff);
		}
		else
		{
			// Two drifting layers of the foam pattern, multiplied.
			DX8Wrapper::Set_DX8_Texture(stage, m_effectFoamTexture);
			setStageSampler(stage, TRUE, TRUE);
			setWorldTexGenMatrix(stage, invView, 1.0f / FOAM_TILE_WORLD, 1.0f / FOAM_TILE_WORLD, foamDriftA, 0.5f * foamDriftA, 0.0f);
			setStageOps(stage, D3DTOP_MODULATE, D3DTA_TEXTURE, D3DTA_TFACTOR, D3DTOP_SELECTARG1, D3DTA_TEXTURE, D3DTA_CURRENT);
			++stage;

			DX8Wrapper::Set_DX8_Texture(stage, m_effectFoamTexture);
			setStageSampler(stage, TRUE, TRUE);
			setWorldTexGenMatrix(stage, invView, 1.0f / (FOAM_TILE_WORLD * 1.37f), 1.0f / (FOAM_TILE_WORLD * 1.37f), -0.6f * foamDriftB, foamDriftB, 0.9f);
			setStageOps(stage, D3DTOP_MODULATE2X, D3DTA_TEXTURE, D3DTA_CURRENT, D3DTOP_SELECTARG2, D3DTA_TEXTURE, D3DTA_CURRENT);
			++stage;

			const UnsignedInt r = (UnsignedInt)(clamp01(lightR * FOAM_STRENGTH) * 255.0f + 0.5f);
			const UnsignedInt g = (UnsignedInt)(clamp01(lightG * FOAM_STRENGTH) * 255.0f + 0.5f);
			const UnsignedInt b = (UnsignedInt)(clamp01(lightB * FOAM_STRENGTH) * 255.0f + 0.5f);
			DX8Wrapper::Set_DX8_Render_State(D3DRS_TEXTUREFACTOR, 0xff000000 | (r << 16) | (g << 8) | b);
		}

		// Shore texture: alpha softens the reflection at the shoreline, colour is the foam band.
		if (doFoam)
		{
			DX8Wrapper::Set_DX8_Texture(stage, m_effectShoreTexture);
			setStageSampler(stage, FALSE, FALSE);
			setWorldTexGenMatrix(stage, invView, 1.0f / m_effectShoreSizeX, 1.0f / m_effectShoreSizeY,
				-m_effectShoreOriginX / m_effectShoreSizeX, -m_effectShoreOriginY / m_effectShoreSizeY, 0.0f);
			if (reflectionPass)
				setStageOps(stage, D3DTOP_SELECTARG2, D3DTA_TEXTURE, D3DTA_CURRENT, D3DTOP_MODULATE, D3DTA_TEXTURE, D3DTA_CURRENT);
			else
				setStageOps(stage, D3DTOP_MODULATE, D3DTA_TEXTURE, D3DTA_CURRENT, D3DTOP_SELECTARG2, D3DTA_TEXTURE, D3DTA_CURRENT);
			++stage;
		}

		// Shroud: darken under fog of war like the rest of the water.
		if (shroud)
		{
			shroudStage = stage;
			W3DShaderManager::setTexture(0, shroud->getShroudTexture());
			W3DShaderManager::setShader(W3DShaderManager::ST_SHROUD_TEXTURE, shroudStage);
			setStageOps(shroudStage, D3DTOP_MODULATE, D3DTA_TEXTURE, D3DTA_CURRENT, D3DTOP_SELECTARG2, D3DTA_TEXTURE, D3DTA_CURRENT);
			++stage;
		}

		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_COLOROP, D3DTOP_DISABLE);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_ALPHAOP, D3DTOP_DISABLE);

		// The shroud shader compares depth with EQUAL, which never passes on water that writes no depth.
		DX8Wrapper::Set_DX8_Render_State(D3DRS_ZFUNC, D3DCMP_LESSEQUAL);
		DX8Wrapper::_Get_D3D_Device8()->SetRenderState(D3DRS_ZFUNC, D3DCMP_LESSEQUAL);

		DX8Wrapper::Draw_Triangles(0, polygonCount, 0, vertexCount);

		if (shroudStage >= 0)
			W3DShaderManager::resetShader(W3DShaderManager::ST_SHROUD_TEXTURE);
		resetWaterEffectStages(stage);
	}

	DX8Wrapper::Set_DX8_Render_State(D3DRS_TEXTUREFACTOR, 0xffffffff);
}
