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
// See modelnormalmap.h for the overview.

#include "modelnormalmap.h"

#include <map>
#include <stdio.h>
#include <string.h>
#include <vector>

#include "assetmgr.h"
#include "dx8caps.h"
#include "dx8wrapper.h"
#include "WWLib/ffactory.h"
#include "meshmdl.h"
#include "statistics.h"
#include "texture.h"
#include "WWMath/vector2.h"
#include "WWMath/wwmath.h"

// GeneralsX @bugfix Claude 17/10/2026 Off until Options.ini ModelNormalMaps = yes turns it on, so a build
// with this renderer plays exactly like one without it unless the feature is asked for.
bool ModelNormalMapClass::Enabled = false;
float ModelNormalMapClass::Specular = 1.0f;

namespace
{

/*
Vertex shader (vs.1.1). Assemble with scripts/tooling/shaders/assemble_ps1x.py.
Inputs: v0 position, v3 normal, v5 diffuse colour, v7 UV set 0, v8 packed tangent (the last UV set).
Constants:
  c0-c3   world * view * projection, transposed      c4-c6  world, transposed (rows 0..2)
  c7      (0, 0.5, 1, 2)                              c8     (fog end, 1 / (fog end - fog start), 0, 0)
  c9      column 2 of world * view (view space z)     c10/c11 diffuse: material * (1 - sel), sel
  c12/c13 ambient: material * (1 - sel), sel          c14/c15 emissive: material * (1 - sel), sel
  c16     global ambient (+ ambient of the per pixel lights)
  c17     camera position (world)                     c18/c19 stage 0 texture transform rows
  c20/c21 direction to per pixel light 0 / 1 (world, unit)
  c22-c25, c26-c29 vertex lights: (position, 1) or (direction to light, 0); diffuse; ambient;
          (attenuation 0, 1, 2, range squared)
Outputs: oT0 UV, oT1/oT2 light 0/1 in tangent space, oT3 half vector of light 0 in tangent space,
  oD0 = emissive + ambient + vertex lights (alpha = diffuse alpha), oD1 = material diffuse, oFog.

The tangent basis: the normal is normalised, a helper axis is X when |raw normal z| >= 0.5 and Z otherwise,
a = normalize(helper - n (n . helper)), b = n x a. The packed tangent is (t . a, t . b), twice as long when
the bitangent is -(n x t).

vs.1.1
dp4 oPos.x, v0, c0
dp4 oPos.y, v0, c1
dp4 oPos.z, v0, c2
dp4 oPos.w, v0, c3
dp4 r0.x, v0, c9
add r0.x, c8.x, -r0.x
mul oFog.x, r0.x, c8.y
mov r0.xy, v7
mov r0.zw, c7.xxzx
dp3 oT0.x, r0, c18
dp3 oT0.y, r0, c19
dp4 r1.x, v0, c4
dp4 r1.y, v0, c5
dp4 r1.z, v0, c6
mov r4.xyz, v3
max r2.x, r4.z, -r4.z
dp3 r4.w, r4, r4
rsq r4.w, r4.w
mul r4.xyz, r4, r4.w
sge r2.x, r2.x, c7.y
mul r3.xyz, r2.x, c7.zxz
add r3.z, c7.z, -r2.x
dp3 r5.w, r4, r3
mad r5.xyz, -r4, r5.w, r3
dp3 r5.w, r5, r5
rsq r5.w, r5.w
mul r5.xyz, r5, r5.w
mul r6.xyz, r4.yzx, r5.zxy
mad r6.xyz, -r4.zxy, r5.yzx, r6
mov r7.xy, v8
mul r7.xy, r7, r7
add r7.x, r7.x, r7.y
sge r7.x, r7.x, c7.w
mul r7.y, r7.x, c7.y
add r7.y, c7.z, -r7.y
add r7.z, r7.x, r7.x
add r7.z, c7.z, -r7.z
mul r8.xyz, r5, v8.x
mad r8.xyz, r6, v8.y, r8
mul r8.xyz, r8, r7.y
dp3 r2.x, r4, c4
dp3 r2.y, r4, c5
dp3 r2.z, r4, c6
dp3 r2.w, r2, r2
rsq r2.w, r2.w
mul r2.xyz, r2, r2.w
dp3 r3.x, r8, c4
dp3 r3.y, r8, c5
dp3 r3.z, r8, c6
dp3 r3.w, r3, r3
rsq r3.w, r3.w
mul r3.xyz, r3, r3.w
mul r4.xyz, r2.yzx, r3.zxy
mad r4.xyz, -r2.zxy, r3.yzx, r4
mul r4.xyz, r4, r7.z
dp3 oT1.x, c20, r3
dp3 oT1.y, c20, r4
dp3 oT1.z, c20, r2
dp3 oT2.x, c21, r3
dp3 oT2.y, c21, r4
dp3 oT2.z, c21, r2
add r5.xyz, c17, -r1
dp3 r5.w, r5, r5
rsq r5.w, r5.w
mad r5.xyz, r5, r5.w, c20
dp3 r5.w, r5, r5
rsq r5.w, r5.w
mul r5.xyz, r5, r5.w
dp3 oT3.x, r5, r3
dp3 oT3.y, r5, r4
dp3 oT3.z, r5, r2
mul r6, v5, c11
add r6, r6, c10
mul r7, v5, c13
add r7, r7, c12
mul r8, v5, c15
add r8, r8, c14
mov r9, c16
mov r10, c7.x
mul r11.xyz, r1, c22.w
add r11.xyz, c22, -r11
dp3 r11.w, r11, r11
rsq r0.y, r11.w
mul r11.xyz, r11, r0.y
mul r0.x, r11.w, r0.y
mul r0.z, r0.x, c25.y
add r0.z, r0.z, c25.x
mad r0.z, r11.w, c25.z, r0.z
rcp r0.z, r0.z
slt r0.w, r11.w, c25.w
mul r0.z, r0.z, r0.w
dp3 r0.x, r2, r11
max r0.x, r0.x, c7.x
mul r0.x, r0.x, r0.z
mad r10.xyz, c23, r0.x, r10
mad r9.xyz, c24, r0.z, r9
mul r11.xyz, r1, c26.w
add r11.xyz, c26, -r11
dp3 r11.w, r11, r11
rsq r0.y, r11.w
mul r11.xyz, r11, r0.y
mul r0.x, r11.w, r0.y
mul r0.z, r0.x, c29.y
add r0.z, r0.z, c29.x
mad r0.z, r11.w, c29.z, r0.z
rcp r0.z, r0.z
slt r0.w, r11.w, c29.w
mul r0.z, r0.z, r0.w
dp3 r0.x, r2, r11
max r0.x, r0.x, c7.x
mul r0.x, r0.x, r0.z
mad r10.xyz, c27, r0.x, r10
mad r9.xyz, c28, r0.z, r9
mul r9.xyz, r9, r7
add r9.xyz, r9, r8
mad oD0.xyz, r10, r6, r9
mov oD0.w, r6.w
mov oD1, r6
*/
static const DWORD kModelNormalMapVS[] =
{
	0xfffe0101, 0x00000009, 0xc0010000, 0x90e40000, 0xa0e40000, 0x00000009,
	0xc0020000, 0x90e40000, 0xa0e40001, 0x00000009, 0xc0040000, 0x90e40000,
	0xa0e40002, 0x00000009, 0xc0080000, 0x90e40000, 0xa0e40003, 0x00000009,
	0x80010000, 0x90e40000, 0xa0e40009, 0x00000002, 0x80010000, 0xa0000008,
	0x81000000, 0x00000005, 0xc0010001, 0x80000000, 0xa0550008, 0x00000001,
	0x80030000, 0x90e40007, 0x00000001, 0x800c0000, 0xa0200007, 0x00000008,
	0xe0010000, 0x80e40000, 0xa0e40012, 0x00000008, 0xe0020000, 0x80e40000,
	0xa0e40013, 0x00000009, 0x80010001, 0x90e40000, 0xa0e40004, 0x00000009,
	0x80020001, 0x90e40000, 0xa0e40005, 0x00000009, 0x80040001, 0x90e40000,
	0xa0e40006, 0x00000001, 0x80070004, 0x90e40003, 0x0000000b, 0x80010002,
	0x80aa0004, 0x81aa0004, 0x00000008, 0x80080004, 0x80e40004, 0x80e40004,
	0x00000007, 0x80080004, 0x80ff0004, 0x00000005, 0x80070004, 0x80e40004,
	0x80ff0004, 0x0000000d, 0x80010002, 0x80000002, 0xa0550007, 0x00000005,
	0x80070003, 0x80000002, 0xa0a20007, 0x00000002, 0x80040003, 0xa0aa0007,
	0x81000002, 0x00000008, 0x80080005, 0x80e40004, 0x80e40003, 0x00000004,
	0x80070005, 0x81e40004, 0x80ff0005, 0x80e40003, 0x00000008, 0x80080005,
	0x80e40005, 0x80e40005, 0x00000007, 0x80080005, 0x80ff0005, 0x00000005,
	0x80070005, 0x80e40005, 0x80ff0005, 0x00000005, 0x80070006, 0x80090004,
	0x80520005, 0x00000004, 0x80070006, 0x81520004, 0x80090005, 0x80e40006,
	0x00000001, 0x80030007, 0x90e40008, 0x00000005, 0x80030007, 0x80e40007,
	0x80e40007, 0x00000002, 0x80010007, 0x80000007, 0x80550007, 0x0000000d,
	0x80010007, 0x80000007, 0xa0ff0007, 0x00000005, 0x80020007, 0x80000007,
	0xa0550007, 0x00000002, 0x80020007, 0xa0aa0007, 0x81550007, 0x00000002,
	0x80040007, 0x80000007, 0x80000007, 0x00000002, 0x80040007, 0xa0aa0007,
	0x81aa0007, 0x00000005, 0x80070008, 0x80e40005, 0x90000008, 0x00000004,
	0x80070008, 0x80e40006, 0x90550008, 0x80e40008, 0x00000005, 0x80070008,
	0x80e40008, 0x80550007, 0x00000008, 0x80010002, 0x80e40004, 0xa0e40004,
	0x00000008, 0x80020002, 0x80e40004, 0xa0e40005, 0x00000008, 0x80040002,
	0x80e40004, 0xa0e40006, 0x00000008, 0x80080002, 0x80e40002, 0x80e40002,
	0x00000007, 0x80080002, 0x80ff0002, 0x00000005, 0x80070002, 0x80e40002,
	0x80ff0002, 0x00000008, 0x80010003, 0x80e40008, 0xa0e40004, 0x00000008,
	0x80020003, 0x80e40008, 0xa0e40005, 0x00000008, 0x80040003, 0x80e40008,
	0xa0e40006, 0x00000008, 0x80080003, 0x80e40003, 0x80e40003, 0x00000007,
	0x80080003, 0x80ff0003, 0x00000005, 0x80070003, 0x80e40003, 0x80ff0003,
	0x00000005, 0x80070004, 0x80090002, 0x80520003, 0x00000004, 0x80070004,
	0x81520002, 0x80090003, 0x80e40004, 0x00000005, 0x80070004, 0x80e40004,
	0x80aa0007, 0x00000008, 0xe0010001, 0xa0e40014, 0x80e40003, 0x00000008,
	0xe0020001, 0xa0e40014, 0x80e40004, 0x00000008, 0xe0040001, 0xa0e40014,
	0x80e40002, 0x00000008, 0xe0010002, 0xa0e40015, 0x80e40003, 0x00000008,
	0xe0020002, 0xa0e40015, 0x80e40004, 0x00000008, 0xe0040002, 0xa0e40015,
	0x80e40002, 0x00000002, 0x80070005, 0xa0e40011, 0x81e40001, 0x00000008,
	0x80080005, 0x80e40005, 0x80e40005, 0x00000007, 0x80080005, 0x80ff0005,
	0x00000004, 0x80070005, 0x80e40005, 0x80ff0005, 0xa0e40014, 0x00000008,
	0x80080005, 0x80e40005, 0x80e40005, 0x00000007, 0x80080005, 0x80ff0005,
	0x00000005, 0x80070005, 0x80e40005, 0x80ff0005, 0x00000008, 0xe0010003,
	0x80e40005, 0x80e40003, 0x00000008, 0xe0020003, 0x80e40005, 0x80e40004,
	0x00000008, 0xe0040003, 0x80e40005, 0x80e40002, 0x00000005, 0x800f0006,
	0x90e40005, 0xa0e4000b, 0x00000002, 0x800f0006, 0x80e40006, 0xa0e4000a,
	0x00000005, 0x800f0007, 0x90e40005, 0xa0e4000d, 0x00000002, 0x800f0007,
	0x80e40007, 0xa0e4000c, 0x00000005, 0x800f0008, 0x90e40005, 0xa0e4000f,
	0x00000002, 0x800f0008, 0x80e40008, 0xa0e4000e, 0x00000001, 0x800f0009,
	0xa0e40010, 0x00000001, 0x800f000a, 0xa0000007, 0x00000005, 0x8007000b,
	0x80e40001, 0xa0ff0016, 0x00000002, 0x8007000b, 0xa0e40016, 0x81e4000b,
	0x00000008, 0x8008000b, 0x80e4000b, 0x80e4000b, 0x00000007, 0x80020000,
	0x80ff000b, 0x00000005, 0x8007000b, 0x80e4000b, 0x80550000, 0x00000005,
	0x80010000, 0x80ff000b, 0x80550000, 0x00000005, 0x80040000, 0x80000000,
	0xa0550019, 0x00000002, 0x80040000, 0x80aa0000, 0xa0000019, 0x00000004,
	0x80040000, 0x80ff000b, 0xa0aa0019, 0x80aa0000, 0x00000006, 0x80040000,
	0x80aa0000, 0x0000000c, 0x80080000, 0x80ff000b, 0xa0ff0019, 0x00000005,
	0x80040000, 0x80aa0000, 0x80ff0000, 0x00000008, 0x80010000, 0x80e40002,
	0x80e4000b, 0x0000000b, 0x80010000, 0x80000000, 0xa0000007, 0x00000005,
	0x80010000, 0x80000000, 0x80aa0000, 0x00000004, 0x8007000a, 0xa0e40017,
	0x80000000, 0x80e4000a, 0x00000004, 0x80070009, 0xa0e40018, 0x80aa0000,
	0x80e40009, 0x00000005, 0x8007000b, 0x80e40001, 0xa0ff001a, 0x00000002,
	0x8007000b, 0xa0e4001a, 0x81e4000b, 0x00000008, 0x8008000b, 0x80e4000b,
	0x80e4000b, 0x00000007, 0x80020000, 0x80ff000b, 0x00000005, 0x8007000b,
	0x80e4000b, 0x80550000, 0x00000005, 0x80010000, 0x80ff000b, 0x80550000,
	0x00000005, 0x80040000, 0x80000000, 0xa055001d, 0x00000002, 0x80040000,
	0x80aa0000, 0xa000001d, 0x00000004, 0x80040000, 0x80ff000b, 0xa0aa001d,
	0x80aa0000, 0x00000006, 0x80040000, 0x80aa0000, 0x0000000c, 0x80080000,
	0x80ff000b, 0xa0ff001d, 0x00000005, 0x80040000, 0x80aa0000, 0x80ff0000,
	0x00000008, 0x80010000, 0x80e40002, 0x80e4000b, 0x0000000b, 0x80010000,
	0x80000000, 0xa0000007, 0x00000005, 0x80010000, 0x80000000, 0x80aa0000,
	0x00000004, 0x8007000a, 0xa0e4001b, 0x80000000, 0x80e4000a, 0x00000004,
	0x80070009, 0xa0e4001c, 0x80aa0000, 0x80e40009, 0x00000005, 0x80070009,
	0x80e40009, 0x80e40007, 0x00000002, 0x80070009, 0x80e40009, 0x80e40008,
	0x00000004, 0xd0070000, 0x80e4000a, 0x80e40006, 0x80e40009, 0x00000001,
	0xd0080000, 0x80ff0006, 0x00000001, 0xd00f0001, 0x80e40006, 0x0000ffff,
};

/*
Pixel shader (ps.1.4).
Stages: 0 base texture, 1 normal map (rgb tangent space normal, alpha gloss), both on UV set 0.
Constants: c0 / c1 = colour of per pixel light 0 / 1, c2 = specular colour (light 0 * ModelSpecular / 2).
Result: base * saturate(v0 + v1 * (light0 + light1)) + 2 * c2 * gloss * (N . H)^16; alpha = base * v0.

ps.1.4
texld r1, t0
texcrd r2.rgb, t1
texcrd r3.rgb, t2
texcrd r4.rgb, t3
dp3_sat r2, r1_bx2, r2
dp3_sat r3, r1_bx2, r3
dp3_sat r4, r1_bx2, r4
mul r2.rgb, r2, c0
mad r2.rgb, r3, c1, r2
mul r4.rgb, r4, r4
mul r4.rgb, r4, r4
mov r5.rgb, r1.a
phase
texld r0, t0
mul r4.rgb, r4, r4
mul r4.rgb, r4, r4
mul r4.rgb, r4, r5
mad_sat r2.rgb, r2, v1, v0
mul r0.rgb, r0, r2
+mul r0.a, r0.a, v0.a
mul_x2 r4.rgb, r4, c2
add_sat r0.rgb, r0, r4
*/
static const DWORD kModelNormalMapPS[] =
{
	0xffff0104, 0x00000042, 0x800f0001, 0xb0e40000, 0x00000040, 0x80070002,
	0xb0e40001, 0x00000040, 0x80070003, 0xb0e40002, 0x00000040, 0x80070004,
	0xb0e40003, 0x00000008, 0x801f0002, 0x84e40001, 0x80e40002, 0x00000008,
	0x801f0003, 0x84e40001, 0x80e40003, 0x00000008, 0x801f0004, 0x84e40001,
	0x80e40004, 0x00000005, 0x80070002, 0x80e40002, 0xa0e40000, 0x00000004,
	0x80070002, 0x80e40003, 0xa0e40001, 0x80e40002, 0x00000005, 0x80070004,
	0x80e40004, 0x80e40004, 0x00000005, 0x80070004, 0x80e40004, 0x80e40004,
	0x00000001, 0x80070005, 0x80ff0001, 0x0000fffd, 0x00000042, 0x800f0000,
	0xb0e40000, 0x00000005, 0x80070004, 0x80e40004, 0x80e40004, 0x00000005,
	0x80070004, 0x80e40004, 0x80e40004, 0x00000005, 0x80070004, 0x80e40004,
	0x80e40005, 0x00000004, 0x80170002, 0x80e40002, 0x90e40001, 0x90e40000,
	0x00000005, 0x80070000, 0x80e40000, 0x80e40002, 0x40000005, 0x80080000,
	0x80ff0000, 0x90ff0000, 0x00000005, 0x81070004, 0x80e40004, 0xa0e40002,
	0x00000002, 0x80170000, 0x80e40000, 0x80e40004, 0x0000ffff,
};

const float SPECULAR_MAX = 2.0f;

struct NormalMapState
{
	NormalMapState() : PixelShader(0), PixelShaderFailed(false), SavedVertexShader(0), SavedPixelShader(0) {}

