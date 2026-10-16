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

// FILE: W3DSkinnedShadow.h ///////////////////////////////////////////////////
//
// GeneralsX @feature Claude 16/10/2026 Real shadows for skinned (and very high poly) W3D models.
//
// The retail shadow volume code ignores skin meshes, so skinned units got no shadow or a flat decal. This
// manager gives them a shadow of their actual pose, selected by Options.ini SkinnedShadows:
//
//  - Projected (default): the posed model is drawn flat from the sun into a small tile of one shared shadow
//    atlas (only when the pose changed, a few tiles per frame), and the tile is laid onto the terrain under the
//    unit in one batched multiplicative pass.
//  - Volume: a stencil shadow volume extruded from the silhouette of the skinned vertices, drawn inside the
//    retail shadow volume pass, so it also shades other objects and the unit itself.
//  - Decal: retail behaviour (this manager is off).
//
// Rendering only: nothing here is read by the game logic, so CRCs and replays are unaffected.

#pragma once

#include "GameClient/Color.h"
#include "GameClient/Shadow.h"

class RenderObjClass;
class RenderInfoClass;
class CameraClass;
class TextureClass;
class Drawable;
class W3DSkinnedShadow;
struct SkinnedShadowModel;

class W3DSkinnedShadowManager
{
public:
	W3DSkinnedShadowManager();
	~W3DSkinnedShadowManager();

	Bool init();					///< reads Options.ini; call once the D3D device exists
	void reset();					///< per map: drops the model cache once all shadows are gone
	void ReleaseResources();		///< device lost: frees the shadow atlas
	Bool ReAcquireResources();		///< device back: recreates the shadow atlas
	void invalidateCachedLightPositions();	///< the sun moved: redraw/rebuild every shadow

	/// Returns a skinned shadow for this model if the model qualifies (skinned caster meshes, or a shadow volume
	/// model over ShadowVolumeMaxTriangles) and the mode is on; nullptr means use the retail shadow.
	Shadow *addShadow(RenderObjClass *robj, Shadow::ShadowTypeInfo *shadowInfo, Drawable *draw);
	void removeShadow(W3DSkinnedShadow *shadow);
	void removeAllShadows();

	/// Before the main scene: decides which shadows are drawn this frame and redraws the atlas tiles that need it.
	void updateRenderTargetTextures(CameraClass *camera);
	/// Terrain pass of the projected shadows (from DoShadows, before the meshes).
	Int renderProjectedShadows(RenderInfoClass &rinfo);
	/// Shadow volumes, called twice inside W3DVolumetricShadowManager::renderShadows: decrementPass FALSE for the
	/// stencil increment pass (rebuilds volumes as needed), TRUE for the decrement pass. Changes the world transform,
	/// vertex format, stream source and index buffer; returns the number of volumes drawn.
	Int renderVolumes(Bool decrementPass);
	/// True when renderVolumes has something to draw, so the stencil pass also runs without retail volumes.
	Bool hasVolumesToRender() const;

	Int getMode() const { return m_mode; }

protected:
	struct QualityPreset
	{
		Int tileSize;			///< texels per tile edge
		Int atlasSize;			///< texels per atlas edge
		Int updateInterval;		///< frames between two redraws of an animated tile
		Int updateBudget;		///< tile redraws per frame
		Int volumeMaxTriangles;	///< shadow volume casters above this use a clustered proxy
		Int volumeBudget;		///< shadow volume rebuilds per frame
	};

	SkinnedShadowModel *getModel(RenderObjClass *robj);
	void releaseModel(SkinnedShadowModel *model);
	Bool createAtlas();
	void releaseAtlas();
	Int allocateTile(W3DSkinnedShadow *forShadow);
	void freeTile(W3DSkinnedShadow *shadow);
	void drawTiles(W3DSkinnedShadow **shadows, Int count);
	Bool updateVolume(W3DSkinnedShadow *shadow);
	void printStats();

	W3DSkinnedShadow *m_shadowList;
	SkinnedShadowModel *m_modelList;

	Int m_mode;					///< OptionPreferences::SkinnedShadowMode
	Int m_quality;				///< 0 Low, 1 Medium, 2 High
	QualityPreset m_preset;
	Real m_fadeDistance;		///< 0 = no fade
	Bool m_keepDecal;
	Int m_minTriangles;
	Int m_maxVolumeTriangles;	///< Options.ini ShadowVolumeMaxTriangles

	TextureClass *m_atlas;
	Int m_atlasSize;			///< actual atlas size (may be smaller than the preset)
	Int m_tilesPerRow;
	Int m_tileCount;
	W3DSkinnedShadow **m_tileOwner;
	Bool m_atlasFailed;			///< could not create the atlas; projected shadows fall back to retail

	UnsignedInt m_frame;
	W3DSkinnedShadow *m_volumeDrawList;	///< volumes drawn in this frame's increment pass, redrawn in the decrement pass
	UnsignedInt m_volumeFrame;	///< m_frame of the increment pass that built m_volumeDrawList

	// statistics for the [SHADOW] lines
	UnsignedInt m_statsFrames;
	UnsignedInt m_statsTileUpdates;
	UnsignedInt m_statsVolumeUpdates;
	UnsignedInt m_statsDrawn;
	UnsignedInt m_statsTerrainTriangles;
	UnsignedInt m_statsDeferred;
	double m_statsMs;
};

extern W3DSkinnedShadowManager *TheW3DSkinnedShadowManager;
