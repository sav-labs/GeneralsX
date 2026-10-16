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

// FILE: W3DSkinnedShadow.cpp /////////////////////////////////////////////////
//
// GeneralsX @feature Claude 16/10/2026 Shadows of skinned (and very high poly) W3D models, see W3DSkinnedShadow.h.
//
// Projected route, per frame:
//  1. updateRenderTargetTextures (before the main scene): culls the shadows, fades them with camera distance and
//     redraws the atlas tiles whose model changed pose (rotation or animation; pure translation keeps the tile),
//     at most updateBudget tiles per frame and one redraw per updateInterval frames for animated models. A tile
//     holds the posed caster triangles seen from the sun, flat in the shadow colour on white.
//  2. renderProjectedShadows (DoShadows, before the meshes): clips the terrain cells under each shadow to the
//     column of light its tile covers and draws them all in one multiplicative pass with the atlas.
// Volume route: renderVolumes is called inside the retail stencil pass; it rebuilds the silhouette volume of a
// shadow when its pose or the sun changed (vertices relative to the model root, so a moving unit only changes its
// world transform) and draws it in the increment and the decrement pass.
//
// Rendering only; nothing here feeds back into the game logic.

#include "WWLib/always.h"
#include "W3DDevice/GameClient/W3DSkinnedShadow.h"

#include <algorithm>
#include <stdio.h>
#include <string.h>
#include <vector>

#include "Common/GlobalData.h"
#include "Common/MapObject.h"
#include "Common/OptionPreferences.h"
#include "Common/PerfStats.h"
#include "GameClient/Drawable.h"
#include "GameClient/DrawableInfo.h"
#include "GameLogic/Object.h"
#include "GameLogic/TerrainLogic.h"
#include "WW3D2/camera.h"
#include "WW3D2/dx8wrapper.h"
#include "WW3D2/hlod.h"
#include "WW3D2/htree.h"
#include "WW3D2/mesh.h"
#include "WW3D2/meshmdl.h"
#include "WW3D2/rinfo.h"
#include "WW3D2/skinshadowgeometry.h"
#include "WWMath/colmath.h"
#include "W3DDevice/GameClient/HeightMap.h"
#include "W3DDevice/GameClient/WorldHeightMap.h"
#include "W3DDevice/GameClient/W3DProjectedShadow.h"
#include "W3DDevice/GameClient/W3DShadow.h"
#if defined(RTS_DEBUG)
#include "Common/DrawModule.h"
#endif

W3DSkinnedShadowManager *TheW3DSkinnedShadowManager = nullptr;

namespace
{
	const char *const s_modeNames[] = { "Decal", "Projected", "Volume" };
	const char *const s_qualityNames[] = { "Low", "Medium", "High" };

	// tile size, atlas size, update interval, updates per frame, volume proxy triangles, volume rebuilds per frame
	const Int s_presets[3][6] =
	{
		{  64, 1024, 3,  8,  1500,  4 },	// Low
		{ 128, 2048, 2, 16,  4000,  8 },	// Medium
		{ 256, 4096, 1, 32, 12000, 16 },	// High
	};

	const UnsignedInt STATS_INTERVAL_FRAMES = 600;
	const Real LIGHT_DIRECTION_COS = 0.99985f;	// redraw when the sun direction to the unit turned by about 1 degree
	const Real POSE_EPS_ROTATION = 0.002f;
	const Real POSE_EPS_POSITION = 0.02f;
	const Real TILE_EXTENT_SCALE = 1.04f;		// tile half size over the bounding sphere radius
	const Real TERRAIN_DECAL_LIFT = 0.01f * MAP_XY_FACTOR;	// same lift as the retail terrain decals
	const Real BRIDGE_DECAL_LIFT = 1.5f;		// same as the retail decals on bridges
	const Int MAX_FOOTPRINT_CELLS = 64;		// terrain cells per side under one shadow
	const Int MAX_DRAW_TRIANGLES = 20000;		// triangles per DrawPrimitiveUP of the terrain pass

	struct TileVertex
	{
		float x, y, z, rhw;
		DWORD diffuse;
	};
	const DWORD TILE_VERTEX_FVF = D3DFVF_XYZRHW | D3DFVF_DIFFUSE;

	struct TerrainVertex
	{
		float x, y, z;
		DWORD diffuse;
		float u, v;
	};
	const DWORD TERRAIN_VERTEX_FVF = D3DFVF_XYZ | D3DFVF_DIFFUSE | D3DFVF_TEX1;

	// scratch buffers, reused every frame
	std::vector<Vector3> s_skinVertices;
	std::vector<Vector3> s_skinNormals;
	std::vector<Vector3> s_worldVertices;
	std::vector<TileVertex> s_tileVertices;
	std::vector<TerrainVertex> s_terrainVertices;
	std::vector<SkinShadow::PrismVertex> s_gridVertices;
	std::vector<float> s_gridDepth;
	std::vector<float> s_poseEntries;

	/// Saves render and texture stage states before raw device calls and puts them back afterwards. The DX8Wrapper
	/// caches are invalidated as well (DX8Wrapper::Invalidate_Cached_Render_States) by the callers, like the retail
	/// shadow code does.
	class DeviceStateSaver
	{
	public:
		explicit DeviceStateSaver(IDirect3DDevice8 *device) : m_device(device), m_renderCount(0), m_stageCount(0) {}
		~DeviceStateSaver() { restore(); }

		void setRender(D3DRENDERSTATETYPE state, DWORD value)
		{
			if (m_renderCount < MAX_STATES && !hasRender(state))
			{
				DWORD old = 0;
				m_device->GetRenderState(state, &old);
				m_render[m_renderCount].state = state;
				m_render[m_renderCount].value = old;
				++m_renderCount;
			}
			m_device->SetRenderState(state, value);
		}

		void setStage(DWORD stage, D3DTEXTURESTAGESTATETYPE state, DWORD value)
		{
			if (m_stageCount < MAX_STATES && !hasStage(stage, state))
			{
				DWORD old = 0;
				m_device->GetTextureStageState(stage, state, &old);
				m_stage[m_stageCount].stage = stage;
				m_stage[m_stageCount].state = state;
				m_stage[m_stageCount].value = old;
				++m_stageCount;
			}
			m_device->SetTextureStageState(stage, state, value);
		}

		void restore()
		{
			while (m_stageCount > 0)
			{
				--m_stageCount;
				m_device->SetTextureStageState(m_stage[m_stageCount].stage, m_stage[m_stageCount].state, m_stage[m_stageCount].value);
			}
			while (m_renderCount > 0)
			{
				--m_renderCount;
				m_device->SetRenderState(m_render[m_renderCount].state, m_render[m_renderCount].value);
			}
		}

	private:
		enum { MAX_STATES = 32 };
		struct RenderEntry { D3DRENDERSTATETYPE state; DWORD value; };
		struct StageEntry { DWORD stage; D3DTEXTURESTAGESTATETYPE state; DWORD value; };

		bool hasRender(D3DRENDERSTATETYPE state) const
		{
			for (Int i = 0; i < m_renderCount; ++i)
				if (m_render[i].state == state)
					return true;
			return false;
		}
		bool hasStage(DWORD stage, D3DTEXTURESTAGESTATETYPE state) const
		{
			for (Int i = 0; i < m_stageCount; ++i)
				if (m_stage[i].stage == stage && m_stage[i].state == state)
					return true;
			return false;
		}

		IDirect3DDevice8 *m_device;
		RenderEntry m_render[MAX_STATES];
		StageEntry m_stage[MAX_STATES];
		Int m_renderCount;
		Int m_stageCount;
	};

	inline DWORD grayColor(Real value)
	{
		Int c = (Int)(value * 255.0f + 0.5f);
		c = c < 0 ? 0 : (c > 255 ? 255 : c);
		return 0xff000000 | (c << 16) | (c << 8) | c;
	}
}

// Model cache ================================================================

/// One caster mesh of a model: a mesh of the top LOD that the retail shadow volume code would use, plus skins.
struct SkinnedShadowCasterMesh
{
	Int lodModelIndex;			///< index in the top LOD of the HLOD, -1 = the render object is this mesh
	Bool isSkin;
	Int vertexCount;
	Int triangleCount;
	std::vector<unsigned short> indices;
	// shadow volume data, built when the first volume of this model is built
	Bool volumeDataBuilt;
	SkinShadow::SkinShadowTopology topology;
	std::vector<unsigned short> proxyIndices;
	SkinShadow::SkinShadowTopology proxyTopology;

	SkinnedShadowCasterMesh() : lodModelIndex(-1), isSkin(FALSE), vertexCount(0), triangleCount(0), volumeDataBuilt(FALSE) {}
};

struct SkinnedShadowModel
{
	SkinnedShadowModel *next;
	AsciiString name;
	std::vector<SkinnedShadowCasterMesh> meshes;
	Int totalTriangles;
	Int skinTriangles;
	Int rigidTriangles;
	Bool logged;