	DWORD PixelShader;
	bool PixelShaderFailed;
	std::map<unsigned, DWORD> VertexShaders;	///< per FVF; 0 = could not be created
	std::map<MeshModelClass *, std::vector<Vector4> > SkinTangents;	///< empty = not normal mapped
	DWORD SavedVertexShader;
	DWORD SavedPixelShader;
};

// GeneralsX @bugfix Claude 17/10/2026 Created on first use and deleted by Shutdown instead of a function
// local static: mesh models can be unregistered (Forget_Mesh) after static destruction has started, and a
// game that never turns the feature on never creates it.
NormalMapState * g_state = nullptr;

NormalMapState & state()
{
	if (g_state == nullptr)
		g_state = W3DNEW NormalMapState;
	return *g_state;
}

bool shaders_supported()
{
	if (DX8Wrapper::_Get_D3D_Device8() == nullptr)
		return false;
	const DX8Caps * caps = DX8Wrapper::Get_Current_Caps();
	const int vs = caps->Get_Vertex_Shader_Major_Version() * 256 + caps->Get_Vertex_Shader_Minor_Version();
	const int ps = caps->Get_Pixel_Shader_Major_Version() * 256 + caps->Get_Pixel_Shader_Minor_Version();
	return vs >= 0x101 && ps >= 0x104;
}

int texcoord_sets(unsigned fvf)
{
	return (int)((fvf & D3DFVF_TEXCOUNT_MASK) >> D3DFVF_TEXCOUNT_SHIFT);
}

/// Vertex shader for one vertex format; the tangent channel is its last texture coordinate set.
DWORD vertex_shader_for(unsigned fvf)
{
	NormalMapState & s = state();
	std::map<unsigned, DWORD>::iterator it = s.VertexShaders.find(fvf);
	if (it != s.VertexShaders.end())
		return it->second;

	DWORD handle = 0;
	const int sets = texcoord_sets(fvf);
	const bool layout_ok = (fvf & D3DFVF_POSITION_MASK) == D3DFVF_XYZ && (fvf & D3DFVF_NORMAL) != 0
		&& sets >= 2 && (fvf >> 16) == 0;
	if (layout_ok) {
		DWORD decl[16];
		int n = 0;
		decl[n++] = D3DVSD_STREAM(0);
		decl[n++] = D3DVSD_REG(0, D3DVSDT_FLOAT3);
		decl[n++] = D3DVSD_REG(3, D3DVSDT_FLOAT3);
		if (fvf & D3DFVF_DIFFUSE) decl[n++] = D3DVSD_REG(5, D3DVSDT_D3DCOLOR);
		if (fvf & D3DFVF_SPECULAR) decl[n++] = D3DVSD_SKIP(1);
		for (int i = 0; i < sets; ++i) {
			if (i == 0) decl[n++] = D3DVSD_REG(7, D3DVSDT_FLOAT2);
			else if (i == sets - 1) decl[n++] = D3DVSD_REG(8, D3DVSDT_FLOAT2);
			else decl[n++] = D3DVSD_SKIP(2);
		}
		decl[n++] = D3DVSD_END();
		if (FAILED(DX8Wrapper::_Get_D3D_Device8()->CreateVertexShader(decl, kModelNormalMapVS, &handle, 0))) {
			handle = 0;
		}
		fprintf(stderr, "[NORMALMAP] vertex shader for FVF 0x%x %s\n", fvf, handle ? "created" : "FAILED, fixed function used");
		fflush(stderr);
	}
	s.VertexShaders[fvf] = handle;
	return handle;
}

DWORD pixel_shader()
{
	NormalMapState & s = state();
	if (s.PixelShader == 0 && !s.PixelShaderFailed) {
		if (FAILED(DX8Wrapper::_Get_D3D_Device8()->CreatePixelShader(kModelNormalMapPS, &s.PixelShader))) {
			s.PixelShader = 0;
			s.PixelShaderFailed = true;
			fprintf(stderr, "[NORMALMAP] pixel shader FAILED, normal maps off\n");
			fflush(stderr);
		}
	}
	return s.PixelShader;
}

/// The texture name without the house colour / hue shift decoration W3DAssetManager adds to recoloured
/// copies ("#color#name", "#color!scale!tex#name", "#name!HxSxVx").
void base_texture_name(const char * name, char * out, size_t out_size)
{
	if (name[0] == '#') {
		const char * last_hash = strrchr(name, '#');
		if (last_hash != name) {
			name = last_hash + 1;
		} else {
			++name;
		}
	}
	strlcpy(out, name, out_size);
	char * bang = strchr(out, '!');
	if (bang) *bang = 0;
	char * dot = strrchr(out, '.');
	if (dot) *dot = 0;
}

bool file_exists(const char * name)
{
	if (_TheFileFactory == nullptr)
		return false;
	file_auto_ptr file(_TheFileFactory, name);
	return file->Is_Available();
}

TextureClass * mesh_normal_map(MeshModelClass * mmc)
{
	if (mmc->Get_Pass_Count() < 1)
		return nullptr;
	if (mmc->Has_Texture_Array(0, 0)) {
		TextureClass * last = nullptr;
		for (int i = 0; i < mmc->Get_Polygon_Count(); ++i) {
			TextureClass * tex = mmc->Peek_Texture(i, 0, 0);
			if (tex == nullptr || tex == last)
				continue;
			last = tex;
			TextureClass * normal_map = ModelNormalMapClass::Peek_Normal_Map(tex, mmc->Get_Name());
			if (normal_map)
				return normal_map;
		}
		return nullptr;
	}
	TextureClass * tex = mmc->Peek_Single_Texture(0, 0);
	return tex ? ModelNormalMapClass::Peek_Normal_Map(tex, mmc->Get_Name()) : nullptr;
}

/// Per vertex tangents from the triangles' UV gradients (xyz unit tangent along +U, w = sign of the
/// bitangent along -V, which is "up" in an OpenGL normal map since the loader flips V).
void compute_tangents(MeshModelClass * mmc, std::vector<Vector4> & out)
{
	const int vcount = mmc->Get_Vertex_Count();
	const Vector3 * pos = mmc->Get_Vertex_Array();
	const Vector3 * nrm = mmc->Get_Vertex_Normal_Array();
	const Vector2 * uv = mmc->Get_UV_Array_By_Index(0);
	const TriIndex * tris = mmc->Get_Polygon_Array();
	const int tcount = mmc->Get_Polygon_Count();

	std::vector<Vector3> sdir(vcount, Vector3(0.0f, 0.0f, 0.0f));
	std::vector<Vector3> tdir(vcount, Vector3(0.0f, 0.0f, 0.0f));
	for (int t = 0; uv != nullptr && t < tcount; ++t) {
		const int i0 = tris[t][0];
		const int i1 = tris[t][1];
		const int i2 = tris[t][2];
		if (i0 >= vcount || i1 >= vcount || i2 >= vcount)
			continue;
		const Vector3 e1 = pos[i1] - pos[i0];
		const Vector3 e2 = pos[i2] - pos[i0];
		const float du1 = uv[i1].X - uv[i0].X;
		const float dv1 = uv[i1].Y - uv[i0].Y;
		const float du2 = uv[i2].X - uv[i0].X;
		const float dv2 = uv[i2].Y - uv[i0].Y;
		const float det = du1 * dv2 - du2 * dv1;
		if (WWMath::Fabs(det) < 1e-12f)
			continue;
		const float r = 1.0f / det;
		const Vector3 s = (e1 * dv2 - e2 * dv1) * r;
		const Vector3 tv = (e2 * du1 - e1 * du2) * r;
		sdir[i0] += s; sdir[i1] += s; sdir[i2] += s;
		tdir[i0] += tv; tdir[i1] += tv; tdir[i2] += tv;
	}

	out.resize(vcount);
	for (int v = 0; v < vcount; ++v) {
		Vector3 n = nrm ? nrm[v] : Vector3(0.0f, 0.0f, 1.0f);
		if (n.Length2() < 1e-12f) n.Set(0.0f, 0.0f, 1.0f);
		n.Normalize();
		Vector3 t = sdir[v] - n * Vector3::Dot_Product(n, sdir[v]);
		if (t.Length2() < 1e-12f) {
			const Vector3 helper = WWMath::Fabs(n.Z) >= 0.5f ? Vector3(1.0f, 0.0f, 0.0f) : Vector3(0.0f, 0.0f, 1.0f);
			t = helper - n * Vector3::Dot_Product(n, helper);
		}
		t.Normalize();
		Vector3 n_cross_t;
		Vector3::Cross_Product(n, t, &n_cross_t);
		const float sign = Vector3::Dot_Product(n_cross_t, -tdir[v]) < 0.0f ? -1.0f : 1.0f;
		out[v].Set(t.X, t.Y, t.Z, sign);
	}
}

void set4(float * c, float x, float y, float z, float w)
{
	c[0] = x; c[1] = y; c[2] = z; c[3] = w;
}

float clamp01(float v)
{
	return v < 0.0f ? 0.0f : (v > 1.0f ? 1.0f : v);
}

void multiply(const D3DMATRIX & a, const D3DMATRIX & b, D3DMATRIX & out)
{
	for (int i = 0; i < 4; ++i) {
		for (int j = 0; j < 4; ++j) {
			out.m[i][j] = a.m[i][0] * b.m[0][j] + a.m[i][1] * b.m[1][j] + a.m[i][2] * b.m[2][j] + a.m[i][3] * b.m[3][j];
		}
	}
}

void column(const D3DMATRIX & m, int c, float * out)
{
	set4(out, m.m[0][c], m.m[1][c], m.m[2][c], m.m[3][c]);
}

float dword_to_float(DWORD v)
{
	float f;
	memcpy(&f, &v, sizeof(f));
	return f;
}

/// Material colour selection: constants (material * (1 - sel), sel) as the vertex shader mixes them.
void material_source(IDirect3DDevice8 * dev, D3DRENDERSTATETYPE rs, bool vertex_colors, const D3DCOLORVALUE & material,
	float * base, float * sel)
{
	DWORD source = D3DMCS_MATERIAL;
	dev->GetRenderState(rs, &source);
	const float s = (vertex_colors && source == D3DMCS_COLOR1) ? 1.0f : 0.0f;
	set4(base, material.r * (1.0f - s), material.g * (1.0f - s), material.b * (1.0f - s), material.a * (1.0f - s));
	set4(sel, s, s, s, s);
}

} // namespace

