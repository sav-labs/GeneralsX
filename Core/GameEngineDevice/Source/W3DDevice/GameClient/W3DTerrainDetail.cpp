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

// FILE: W3DTerrainDetail.cpp /////////////////////////////////////////////////
//
// GeneralsX @feature Claude 16/10/2026 Close-up terrain detail, see W3DTerrainDetail.h.
//
// The pixel shaders are ps.1.4 token streams: the 64 bit and non-Windows builds have no D3DXAssembleShader.
// Their assembly is kept next to each array; scripts/tooling/shaders/assemble_ps1x.py regenerates the tokens.
//
// Texture stages of the terrain shader:
//   0  terrain atlas, base layer uv          rgb colour, alpha relief shade / 2
//   1  terrain atlas, blend layer uv         rgb colour, alpha relief shade / 2
//   2  cloud shadows (camera space texgen)   white when clouds are off
//   3  macro light map (camera space texgen) white when the light map is off
//   4  detail texture (camera space texgen)  rgb detail around 0.5, alpha blend noise
// Constants: c0 = (detail strength x3, soft blend on), c1 = 0.5, c2.a = relief strength.
// The three-texture blend tiles use stage 0 for their texture and the same stages 2..4.

#include "WWLib/always.h"
#include "W3DDevice/GameClient/W3DTerrainDetail.h"

#include <chrono>
#include <stdio.h>
#include <string.h>
#include <vector>

#include "Common/GlobalData.h"
#include "Common/PerfStats.h"
#include "WW3D2/dx8caps.h"
#include "WW3D2/dx8wrapper.h"
#include "WWMath/wwmath.h"