	SkinnedShadowModel() : next(nullptr), totalTriangles(0), skinTriangles(0), rigidTriangles(0), logged(FALSE) {}
};

// Shadow =====================================================================

class W3DSkinnedShadow final : public Shadow
{
	friend class W3DSkinnedShadowManager;

public:
	W3DSkinnedShadow();
	~W3DSkinnedShadow();	///< Shadow has no virtual destructor; the manager deletes W3DSkinnedShadow pointers only

	virtual void release() override;
#if defined(RTS_DEBUG)
	virtual void getRenderCost(RenderCost &rc) const override;
#endif

	/// Mesh of caster i of this instance, nullptr if missing.
	MeshClass *peekCasterMesh(const SkinnedShadowCasterMesh &caster) const;
	/// World space vertices of a caster mesh in its current pose (valid until the next call).
	const Vector3 *getCasterVertices(MeshClass *mesh, const SkinnedShadowCasterMesh &caster) const;
	/// Fills s_poseEntries and returns the hidden mask of the caster meshes.
	unsigned long long buildPoseKey() const;
	/// Sun direction (from the sun to the unit, normalised) and the tile axes perpendicular to it.
	void computeLightFrame(const Vector3 &root, Vector3 &dir, Vector3 &axisU, Vector3 &axisV) const;

	W3DSkinnedShadow *m_next;
	W3DSkinnedShadow *m_nextDraw;
	RenderObjClass *m_robj;
	SkinnedShadowModel *m_model;
	Shadow *m_companionDecal;		///< retail decal kept under the shadow (SkinnedShadowKeepDecal)
	ShadowType m_originalType;		///< the type the data asked for, decides which shadow option turns it off
	Bool m_useVolume;
	Real m_radius;					///< object space bounding sphere radius

	// per frame state from updateRenderTargetTextures
	Bool m_visible;
	Real m_fade;
	UnsignedInt m_lastVisibleFrame;

	// projected route
	Int m_tile;
	Bool m_tileValid;
	UnsignedInt m_tileFrame;
	Vector3 m_lightDir;
	Vector3 m_axisU;
	Vector3 m_axisV;
	Vector3 m_centerOffset;		///< tile centre relative to the root
	Real m_extent;				///< half size of the tile in world units
	UnsignedInt m_tileColor;
	SkinShadow::SkinShadowPoseKey m_poseKey;

	// volume route
	SkinShadow::VolumeBuffers m_volume;
	Bool m_volumeValid;
	UnsignedInt m_volumeFrame;
	Vector3 m_volumeLightDir;
	Real m_volumeRootZ;
	Real m_volumeLength;
};

W3DSkinnedShadow::W3DSkinnedShadow() :
	m_next(nullptr),
	m_nextDraw(nullptr),
	m_robj(nullptr),
	m_model(nullptr),
	m_companionDecal(nullptr),
	m_originalType(SHADOW_NONE),
	m_useVolume(FALSE),
	m_radius(0.0f),
	m_visible(FALSE),
	m_fade(0.0f),
	m_lastVisibleFrame(0),
	m_tile(-1),
	m_tileValid(FALSE),
	m_tileFrame(0),
	m_lightDir(0.0f, 0.0f, -1.0f),
	m_axisU(1.0f, 0.0f, 0.0f),
	m_axisV(0.0f, 1.0f, 0.0f),
	m_centerOffset(0.0f, 0.0f, 0.0f),
	m_extent(1.0f),
	m_tileColor(0),
	m_volumeValid(FALSE),
	m_volumeFrame(0),
	m_volumeLightDir(0.0f, 0.0f, -1.0f),
	m_volumeRootZ(0.0f),
	m_volumeLength(0.0f)
{
	m_isEnabled = TRUE;
	m_isInvisibleEnabled = FALSE;
	m_type = SHADOW_VOLUME;
	m_x = m_y = m_z = 0.0f;
	m_oowDecalSizeX = m_oowDecalSizeY = 0.0f;
	m_decalSizeX = m_decalSizeY = 0.0f;
}

W3DSkinnedShadow::~W3DSkinnedShadow()
{
	if (m_companionDecal)
	{
		m_companionDecal->release();
		m_companionDecal = nullptr;
	}
	if (m_robj)
	{
		m_robj->Release_Ref();
		m_robj = nullptr;
	}
}

void W3DSkinnedShadow::release()
{
	if (TheW3DSkinnedShadowManager)
		TheW3DSkinnedShadowManager->removeShadow(this);
}

#if defined(RTS_DEBUG)
void W3DSkinnedShadow::getRenderCost(RenderCost &rc) const
{
	if (m_isEnabled && !m_isInvisibleEnabled && m_visible)
		rc.addShadowDrawCalls(m_useVolume ? 2 : 1);
}
#endif

MeshClass *W3DSkinnedShadow::peekCasterMesh(const SkinnedShadowCasterMesh &caster) const
{
	if (caster.lodModelIndex < 0)
		return m_robj->Class_ID() == RenderObjClass::CLASSID_MESH ? (MeshClass *)m_robj : nullptr;

	if (m_robj->Class_ID() != RenderObjClass::CLASSID_HLOD)
		return nullptr;
	HLodClass *hlod = (HLodClass *)m_robj;
	const Int top = hlod->Get_LOD_Count() - 1;
	if (top < 0 || caster.lodModelIndex >= hlod->Get_Lod_Model_Count(top))
		return nullptr;
	RenderObjClass *model = hlod->Peek_Lod_Model(top, caster.lodModelIndex);
	if (model == nullptr || model->Class_ID() != RenderObjClass::CLASSID_MESH)
		return nullptr;
	MeshClass *mesh = (MeshClass *)model;
	if (mesh->Peek_Model() == nullptr || mesh->Peek_Model()->Get_Vertex_Count() != caster.vertexCount)
		return nullptr;
	return mesh;
}

const Vector3 *W3DSkinnedShadow::getCasterVertices(MeshClass *mesh, const SkinnedShadowCasterMesh &caster) const
{
	MeshModelClass *model = mesh->Peek_Model();
	const Int count = caster.vertexCount;
	if (caster.isSkin)
	{
		// Skin vertices are deformed into world space by the hierarchy; the skin cache (Options.ini SkinCache) shares
		// the result with the mesh renderer, so a pose the renderer already skinned costs nothing here.
		if ((Int)s_skinVertices.size() < count)
		{
			s_skinVertices.resize(count);
			s_skinNormals.resize(count);
		}
		const Vector3 *vertices = nullptr;
		const Vector3 *normals = nullptr;
		mesh->Get_Deformed_Vertices_Cached(&s_skinVertices[0], &s_skinNormals[0], vertices, normals);
		return vertices;
	}

	if ((Int)s_worldVertices.size() < count)
		s_worldVertices.resize(count);
	const Matrix3D &transform = mesh->Get_Transform_No_Validity_Check();
	const Vector3 *source = model->Get_Vertex_Array();
	for (Int i = 0; i < count; ++i)
		Matrix3D::Transform_Vector(transform, source[i], &s_worldVertices[i]);
	return &s_worldVertices[0];
}

unsigned long long W3DSkinnedShadow::buildPoseKey() const
{
	s_poseEntries.clear();
	const HTreeClass *htree = m_robj->Get_HTree();
	if (htree != nullptr && htree->Num_Pivots() > 0)
	{
		const Matrix3D &root = htree->Get_Transform(0);
		for (Int p = 0; p < htree->Num_Pivots(); ++p)
		{
			const Matrix3D &m = htree->Get_Transform(p);
			for (Int r = 0; r < 3; ++r)
				for (Int c = 0; c < 3; ++c)
					s_poseEntries.push_back(m[r][c]);
			for (Int r = 0; r < 3; ++r)
				s_poseEntries.push_back(m[r][3] - root[r][3]);
		}
	}
	else
	{
		const Matrix3D &m = m_robj->Get_Transform_No_Validity_Check();
		for (Int r = 0; r < 3; ++r)
			for (Int c = 0; c < 3; ++c)
				s_poseEntries.push_back(m[r][c]);
		for (Int r = 0; r < 3; ++r)
			s_poseEntries.push_back(0.0f);
	}

	unsigned long long hidden = 0;
	for (size_t i = 0; i < m_model->meshes.size() && i < 64; ++i)
	{
		MeshClass *mesh = peekCasterMesh(m_model->meshes[i]);
		if (mesh == nullptr || !mesh->Is_Not_Hidden_At_All())
			hidden |= 1ull << i;
	}
	return hidden;
}

void W3DSkinnedShadow::computeLightFrame(const Vector3 &root, Vector3 &dir, Vector3 &axisU, Vector3 &axisV) const
{
	// Same light as the retail shadow volumes: a point 10000 units away in the sun's direction.
	dir = root - TheW3DShadowManager->getLightPosWorld(0);
	if (dir.Length2() < 1.0e-6f)
		dir.Set(0.0f, 0.0f, -1.0f);
	dir.Normalize();

	Vector3::Cross_Product(Vector3(0.0f, 0.0f, 1.0f), dir, &axisU);
	if (axisU.Length2() < 1.0e-4f)
		Vector3::Cross_Product(Vector3(0.0f, 1.0f, 0.0f), dir, &axisU);
	axisU.Normalize();
	Vector3::Cross_Product(dir, axisU, &axisV);
}