void ModelNormalMapClass::Set_Specular(float strength)
{
	Specular = strength < 0.0f ? 0.0f : (strength > SPECULAR_MAX ? SPECULAR_MAX : strength);
}

TextureClass * ModelNormalMapClass::Peek_Normal_Map(TextureClass * base, const char * mesh_name)
{
	// GeneralsX @bugfix Claude 17/10/2026 No lookups at all while the feature is off. Otherwise the result,
	// found or not, is cached on the texture: a texture without a _n map is probed once and stays silent.
	if (!Enabled || base == nullptr)
		return nullptr;
	if (base->NormalMapLookedUp)
		return base->NormalMap;
	base->NormalMapLookedUp = true;

	const char * texture_name = base->Get_Texture_Name().str();
	if (texture_name == nullptr || texture_name[0] == 0)
		return nullptr;
	char name[256];
	base_texture_name(texture_name, name, sizeof(name));
	if (name[0] == 0)
		return nullptr;
	const size_t len = strlen(name);
	if (len > 2 && stricmp(name + len - 2, "_n") == 0)
		return nullptr;	// a normal map itself

	static const char * const extensions[] = { "_n.dds", "_n.tga" };
	for (int i = 0; i < 2; ++i) {
		char file[280];
		snprintf(file, sizeof(file), "%s%s", name, extensions[i]);
		if (!file_exists(file))
			continue;
		base->NormalMap = WW3DAssetManager::Get_Instance()->Get_Texture(file, MIP_LEVELS_ALL, WW3D_FORMAT_UNKNOWN, false);
		fprintf(stderr, "[NORMALMAP] %s %s for mesh %s (texture %s)\n", base->NormalMap ? "loaded" : "FAILED to load", file,
			mesh_name ? mesh_name : "?", base->Get_Texture_Name().str());
		fflush(stderr);
		break;
	}
	return base->NormalMap;
}