namespace
{

/*
ps.1.4
texld r0, t0							; base tile, alpha = relief shade / 2
texld r1, t1							; blend tile, alpha = relief shade / 2
texld r2, t2							; cloud shadows (white when off)
texld r3, t3							; macro light map (white when off)
texld r4, t4							; detail: rgb = detail (0.5 neutral), alpha = blend noise
mul r3.rgb, r2, r3						; clouds * light map
+add_x4_sat r5.a, v0_bias.a, r4_bias.a	; noise-shaped blend factor
lrp r4.rgb, c0, r4, c1					; detail strength: lerp(grey, detail, c0)
+lrp r5.a, c0.a, r5.a, v0.a				; c0.a = 1 soft blend, 0 retail vertex alpha
lrp r0, r5.a, r1, r0					; blend the two tiles (colour and relief)
mul r0.rgb, r0, v0						; vertex lighting
+lrp r0.a, c2.a, r0.a, c1.a				; relief strength: lerp(0.5, relief, c2.a)
mul_x2 r0.rgb, r0, r0.a					; apply relief
mul_x2 r0.rgb, r0, r4					; apply detail
mul r0.rgb, r0, r3						; apply clouds and light map
*/
const DWORD kTerrainDetailPS[] =
{
	0xffff0104, 0x00000042, 0x800f0000, 0xb0e40000, 0x00000042, 0x800f0001,
	0xb0e40001, 0x00000042, 0x800f0002, 0xb0e40002, 0x00000042, 0x800f0003,
	0xb0e40003, 0x00000042, 0x800f0004, 0xb0e40004, 0x00000005, 0x80070003,
	0x80e40002, 0x80e40003, 0x40000002, 0x82180005, 0x92ff0000, 0x82ff0004,
	0x00000012, 0x80070004, 0xa0e40000, 0x80e40004, 0xa0e40001, 0x40000012,
	0x80080005, 0xa0ff0000, 0x80ff0005, 0x90ff0000, 0x00000012, 0x800f0000,
	0x80ff0005, 0x80e40001, 0x80e40000, 0x00000005, 0x80070000, 0x80e40000,
	0x90e40000, 0x40000012, 0x80080000, 0xa0ff0002, 0x80ff0000, 0xa0ff0001,
	0x00000005, 0x81070000, 0x80e40000, 0x80ff0000, 0x00000005, 0x81070000,
	0x80e40000, 0x80e40004, 0x00000005, 0x80070000, 0x80e40000, 0x80e40003,
	0x0000ffff,
};

/*
ps.1.4
texld r0, t0							; third tile, alpha = relief shade / 2
texld r2, t2							; cloud shadows (white when off)
texld r3, t3							; macro light map (white when off)
texld r4, t4							; detail: rgb = detail (0.5 neutral), alpha = blend noise
mul r3.rgb, r2, r3
+add_x4_sat r5.a, v0_bias.a, r4_bias.a
lrp r4.rgb, c0, r4, c1
+lrp r5.a, c0.a, r5.a, v0.a
mul r0.rgb, r0, v0
+lrp r0.a, c2.a, r0.a, c1.a
mul_x2 r0.rgb, r0, r0.a
mul_x2 r0.rgb, r0, r4
mul r0.rgb, r0, r3
+mov r0.a, r5.a							; blend factor drives the frame buffer blend
*/
const DWORD kTerrainDetailExtraPS[] =
{
	0xffff0104, 0x00000042, 0x800f0000, 0xb0e40000, 0x00000042, 0x800f0002,
	0xb0e40002, 0x00000042, 0x800f0003, 0xb0e40003, 0x00000042, 0x800f0004,
	0xb0e40004, 0x00000005, 0x80070003, 0x80e40002, 0x80e40003, 0x40000002,
	0x82180005, 0x92ff0000, 0x82ff0004, 0x00000012, 0x80070004, 0xa0e40000,
	0x80e40004, 0xa0e40001, 0x40000012, 0x80080005, 0xa0ff0000, 0x80ff0005,
	0x90ff0000, 0x00000005, 0x80070000, 0x80e40000, 0x90e40000, 0x40000012,
	0x80080000, 0xa0ff0002, 0x80ff0000, 0xa0ff0001, 0x00000005, 0x81070000,
	0x80e40000, 0x80ff0000, 0x00000005, 0x81070000, 0x80e40000, 0x80e40004,
	0x00000005, 0x80070000, 0x80e40000, 0x80e40003, 0x40000001, 0x80080000,
	0x80ff0005, 0x0000ffff,
};

const Int DETAIL_SIZE = 1024;					///< detail texture size in texels
const Real DETAIL_WORLD_SIZE = 64.0f;			///< world units covered by one repeat of the detail texture
const Real DETAIL_ANGLE_COS = 0.894427191f;		///< the detail texture is turned by atan(1/2) against the
const Real DETAIL_ANGLE_SIN = 0.447213595f;		///< cell grid so its repeats do not line up with the cells
const Real DETAIL_RELIEF_SLOPE = 22.0f;			///< height gain of the detail micro relief
const Real TILE_RELIEF_SLOPE = 7.0f;			///< height gain of the tile relief (half resolution texels)
/// Strength of the detail colour in each mip level; smaller mips fade to neutral grey.
const Real DETAIL_MIP_FADE[] = { 1.0f, 1.0f, 0.75f, 0.4f, 0.15f, 0.0f };
/// Strength of the relief in each terrain atlas mip level.
const Real RELIEF_MIP_FADE[] = { 1.0f, 0.8f, 0.4f, 0.0f };

/// Luminance of the global terrain lights; L points towards each light.
struct TerrainLights
{
	Int count;
	Real ambient;
	Real dir[MAX_GLOBAL_LIGHTS][3];
	Real diffuse[MAX_GLOBAL_LIGHTS];
	Real flat;		///< lighting of a flat (upward facing) surface

	Bool operator==(const TerrainLights &other) const
	{
		if (count != other.count || ambient != other.ambient)
			return FALSE;
		for (Int i = 0; i < count; ++i) {
			if (diffuse[i] != other.diffuse[i] || dir[i][0] != other.dir[i][0]
				|| dir[i][1] != other.dir[i][1] || dir[i][2] != other.dir[i][2])
				return FALSE;
		}
		return TRUE;
	}