// Manager ====================================================================

W3DSkinnedShadowManager::W3DSkinnedShadowManager() :
	m_shadowList(nullptr),
	m_modelList(nullptr),
	m_mode(OptionPreferences::SKINNED_SHADOWS_DECAL),
	m_quality(1),
	m_fadeDistance(0.0f),
	m_keepDecal(FALSE),
	m_minTriangles(2000),
	m_maxVolumeTriangles(0),
	m_atlas(nullptr),
	m_atlasSize(0),
	m_tilesPerRow(0),
	m_tileCount(0),
	m_tileOwner(nullptr),
	m_atlasFailed(FALSE),
	m_frame(0),
	m_volumeDrawList(nullptr),
	m_volumeFrame(0),
	m_statsFrames(0),
	m_statsTileUpdates(0),
	m_statsVolumeUpdates(0),
	m_statsDrawn(0),
	m_statsTerrainTriangles(0),
	m_statsDeferred(0),
	m_statsMs(0.0)
{
	for (Int i = 0; i < 6; ++i)
		(&m_preset.tileSize)[i] = s_presets[1][i];
}

W3DSkinnedShadowManager::~W3DSkinnedShadowManager()
{
	removeAllShadows();
	while (m_modelList)
	{
		SkinnedShadowModel *next = m_modelList->next;
		delete m_modelList;
		m_modelList = next;
	}
	releaseAtlas();
	delete[] m_tileOwner;
	m_tileOwner = nullptr;
}

Bool W3DSkinnedShadowManager::init()
{
	OptionPreferences prefs;
	m_mode = prefs.getSkinnedShadowMode();
	m_quality = clamp(0, prefs.getSkinnedShadowQuality(), 2);
	m_preset.tileSize = s_presets[m_quality][0];
	m_preset.atlasSize = s_presets[m_quality][1];
	m_preset.updateInterval = s_presets[m_quality][2];
	m_preset.updateBudget = s_presets[m_quality][3];
	m_preset.volumeMaxTriangles = s_presets[m_quality][4];
	m_preset.volumeBudget = s_presets[m_quality][5];
	m_fadeDistance = prefs.getSkinnedShadowDistance();
	m_keepDecal = prefs.getSkinnedShadowKeepDecal();
	m_minTriangles = prefs.getSkinnedShadowMinTriangles();
	m_maxVolumeTriangles = prefs.getShadowVolumeMaxTriangles();

	fprintf(stderr, "[SHADOW] skinned shadows: mode=%s quality=%s tile=%d atlas=%d interval=%d budget=%d"
		" volume_proxy=%d volume_budget=%d distance=%.0f keep_decal=%s min_triangles=%d stencil=%s\n",
		s_modeNames[m_mode], s_qualityNames[m_quality], m_preset.tileSize, m_preset.atlasSize,
		m_preset.updateInterval, m_preset.updateBudget, m_preset.volumeMaxTriangles, m_preset.volumeBudget,
		m_fadeDistance, m_keepDecal ? "yes" : "no", m_minTriangles, DX8Wrapper::Has_Stencil() ? "yes" : "no");
	fflush(stderr);
	return TRUE;
}

void W3DSkinnedShadowManager::reset()
{
	// Shadows belong to their drawables, which release them before a map reset; the model cache only holds copies
	// of mesh data and is dropped once no shadow uses it.
	if (m_shadowList != nullptr)
		return;
	while (m_modelList)
	{
		SkinnedShadowModel *next = m_modelList->next;
		delete m_modelList;
		m_modelList = next;
	}
}

void W3DSkinnedShadowManager::ReleaseResources()
{
	releaseAtlas();
}

Bool W3DSkinnedShadowManager::ReAcquireResources()
{
	// The atlas is created on demand by the first projected shadow; after a device reset it comes back here.
	if (m_tileOwner != nullptr && m_atlas == nullptr && !m_atlasFailed)
		return createAtlas();
	return TRUE;
}

void W3DSkinnedShadowManager::invalidateCachedLightPositions()
{
	for (W3DSkinnedShadow *shadow = m_shadowList; shadow; shadow = shadow->m_next)
	{
		shadow->m_tileValid = FALSE;
		shadow->m_volumeValid = FALSE;
		shadow->m_poseKey.invalidate();
	}
}

Bool W3DSkinnedShadowManager::createAtlas()
{
	releaseAtlas();

	static const WW3DFormat formats[] = { WW3D_FORMAT_R5G6B5, WW3D_FORMAT_X8R8G8B8, WW3D_FORMAT_A8R8G8B8 };
	static const char *const formatNames[] = { "R5G6B5", "X8R8G8B8", "A8R8G8B8" };
	Int formatIndex = -1;
	for (Int size = m_preset.atlasSize; size >= 512 && m_atlas == nullptr; size /= 2)
	{
		for (Int f = 0; f < 3 && m_atlas == nullptr; ++f)
		{
			m_atlas = DX8Wrapper::Create_Render_Target(size, size, formats[f]);
			formatIndex = f;
		}
	}

	if (m_atlas == nullptr || m_atlas->Peek_D3D_Base_Texture() == nullptr)
	{
		REF_PTR_RELEASE(m_atlas);
		m_atlasFailed = TRUE;
		fprintf(stderr, "[SHADOW] could not create the skinned shadow atlas, projected skinned shadows use the retail path\n");
		fflush(stderr);
		return FALSE;
	}

	SurfaceClass::SurfaceDescription desc;
	m_atlas->Get_Level_Description(desc);
	const Int atlasSize = (Int)desc.Width;
	const Int tilesPerRow = atlasSize / m_preset.tileSize;
	const Int tileCount = tilesPerRow * tilesPerRow;

	if (m_tileOwner == nullptr || tileCount != m_tileCount)
	{
		// first creation, or a different size after a device reset: give every shadow a new tile
		for (W3DSkinnedShadow *shadow = m_shadowList; shadow; shadow = shadow->m_next)
			shadow->m_tile = -1;
		delete[] m_tileOwner;
		m_tileOwner = NEW W3DSkinnedShadow *[tileCount];
		memset(m_tileOwner, 0, sizeof(W3DSkinnedShadow *) * tileCount);
	}
	m_atlasSize = atlasSize;
	m_tilesPerRow = tilesPerRow;
	m_tileCount = tileCount;

	for (W3DSkinnedShadow *shadow = m_shadowList; shadow; shadow = shadow->m_next)
		shadow->m_tileValid = FALSE;

	fprintf(stderr, "[SHADOW] skinned shadow atlas %dx%d %s, %d tiles of %d texels\n",
		atlasSize, atlasSize, formatNames[formatIndex], tileCount, m_preset.tileSize);
	fflush(stderr);
	return TRUE;
}

void W3DSkinnedShadowManager::releaseAtlas()
{
	REF_PTR_RELEASE(m_atlas);
	for (W3DSkinnedShadow *shadow = m_shadowList; shadow; shadow = shadow->m_next)
		shadow->m_tileValid = FALSE;
}

Int W3DSkinnedShadowManager::allocateTile(W3DSkinnedShadow *forShadow)
{
	if (m_tileOwner == nullptr)
		return -1;
	for (Int i = 0; i < m_tileCount; ++i)
	{
		if (m_tileOwner[i] == nullptr)
		{
			m_tileOwner[i] = forShadow;
			return i;
		}
	}
	// All taken: reuse the tile of the shadow that has been off screen the longest.
	Int best = -1;
	UnsignedInt bestFrame = m_frame;
	for (Int i = 0; i < m_tileCount; ++i)
	{
		W3DSkinnedShadow *owner = m_tileOwner[i];
		if (owner && !owner->m_visible && owner->m_lastVisibleFrame < bestFrame)
		{
			bestFrame = owner->m_lastVisibleFrame;
			best = i;
		}
	}
	if (best < 0)
		return -1;
	W3DSkinnedShadow *previous = m_tileOwner[best];
	previous->m_tile = -1;
	previous->m_tileValid = FALSE;
	m_tileOwner[best] = forShadow;
	return best;
}

void W3DSkinnedShadowManager::freeTile(W3DSkinnedShadow *shadow)
{
	if (shadow->m_tile >= 0 && m_tileOwner != nullptr && shadow->m_tile < m_tileCount && m_tileOwner[shadow->m_tile] == shadow)
		m_tileOwner[shadow->m_tile] = nullptr;
	shadow->m_tile = -1;
	shadow->m_tileValid = FALSE;
}