bool ModelNormalMapClass::Mesh_Wants_Tangents(MeshModelClass * mmc)
{
	if (!Enabled || !shaders_supported())
		return false;
	if (!mmc->Needs_Vertex_Normals() || mmc->Get_UV_Array_By_Index(0) == nullptr)
		return false;
	const int sets = mmc->Get_UV_Array_Count();
	if (sets < 1 || sets > 7)
		return false;
	return mesh_normal_map(mmc) != nullptr;
}

unsigned ModelNormalMapClass::Add_Tangent_Channel(unsigned fvf)
{
	const unsigned sets = (unsigned)texcoord_sets(fvf) + 1;
	return (fvf & ~D3DFVF_TEXCOUNT_MASK) | (sets << D3DFVF_TEXCOUNT_SHIFT);
}

void ModelNormalMapClass::Write_Rigid_Tangents(MeshModelClass * mmc, unsigned char * vertices, unsigned stride, unsigned offset)
{
	std::vector<Vector4> tangents;
	compute_tangents(mmc, tangents);
	const Vector3 * nrm = mmc->Get_Vertex_Normal_Array();
	for (size_t v = 0; v < tangents.size(); ++v) {
		float * dst = (float *)(vertices + v * stride + offset);
		const Vector3 n = nrm ? nrm[v] : Vector3(0.0f, 0.0f, 1.0f);
		Pack_Tangent(n, Vector3(tangents[v].X, tangents[v].Y, tangents[v].Z), tangents[v].W, dst[0], dst[1]);
	}
}