	Real shade(Real nx, Real ny, Real nz) const
	{
		Real s = ambient;
		for (Int i = 0; i < count; ++i) {
			Real d = nx * dir[i][0] + ny * dir[i][1] + nz * dir[i][2];
			if (d > 0.0f)
				s += diffuse[i] * (d > 1.0f ? 1.0f : d);
		}
		return s;
	}
};

inline Real luminance(Real r, Real g, Real b)
{
	return 0.299f * r + 0.587f * g + 0.114f * b;
}

TerrainLights currentLights()
{
	TerrainLights lights;
	memset(&lights, 0, sizeof(lights));
	if (!TheGlobalData) {
		lights.count = 1;
		lights.dir[0][2] = 1.0f;
		lights.diffuse[0] = 1.0f;
		lights.flat = 1.0f;
		return lights;
	}
	lights.count = TheGlobalData->m_numGlobalLights;
	if (lights.count < 0)
		lights.count = 0;
	if (lights.count > MAX_GLOBAL_LIGHTS)
		lights.count = MAX_GLOBAL_LIGHTS;
	const RGBColor &amb = TheGlobalData->m_terrainAmbient[0];
	lights.ambient = luminance(amb.red, amb.green, amb.blue);
	for (Int i = 0; i < lights.count; ++i) {
		const Coord3D &pos = TheGlobalData->m_terrainLightPos[i];
		Real len = WWMath::Sqrt(pos.x * pos.x + pos.y * pos.y + pos.z * pos.z);
		if (len > 0.0f) {
			lights.dir[i][0] = -pos.x / len;
			lights.dir[i][1] = -pos.y / len;
			lights.dir[i][2] = -pos.z / len;
		}
		const RGBColor &dif = TheGlobalData->m_terrainDiffuse[i];
		lights.diffuse[i] = luminance(dif.red, dif.green, dif.blue);
	}
	lights.flat = lights.shade(0.0f, 0.0f, 1.0f);
	return lights;
}

/// Integer hash for the value noise lattice; the same arithmetic as the preview script.
inline Real latticeValue(UnsignedInt x, UnsignedInt y, UnsignedInt seed)
{
	UnsignedInt n = x * 374761393u + y * 668265263u + seed * 1442695041u;
	n = (n ^ (n >> 13)) * 1274126177u;
	n = n ^ (n >> 16);
	return (Real)(n & 0xFFFF) / 65535.0f;
}

/// Adds weight * tileable value noise with one lattice cell per `period` texels to a size x size field.
void addValueNoise(std::vector<Real> &field, Int size, Int period, UnsignedInt seed, Real weight)
{
	const Int cells = size / period;
	std::vector<Real> fade(period);
	for (Int i = 0; i < period; ++i) {
		Real f = (Real)i / (Real)period;
		fade[i] = f * f * (3.0f - 2.0f * f);
	}
	for (Int y = 0; y < size; ++y) {
		const UnsignedInt y0 = (UnsignedInt)(y / period);
		const UnsignedInt y1 = (UnsignedInt)((y / period + 1) % cells);
		const Real fy = fade[y % period];
		Real *row = &field[y * size];
		for (Int x = 0; x < size; ++x) {
			const UnsignedInt x0 = (UnsignedInt)(x / period);
			const UnsignedInt x1 = (UnsignedInt)((x / period + 1) % cells);
			const Real fx = fade[x % period];
			const Real a = latticeValue(x0, y0, seed);
			const Real b = latticeValue(x1, y0, seed);
			const Real c = latticeValue(x0, y1, seed);
			const Real d = latticeValue(x1, y1, seed);
			const Real top = a + (b - a) * fx;
			const Real bottom = c + (d - c) * fx;
			row[x] += weight * (top + (bottom - top) * fy);
		}
	}
}

inline Real clampReal(Real v, Real lo, Real hi)
{
	return v < lo ? lo : (v > hi ? hi : v);
}

inline UnsignedInt toByte(Real v)
{
	Int i = (Int)(clampReal(v, 0.0f, 1.0f) * 255.0f + 0.5f);
	return (UnsignedInt)i;
}

/// Halves a square field with a box filter.
std::vector<Real> downsample(const std::vector<Real> &src, Int size)
{
	const Int half = size / 2;
	std::vector<Real> dst(half * half);
	for (Int y = 0; y < half; ++y) {
		for (Int x = 0; x < half; ++x) {
			const Real *a = &src[(2 * y) * size + 2 * x];
			const Real *b = a + size;
			dst[y * half + x] = 0.25f * (a[0] + a[1] + b[0] + b[1]);
		}
	}
	return dst;
}

void meanAndDeviation(const std::vector<Real> &field, Real &mean, Real &deviation)
{
	double sum = 0.0;
	double sumSq = 0.0;
	for (size_t i = 0; i < field.size(); ++i) {
		sum += field[i];
		sumSq += (double)field[i] * field[i];
	}
	const double n = (double)field.size();
	mean = (Real)(sum / n);
	double var = sumSq / n - (sum / n) * (sum / n);
	deviation = var > 0.0 ? WWMath::Sqrt((Real)var) : 0.0f;
}

/// Wrapping 3 tap box blur along both axes.
void boxBlurWrap(std::vector<Real> &field, Int size)
{
	std::vector<Real> tmp(field.size());
	for (Int y = 0; y < size; ++y) {
		const Real *row = &field[y * size];
		for (Int x = 0; x < size; ++x) {
			tmp[y * size + x] = (row[(x + size - 1) % size] + row[x] + row[(x + 1) % size]) * (1.0f / 3.0f);
		}
	}
	for (Int y = 0; y < size; ++y) {
		const Real *up = &tmp[((y + size - 1) % size) * size];
		const Real *mid = &tmp[y * size];
		const Real *down = &tmp[((y + 1) % size) * size];
		for (Int x = 0; x < size; ++x) {
			field[y * size + x] = (up[x] + mid[x] + down[x]) * (1.0f / 3.0f);
		}
	}
}

DWORD s_terrainShader = 0;
DWORD s_extraBlendShader = 0;
Bool s_active = FALSE;
TextureClass *s_detailTexture = nullptr;
TextureClass *s_whiteTexture = nullptr;
Bool s_atlasHasRelief = FALSE;
TerrainLights s_reliefLights;
TerrainLights s_detailLights;
Bool s_detailBuilt = FALSE;

/// Fills the detail texture: grey detail lit by the terrain lights, blend noise in alpha, faded mips.
void buildDetailTexture(const TerrainLights &lights)
{
	if (!s_detailTexture || !s_detailTexture->Peek_D3D_Texture())
		return;
	const auto start = std::chrono::steady_clock::now();
	const Int n = DETAIL_SIZE;

	// Height of the detail: octaves of 8 down to 0.5 world units, plus a fine grain for the colour.
	std::vector<Real> height(n * n, 0.0f);
	addValueNoise(height, n, 128, 11, 0.32f);
	addValueNoise(height, n, 64, 12, 0.26f);
	addValueNoise(height, n, 32, 13, 0.20f);
	addValueNoise(height, n, 16, 14, 0.13f);
	addValueNoise(height, n, 8, 15, 0.09f);
	std::vector<Real> grain(n * n, 0.0f);
	addValueNoise(grain, n, 4, 16, 1.0f);

	// Micro relief of the same height field, lit by the terrain lights in world space.
	std::vector<Real> shade(n * n);
	double shadeSum = 0.0;
	for (Int y = 0; y < n; ++y) {
		const Real *up = &height[((y + n - 1) % n) * n];
		const Real *down = &height[((y + 1) % n) * n];
		const Real *row = &height[y * n];
		for (Int x = 0; x < n; ++x) {
			const Real gx = (row[(x + 1) % n] - row[(x + n - 1) % n]) * 0.5f;
			const Real gy = (down[x] - up[x]) * 0.5f;
			// Texture +column is world (cos, sin), texture +row is world (-sin, cos).
			const Real wx = gx * DETAIL_ANGLE_COS - gy * DETAIL_ANGLE_SIN;
			const Real wy = gx * DETAIL_ANGLE_SIN + gy * DETAIL_ANGLE_COS;
			Real nx = -DETAIL_RELIEF_SLOPE * wx;
			Real ny = -DETAIL_RELIEF_SLOPE * wy;
			const Real len = WWMath::Sqrt(nx * nx + ny * ny + 1.0f);
			const Real s = lights.flat > 0.05f ? lights.shade(nx / len, ny / len, 1.0f / len) / lights.flat : 1.0f;
			shade[y * n + x] = s;
			shadeSum += s;
		}
	}
	const Real shadeMean = (Real)(shadeSum / (double)(n * n));
	std::vector<Real> detail(n * n);
	for (Int i = 0; i < n * n; ++i) {
		const Real albedo = 0.5f + 0.55f * (height[i] - 0.5f) + 0.10f * (grain[i] - 0.5f);
		const Real s = clampReal(shadeMean > 0.0f ? shade[i] / shadeMean : 1.0f, 0.6f, 1.4f);
		detail[i] = clampReal(albedo * s, 0.0f, 1.0f);
	}

	// Blend noise: octaves of 16 down to 1 world units, contrast stretched.
	std::vector<Real> noise(n * n, 0.0f);
	addValueNoise(noise, n, 256, 21, 0.40f);
	addValueNoise(noise, n, 128, 22, 0.25f);
	addValueNoise(noise, n, 64, 23, 0.17f);
	addValueNoise(noise, n, 32, 24, 0.10f);
	addValueNoise(noise, n, 16, 25, 0.08f);
	for (Int i = 0; i < n * n; ++i)
		noise[i] = clampReal((noise[i] - 0.5f) * 2.2f + 0.5f, 0.0f, 1.0f);
	Real noiseMean0, noiseDeviation0;
	meanAndDeviation(noise, noiseMean0, noiseDeviation0);

	IDirect3DTexture8 *tex = s_detailTexture->Peek_D3D_Texture();
	const Int levels = (Int)tex->GetLevelCount();
	Int size = n;
	const Int fadeCount = (Int)(sizeof(DETAIL_MIP_FADE) / sizeof(DETAIL_MIP_FADE[0]));
	for (Int level = 0; level < levels && size >= 1; ++level) {
		const Real fade = DETAIL_MIP_FADE[level < fadeCount ? level : fadeCount - 1];
		Real noiseMean, noiseDeviation;
		meanAndDeviation(noise, noiseMean, noiseDeviation);
		// Keep the noise contrast in every mip, so blend edges stay shaped at a distance.
		const Real contrast = noiseDeviation > 1.0e-4f ? noiseDeviation0 / noiseDeviation : 1.0f;
		D3DLOCKED_RECT locked;
		if (SUCCEEDED(tex->LockRect(level, &locked, nullptr, 0))) {
			for (Int y = 0; y < size; ++y) {
				UnsignedInt *dst = (UnsignedInt *)((UnsignedByte *)locked.pBits + y * locked.Pitch);
				for (Int x = 0; x < size; ++x) {
					const Real d = 0.5f + (detail[y * size + x] - 0.5f) * fade;
					// Stored blend offset t: the shader computes saturate(4 * (alpha - 0.5 + t - 0.5)),
					// t is kept in 0.25..1 so alpha 0 and 1 stay fully one layer.
					const Real t = clampReal(0.625f + 1.5f * (noise[y * size + x] - noiseMean) * contrast, 0.25f, 1.0f);
					const UnsignedInt g = toByte(d);
					dst[x] = (toByte(t) << 24) | (g << 16) | (g << 8) | g;
				}
			}
			tex->UnlockRect(level);
		}
		if (size > 1) {
			detail = downsample(detail, size);
			noise = downsample(noise, size);
		}
		size /= 2;
	}
	s_detailLights = lights;
	s_detailBuilt = TRUE;
	const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count();
	fprintf(stderr, "[TERRAIN] detail texture built in %.1f ms\n", ms);
	fflush(stderr);
}

void setTerrainFilter(Int stage)
{
	if (TheGlobalData && (TheGlobalData->m_bilinearTerrainTex || TheGlobalData->m_trilinearTerrainTex)) {
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_MINFILTER, D3DTEXF_LINEAR);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_MAGFILTER, D3DTEXF_LINEAR);
	} else {
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_MINFILTER, D3DTEXF_POINT);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_MAGFILTER, D3DTEXF_POINT);
	}
	if (TheGlobalData && TheGlobalData->m_trilinearTerrainTex) {
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_MIPFILTER, D3DTEXF_LINEAR);
	} else {
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_MIPFILTER, stage == 0 ? D3DTEXF_POINT : D3DTEXF_LINEAR);
	}
}