SkinnedShadowModel *W3DSkinnedShadowManager::getModel(RenderObjClass *robj)
{
	const char *name = robj->Get_Name();
	if (name == nullptr || name[0] == 0)
		return nullptr;

	for (SkinnedShadowModel *model = m_modelList; model; model = model->next)
		if (model->name.compareNoCase(name) == 0)
			return model;

	SkinnedShadowModel *model = NEW SkinnedShadowModel;
	model->name = name;

	const Bool hasHierarchy = robj->Get_HTree() != nullptr;
	if (robj->Class_ID() == RenderObjClass::CLASSID_HLOD)
	{
		HLodClass *hlod = (HLodClass *)robj;
		const Int top = hlod->Get_LOD_Count() - 1;
		for (Int i = 0; top >= 0 && i < hlod->Get_Lod_Model_Count(top); ++i)
		{
			RenderObjClass *sub = hlod->Peek_Lod_Model(top, i);
			if (sub == nullptr || sub->Class_ID() != RenderObjClass::CLASSID_MESH)
				continue;
			MeshClass *mesh = (MeshClass *)sub;
			MeshModelClass *mm = mesh->Peek_Model();
			if (mm == nullptr)
				continue;
			// same caster rules as W3DShadowGeometry::initFromHLOD, except that skins are welcome here
			if ((mesh->Is_Alpha() || mesh->Is_Translucent()) && !mm->Get_Flag(MeshGeometryClass::CAST_SHADOW))
				continue;
			const Bool isSkin = mm->Get_Flag(MeshGeometryClass::SKIN) != 0;
			if (isSkin && (!hasHierarchy || mm->Get_Vertex_Bone_Links() == nullptr))
				continue;
			if (mm->Get_Vertex_Count() <= 0 || mm->Get_Vertex_Count() > 65535 || mm->Get_Polygon_Count() <= 0)
				continue;
			if (model->meshes.size() >= 64)
				break;

			SkinnedShadowCasterMesh caster;
			caster.lodModelIndex = i;
			caster.isSkin = isSkin;
			caster.vertexCount = mm->Get_Vertex_Count();
			caster.triangleCount = mm->Get_Polygon_Count();
			const unsigned short *polys = (const unsigned short *)mm->Get_Polygon_Array();
			caster.indices.assign(polys, polys + caster.triangleCount * 3);
			model->meshes.push_back(caster);
		}
	}
	else if (robj->Class_ID() == RenderObjClass::CLASSID_MESH)
	{
		MeshClass *mesh = (MeshClass *)robj;
		MeshModelClass *mm = mesh->Peek_Model();
		if (mm != nullptr && !mm->Get_Flag(MeshGeometryClass::SKIN) && mm->Get_Vertex_Count() > 0
			&& mm->Get_Vertex_Count() <= 65535 && mm->Get_Polygon_Count() > 0)
		{
			SkinnedShadowCasterMesh caster;
			caster.lodModelIndex = -1;
			caster.vertexCount = mm->Get_Vertex_Count();
			caster.triangleCount = mm->Get_Polygon_Count();
			const unsigned short *polys = (const unsigned short *)mm->Get_Polygon_Array();
			caster.indices.assign(polys, polys + caster.triangleCount * 3);
			model->meshes.push_back(caster);
		}
	}

	for (size_t i = 0; i < model->meshes.size(); ++i)
	{
		model->totalTriangles += model->meshes[i].triangleCount;
		if (model->meshes[i].isSkin)
			model->skinTriangles += model->meshes[i].triangleCount;
		else
			model->rigidTriangles += model->meshes[i].triangleCount;
	}

	model->next = m_modelList;
	m_modelList = model;
	return model;
}

Shadow *W3DSkinnedShadowManager::addShadow(RenderObjClass *robj, Shadow::ShadowTypeInfo *shadowInfo, Drawable *draw)
{
	if (m_mode == OptionPreferences::SKINNED_SHADOWS_DECAL || robj == nullptr || shadowInfo == nullptr)
		return nullptr;

	const Int type = shadowInfo->m_type;
	const Bool isVolume = (type & SHADOW_VOLUME) != 0;
	const Bool isShadowDecal = (type & SHADOW_DECAL) != 0
		&& (type & (SHADOW_ALPHA_DECAL | SHADOW_ADDITIVE_DECAL | SHADOW_PROJECTION | SHADOW_DYNAMIC_PROJECTION)) == 0;
	if (!isVolume && !isShadowDecal)
		return nullptr;

	SkinnedShadowModel *model = getModel(robj);
	if (model == nullptr || model->meshes.empty())
		return nullptr;

	const Bool skinned = model->skinTriangles > 0 && (isVolume || model->totalTriangles >= m_minTriangles);
	const Bool overVolumeLimit = isVolume && m_maxVolumeTriangles > 0 && model->rigidTriangles > m_maxVolumeTriangles;
	if (!skinned && !overVolumeLimit)
		return nullptr;

	// The stencil route only replaces shadow volumes; decal typed models and missing stencil use the projected route.
	Bool useVolume = m_mode == OptionPreferences::SKINNED_SHADOWS_VOLUME && isVolume
		&& DX8Wrapper::Has_Stencil() && TheGlobalData->m_useShadowVolumes;
	if (!useVolume)
	{
		if (m_atlas == nullptr && !m_atlasFailed)
			createAtlas();
		if (m_atlas == nullptr)
			return nullptr;
	}

	if (!model->logged)
	{
		model->logged = TRUE;
		fprintf(stderr, "[SHADOW] model %s: %d caster meshes, %d triangles (%d skinned) -> %s\n",
			model->name.str(), (Int)model->meshes.size(), model->totalTriangles, model->skinTriangles,
			useVolume ? "Volume" : "Projected");
		fflush(stderr);
	}

	W3DSkinnedShadow *shadow = NEW W3DSkinnedShadow;
	shadow->m_robj = robj;
	robj->Add_Ref();
	shadow->m_model = model;
	shadow->m_originalType = (ShadowType)type;
	shadow->m_type = useVolume ? SHADOW_VOLUME : SHADOW_PROJECTION;
	shadow->m_useVolume = useVolume;
	SphereClass sphere;
	robj->Get_Obj_Space_Bounding_Sphere(sphere);
	shadow->m_radius = sphere.Radius > 1.0f ? sphere.Radius : 1.0f;

	if (m_keepDecal && TheW3DProjectedShadowManager)
	{
		// The retail decal (or, for shadow volume models, the default decal sized to the model) under the shadow.
		Shadow::ShadowTypeInfo decalInfo = *shadowInfo;
		if (isVolume)
		{
			decalInfo.m_ShadowName[0] = 0;
			decalInfo.m_sizeX = 0.0f;
			decalInfo.m_sizeY = 0.0f;
			decalInfo.m_offsetX = 0.0f;
			decalInfo.m_offsetY = 0.0f;
		}
		decalInfo.m_type = SHADOW_DECAL;
		shadow->m_companionDecal = (Shadow *)TheW3DProjectedShadowManager->addShadow(robj, &decalInfo, draw);
	}

	shadow->m_next = m_shadowList;
	m_shadowList = shadow;
	return shadow;
}

void W3DSkinnedShadowManager::removeShadow(W3DSkinnedShadow *shadow)
{
	W3DSkinnedShadow *prev = nullptr;
	for (W3DSkinnedShadow *s = m_shadowList; s; prev = s, s = s->m_next)
	{
		if (s != shadow)
			continue;
		if (prev)
			prev->m_next = s->m_next;
		else
			m_shadowList = s->m_next;

		// never leave a deleted shadow in this frame's volume list
		W3DSkinnedShadow *prevDraw = nullptr;
		for (W3DSkinnedShadow *d = m_volumeDrawList; d; prevDraw = d, d = d->m_nextDraw)
		{
			if (d == shadow)
			{
				if (prevDraw)
					prevDraw->m_nextDraw = d->m_nextDraw;
				else
					m_volumeDrawList = d->m_nextDraw;
				break;
			}
		}

		freeTile(shadow);
		delete shadow;
		return;
	}
}

void W3DSkinnedShadowManager::removeAllShadows()
{
	m_volumeDrawList = nullptr;
	while (m_shadowList)
	{
		W3DSkinnedShadow *next = m_shadowList->m_next;
		freeTile(m_shadowList);
		delete m_shadowList;
		m_shadowList = next;
	}
}

Bool W3DSkinnedShadowManager::hasVolumesToRender() const
{
	for (W3DSkinnedShadow *shadow = m_shadowList; shadow; shadow = shadow->m_next)
		if (shadow->m_useVolume && shadow->m_visible)
			return TRUE;
	return FALSE;
}

// Per frame update ===========================================================