const Vector4 * ModelNormalMapClass::Peek_Skin_Tangents(MeshModelClass * mmc)
{
	// GeneralsX @bugfix Claude 17/10/2026 Nothing is created or kept for skins while the feature is off.
	if (!Enabled || mmc == nullptr)
		return nullptr;
	NormalMapState & s = state();
	std::map<MeshModelClass *, std::vector<Vector4> >::iterator it = s.SkinTangents.find(mmc);
	if (it == s.SkinTangents.end()) {
		std::vector<Vector4> & tangents = s.SkinTangents[mmc];
		if (Enabled && shaders_supported() && mmc->Get_UV_Array_By_Index(0) != nullptr
			&& mmc->Get_UV_Array_By_Index(1) == nullptr && mmc->Get_Vertex_Bone_Links() != nullptr
			&& mesh_normal_map(mmc) != nullptr) {
			compute_tangents(mmc, tangents);
		}
		return tangents.empty() ? nullptr : &tangents[0];
	}
	return it->second.empty() ? nullptr : &it->second[0];
}

void ModelNormalMapClass::Forget_Mesh(MeshModelClass * mmc)
{
	// GeneralsX @bugfix Claude 17/10/2026 A no-op when nothing was ever kept.
	if (g_state != nullptr)
		g_state->SkinTangents.erase(mmc);
}