void setProjectedStage(Int stage, TextureClass *texture, const D3DXMATRIX &matrix, Bool pointMin)
{
	TextureClass *bind = texture ? texture : s_whiteTexture;
	DX8Wrapper::_Get_D3D_Device8()->SetTexture(stage, bind ? bind->Peek_D3D_Texture() : nullptr);
	DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_TEXCOORDINDEX, D3DTSS_TCI_CAMERASPACEPOSITION);
	DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_TEXTURETRANSFORMFLAGS, D3DTTFF_COUNT2);
	DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_ADDRESSU, D3DTADDRESS_WRAP);
	DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_ADDRESSV, D3DTADDRESS_WRAP);
	DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_MINFILTER, pointMin ? D3DTEXF_POINT : D3DTEXF_LINEAR);
	DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_MAGFILTER, D3DTEXF_LINEAR);
	DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_MIPFILTER, D3DTEXF_LINEAR);
	Matrix4x4 transform;
	*(D3DXMATRIX *)&transform = matrix;
	DX8Wrapper::_Set_DX8_Transform((D3DTRANSFORMSTATETYPE)(D3DTS_TEXTURE0 + stage), transform);
}

} // namespace

Bool W3DTerrainDetail::init()
{
	shutdown();
	if (!TheGlobalData)
		return FALSE;
	const Bool detail = TheGlobalData->m_terrainDetail && TheGlobalData->m_terrainDetailStrength > 0.0f;
	if (!detail && !TheGlobalData->m_terrainRelief && !TheGlobalData->m_terrainSoftBlend)
		return FALSE;
	IDirect3DDevice8 *device = DX8Wrapper::_Get_D3D_Device8();
	if (!device)
		return FALSE;
	const DX8Caps *caps = DX8Wrapper::Get_Current_Caps();
	const Int major = caps->Get_Pixel_Shader_Major_Version();
	const Int minor = caps->Get_Pixel_Shader_Minor_Version();
	if (major < 1 || (major == 1 && minor < 4)) {
		fprintf(stderr, "[TERRAIN] terrain detail needs pixel shader 1.4 (device has %d.%d), using the retail terrain\n", major, minor);
		fflush(stderr);
		return FALSE;
	}
	if (FAILED(device->CreatePixelShader(kTerrainDetailPS, &s_terrainShader))
		|| FAILED(device->CreatePixelShader(kTerrainDetailExtraPS, &s_extraBlendShader))) {
		fprintf(stderr, "[TERRAIN] terrain detail pixel shaders failed, using the retail terrain\n");
		fflush(stderr);
		shutdown();
		return FALSE;
	}
	// GeneralsX @performance Claude 16/10/2026 Shader creations for the frame profiler's hitch lines.
	PerfStats::addShaderCreated();
	PerfStats::addShaderCreated();

	s_whiteTexture = MSGNEW("TextureClass") TextureClass(1, 1, WW3D_FORMAT_A8R8G8B8, MIP_LEVELS_1,
		TextureBaseClass::POOL_MANAGED, false, false);
	s_detailTexture = MSGNEW("TextureClass") TextureClass(DETAIL_SIZE, DETAIL_SIZE, WW3D_FORMAT_A8R8G8B8, MIP_LEVELS_ALL,
		TextureBaseClass::POOL_MANAGED, false, false);
	if (!s_whiteTexture->Peek_D3D_Texture() || !s_detailTexture->Peek_D3D_Texture()) {
		fprintf(stderr, "[TERRAIN] terrain detail textures could not be created, using the retail terrain\n");
		fflush(stderr);
		shutdown();
		return FALSE;
	}
	D3DLOCKED_RECT locked;
	if (SUCCEEDED(s_whiteTexture->Peek_D3D_Texture()->LockRect(0, &locked, nullptr, 0))) {
		*(UnsignedInt *)locked.pBits = 0xFFFFFFFFu;
		s_whiteTexture->Peek_D3D_Texture()->UnlockRect(0);
	}
	buildDetailTexture(currentLights());

	s_active = TRUE;
	fprintf(stderr, "[TERRAIN] detail terrain shader on: TerrainDetail=%d strength=%.2f TerrainRelief=%d TerrainSoftBlend=%d\n",
		(Int)detail, TheGlobalData->m_terrainDetailStrength, (Int)TheGlobalData->m_terrainRelief, (Int)TheGlobalData->m_terrainSoftBlend);
	fflush(stderr);
	return TRUE;
}