void W3DSkinnedShadowManager::updateRenderTargetTextures(CameraClass *camera)
{
	if (m_mode == OptionPreferences::SKINNED_SHADOWS_DECAL)
		return;

	++m_frame;
	if (m_shadowList == nullptr || camera == nullptr || TheW3DShadowManager == nullptr)
	{
		printStats();
		return;
	}

	PERF_STATS_SCOPE(SECTION_SKINNED_SHADOWS);
	const double startMs = PerfStats::nowMs();

	const Vector3 cameraPos = camera->Get_Position();
	const FrustumClass &frustum = camera->Get_Frustum();
	const UnsignedInt shadowColor = TheW3DShadowManager->getShadowColor() & 0x00ffffff;
	const Real fadeStart = m_fadeDistance * 0.75f;
	const Real terrainMin = TheTerrainRenderObject ? TheTerrainRenderObject->getMinHeight() : 0.0f;

	static std::vector<W3DSkinnedShadow *> urgent;
	static std::vector<W3DSkinnedShadow *> due;
	urgent.clear();
	due.clear();

	Int drawn = 0;
	for (W3DSkinnedShadow *shadow = m_shadowList; shadow; shadow = shadow->m_next)
	{
		if (shadow->m_companionDecal)
		{
			shadow->m_companionDecal->enableShadowRender(shadow->m_isEnabled);
			shadow->m_companionDecal->enableShadowInvisible(shadow->m_isInvisibleEnabled);
		}

		shadow->m_visible = FALSE;
		const Bool optionOn = (shadow->m_originalType & SHADOW_VOLUME) ? TheGlobalData->m_useShadowVolumes : TheGlobalData->m_useShadowDecals;
		if (!optionOn || !shadow->m_isEnabled || shadow->m_isInvisibleEnabled || !shadow->m_robj->Is_Really_Visible())
			continue;

		const Vector3 root = shadow->m_robj->Get_Position();
		Real fade = 1.0f;
		if (m_fadeDistance > 0.0f)
		{
			const Real distance = (root - cameraPos).Length();
			if (distance >= m_fadeDistance)
				continue;
			if (distance > fadeStart)
				fade = (m_fadeDistance - distance) / (m_fadeDistance - fadeStart);
		}

		Vector3 dir, axisU, axisV;
		shadow->computeLightFrame(root, dir, axisU, axisV);
		if (dir.Z > -0.05f)
			continue;	// sun at the horizon: no ground under the shadow

		// The shadow can reach from the model down to the lowest terrain along the sun direction.
		const Real radius = shadow->m_radius * TILE_EXTENT_SCALE;
		Real length = (root.Z + 2.0f * radius - terrainMin + 20.0f) / (-dir.Z < 0.3f ? 0.3f : -dir.Z);
		length = clamp(radius, length, 4000.0f);
		SphereClass reach(root + dir * (length * 0.5f), radius + length * 0.5f);
		if (CollisionMath::Overlap_Test(frustum, reach) == CollisionMath::OUTSIDE)
			continue;

		shadow->m_visible = TRUE;
		shadow->m_fade = fade;
		shadow->m_lastVisibleFrame = m_frame;

		if (shadow->m_useVolume)
			continue;	// rebuilt, drawn and counted inside the stencil pass
		++drawn;

		const unsigned long long hidden = shadow->buildPoseKey();
		const Bool poseChanged = shadow->m_poseKey.differs(s_poseEntries.empty() ? nullptr : &s_poseEntries[0],
			(Int)s_poseEntries.size(), hidden, POSE_EPS_ROTATION, POSE_EPS_POSITION);
		const Bool lightChanged = Vector3::Dot_Product(dir, shadow->m_lightDir) < LIGHT_DIRECTION_COS;

		if (shadow->m_tile < 0 || !shadow->m_tileValid || shadow->m_tileColor != shadowColor || lightChanged)
			urgent.push_back(shadow);
		else if (poseChanged && m_frame - shadow->m_tileFrame >= (UnsignedInt)m_preset.updateInterval)
			due.push_back(shadow);
	}

	// Oldest tiles first; whatever does not fit the budget keeps its previous tile for another frame.
	std::sort(due.begin(), due.end(), [](const W3DSkinnedShadow *a, const W3DSkinnedShadow *b) {
		return a->m_tileFrame < b->m_tileFrame;
	});
	static std::vector<W3DSkinnedShadow *> work;
	work.clear();
	const Int urgentBudget = m_preset.updateBudget * 4;
	for (size_t i = 0; i < urgent.size() && (Int)work.size() < urgentBudget; ++i)
		work.push_back(urgent[i]);
	for (size_t i = 0; i < due.size() && (Int)work.size() < m_preset.updateBudget; ++i)
		work.push_back(due[i]);
	m_statsDeferred += (UnsignedInt)(urgent.size() + due.size() - work.size());

	if (!work.empty() && m_atlas != nullptr)
		drawTiles(&work[0], (Int)work.size());

	m_statsDrawn += drawn;
	PerfStats::addSkinnedShadowsDrawn((UnsignedInt)drawn);
	m_statsMs += PerfStats::nowMs() - startMs;
	printStats();
}

void W3DSkinnedShadowManager::drawTiles(W3DSkinnedShadow **shadows, Int count)
{
	IDirect3DDevice8 *device = DX8Wrapper::_Get_D3D_Device8();
	if (device == nullptr)
		return;

	// Tiles first, so every shadow below has one (a shadow without a free tile is skipped).
	for (Int i = 0; i < count; ++i)
		if (shadows[i]->m_tile < 0)
			shadows[i]->m_tile = allocateTile(shadows[i]);

	IDirect3DSurface8 *surface = m_atlas->Get_D3D_Surface_Level(0);
	if (surface == nullptr)
		return;

	D3DVIEWPORT8 oldViewport;
	device->GetViewport(&oldViewport);
	device->BeginScene();
	DX8Wrapper::Set_Render_Target(surface, false);	// no depth buffer (the overload taking one AddRefs it)

	{
		DeviceStateSaver states(device);
		states.setRender(D3DRS_ZENABLE, D3DZB_FALSE);
		states.setRender(D3DRS_ZWRITEENABLE, FALSE);
		states.setRender(D3DRS_STENCILENABLE, FALSE);
		states.setRender(D3DRS_ALPHABLENDENABLE, FALSE);
		states.setRender(D3DRS_ALPHATESTENABLE, FALSE);
		states.setRender(D3DRS_FOGENABLE, FALSE);
		states.setRender(D3DRS_LIGHTING, FALSE);
		states.setRender(D3DRS_SPECULARENABLE, FALSE);
		states.setRender(D3DRS_CULLMODE, D3DCULL_NONE);
		states.setRender(D3DRS_SHADEMODE, D3DSHADE_FLAT);
		states.setRender(D3DRS_FILLMODE, D3DFILL_SOLID);
		states.setRender(D3DRS_COLORWRITEENABLE, 0x0000000f);
		states.setStage(0, D3DTSS_COLOROP, D3DTOP_SELECTARG1);
		states.setStage(0, D3DTSS_COLORARG1, D3DTA_DIFFUSE);
		states.setStage(0, D3DTSS_ALPHAOP, D3DTOP_SELECTARG1);
		states.setStage(0, D3DTSS_ALPHAARG1, D3DTA_DIFFUSE);
		states.setStage(1, D3DTSS_COLOROP, D3DTOP_DISABLE);
		states.setStage(1, D3DTSS_ALPHAOP, D3DTOP_DISABLE);
		device->SetTexture(0, nullptr);
		device->SetTexture(1, nullptr);
		device->SetVertexShader(TILE_VERTEX_FVF);

		const UnsignedInt shadowColor = TheW3DShadowManager->getShadowColor() & 0x00ffffff;
		const DWORD casterColor = 0xff000000 | shadowColor;
		const Int tileSize = m_preset.tileSize;
		const Real inner = (Real)(tileSize - 2);	// one white texel around each tile keeps filtering inside it

		for (Int i = 0; i < count; ++i)
		{
			W3DSkinnedShadow *shadow = shadows[i];
			if (shadow->m_tile < 0)
				continue;

			const Int tileX = (shadow->m_tile % m_tilesPerRow) * tileSize;
			const Int tileY = (shadow->m_tile / m_tilesPerRow) * tileSize;
			D3DVIEWPORT8 viewport;
			viewport.X = tileX;
			viewport.Y = tileY;
			viewport.Width = tileSize;
			viewport.Height = tileSize;
			viewport.MinZ = 0.0f;
			viewport.MaxZ = 1.0f;
			device->SetViewport(&viewport);
			device->Clear(0, nullptr, D3DCLEAR_TARGET, 0xffffffff, 1.0f, 0);

			const Vector3 root = shadow->m_robj->Get_Position();
			Vector3 dir, axisU, axisV;
			shadow->computeLightFrame(root, dir, axisU, axisV);

			SphereClass sphere;
			shadow->m_robj->Get_Obj_Space_Bounding_Sphere(sphere);
			Vector3 center;
			Matrix3D::Transform_Vector(shadow->m_robj->Get_Transform_No_Validity_Check(), sphere.Center, &center);
			const Real extent = shadow->m_radius * TILE_EXTENT_SCALE;

			// light space (a, b) in [-extent, extent] -> tile texels; D3D9 pixel centres sit on whole coordinates
			const Real scale = inner / (2.0f * extent);
			const Real offsetX = (Real)tileX + 1.0f + inner * 0.5f - 0.5f;
			const Real offsetY = (Real)tileY + 1.0f + inner * 0.5f - 0.5f;

			Int triangles = 0;
			const SkinnedShadowModel *model = shadow->m_model;
			for (size_t m = 0; m < model->meshes.size(); ++m)
			{
				const SkinnedShadowCasterMesh &caster = model->meshes[m];
				MeshClass *mesh = shadow->peekCasterMesh(caster);
				if (mesh == nullptr || !mesh->Is_Not_Hidden_At_All())
					continue;
				const Vector3 *vertices = shadow->getCasterVertices(mesh, caster);
				if (vertices == nullptr)
					continue;

				if ((Int)s_tileVertices.size() < caster.vertexCount)
					s_tileVertices.resize(caster.vertexCount);
				for (Int v = 0; v < caster.vertexCount; ++v)
				{
					const Vector3 rel = vertices[v] - center;
					TileVertex &out = s_tileVertices[v];
					out.x = offsetX + Vector3::Dot_Product(rel, axisU) * scale;
					out.y = offsetY + Vector3::Dot_Product(rel, axisV) * scale;
					out.z = 0.0f;
					out.rhw = 1.0f;
					out.diffuse = casterColor;
				}
				if (DX8Wrapper::_Is_Triangle_Draw_Enabled())
				{
					device->DrawIndexedPrimitiveUP(D3DPT_TRIANGLELIST, 0, caster.vertexCount, caster.triangleCount,
						&caster.indices[0], D3DFMT_INDEX16, &s_tileVertices[0], sizeof(TileVertex));
				}
				triangles += caster.triangleCount;
			}

			shadow->m_lightDir = dir;
			shadow->m_axisU = axisU;
			shadow->m_axisV = axisV;
			shadow->m_centerOffset = center - root;
			shadow->m_extent = extent;
			shadow->m_tileColor = shadowColor;
			shadow->m_tileValid = TRUE;
			shadow->m_tileFrame = m_frame;
			const unsigned long long hidden = shadow->buildPoseKey();
			shadow->m_poseKey.store(s_poseEntries.empty() ? nullptr : &s_poseEntries[0], (Int)s_poseEntries.size(), hidden);

			++m_statsTileUpdates;
			PerfStats::addSkinnedShadowUpdate((UnsignedInt)triangles);
		}

		states.restore();
	}

	DX8Wrapper::Set_Render_Target((IDirect3DSurface8 *)nullptr);
	device->SetViewport(&oldViewport);
	device->EndScene();
	surface->Release();
	DX8Wrapper::Invalidate_Cached_Render_States();
}