void ModelNormalMapClass::Pack_Tangent(const Vector3 & normal, const Vector3 & tangent, float sign, float & a, float & b)
{
	const bool helper_x = WWMath::Fabs(normal.Z) >= 0.5f;
	Vector3 n = normal;
	if (n.Length2() < 1e-12f) n.Set(0.0f, 0.0f, 1.0f);
	n.Normalize();
	const Vector3 helper = helper_x ? Vector3(1.0f, 0.0f, 0.0f) : Vector3(0.0f, 0.0f, 1.0f);
	Vector3 axis_a = helper - n * Vector3::Dot_Product(n, helper);
	axis_a.Normalize();
	Vector3 axis_b;
	Vector3::Cross_Product(n, axis_a, &axis_b);
	float ta = Vector3::Dot_Product(tangent, axis_a);
	float tb = Vector3::Dot_Product(tangent, axis_b);
	const float len2 = ta * ta + tb * tb;
	if (len2 < 1e-12f) {
		ta = 1.0f;
		tb = 0.0f;
	} else {
		const float inv = 1.0f / WWMath::Sqrt(len2);
		ta *= inv;
		tb *= inv;
	}
	if (sign < 0.0f) {
		ta *= 2.0f;
		tb *= 2.0f;
	}
	a = ta;
	b = tb;
}