void W3DTerrainDetail::shutdown()
{
	IDirect3DDevice8 *device = DX8Wrapper::_Get_D3D_Device8();
	if (device) {
		if (s_terrainShader)
			device->DeletePixelShader(s_terrainShader);
		if (s_extraBlendShader)
			device->DeletePixelShader(s_extraBlendShader);
	}
	s_terrainShader = 0;
	s_extraBlendShader = 0;
	REF_PTR_RELEASE(s_detailTexture);
	REF_PTR_RELEASE(s_whiteTexture);
	s_detailBuilt = FALSE;
	s_active = FALSE;
}

Bool W3DTerrainDetail::isActive()
{
	return s_active;
}

Bool W3DTerrainDetail::wantsReliefInAtlas()
{
	return s_active && TheGlobalData && TheGlobalData->m_terrainRelief;
}

void W3DTerrainDetail::bakeReliefRegion(UnsignedByte *bits, Int pitchBytes, Int x0, Int y0, Int size)
{
	if (!bits || size < 4)
		return;
	const TerrainLights lights = currentLights();
	const Int half = size / 2;

	// Height: luminance at half resolution (also softens the 4x4 blocks of upscaled 64 pixel retail tiles).
	std::vector<Real> height(half * half);
	for (Int y = 0; y < half; ++y) {
		const UnsignedByte *row0 = bits + (y0 + 2 * y) * pitchBytes + x0 * 4;
		const UnsignedByte *row1 = row0 + pitchBytes;
		for (Int x = 0; x < half; ++x) {
			const UnsignedByte *a = row0 + 8 * x;
			const UnsignedByte *b = row1 + 8 * x;
			// Texels are B, G, R, A in memory.
			const Real sum = luminance((Real)(a[2] + a[6] + b[2] + b[6]), (Real)(a[1] + a[5] + b[1] + b[5]),
				(Real)(a[0] + a[4] + b[0] + b[4]));
			height[y * half + x] = sum * (1.0f / (4.0f * 255.0f));
		}
	}
	boxBlurWrap(height, half);
	boxBlurWrap(height, half);

	// Relief shade relative to a flat surface; atlas +column is world +X, atlas +row is world -Y.
	std::vector<Real> shade(half * half);
	double sum = 0.0;
	for (Int y = 0; y < half; ++y) {
		const Real *up = &height[((y + half - 1) % half) * half];
		const Real *down = &height[((y + 1) % half) * half];
		const Real *row = &height[y * half];
		for (Int x = 0; x < half; ++x) {
			const Real dcol = (row[(x + 1) % half] - row[(x + half - 1) % half]) * 0.5f;
			const Real drow = (down[x] - up[x]) * 0.5f;
			const Real nx = -TILE_RELIEF_SLOPE * dcol;
			const Real ny = TILE_RELIEF_SLOPE * drow;
			const Real len = WWMath::Sqrt(nx * nx + ny * ny + 1.0f);
			const Real s = lights.flat > 0.05f ? lights.shade(nx / len, ny / len, 1.0f / len) / lights.flat : 1.0f;
			shade[y * half + x] = s;
			sum += s;
		}
	}
	// An average of 1 keeps the brightness of the texture class (and the far view) as before.
	const Real mean = (Real)(sum / (double)(half * half));
	const Real scale = mean > 0.0f ? 1.0f / mean : 1.0f;
	for (Int i = 0; i < half * half; ++i)
		shade[i] = clampReal(shade[i] * scale, 0.5f, 1.5f);

	// Bilinear upsample into the alpha channel, stored as shade / 2.
	for (Int y = 0; y < size; ++y) {
		const Real sy = (y + 0.5f) * 0.5f - 0.5f;
		const Int iy = (Int)WWMath::Floor(sy);
		const Real fy = sy - (Real)iy;
		const Int ya = (iy + half) % half;
		const Int yb = (iy + 1 + half) % half;
		UnsignedByte *dst = bits + (y0 + y) * pitchBytes + x0 * 4 + 3;
		for (Int x = 0; x < size; ++x) {
			const Real sx = (x + 0.5f) * 0.5f - 0.5f;
			const Int ix = (Int)WWMath::Floor(sx);
			const Real fx = sx - (Real)ix;
			const Int xa = (ix + half) % half;
			const Int xb = (ix + 1 + half) % half;
			const Real top = shade[ya * half + xa] + (shade[ya * half + xb] - shade[ya * half + xa]) * fx;
			const Real bottom = shade[yb * half + xa] + (shade[yb * half + xb] - shade[yb * half + xa]) * fx;
			dst[4 * x] = (UnsignedByte)toByte((top + (bottom - top) * fy) * 0.5f);
		}
	}
}