// Terrain pass of the projected shadows ======================================

Int W3DSkinnedShadowManager::renderProjectedShadows(RenderInfoClass &rinfo)
{
	if (m_mode == OptionPreferences::SKINNED_SHADOWS_DECAL || m_shadowList == nullptr || m_atlas == nullptr
		|| TheTerrainRenderObject == nullptr)
		return 0;

	WorldHeightMap *hmap = TheTerrainRenderObject->getMap();
	IDirect3DDevice8 *device = DX8Wrapper::_Get_D3D_Device8();
	if (hmap == nullptr || device == nullptr)
		return 0;

	PERF_STATS_SCOPE(SECTION_SKINNED_SHADOWS);
	const double startMs = PerfStats::nowMs();

	const Int border = hmap->getBorderSizeInline();
	Int drawStartX = hmap->getDrawOrgX();
	Int drawStartY = hmap->getDrawOrgY();
	Int drawEdgeX = drawStartX + hmap->getDrawWidth() - 1;
	Int drawEdgeY = drawStartY + hmap->getDrawHeight() - 1;
	if (drawEdgeX > hmap->getXExtent() - 1)
		drawEdgeX = hmap->getXExtent() - 1;
	if (drawEdgeY > hmap->getYExtent() - 1)
		drawEdgeY = hmap->getYExtent() - 1;

	const Real atlasScale = 1.0f / (Real)m_atlasSize;
	const Real inner = (Real)(m_preset.tileSize - 2);
	s_terrainVertices.clear();
	Int shadowsDrawn = 0;

	for (W3DSkinnedShadow *shadow = m_shadowList; shadow; shadow = shadow->m_next)
	{
		if (shadow->m_useVolume || !shadow->m_visible || !shadow->m_tileValid || shadow->m_tile < 0)
			continue;
		if (!shadow->m_isEnabled || shadow->m_isInvisibleEnabled)
			continue;

		const Vector3 root = shadow->m_robj->Get_Position();
		const Vector3 center = root + shadow->m_centerOffset;
		const Vector3 &dir = shadow->m_lightDir;
		const Vector3 &axisU = shadow->m_axisU;
		const Vector3 &axisV = shadow->m_axisV;
		const Real extent = shadow->m_extent;
		const DWORD diffuse = grayColor(1.0f - shadow->m_fade);	// added to the tile: 0 keeps it, 1 turns it white

		// Bridges: like the retail decals, lift the shadow onto the bridge deck.
		Real layerHeight = 0.0f;
		DrawableInfo *info = (DrawableInfo *)shadow->m_robj->Get_User_Data();
		if (info && info->m_drawable && TheTerrainLogic)
		{
			const Object *object = info->m_drawable->getObject();
			if (object && object->getLayer() != LAYER_GROUND)
				layerHeight = BRIDGE_DECAL_LIFT + TheTerrainLogic->getLayerHeight(root.X, root.Y, object->getLayer());
		}

		// Ground area under the column of light: the tile square swept along the sun direction between the top of
		// the model and somewhat below the ground under it.
		const Real ground = TheTerrainRenderObject->getHeightMapHeight(root.X, root.Y, nullptr);
		const Real zHigh = center.Z + extent;
		Real zLow = (ground < center.Z - extent ? ground : center.Z - extent) - 40.0f;
		if (layerHeight > 0.0f && layerHeight - 40.0f < zLow)
			zLow = layerHeight - 40.0f;
		Real minX = 1.0e30f, minY = 1.0e30f, maxX = -1.0e30f, maxY = -1.0e30f;
		for (Int corner = 0; corner < 4; ++corner)
		{
			const Real su = (corner & 1) ? extent : -extent;
			const Real sv = (corner & 2) ? extent : -extent;
			const Vector3 k = center + axisU * su + axisV * sv;
			const Real zs[2] = { zHigh, zLow };
			for (Int z = 0; z < 2; ++z)
			{
				const Real t = (zs[z] - k.Z) / dir.Z;
				const Real x = k.X + dir.X * t;
				const Real y = k.Y + dir.Y * t;
				minX = x < minX ? x : minX;
				maxX = x > maxX ? x : maxX;
				minY = y < minY ? y : minY;
				maxY = y > maxY ? y : maxY;
			}
		}

		const Real cellInv = 1.0f / MAP_XY_FACTOR;
		Int startX = (Int)WWMath::Floor(minX * cellInv) + border;
		Int endX = (Int)WWMath::Ceil(maxX * cellInv) + border;
		Int startY = (Int)WWMath::Floor(minY * cellInv) + border;
		Int endY = (Int)WWMath::Ceil(maxY * cellInv) + border;
		if (endX - startX > MAX_FOOTPRINT_CELLS)
		{
			const Int middle = (Int)WWMath::Floor(root.X * cellInv) + border;
			startX = middle - MAX_FOOTPRINT_CELLS / 2;
			endX = middle + MAX_FOOTPRINT_CELLS / 2;
		}
		if (endY - startY > MAX_FOOTPRINT_CELLS)
		{
			const Int middle = (Int)WWMath::Floor(root.Y * cellInv) + border;
			startY = middle - MAX_FOOTPRINT_CELLS / 2;
			endY = middle + MAX_FOOTPRINT_CELLS / 2;
		}
		startX = clamp(drawStartX, startX, drawEdgeX);
		endX = clamp(drawStartX, endX, drawEdgeX);
		startY = clamp(drawStartY, startY, drawEdgeY);
		endY = clamp(drawStartY, endY, drawEdgeY);
		if (endX <= startX || endY <= startY)
			continue;

		// Terrain vertices of the area in light space.
		const Int columns = endX - startX + 1;
		const Int rows = endY - startY + 1;
		s_gridVertices.resize(columns * rows);
		s_gridDepth.resize(columns * rows);
		for (Int j = 0; j < rows; ++j)
		{
			for (Int i = 0; i < columns; ++i)
			{
				SkinShadow::PrismVertex &v = s_gridVertices[j * columns + i];
				v.p[0] = (Real)(startX + i - border) * MAP_XY_FACTOR;
				v.p[1] = (Real)(startY + j - border) * MAP_XY_FACTOR;
				Real z = (Real)hmap->getHeight(startX + i, startY + j) * MAP_HEIGHT_SCALE;
				if (layerHeight > 0.0f)
					z = z > layerHeight ? z : layerHeight;
				else
					z += TERRAIN_DECAL_LIFT;
				v.p[2] = z;
				const Vector3 rel(v.p[0] - center.X, v.p[1] - center.Y, v.p[2] - center.Z);
				v.a = Vector3::Dot_Product(rel, axisU);
				v.b = Vector3::Dot_Product(rel, axisV);
				s_gridDepth[j * columns + i] = Vector3::Dot_Product(rel, dir);
			}
		}

		const Real tileX = (Real)((shadow->m_tile % m_tilesPerRow) * m_preset.tileSize) + 1.0f + inner * 0.5f;
		const Real tileY = (Real)((shadow->m_tile / m_tilesPerRow) * m_preset.tileSize) + 1.0f + inner * 0.5f;
		const Real uvScale = inner / (2.0f * extent);
		const size_t firstVertex = s_terrainVertices.size();

		for (Int j = 0; j < rows - 1; ++j)
		{
			for (Int i = 0; i < columns - 1; ++i)
			{
				const Int c00 = j * columns + i;
				const Int c10 = c00 + 1;
				const Int c01 = c00 + columns;
				const Int c11 = c01 + 1;
				Int tris[6];
				if (hmap->getFlipState(startX + i, startY + j))
				{
					tris[0] = c10; tris[1] = c01; tris[2] = c00;
					tris[3] = c10; tris[4] = c11; tris[5] = c01;
				}
				else
				{
					tris[0] = c00; tris[1] = c11; tris[2] = c01;
					tris[3] = c00; tris[4] = c10; tris[5] = c11;
				}

				for (Int t = 0; t < 6; t += 3)
				{
					const SkinShadow::PrismVertex *corner[3] = { &s_gridVertices[tris[t]], &s_gridVertices[tris[t + 1]], &s_gridVertices[tris[t + 2]] };
					// skip ground in front of the model (between it and the sun) and triangles outside the column
					if (s_gridDepth[tris[t]] < -extent && s_gridDepth[tris[t + 1]] < -extent && s_gridDepth[tris[t + 2]] < -extent)
						continue;
					Int outside[4] = { 0, 0, 0, 0 };
					for (Int k = 0; k < 3; ++k)
					{
						outside[0] += corner[k]->a > extent ? 1 : 0;
						outside[1] += corner[k]->a < -extent ? 1 : 0;
						outside[2] += corner[k]->b > extent ? 1 : 0;
						outside[3] += corner[k]->b < -extent ? 1 : 0;
					}
					if (outside[0] == 3 || outside[1] == 3 || outside[2] == 3 || outside[3] == 3)
						continue;

					SkinShadow::PrismVertex polygon[7];
					Int polygonCount = 3;
					SkinShadow::PrismVertex input[3] = { *corner[0], *corner[1], *corner[2] };
					if (outside[0] + outside[1] + outside[2] + outside[3] == 0)
					{
						polygon[0] = input[0];
						polygon[1] = input[1];
						polygon[2] = input[2];
					}
					else
					{
						SkinShadow::PrismVertex scratch[7];
						polygonCount = SkinShadow::clipToLightPrism(input, 3, extent, extent, polygon, scratch);
					}

					for (Int k = 1; k + 1 < polygonCount; ++k)
					{
						const SkinShadow::PrismVertex *fan[3] = { &polygon[0], &polygon[k], &polygon[k + 1] };
						for (Int f = 0; f < 3; ++f)
						{
							TerrainVertex out;
							out.x = fan[f]->p[0];
							out.y = fan[f]->p[1];
							out.z = fan[f]->p[2];
							out.diffuse = diffuse;
							out.u = (tileX + fan[f]->a * uvScale) * atlasScale;
							out.v = (tileY + fan[f]->b * uvScale) * atlasScale;
							s_terrainVertices.push_back(out);
						}
					}
				}
			}
		}

		if (s_terrainVertices.size() > firstVertex)
			++shadowsDrawn;
	}

	const Int triangleCount = (Int)(s_terrainVertices.size() / 3);
	if (triangleCount > 0)
	{
		// Known W3D state first (this also applies the camera's view and projection), then the raw states.
		VertexMaterialClass *material = VertexMaterialClass::Get_Preset(VertexMaterialClass::PRELIT_DIFFUSE);
		DX8Wrapper::Set_Material(material);
		REF_PTR_RELEASE(material);
		DX8Wrapper::Set_Shader(ShaderClass::_PresetOpaqueShader);
		DX8Wrapper::Set_Texture(0, nullptr);
		DX8Wrapper::Set_Texture(1, nullptr);
		DX8Wrapper::Apply_Render_State_Changes();

		{
			DeviceStateSaver states(device);
			states.setRender(D3DRS_ZENABLE, D3DZB_TRUE);
			states.setRender(D3DRS_ZFUNC, D3DCMP_LESSEQUAL);
			states.setRender(D3DRS_ZWRITEENABLE, FALSE);
			states.setRender(D3DRS_STENCILENABLE, FALSE);
			states.setRender(D3DRS_ALPHATESTENABLE, FALSE);
			states.setRender(D3DRS_FOGENABLE, FALSE);
			states.setRender(D3DRS_LIGHTING, FALSE);
			states.setRender(D3DRS_SPECULARENABLE, FALSE);
			states.setRender(D3DRS_CULLMODE, D3DCULL_NONE);
			states.setRender(D3DRS_SHADEMODE, D3DSHADE_GOURAUD);
			states.setRender(D3DRS_ALPHABLENDENABLE, TRUE);
			states.setRender(D3DRS_SRCBLEND, D3DBLEND_ZERO);
			states.setRender(D3DRS_DESTBLEND, D3DBLEND_SRCCOLOR);
			// colour = min(tile + fade, 1); the frame buffer is multiplied by it
			states.setStage(0, D3DTSS_COLOROP, D3DTOP_ADD);
			states.setStage(0, D3DTSS_COLORARG1, D3DTA_TEXTURE);
			states.setStage(0, D3DTSS_COLORARG2, D3DTA_DIFFUSE);
			states.setStage(0, D3DTSS_ALPHAOP, D3DTOP_SELECTARG1);
			states.setStage(0, D3DTSS_ALPHAARG1, D3DTA_DIFFUSE);
			states.setStage(0, D3DTSS_TEXCOORDINDEX, 0);
			states.setStage(0, D3DTSS_TEXTURETRANSFORMFLAGS, D3DTTFF_DISABLE);
			states.setStage(0, D3DTSS_ADDRESSU, D3DTADDRESS_CLAMP);
			states.setStage(0, D3DTSS_ADDRESSV, D3DTADDRESS_CLAMP);
			states.setStage(0, D3DTSS_MAGFILTER, D3DTEXF_LINEAR);
			states.setStage(0, D3DTSS_MINFILTER, D3DTEXF_LINEAR);
			states.setStage(0, D3DTSS_MIPFILTER, D3DTEXF_NONE);
			states.setStage(1, D3DTSS_COLOROP, D3DTOP_DISABLE);
			states.setStage(1, D3DTSS_ALPHAOP, D3DTOP_DISABLE);

			Matrix3D identity(true);
			D3DMATRIX world;
			To_D3DMATRIX(world, identity);
			device->SetTransform(D3DTS_WORLD, &world);
			device->SetTexture(0, m_atlas->Peek_D3D_Base_Texture());
			device->SetTexture(1, nullptr);
			device->SetVertexShader(TERRAIN_VERTEX_FVF);

			if (DX8Wrapper::_Is_Triangle_Draw_Enabled())
			{
				for (Int first = 0; first < triangleCount; first += MAX_DRAW_TRIANGLES)
				{
					const Int batch = triangleCount - first < MAX_DRAW_TRIANGLES ? triangleCount - first : MAX_DRAW_TRIANGLES;
					device->DrawPrimitiveUP(D3DPT_TRIANGLELIST, batch, &s_terrainVertices[first * 3], sizeof(TerrainVertex));
				}
			}

			device->SetTexture(0, nullptr);
			states.restore();
		}
		DX8Wrapper::Invalidate_Cached_Render_States();
	}

	m_statsTerrainTriangles += (UnsignedInt)triangleCount;
	m_statsMs += PerfStats::nowMs() - startMs;
	return shadowsDrawn;
}

