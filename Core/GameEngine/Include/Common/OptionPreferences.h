/*
**	Command & Conquer Generals Zero Hour(tm)
**	Copyright 2025 Electronic Arts Inc.
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

////////////////////////////////////////////////////////////////////////////////
//																																						//
//  (c) 2001-2003 Electronic Arts Inc.																				//
//																																						//
////////////////////////////////////////////////////////////////////////////////

///////////////////////////////////////////////////////////////////////////////////////
// FILE: OptionPreferences.h
// Author: Matthew D. Campbell, April 2002
// Description: Saving/Loading of option preferences
///////////////////////////////////////////////////////////////////////////////////////

#pragma once

#include "WW3D2/ww3d.h"
#include "WW3D2/texturefilter.h"

#include "Common/UserPreferences.h"

typedef UnsignedInt CursorCaptureMode;
typedef UnsignedInt ScreenEdgeScrollMode;

//-----------------------------------------------------------------------------
// OptionsPreferences options menu class
//-----------------------------------------------------------------------------
class OptionPreferences : public UserPreferences
{
public:
	OptionPreferences();
	virtual ~OptionPreferences() override;

	enum AntiAliasingMode CPP_11(: Int)
	{
		AntiAliasingMode_OFF = 0,
		AntiAliasingMode_MSAA_2X,
		AntiAliasingMode_MSAA_4X,
		AntiAliasingMode_MSAA_8X,
		AntiAliasingMode_Count
	};

	// GeneralsX @feature Claude 14/10/2026 FSR render scale limits, in percent of the display size.
	enum RenderScaleLimits CPP_11(: Int)
	{
		RENDER_SCALE_MIN = 50,
		RENDER_SCALE_OFF = 100,
		RENDER_SCALE_MIN_HEIGHT = 600
	};

	// GeneralsX @feature Claude 16/10/2026 Upscaler choice (Options.ini Upscaler, -upscaler). UPSCALER_DEFAULT
	// keeps the behaviour from before FSR 2: FSR 1.0 when RenderScale is below 100, else none. DLSS is a
	// placeholder that falls back to FSR 2, no NVIDIA SDK is part of the build.
	enum UpscalerType CPP_11(: Int)
	{
		UPSCALER_DEFAULT = 0,
		UPSCALER_OFF,
		UPSCALER_FSR1,
		UPSCALER_FSR2,
		UPSCALER_DLSS,
		// GeneralsX @feature Claude 16/10/2026 FSR 3.1 through the patched DXVK (patches 0016 and 0017), falls
		// back to FSR 2 when the DXVK build has no FidelityFX SDK. Appended so the other values keep theirs.
		UPSCALER_FSR3
	};

	// GeneralsX @feature Claude 16/10/2026 Render scale of the UpscalerQuality presets, in percent of the
	// display size: 1.5x, 1.7x, 2x and 3x upscaling as AMD defines them for FSR 2.
	enum UpscalerQualityScale CPP_11(: Int)
	{
		UPSCALER_QUALITY_SCALE = 67,
		UPSCALER_BALANCED_SCALE = 59,
		UPSCALER_PERFORMANCE_SCALE = 50,
		UPSCALER_ULTRA_PERFORMANCE_SCALE = 33,
		// GeneralsX @feature Claude 16/10/2026 Native: FSR 2 / FSR 3 render at the output size as anti-aliasing
		UPSCALER_NATIVE_SCALE = 100
	};

	Bool loadFromIniFile();

	WW3D::MultiSampleModeEnum getAntiAliasing() const;
	// GeneralsX @tweak Claude 15/10/2026 False when Options.ini has no AntiAliasing entry and the default applies.
	Bool hasAntiAliasing() const;
	TextureFilterClass::TextureFilterMode getTextureFilterMode() const;
	TextureFilterClass::AnisotropicFilterMode getTextureAnisotropyLevel() const;
	// GeneralsX @feature Claude 15/10/2026 Mip LOD bias from Options.ini (TextureLodBias).
	Real getTextureLodBias() const;
	UnsignedInt getLANIPAddress();
	UnsignedInt getOnlineIPAddress();
	void setLANIPAddress(AsciiString IP);
	void setOnlineIPAddress(AsciiString IP);
	void setLANIPAddress(UnsignedInt IP);
	void setOnlineIPAddress(UnsignedInt IP);
	Bool getArchiveReplaysEnabled() const;
	Bool getAlternateMouseModeEnabled();
	Bool getRightMouseScrollWithAlternateMouseEnabled() const;
	Bool getRetaliationModeEnabled();
	Bool getDoubleClickAttackMoveEnabled();
	Int getJpegQuality() const;
	Real getScrollFactor();
	Bool getDrawScrollAnchor();
	Bool getMoveScrollAnchor();
	Bool getCursorCaptureEnabledInWindowedGame() const;
	Bool getCursorCaptureEnabledInWindowedMenu() const;
	Bool getCursorCaptureEnabledInFullscreenGame() const;
	Bool getCursorCaptureEnabledInFullscreenMenu() const;
	CursorCaptureMode getCursorCaptureMode() const;
	Bool getScreenEdgeScrollEnabledInWindowedApp() const;
	Bool getScreenEdgeScrollEnabledInFullscreenApp() const;
	ScreenEdgeScrollMode getScreenEdgeScrollMode() const;
	Int getFirewallBehavior();
	Short getFirewallPortAllocationDelta();
	UnsignedShort getFirewallPortOverride();
	Bool getFirewallNeedToRefresh();
	Bool usesSystemMapDir();
	AsciiString getPreferred3DProvider();
	AsciiString getSpeakerType();
	Real getSoundVolume();
	Real get3DSoundVolume();
	Real getSpeechVolume();
	Real getMusicVolume();
	Real getMoneyTransactionVolume() const;
	Bool saveCameraInReplays();
	Bool useCameraInReplays();
	Bool getPlayerObserverEnabled() const;
	Int getStaticGameDetail();
	Int getIdealStaticGameDetail();
	Real getGammaValue();
	Int getTextureReduction();
	void getResolution(Int *xres, Int *yres);
	Bool get3DShadowsEnabled();
	Bool get2DShadowsEnabled();
	Bool getCloudShadowsEnabled();
	Bool getLightmapEnabled();
	Bool getSmoothWaterEnabled();
	Bool getTreesEnabled();
	Bool getExtraAnimationsDisabled();
	Bool getUseHeatEffects();
	Bool getDynamicLODEnabled();
	Bool getFPSLimitEnabled();
	Bool getBuildingOcclusionEnabled();
	Int getParticleCap();

	Int getCampaignDifficulty();
	void setCampaignDifficulty(Int diff);

	Int getNetworkLatencyFontSize();
	Int getRenderFpsFontSize();
	Int getSystemTimeFontSize();
	Int getGameTimeFontSize();
	Int getPlayerInfoListFontSize();

	Real getResolutionFontAdjustment();

	Bool getShowMoneyPerMinute() const;
	// GeneralsX @feature Claude 14/10/2026 Smooth object motion between logic frames, on by default.
	Bool getSmoothMotion() const;

	Real getMaxCameraHeight() const;
	Real getMinCameraHeight() const;
	Real getCameraPitch() const;
	Real getTerrainDrawDistanceScale() const;
	Real getGameWindowTransitionSpeedMultiplier() const;
	// GeneralsX @feature felipebraz 17/09/2026 Skirmish simulation tick rate configuration (#281)
	Int getSkirmishTickRate() const;
	// GeneralsX @feature Claude 14/10/2026 FSR render scale (Options.ini RenderScale, 100 = off)
	Int getRenderScale() const;
	static Bool getRenderScaleResolution(Int scale, Int displayWidth, Int displayHeight, Int *xres, Int *yres);
	// GeneralsX @bugfix Claude 16/10/2026 Whether Options.ini sets Resolution at all
	Bool hasResolution() const;
	// GeneralsX @bugfix Claude 16/10/2026 The largest rectangle of the aspect ratio of width x height that fits in
	// displayWidth x displayHeight, with the rounding of fitAspectRatio in DXVK patch 0001 (the image DXVK presents)
	static void fitToDisplay(Int width, Int height, Int displayWidth, Int displayHeight, Int *fitWidth, Int *fitHeight);
	// GeneralsX @feature Claude 15/10/2026 FSR RCAS sharpening in stops (Options.ini FSRSharpness, 0 = sharpest)
	Real getFSRSharpness() const;
	// GeneralsX @feature Claude 16/10/2026 Whether Options.ini sets RenderScale at all
	Bool hasRenderScale() const;
	// GeneralsX @feature Claude 16/10/2026 Upscaler (Options.ini Upscaler = FSR3 | FSR2 | FSR1 | OFF | DLSS)
	UpscalerType getUpscaler() const;
	static UpscalerType parseUpscaler(const char *name);
	static const char *getUpscalerName(UpscalerType upscaler);
	// GeneralsX @feature Claude 16/10/2026 Render scale of Options.ini UpscalerQuality
	// (Quality | Balanced | Performance | UltraPerformance | Native, default Quality)
	Int getUpscalerQualityScale() const;
	AsciiString getUpscalerQualityName() const;
	// GeneralsX @feature Claude 16/10/2026 FSR 2 reactive mask strength for particles and other alpha-blended
	// effects (Options.ini UpscalerReactiveScale, 0 to 1, 0 = off, default 0.9)
	Real getUpscalerReactiveScale() const;
	// GeneralsX @feature Claude 16/10/2026 FSR 2's own RCAS sharpening (Options.ini UpscalerSharpness, 0 to 1,
	// 0 = leave sharpening to FSRSharpness, default 0.5)
	Real getUpscalerSharpness() const;
	// GeneralsX @feature Claude 16/10/2026 FSR 3 frame generation (Options.ini FrameGeneration = yes | no,
	// default no, only with Upscaler = FSR3)
	Bool getFrameGeneration() const;
	// GeneralsX @feature Claude 16/10/2026 DXVK bloom, colour grade and FXAA (Options.ini PostEffects, default yes)
	Bool getPostEffectsEnabled() const;
	// GeneralsX @feature Claude 16/10/2026 DXVK ambient occlusion (Options.ini AmbientOcclusion, default yes)
	Bool getAmbientOcclusionEnabled() const;
	// GeneralsX @feature Claude 16/10/2026 Close-up terrain detail (Options.ini TerrainDetail, TerrainDetailStrength,
	// TerrainRelief and TerrainSoftBlend; all default on, strength 0.7).
	Bool getTerrainDetailEnabled() const;
	Real getTerrainDetailStrength() const;
	Bool getTerrainReliefEnabled() const;
	Bool getTerrainSoftBlendEnabled() const;
	// GeneralsX @feature Claude 16/10/2026 Normal and gloss maps for unit and building models (Options.ini
	// ModelNormalMaps, default no; ModelSpecular 0..2, default 1).
	Bool getModelNormalMapsEnabled() const;
	Real getModelSpecular() const;
	// GeneralsX @feature Claude 15/10/2026 Folder for bug report screenshots and videos (Options.ini CapturePath).
	AsciiString getCapturePath() const;
	// GeneralsX @performance Claude 16/10/2026 Frame profiler and big battle render options.
	Bool getPerfOverlayEnabled() const;			///< Options.ini PerfOverlay, default no
	Real getPerfIntervalSeconds() const;		///< Options.ini PerfInterval, default 5
	Bool getSkinCacheEnabled() const;			///< Options.ini SkinCache, default yes
	// GeneralsX @performance Claude 16/10/2026 Options.ini PreloadAssets = yes | no | everything, default yes.
	enum PreloadAssetsMode { PRELOAD_ASSETS_NO, PRELOAD_ASSETS_YES, PRELOAD_ASSETS_EVERYTHING };
	PreloadAssetsMode getPreloadAssetsMode() const;
	Int getShadowVolumeHighPolyTriangles() const;	///< Options.ini ShadowVolumeHighPolyTriangles, default 4000
	Real getShadowVolumeHighPolyAngle() const;	///< Options.ini ShadowVolumeHighPolyAngle in degrees, default 3
	Int getShadowVolumeMaxTriangles() const;	///< Options.ini ShadowVolumeMaxTriangles, default 0 (no limit)
	// GeneralsX @feature Claude 16/10/2026 Shadows of skinned models (W3DSkinnedShadow).
	enum SkinnedShadowMode { SKINNED_SHADOWS_DECAL, SKINNED_SHADOWS_PROJECTED, SKINNED_SHADOWS_VOLUME };
	Int getSkinnedShadowMode() const;			///< Options.ini SkinnedShadows = Volume | Projected | Decal, default Projected
	Int getSkinnedShadowQuality() const;		///< Options.ini SkinnedShadowQuality = Low | Medium | High (0, 1, 2), default Medium
	Real getSkinnedShadowDistance() const;		///< Options.ini SkinnedShadowDistance in world units, default 1500, 0 = no limit
	Bool getSkinnedShadowKeepDecal() const;		///< Options.ini SkinnedShadowKeepDecal, default no
	Int getSkinnedShadowMinTriangles() const;	///< Options.ini SkinnedShadowMinTriangles, default 2000
	// GeneralsX @feature Claude 16/10/2026 Coloured lights from explosions, fires, muzzle flashes and missile exhausts
	// (W3DEffectLights).
	enum DynamicLightsMode { DYNAMIC_LIGHTS_OFF, DYNAMIC_LIGHTS_LOW, DYNAMIC_LIGHTS_HIGH };
	Int getDynamicLightsMode() const;			///< Options.ini DynamicLights = Off | Low | High, default High
	Real getDynamicLightIntensity() const;		///< Options.ini DynamicLightIntensity, 0 to 2, default 1
	// GeneralsX @feature Claude 18/10/2026 -dynamicLights <off|low|high> overrides DynamicLights for profiling
	static void setDynamicLightsOverride(Int mode);	///< -1 clears the override, else a DynamicLightsMode value
	static Int getDynamicLightsOverride();			///< -1 when no override is active
	// GeneralsX @feature Claude 16/10/2026 Water effects of standing water and rivers (W3DWaterEffects.cpp).
	Int getWaterReflections() const;			///< Options.ini WaterReflections = Off | Sky | Full (0, 1, 2), default Full
	Real getWaterReflectionScale() const;		///< Options.ini WaterReflectionScale, 0.25 to 1, default 0.5
	Bool getShoreFoamEnabled() const;			///< Options.ini ShoreFoam, default yes
	Bool getWaterWavesEnabled() const;			///< Options.ini WaterWaves, default yes
};