void W3DTerrainDetail::finishReliefAtlas(IDirect3DTexture8 *atlas, Bool baked)
{
	s_atlasHasRelief = FALSE;
	if (!baked || !atlas)
		return;
	D3DSURFACE_DESC desc;
	const Int levels = (Int)atlas->GetLevelCount();
	const Int fadeCount = (Int)(sizeof(RELIEF_MIP_FADE) / sizeof(RELIEF_MIP_FADE[0]));
	for (Int level = 1; level < levels; ++level) {
		if (FAILED(atlas->GetLevelDesc(level, &desc)) || desc.Format != D3DFMT_A8R8G8B8)
			return;
		const Real fade = RELIEF_MIP_FADE[level < fadeCount ? level : fadeCount - 1];
		D3DLOCKED_RECT locked;
		if (FAILED(atlas->LockRect(level, &locked, nullptr, 0)))
			return;
		for (UnsignedInt y = 0; y < desc.Height; ++y) {
			UnsignedByte *p = (UnsignedByte *)locked.pBits + y * locked.Pitch + 3;
			for (UnsignedInt x = 0; x < desc.Width; ++x, p += 4) {
				const Real a = (Real)*p - 127.5f;
				*p = (UnsignedByte)toByte((127.5f + a * fade) / 255.0f);
			}
		}
		atlas->UnlockRect(level);
	}
	s_atlasHasRelief = TRUE;
	s_reliefLights = currentLights();
	if (!s_detailBuilt || !(s_detailLights == s_reliefLights))
		buildDetailTexture(s_reliefLights);
}