// Shadow volumes =============================================================

Bool W3DSkinnedShadowManager::updateVolume(W3DSkinnedShadow *shadow)
{
	const Vector3 root = shadow->m_robj->Get_Position();
	Vector3 dir, axisU, axisV;
	shadow->computeLightFrame(root, dir, axisU, axisV);

	// Long enough to pass below the lowest terrain (z-pass volumes have no caps).
	const Real terrainMin = TheTerrainRenderObject ? TheTerrainRenderObject->getMinHeight() : root.Z - 200.0f;
	Real length = (root.Z + 2.0f * shadow->m_radius - terrainMin + 40.0f) / (-dir.Z < 0.3f ? 0.3f : -dir.Z);
	length = clamp(shadow->m_radius, length, 4000.0f);

	SkinShadow::VolumeBuffers &volume = shadow->m_volume;
	volume.vertices.clear();
	volume.indices.clear();
	volume.silhouetteEdges = 0;

	const float lightDir[3] = { dir.X, dir.Y, dir.Z };
	const float origin[3] = { root.X, root.Y, root.Z };
	SkinnedShadowModel *model = shadow->m_model;
	Int triangles = 0;
	for (size_t m = 0; m < model->meshes.size(); ++m)
	{
		SkinnedShadowCasterMesh &caster = model->meshes[m];
		MeshClass *mesh = shadow->peekCasterMesh(caster);
		if (mesh == nullptr || !mesh->Is_Not_Hidden_At_All())
			continue;
		const Vector3 *vertices = shadow->getCasterVertices(mesh, caster);
		if (vertices == nullptr)
			continue;

		if (!caster.volumeDataBuilt)
		{
			// Once per model: the edge table from the stored vertices (bone space for skins, so vertices are only
			// welded within one bone), and for very dense meshes a clustered stand-in from this first pose.
			caster.volumeDataBuilt = TRUE;
			MeshModelClass *mm = mesh->Peek_Model();
			const unsigned short *groups = caster.isSkin ? (const unsigned short *)mm->Get_Vertex_Bone_Links() : nullptr;
			caster.topology.build(mm->Get_Vertex_Array(), caster.vertexCount, &caster.indices[0], caster.triangleCount, groups);
			Int cap = model->totalTriangles > 0 ? (Int)((long long)m_preset.volumeMaxTriangles * caster.triangleCount / model->totalTriangles) : 0;
			if (cap < 64)
				cap = 64;
			if (SkinShadow::buildClusterProxy(vertices, caster.vertexCount, &caster.indices[0], caster.triangleCount, cap, caster.proxyIndices) > 0)
			{
				caster.proxyTopology.build(mm->Get_Vertex_Array(), caster.vertexCount, &caster.proxyIndices[0],
					(Int)(caster.proxyIndices.size() / 3), groups);
			}
			fprintf(stderr, "[SHADOW] volume edges %s mesh %d: %d triangles, %d edges (%d open)%s%d\n",
				model->name.str(), (Int)m, caster.topology.getTriangleCount(), caster.topology.getEdgeCount(),
				caster.topology.getOpenEdgeCount(), caster.proxyIndices.empty() ? ", no proxy" : ", proxy triangles ",
				caster.proxyIndices.empty() ? 0 : caster.proxyTopology.getTriangleCount());
			fflush(stderr);
		}

		const SkinShadow::SkinShadowTopology &topology = caster.proxyIndices.empty() ? caster.topology : caster.proxyTopology;
		SkinShadow::buildSilhouetteVolume(topology, vertices, lightDir, origin, length, volume);
		triangles += topology.getTriangleCount();
	}

	shadow->m_volumeValid = TRUE;
	shadow->m_volumeFrame = m_frame;
	shadow->m_volumeLightDir = dir;
	shadow->m_volumeRootZ = root.Z;
	shadow->m_volumeLength = length;
	const unsigned long long hidden = shadow->buildPoseKey();
	shadow->m_poseKey.store(s_poseEntries.empty() ? nullptr : &s_poseEntries[0], (Int)s_poseEntries.size(), hidden);
	++m_statsVolumeUpdates;
	PerfStats::addSkinnedShadowUpdate((UnsignedInt)triangles);
	return TRUE;
}