bool ModelNormalMapClass::Begin(TextureClass * normal_map)
{
	IDirect3DDevice8 * dev = DX8Wrapper::_Get_D3D_Device8();
	if (!Enabled || normal_map == nullptr || dev == nullptr || pixel_shader() == 0)
		return false;

	DX8Wrapper::Apply_Render_State_Changes();

	DWORD fvf = 0;
	dev->GetVertexShader(&fvf);
	if (fvf == 0 || (fvf & 1) != 0)
		return false;	// not an FVF draw
	const DWORD vs = vertex_shader_for(fvf);
	if (vs == 0)
		return false;

	DWORD value = 0;
	dev->GetRenderState(D3DRS_LIGHTING, &value);
	if (!value)
		return false;
	dev->GetTextureStageState(0, D3DTSS_TEXCOORDINDEX, &value);
	if (value != 0)
		return false;	// generated or remapped UVs

	float vc[30][4];
	memset(vc, 0, sizeof(vc));
	float pc[3][4];
	memset(pc, 0, sizeof(pc));

	// Texture transform of stage 0 (scrolling treads, animated UVs).
	DWORD tt_flags = D3DTTFF_DISABLE;
	dev->GetTextureStageState(0, D3DTSS_TEXTURETRANSFORMFLAGS, &tt_flags);
	if (tt_flags == D3DTTFF_DISABLE) {
		set4(vc[18], 1.0f, 0.0f, 0.0f, 0.0f);
		set4(vc[19], 0.0f, 1.0f, 0.0f, 0.0f);
	} else if (tt_flags == D3DTTFF_COUNT2) {
		D3DMATRIX tm;
		dev->GetTransform(D3DTS_TEXTURE0, &tm);
		set4(vc[18], tm.m[0][0], tm.m[1][0], tm.m[2][0], 0.0f);
		set4(vc[19], tm.m[0][1], tm.m[1][1], tm.m[2][1], 0.0f);
	} else {
		return false;
	}

	// Lights: the first two directional lights per pixel, up to two more per vertex.
	DWORD ambient_color = 0;
	dev->GetRenderState(D3DRS_AMBIENT, &ambient_color);
	float ambient[3] = {
		((ambient_color >> 16) & 0xFF) / 255.0f, ((ambient_color >> 8) & 0xFF) / 255.0f, (ambient_color & 0xFF) / 255.0f };
	int pixel_lights = 0;
	int vertex_lights = 0;
	for (int slot = 0; slot < 2; ++slot) {
		set4(vc[20 + slot], 0.0f, 0.0f, 1.0f, 0.0f);
		set4(vc[22 + slot * 4], 0.0f, 0.0f, 1.0f, 0.0f);
		set4(vc[25 + slot * 4], 1.0f, 0.0f, 0.0f, 0.0f);
	}
	for (DWORD i = 0; i < 4; ++i) {
		BOOL enabled = FALSE;
		if (FAILED(dev->GetLightEnable(i, &enabled)) || !enabled)
			continue;
		D3DLIGHT8 light;
		if (FAILED(dev->GetLight(i, &light)))
			continue;
		if (light.Type == D3DLIGHT_DIRECTIONAL) {
			Vector3 to_light(-light.Direction.x, -light.Direction.y, -light.Direction.z);
			if (to_light.Length2() < 1e-12f)
				continue;
			to_light.Normalize();
			if (pixel_lights < 2) {
				set4(vc[20 + pixel_lights], to_light.X, to_light.Y, to_light.Z, 0.0f);
				set4(pc[pixel_lights], clamp01(light.Diffuse.r), clamp01(light.Diffuse.g), clamp01(light.Diffuse.b), 0.0f);
				ambient[0] += light.Ambient.r;
				ambient[1] += light.Ambient.g;
				ambient[2] += light.Ambient.b;
				++pixel_lights;
				continue;
			}
			if (vertex_lights == 2)
				return false;
			float * c = vc[22 + vertex_lights * 4];
			set4(c, to_light.X, to_light.Y, to_light.Z, 0.0f);
			set4(c + 12, 1.0f, 0.0f, 0.0f, 1e30f);
		} else {
			if (vertex_lights == 2)
				return false;
			float * c = vc[22 + vertex_lights * 4];
			set4(c, light.Position.x, light.Position.y, light.Position.z, 1.0f);
			float a0 = light.Attenuation0;
			if (a0 + light.Attenuation1 + light.Attenuation2 <= 0.0f)
				a0 = 1.0f;
			set4(c + 12, a0, light.Attenuation1, light.Attenuation2, light.Range * light.Range);
		}
		float * c = vc[22 + vertex_lights * 4];
		set4(c + 4, light.Diffuse.r, light.Diffuse.g, light.Diffuse.b, 0.0f);
		set4(c + 8, light.Ambient.r, light.Ambient.g, light.Ambient.b, 0.0f);
		++vertex_lights;
	}
	if (pixel_lights == 0)
		return false;	// nothing to bump; keep fixed function
	set4(vc[16], ambient[0], ambient[1], ambient[2], 0.0f);
	const float spec = Specular * 0.5f;
	set4(pc[2], clamp01(pc[0][0] * spec), clamp01(pc[0][1] * spec), clamp01(pc[0][2] * spec), 0.0f);

	// Material and its colour sources.
	D3DMATERIAL8 material;
	if (FAILED(dev->GetMaterial(&material)))
		return false;
	DWORD color_vertex = FALSE;
	dev->GetRenderState(D3DRS_COLORVERTEX, &color_vertex);
	const bool vertex_colors = color_vertex && (fvf & D3DFVF_DIFFUSE) != 0;
	material_source(dev, D3DRS_DIFFUSEMATERIALSOURCE, vertex_colors, material.Diffuse, vc[10], vc[11]);
	material_source(dev, D3DRS_AMBIENTMATERIALSOURCE, vertex_colors, material.Ambient, vc[12], vc[13]);
	material_source(dev, D3DRS_EMISSIVEMATERIALSOURCE, vertex_colors, material.Emissive, vc[14], vc[15]);

	// Transforms, camera and fog.
	D3DMATRIX world, view, proj, world_view, wvp;
	dev->GetTransform(D3DTS_WORLD, &world);
	dev->GetTransform(D3DTS_VIEW, &view);
	dev->GetTransform(D3DTS_PROJECTION, &proj);
	multiply(world, view, world_view);
	multiply(world_view, proj, wvp);
	for (int i = 0; i < 4; ++i) column(wvp, i, vc[i]);
	for (int i = 0; i < 3; ++i) column(world, i, vc[4 + i]);
	set4(vc[7], 0.0f, 0.5f, 1.0f, 2.0f);
	column(world_view, 2, vc[9]);
	for (int i = 0; i < 3; ++i) {
		vc[17][i] = -(view.m[i][0] * view.m[3][0] + view.m[i][1] * view.m[3][1] + view.m[i][2] * view.m[3][2]);
	}
	DWORD fog_start = 0;
	DWORD fog_end = 0;
	dev->GetRenderState(D3DRS_FOGSTART, &fog_start);
	dev->GetRenderState(D3DRS_FOGEND, &fog_end);
	const float fs = dword_to_float(fog_start);
	const float fe = dword_to_float(fog_end);
	set4(vc[8], fe, (fe - fs) > 1e-6f ? 1.0f / (fe - fs) : 0.0f, 0.0f, 0.0f);

	NormalMapState & s = state();
	dev->GetPixelShader(&s.SavedPixelShader);
	s.SavedVertexShader = fvf;

	// Some code sets shader constants on the device directly, so the wrapper's constant cache cannot be trusted
	// to skip a write: set them on the device, then let the wrapper record them.
	dev->SetVertexShaderConstant(0, vc, 30);
	dev->SetPixelShaderConstant(0, pc, 3);
	DX8Wrapper::Set_Vertex_Shader_Constant(0, vc, 30);
	DX8Wrapper::Set_Pixel_Shader_Constant(0, pc, 3);
	DX8Wrapper::Set_Vertex_Shader(vs);
	DX8Wrapper::Set_Pixel_Shader(s.PixelShader);
	normal_map->Apply(1);
	Debug_Statistics::Record_DX8_Normal_Map_Draw();
	return true;
}

void ModelNormalMapClass::End()
{
	NormalMapState & s = state();
	DX8Wrapper::Set_Vertex_Shader(s.SavedVertexShader);
	DX8Wrapper::Set_Pixel_Shader(s.SavedPixelShader);
	TextureBaseClass::Apply_Null(1);
}

void ModelNormalMapClass::Shutdown()
{
	if (g_state == nullptr)
		return;
	NormalMapState & s = *g_state;
	IDirect3DDevice8 * dev = DX8Wrapper::_Get_D3D_Device8();
	if (dev) {
		for (std::map<unsigned, DWORD>::iterator it = s.VertexShaders.begin(); it != s.VertexShaders.end(); ++it) {
			if (it->second) dev->DeleteVertexShader(it->second);
		}
		if (s.PixelShader) dev->DeletePixelShader(s.PixelShader);
	}
	s.VertexShaders.clear();
	s.PixelShader = 0;
	s.PixelShaderFailed = false;
	s.SkinTangents.clear();
	delete g_state;
	g_state = nullptr;
}