Bool W3DTerrainDetail::reliefNeedsRebake()
{
	return s_active && s_atlasHasRelief && !(currentLights() == s_reliefLights);
}

void W3DTerrainDetail::apply(Bool extraBlendTiles, TextureClass *atlas, TextureClass *cloud, TextureClass *lightMap,
	const D3DXMATRIX *cloudMatrix, const D3DXMATRIX *lightMapMatrix, const D3DXMATRIX &viewInverse)
{
	IDirect3DDevice8 *device = DX8Wrapper::_Get_D3D_Device8();
	DX8Wrapper::Apply_Render_State_Changes();

	IDirect3DTexture8 *atlasTexture = atlas ? atlas->Peek_D3D_Texture() : nullptr;
	device->SetTexture(0, atlasTexture);
	device->SetTexture(1, extraBlendTiles ? nullptr : atlasTexture);
	for (Int stage = 0; stage < 2; ++stage) {
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_ADDRESSU, D3DTADDRESS_CLAMP);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_ADDRESSV, D3DTADDRESS_CLAMP);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_TEXCOORDINDEX, stage);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_TEXTURETRANSFORMFLAGS, D3DTTFF_DISABLE);
		setTerrainFilter(stage);
	}

	D3DXMATRIX identity;
	D3DXMatrixIdentity(&identity);
	setProjectedStage(2, cloud, cloud && cloudMatrix ? *cloudMatrix : identity, FALSE);
	setProjectedStage(3, lightMap, lightMap && lightMapMatrix ? *lightMapMatrix : identity, TRUE);

	// World x, y -> detail uv: turned against the cell grid, one repeat per DETAIL_WORLD_SIZE units.
	D3DXMATRIX worldToDetail;
	D3DXMatrixIdentity(&worldToDetail);
	const Real inv = 1.0f / DETAIL_WORLD_SIZE;
	worldToDetail._11 = DETAIL_ANGLE_COS * inv;
	worldToDetail._21 = DETAIL_ANGLE_SIN * inv;
	worldToDetail._12 = -DETAIL_ANGLE_SIN * inv;
	worldToDetail._22 = DETAIL_ANGLE_COS * inv;
	D3DXMATRIX detailMatrix = viewInverse * worldToDetail;
	setProjectedStage(4, s_detailTexture, detailMatrix, FALSE);

	const Bool detailOn = TheGlobalData->m_terrainDetail;
	const Real detail = detailOn ? clampReal(TheGlobalData->m_terrainDetailStrength, 0.0f, 1.0f) : 0.0f;
	const Real soft = TheGlobalData->m_terrainSoftBlend ? 1.0f : 0.0f;
	const Real relief = (TheGlobalData->m_terrainRelief && s_atlasHasRelief) ? 1.0f : 0.0f;
	const float constants[12] =
	{
		detail, detail, detail, soft,
		0.5f, 0.5f, 0.5f, 0.5f,
		0.0f, 0.0f, 0.0f, relief,
	};
	device->SetPixelShaderConstant(0, constants, 3);
	device->SetPixelShader(extraBlendTiles ? s_extraBlendShader : s_terrainShader);

	if (extraBlendTiles) {
		DX8Wrapper::Set_DX8_Render_State(D3DRS_ALPHABLENDENABLE, TRUE);
		DX8Wrapper::Set_DX8_Render_State(D3DRS_SRCBLEND, D3DBLEND_SRCALPHA);
		DX8Wrapper::Set_DX8_Render_State(D3DRS_DESTBLEND, D3DBLEND_INVSRCALPHA);
	}
}

void W3DTerrainDetail::reset()
{
	IDirect3DDevice8 *device = DX8Wrapper::_Get_D3D_Device8();
	device->SetPixelShader(0);
	for (Int stage = 0; stage < 5; ++stage) {
		device->SetTexture(stage, nullptr);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_TEXTURETRANSFORMFLAGS, D3DTTFF_DISABLE);
		DX8Wrapper::Set_DX8_Texture_Stage_State(stage, D3DTSS_TEXCOORDINDEX, D3DTSS_TCI_PASSTHRU | stage);
	}
	DX8Wrapper::Invalidate_Cached_Render_States();
}