Int W3DSkinnedShadowManager::renderVolumes(Bool decrementPass)
{
	if (m_mode != OptionPreferences::SKINNED_SHADOWS_VOLUME || m_shadowList == nullptr)
		return 0;
	IDirect3DDevice8 *device = DX8Wrapper::_Get_D3D_Device8();
	if (device == nullptr)
		return 0;

	PERF_STATS_SCOPE(SECTION_SKINNED_SHADOWS);
	const double startMs = PerfStats::nowMs();

	if (!decrementPass)
	{
		// Increment pass: pick this frame's volumes and rebuild the ones whose pose or sun changed, oldest first.
		m_volumeDrawList = nullptr;
		m_volumeFrame = m_frame;
		static std::vector<W3DSkinnedShadow *> due;
		due.clear();
		for (W3DSkinnedShadow *shadow = m_shadowList; shadow; shadow = shadow->m_next)
		{
			if (!shadow->m_useVolume || !shadow->m_visible || !shadow->m_isEnabled || shadow->m_isInvisibleEnabled)
				continue;

			if (!shadow->m_volumeValid)
				updateVolume(shadow);
			else
			{
				const Vector3 root = shadow->m_robj->Get_Position();
				Vector3 dir, axisU, axisV;
				shadow->computeLightFrame(root, dir, axisU, axisV);
				const unsigned long long hidden = shadow->buildPoseKey();
				const Bool poseChanged = shadow->m_poseKey.differs(s_poseEntries.empty() ? nullptr : &s_poseEntries[0],
					(Int)s_poseEntries.size(), hidden, POSE_EPS_ROTATION, POSE_EPS_POSITION);
				const Real climb = root.Z - shadow->m_volumeRootZ;
				if (poseChanged || Vector3::Dot_Product(dir, shadow->m_volumeLightDir) < LIGHT_DIRECTION_COS
					|| climb > shadow->m_radius || climb < -shadow->m_radius)
					due.push_back(shadow);
			}
			shadow->m_nextDraw = m_volumeDrawList;
			m_volumeDrawList = shadow;
		}
		std::sort(due.begin(), due.end(), [](const W3DSkinnedShadow *a, const W3DSkinnedShadow *b) {
			return a->m_volumeFrame < b->m_volumeFrame;
		});
		for (size_t i = 0; i < due.size(); ++i)
		{
			if ((Int)i < m_preset.volumeBudget)
				updateVolume(due[i]);
			else
				++m_statsDeferred;
		}
	}
	else if (m_volumeFrame != m_frame)
	{
		return 0;
	}

	device->SetVertexShader(D3DFVF_XYZ);
	Int drawn = 0;
	for (W3DSkinnedShadow *shadow = m_volumeDrawList; shadow; shadow = shadow->m_nextDraw)
	{
		const SkinShadow::VolumeBuffers &volume = shadow->m_volume;
		if (!shadow->m_volumeValid || volume.indices.empty())
			continue;

		Matrix3D transform(true);
		transform.Set_Translation(shadow->m_robj->Get_Position());
		D3DMATRIX world;
		To_D3DMATRIX(world, transform);
		device->SetTransform(D3DTS_WORLD, &world);
		if (DX8Wrapper::_Is_Triangle_Draw_Enabled())
		{
			device->DrawIndexedPrimitiveUP(D3DPT_TRIANGLELIST, 0, volume.getVertexCount(), volume.getTriangleCount(),
				&volume.indices[0], D3DFMT_INDEX16, &volume.vertices[0], sizeof(float) * 3);
		}
		++drawn;
	}

	if (!decrementPass)
	{
		m_statsDrawn += drawn;
		PerfStats::addSkinnedShadowsDrawn((UnsignedInt)drawn);
	}
	m_statsMs += PerfStats::nowMs() - startMs;
	return drawn;
}

// Diagnostics ================================================================

void W3DSkinnedShadowManager::printStats()
{
	++m_statsFrames;
	if (m_statsFrames < STATS_INTERVAL_FRAMES)
		return;

	Int shadows = 0;
	Int volumes = 0;
	for (W3DSkinnedShadow *shadow = m_shadowList; shadow; shadow = shadow->m_next)
	{
		++shadows;
		volumes += shadow->m_useVolume ? 1 : 0;
	}
	Int tilesUsed = 0;
	for (Int i = 0; m_tileOwner != nullptr && i < m_tileCount; ++i)
		tilesUsed += m_tileOwner[i] ? 1 : 0;

	if (shadows > 0 || m_statsDrawn > 0)
	{
		const double n = (double)m_statsFrames;
		fprintf(stderr, "[SHADOW] %u frames: shadows=%d (volumes=%d) drawn=%.1f tile_updates=%.2f volume_updates=%.2f"
			" deferred=%.2f terrain_tris=%.0f ms=%.3f tiles=%d/%d\n",
			m_statsFrames, shadows, volumes, m_statsDrawn / n, m_statsTileUpdates / n, m_statsVolumeUpdates / n,
			m_statsDeferred / n, m_statsTerrainTriangles / n, m_statsMs / n, tilesUsed, m_tileCount);
		fflush(stderr);
	}

	m_statsFrames = 0;
	m_statsTileUpdates = 0;
	m_statsVolumeUpdates = 0;
	m_statsDrawn = 0;
	m_statsTerrainTriangles = 0;
	m_statsDeferred = 0;
	m_statsMs = 0.0;
}
