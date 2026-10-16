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
// FILE: OptionPreferences.cpp
// Author: Matthew D. Campbell, April 2002
// Description: Saving/Loading of option preferences
///////////////////////////////////////////////////////////////////////////////////////

// INCLUDES ///////////////////////////////////////////////////////////////////////////////////////
#include "PreRTS.h"	// This must go first in EVERY cpp file in the GameEngine

#include "Common/AudioSettings.h"
#include "Common/GameAudio.h"
#include "Common/GameLOD.h"
#include "Common/GlobalData.h"
#include "Common/OptionPreferences.h"

#include "GameClient/ClientInstance.h"
#include "GameClient/Display.h"
#include "GameClient/LookAtXlat.h"
#include "GameClient/Mouse.h"

#include "GameLogic/ScriptEngine.h"

#include "GameNetwork/IPEnumeration.h"

OptionPreferences::OptionPreferences()
{
	loadFromIniFile();
}

OptionPreferences::~OptionPreferences()
{
}

Bool OptionPreferences::loadFromIniFile()
{
	if (rts::ClientInstance::getInstanceId() > 1u)
	{
		AsciiString fname;
		fname.format("Options_Instance%.2u.ini", rts::ClientInstance::getInstanceId());
		return load(fname);
	}

	return load("Options.ini");
}

WW3D::MultiSampleModeEnum OptionPreferences::getAntiAliasing() const
{
	OptionPreferences::const_iterator it = find("AntiAliasing");
	// GeneralsX @feature Claude 15/10/2026 4x MSAA by default; the device falls back to a supported level.
	// GeneralsX @tweak Claude 15/10/2026 The device lowers this default to 2x on integrated GPUs (DX8Wrapper::Set_Render_Device).
	if (it == end())
		return WW3D::MULTISAMPLE_MODE_4X;

	WW3D::MultiSampleModeEnum level = (WW3D::MultiSampleModeEnum)atoi(it->second.str());
	level = clamp(WW3D::MULTISAMPLE_MODE_NONE, level, WW3D::MULTISAMPLE_MODE_8X);
	level = highestBit(level);

	return level;
}

Bool OptionPreferences::hasAntiAliasing() const
{
	return find("AntiAliasing") != end();
}

TextureFilterClass::TextureFilterMode OptionPreferences::getTextureFilterMode() const
{
	// GeneralsX @tweak sav-labs 14/10/2026 Default to anisotropic filtering; every DXVK-capable GPU supports it.
	OptionPreferences::const_iterator it = find("TextureFilter");
	if (it == end())
		return TextureFilterClass::TEXTURE_FILTER_ANISOTROPIC;

	return TextureFilterClass::getTextureFilterMode(it->second.str());
}

TextureFilterClass::AnisotropicFilterMode OptionPreferences::getTextureAnisotropyLevel() const
{
	// GeneralsX @tweak sav-labs 14/10/2026 Default to 16x anisotropy for sharp terrain at oblique camera angles.
	OptionPreferences::const_iterator it = find("AnisotropyLevel");
	if (it == end())
		return TextureFilterClass::TEXTURE_FILTER_ANISOTROPIC_16X;

	TextureFilterClass::AnisotropicFilterMode level = (TextureFilterClass::AnisotropicFilterMode)atoi(it->second.str());
	level = clamp(TextureFilterClass::TEXTURE_FILTER_ANISOTROPIC_2X, level, TextureFilterClass::TEXTURE_FILTER_ANISOTROPIC_16X);
	level = highestBit(level);

	return level;
}

// GeneralsX @feature Claude 15/10/2026 Read the mip LOD bias, clamped to -2..1; default -0.5 for sharper textures.
Real OptionPreferences::getTextureLodBias() const
{
	OptionPreferences::const_iterator it = find("TextureLodBias");
	if (it == end())
		return -0.5f;

	Real bias = (Real)atof(it->second.str());
	if (bias < -2.0f)
		bias = -2.0f;
	if (bias > 1.0f)
		bias = 1.0f;

	return bias;
}

Int OptionPreferences::getCampaignDifficulty()
{
	OptionPreferences::const_iterator it = find("CampaignDifficulty");
	if (it == end())
		return TheScriptEngine->getGlobalDifficulty();

	Int factor = atoi(it->second.str());
	if (factor < DIFFICULTY_EASY)
		factor = DIFFICULTY_EASY;
	if (factor > DIFFICULTY_HARD)
		factor = DIFFICULTY_HARD;

	return factor;
}

void OptionPreferences::setCampaignDifficulty(Int diff)
{
	AsciiString prefString;
	prefString.format("%d", diff);
	(*this)["CampaignDifficulty"] = prefString;
}

UnsignedInt OptionPreferences::getLANIPAddress()
{
	AsciiString selectedIP = (*this)["IPAddress"];
	IPEnumeration IPs;
	EnumeratedIP *IPlist = IPs.getAddresses();
	while (IPlist)
	{
		if (selectedIP.compareNoCase(IPlist->getIPstring()) == 0)
		{
			return IPlist->getIP();
		}
		IPlist = IPlist->getNext();
	}
	return TheGlobalData->m_defaultIP;
}

void OptionPreferences::setLANIPAddress(AsciiString IP)
{
	(*this)["IPAddress"] = IP;
}

void OptionPreferences::setLANIPAddress(UnsignedInt IP)
{
	AsciiString tmp;
	tmp.format("%d.%d.%d.%d", PRINTF_IP_AS_4_INTS(IP));
	(*this)["IPAddress"] = tmp;
}

UnsignedInt OptionPreferences::getOnlineIPAddress()
{
	AsciiString selectedIP = (*this)["GameSpyIPAddress"];
	IPEnumeration IPs;
	EnumeratedIP *IPlist = IPs.getAddresses();
	while (IPlist)
	{
		if (selectedIP.compareNoCase(IPlist->getIPstring()) == 0)
		{
			return IPlist->getIP();
		}
		IPlist = IPlist->getNext();
	}
	return TheGlobalData->m_defaultIP;
}

void OptionPreferences::setOnlineIPAddress(AsciiString IP)
{
	(*this)["GameSpyIPAddress"] = IP;
}

void OptionPreferences::setOnlineIPAddress(UnsignedInt IP)
{
	AsciiString tmp;
	tmp.format("%d.%d.%d.%d", PRINTF_IP_AS_4_INTS(IP));
	(*this)["GameSpyIPAddress"] = tmp;
}

Bool OptionPreferences::getArchiveReplaysEnabled() const
{
	OptionPreferences::const_iterator it = find("ArchiveReplays");
	if (it == end())
		return FALSE;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::getAlternateMouseModeEnabled()
{
	OptionPreferences::const_iterator it = find("UseAlternateMouse");
	if (it == end())
		return TheGlobalData->m_useAlternateMouse;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::getRightMouseScrollWithAlternateMouseEnabled() const
{
	OptionPreferences::const_iterator it = find("UseRightMouseScrollWithAlternateMouse");
	if (it == end())
		return TheGlobalData->m_useRightMouseScrollWithAlternateMouse;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::getRetaliationModeEnabled()
{
	OptionPreferences::const_iterator it = find("Retaliation");
	if (it == end())
		return TheGlobalData->m_clientRetaliationModeEnabled;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::getDoubleClickAttackMoveEnabled()
{
	OptionPreferences::const_iterator it = find("UseDoubleClickAttackMove");
	if( it == end() )
		return TheGlobalData->m_doubleClickAttackMove;

	if( stricmp( it->second.str(), "yes" ) == 0 )
		return TRUE;

	return FALSE;
}

Int OptionPreferences::getJpegQuality() const
{
	OptionPreferences::const_iterator it = find("JpegQuality");
	if (it == end())
		return DEFAULT_JPEG_QUALITY;

	// TheSuperHackers @info bobtista 14/07/2026 Clamp the quality to 50-95: above 95 the file
	// size increases significantly with no visible benefit, below 50 the image degrades visibly.
	const Int quality = atoi(it->second.str());
	return clamp(50, quality, 95);
}

Real OptionPreferences::getScrollFactor()
{
	OptionPreferences::const_iterator it = find("ScrollFactor");
	if (it == end())
		return TheGlobalData->m_keyboardDefaultScrollFactor;

	Int factor = atoi(it->second.str());

	// TheSuperHackers @tweak xezon 11/07/2025
	// No longer caps the upper limit to 100, because the options setting can go beyond that.
	// No longer caps the lower limit to 0, because that would mean standstill.
	if (factor < 1)
		factor = 1;

	return factor/100.0f;
}

Bool OptionPreferences::getDrawScrollAnchor()
{
	OptionPreferences::const_iterator it = find("DrawScrollAnchor");
	// TheSuperHackers @info this default is based on the same variable within InGameUi.ini
	if (it == end())
		return FALSE;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::getMoveScrollAnchor()
{
	OptionPreferences::const_iterator it = find("MoveScrollAnchor");
	// TheSuperHackers @info this default is based on the same variable within InGameUi.ini
	if (it == end())
		return TRUE;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::getCursorCaptureEnabledInWindowedGame() const
{
	OptionPreferences::const_iterator it = find("CursorCaptureEnabledInWindowedGame");
	if (it == end())
		return (CursorCaptureMode_Default & CursorCaptureMode_EnabledInWindowedGame) != 0;

	if (stricmp(it->second.str(), "yes") == 0)
		return TRUE;

	return FALSE;
}

Bool OptionPreferences::getCursorCaptureEnabledInWindowedMenu() const
{
	OptionPreferences::const_iterator it = find("CursorCaptureEnabledInWindowedMenu");
	if (it == end())
		return (CursorCaptureMode_Default & CursorCaptureMode_EnabledInWindowedMenu) != 0;

	if (stricmp(it->second.str(), "yes") == 0)
		return TRUE;

	return FALSE;
}

Bool OptionPreferences::getCursorCaptureEnabledInFullscreenGame() const
{
	OptionPreferences::const_iterator it = find("CursorCaptureEnabledInFullscreenGame");
	if (it == end())
		return (CursorCaptureMode_Default & CursorCaptureMode_EnabledInFullscreenGame) != 0;

	if (stricmp(it->second.str(), "yes") == 0)
		return TRUE;

	return FALSE;
}

Bool OptionPreferences::getCursorCaptureEnabledInFullscreenMenu() const
{
	OptionPreferences::const_iterator it = find("CursorCaptureEnabledInFullscreenMenu");
	if (it == end())
		return (CursorCaptureMode_Default & CursorCaptureMode_EnabledInFullscreenMenu) != 0;

	if (stricmp(it->second.str(), "yes") == 0)
		return TRUE;

	return FALSE;
}

CursorCaptureMode OptionPreferences::getCursorCaptureMode() const
{
	CursorCaptureMode mode = 0;
	mode |= getCursorCaptureEnabledInWindowedGame() ? CursorCaptureMode_EnabledInWindowedGame : 0;
	mode |= getCursorCaptureEnabledInWindowedMenu() ? CursorCaptureMode_EnabledInWindowedMenu : 0;
	mode |= getCursorCaptureEnabledInFullscreenGame() ? CursorCaptureMode_EnabledInFullscreenGame : 0;
	mode |= getCursorCaptureEnabledInFullscreenMenu() ? CursorCaptureMode_EnabledInFullscreenMenu : 0;
	return mode;
}

Bool OptionPreferences::getScreenEdgeScrollEnabledInWindowedApp() const
{
	OptionPreferences::const_iterator it = find("ScreenEdgeScrollEnabledInWindowedApp");
	if (it == end())
		return (ScreenEdgeScrollMode_Default & ScreenEdgeScrollMode_EnabledInWindowedApp) != 0;

	if (stricmp(it->second.str(), "yes") == 0)
		return TRUE;

	return FALSE;
}

Bool OptionPreferences::getScreenEdgeScrollEnabledInFullscreenApp() const
{
	OptionPreferences::const_iterator it = find("ScreenEdgeScrollEnabledInFullscreenApp");
	if (it == end())
		return (ScreenEdgeScrollMode_Default & ScreenEdgeScrollMode_EnabledInFullscreenApp) != 0;

	if (stricmp(it->second.str(), "yes") == 0)
		return TRUE;

	return FALSE;
}

ScreenEdgeScrollMode OptionPreferences::getScreenEdgeScrollMode() const
{
	ScreenEdgeScrollMode mode = 0;
	mode |= getScreenEdgeScrollEnabledInWindowedApp() ? ScreenEdgeScrollMode_EnabledInWindowedApp : 0;
	mode |= getScreenEdgeScrollEnabledInFullscreenApp() ? ScreenEdgeScrollMode_EnabledInFullscreenApp : 0;
	return mode;
}

Bool OptionPreferences::usesSystemMapDir()
{
	OptionPreferences::const_iterator it = find("UseSystemMapDir");
	if (it == end())
		return TRUE;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::saveCameraInReplays()
{
	OptionPreferences::const_iterator it = find("SaveCameraInReplays");
	if (it == end())
		return TRUE;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::useCameraInReplays()
{
	OptionPreferences::const_iterator it = find("UseCameraInReplays");
	if (it == end())
		return TRUE;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::getPlayerObserverEnabled() const
{
	OptionPreferences::const_iterator it = find("PlayerObserverEnabled");
	if (it == end())
		return TRUE;

	if (stricmp(it->second.str(), "yes") == 0)
		return TRUE;

	return FALSE;
}

Int OptionPreferences::getIdealStaticGameDetail()
{
	OptionPreferences::const_iterator it = find("IdealStaticGameLOD");
	if (it == end())
		return STATIC_GAME_LOD_UNKNOWN;

	return TheGameLODManager->getStaticGameLODIndex(it->second);
}

Int OptionPreferences::getStaticGameDetail()
{
	OptionPreferences::const_iterator it = find("StaticGameLOD");
	if (it == end())
		return TheGameLODManager->getStaticLODLevel();

	return TheGameLODManager->getStaticGameLODIndex(it->second);
}

Int OptionPreferences::getFirewallBehavior()
{
	OptionPreferences::const_iterator it = find("FirewallBehavior");
	if (it == end())
		return TheGlobalData->m_firewallBehavior;

	Int behavior = atoi(it->second.str());
	if (behavior < 0)
	{
		behavior = 0;
	}
	return behavior;
}

Short OptionPreferences::getFirewallPortAllocationDelta()
{
	OptionPreferences::const_iterator it = find("FirewallPortAllocationDelta");
	if (it == end()) {
		return TheGlobalData->m_firewallPortAllocationDelta;
	}

	Short delta = atoi(it->second.str());
	return delta;
}

UnsignedShort OptionPreferences::getFirewallPortOverride()
{
	OptionPreferences::const_iterator it = find("FirewallPortOverride");
	if (it == end()) {
		return TheGlobalData->m_firewallPortOverride;
	}

	Int portOverride = atoi(it->second.str());
	if (portOverride < 0 || portOverride > 65535)
		portOverride = 0;
	return portOverride;
}

Bool OptionPreferences::getFirewallNeedToRefresh()
{
	OptionPreferences::const_iterator it = find("FirewallNeedToRefresh");
	if (it == end()) {
		return FALSE;
	}

	Bool retval = FALSE;
	AsciiString str = it->second;
	if (str.compareNoCase("TRUE") == 0) {
		retval = TRUE;
	}
	return retval;
}

AsciiString OptionPreferences::getPreferred3DProvider()
{
	OptionPreferences::const_iterator it = find("3DAudioProvider");
	if (it == end())
		return TheAudio->getAudioSettings()->m_preferred3DProvider[MAX_HW_PROVIDERS];
	return it->second;
}

AsciiString OptionPreferences::getSpeakerType()
{
	OptionPreferences::const_iterator it = find("SpeakerType");
	if (it == end())
		return TheAudio->translateUnsignedIntToSpeakerType(TheAudio->getAudioSettings()->m_defaultSpeakerType2D);
	return it->second;
}

Real OptionPreferences::getSoundVolume()
{
	OptionPreferences::const_iterator it = find("SFXVolume");
	if (it == end())
	{
		Real relative = TheAudio->getAudioSettings()->m_relative2DVolume;
		if( relative < 0 )
		{
			Real scale = 1.0f + relative;
			return TheAudio->getAudioSettings()->m_defaultSoundVolume * 100.0f * scale;
		}
		return TheAudio->getAudioSettings()->m_defaultSoundVolume * 100.0f;
	}

	Real volume = (Real) atof(it->second.str());
	if (volume < 0.0f)
	{
		volume = 0.0f;
	}
	return volume;
}

Real OptionPreferences::get3DSoundVolume()
{
	OptionPreferences::const_iterator it = find("SFX3DVolume");
	if (it == end())
	{
		Real relative = TheAudio->getAudioSettings()->m_relative2DVolume;
		if( relative > 0 )
		{
			Real scale = 1.0f - relative;
			return TheAudio->getAudioSettings()->m_default3DSoundVolume * 100.0f * scale;
		}
		return TheAudio->getAudioSettings()->m_default3DSoundVolume * 100.0f;
	}

	Real volume = (Real) atof(it->second.str());
	if (volume < 0.0f)
	{
		volume = 0.0f;
	}
	return volume;
}

Real OptionPreferences::getSpeechVolume()
{
	OptionPreferences::const_iterator it = find("VoiceVolume");
	if (it == end())
		return TheAudio->getAudioSettings()->m_defaultSpeechVolume * 100.0f;

	Real volume = (Real) atof(it->second.str());
	if (volume < 0.0f)
	{
		volume = 0.0f;
	}
	return volume;
}

Bool OptionPreferences::getCloudShadowsEnabled()
{
	OptionPreferences::const_iterator it = find("UseCloudMap");
	if (it == end())
		return TheGlobalData->m_useCloudMap;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::getLightmapEnabled()
{
	OptionPreferences::const_iterator it = find("UseLightMap");
	if (it == end())
		return TheGlobalData->m_useLightMap;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::getSmoothWaterEnabled()
{
	OptionPreferences::const_iterator it = find("ShowSoftWaterEdge");
	if (it == end())
		return TheGlobalData->m_showSoftWaterEdge;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::getTreesEnabled()
{
	OptionPreferences::const_iterator it = find("ShowTrees");
	if (it == end())
		return TheGlobalData->m_useTrees;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::getExtraAnimationsDisabled()
{
	OptionPreferences::const_iterator it = find("ExtraAnimations");
	if (it == end())
		return TheGlobalData->m_useDrawModuleLOD;

	if (stricmp(it->second.str(), "yes") == 0) {
		return FALSE;	//we are enabling extra animations, so disabled LOD
	}
	return TRUE;
}

Bool OptionPreferences::getUseHeatEffects()
{
	OptionPreferences::const_iterator it = find("HeatEffects");
	if (it == end())
		return TheGlobalData->m_useHeatEffects;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::getDynamicLODEnabled()
{
	OptionPreferences::const_iterator it = find("DynamicLOD");
	if (it == end())
		return TheGlobalData->m_enableDynamicLOD;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::getFPSLimitEnabled()
{
	OptionPreferences::const_iterator it = find("FPSLimit");
	if (it == end())
	{
		// GeneralsX @bugfix Copilot 11/05/2026 Keep the FPS limiter enabled by default when no explicit preference exists.
		return TRUE;
	}

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::get3DShadowsEnabled()
{
	OptionPreferences::const_iterator it = find("UseShadowVolumes");
	if (it == end())
		return TheGlobalData->m_useShadowVolumes;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::get2DShadowsEnabled()
{
	OptionPreferences::const_iterator it = find("UseShadowDecals");
	if (it == end())
		return TheGlobalData->m_useShadowDecals;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Bool OptionPreferences::getBuildingOcclusionEnabled()
{
	OptionPreferences::const_iterator it = find("BuildingOcclusion");
	if (it == end())
		return TheGlobalData->m_enableBehindBuildingMarkers;

	if (stricmp(it->second.str(), "yes") == 0) {
		return TRUE;
	}
	return FALSE;
}

Int OptionPreferences::getParticleCap()
{
	OptionPreferences::const_iterator it = find("MaxParticleCount");
	if (it == end())
		return TheGlobalData->m_maxParticleCount;

	Int factor = (Int) atoi(it->second.str());
	if (factor < 100)	//clamp to at least 100 particles.
		factor = 100;

	return factor;
}

Int OptionPreferences::getTextureReduction()
{
	OptionPreferences::const_iterator it = find("TextureReduction");
	if (it == end())
		return -1;	//unknown texture reduction

	Int factor = (Int) atoi(it->second.str());
	if (factor > 2)	//clamp it.
		factor=2;
	return factor;
}

Real OptionPreferences::getGammaValue()
{
	OptionPreferences::const_iterator it = find("Gamma");
	if (it == end())
		return 50.0f;

	Real gamma = (Real) atoi(it->second.str());
	return gamma;
}

void OptionPreferences::getResolution(Int *xres, Int *yres)
{
	*xres = TheGlobalData->m_xResolution;
	*yres = TheGlobalData->m_yResolution;

	OptionPreferences::const_iterator it = find("Resolution");
	if (it == end())
		return;

	Int selectedXRes,selectedYRes;
	if (sscanf(it->second.str(),"%d%d", &selectedXRes, &selectedYRes) != 2)
		return;

	*xres=selectedXRes;
	*yres=selectedYRes;
}

Real OptionPreferences::getMusicVolume()
{
	OptionPreferences::const_iterator it = find("MusicVolume");
	if (it == end())
		return TheAudio->getAudioSettings()->m_defaultMusicVolume * 100.0f;

	Real volume = (Real) atof(it->second.str());
	if (volume < 0.0f)
	{
		volume = 0.0f;
	}
	return volume;
}

Real OptionPreferences::getMoneyTransactionVolume() const
{
	OptionPreferences::const_iterator it = find("MoneyTransactionVolume");
	if (it == end())
		return TheAudio->getAudioSettings()->m_defaultMoneyTransactionVolume * 100.0f;

	Real volume = (Real) atof(it->second.str());
	if (volume < 0.0f)
		volume = 0.0f;

	return volume;
}

Int OptionPreferences::getNetworkLatencyFontSize()
{
	OptionPreferences::const_iterator it = find("NetworkLatencyFontSize");
	if (it == end())
		return 8;

	Int fontSize = atoi(it->second.str());
	if (fontSize < 0)
	{
		fontSize = 0;
	}
	return fontSize;
}

Int OptionPreferences::getRenderFpsFontSize()
{
	OptionPreferences::const_iterator it = find("RenderFpsFontSize");
	if (it == end())
		return 8;

	Int fontSize = atoi(it->second.str());
	if (fontSize < 0)
	{
		fontSize = 0;
	}
	return fontSize;
}

Int OptionPreferences::getSystemTimeFontSize()
{
	OptionPreferences::const_iterator it = find("SystemTimeFontSize");
	if (it == end())
		return 8;

	Int fontSize = atoi(it->second.str());
	if (fontSize < 0)
	{
		fontSize = 0;
	}
	return fontSize;
}

Int OptionPreferences::getGameTimeFontSize()
{
	OptionPreferences::const_iterator it = find("GameTimeFontSize");
	if (it == end())
		return 8;

	Int fontSize = atoi(it->second.str());
	if (fontSize < 0)
	{
		fontSize = 0;
	}
	return fontSize;
}

Int OptionPreferences::getPlayerInfoListFontSize()
{
	OptionPreferences::const_iterator it = find("PlayerInfoListFontSize");
	if (it == end())
		return 8;

	Int fontSize = atoi(it->second.str());
	if (fontSize < 0)
	{
		fontSize = 0;
	}
	return fontSize;
}

Real OptionPreferences::getResolutionFontAdjustment()
{
	OptionPreferences::const_iterator it = find("ResolutionFontAdjustment");
	if (it == end())
		return -1.0f;

	Real fontScale = (Real)atof(it->second.str()) / 100.0f;
	if (fontScale < 0.0f)
	{
		fontScale = -1.0f;
	}
	return fontScale;
}

Bool OptionPreferences::getShowMoneyPerMinute() const
{
	OptionPreferences::const_iterator it = find("ShowMoneyPerMinute");
	if (it == end())
		return TheGlobalData->m_showMoneyPerMinute;

	if (stricmp(it->second.str(), "yes") == 0)
	{
		return TRUE;
	}
	return FALSE;
}

// GeneralsX @feature Claude 14/10/2026 Smooth object motion between logic frames, on by default.
Bool OptionPreferences::getSmoothMotion() const
{
	OptionPreferences::const_iterator it = find("SmoothMotion");
	if (it == end())
		return TheGlobalData->m_smoothMotion;

	if (stricmp(it->second.str(), "yes") == 0)
	{
		return TRUE;
	}
	return FALSE;
}

Real OptionPreferences::getMaxCameraHeight() const
{
	OptionPreferences::const_iterator it = find("MaxCameraHeight");
	if (it == end())
		return TheGlobalData->m_maxCameraHeight;

	Real val = (Real)atof(it->second.str());
	if (val < 100.0f)
		val = 100.0f;
	if (val > 1000.0f)
		val = 1000.0f;
	return val;
}

Real OptionPreferences::getMinCameraHeight() const
{
	OptionPreferences::const_iterator it = find("MinCameraHeight");
	if (it == end())
		return TheGlobalData->m_minCameraHeight;

	Real val = (Real)atof(it->second.str());
	if (val < 50.0f)
		val = 50.0f;
	if (val > 300.0f)
		val = 300.0f;
	return val;
}

Real OptionPreferences::getCameraPitch() const
{
	OptionPreferences::const_iterator it = find("CameraPitch");
	if (it == end())
		return TheGlobalData->m_cameraPitch;

	Real val = (Real)atof(it->second.str());
	if (val < 20.0f)
		val = 20.0f;
	if (val > 60.0f)
		val = 60.0f;
	return val;
}

Real OptionPreferences::getTerrainDrawDistanceScale() const
{
	OptionPreferences::const_iterator it = find("TerrainDrawDistanceScale");
	if (it == end())
		return TheGlobalData->m_terrainDrawDistanceScale;

	Real val = (Real)atof(it->second.str());
	if (val < 1.0f)
		val = 1.0f;
	if (val > 2.0f)
		val = 2.0f;
	return val;
}

Real OptionPreferences::getGameWindowTransitionSpeedMultiplier() const
{
	OptionPreferences::const_iterator it = find("GameWindowTransitionSpeedMultiplier");
	if (it == end())
		return 1.0f;

	Real speed = (Real) atof(it->second.str());
	return clamp(1.0f, speed, 1000.0f);
}

// GeneralsX @feature felipebraz 17/09/2026 Skirmish simulation tick rate configuration (#281)
Int OptionPreferences::getSkirmishTickRate() const
{
	OptionPreferences::const_iterator it = find("TickRate");
	if (it == end())
	{
		it = find("GameSpeed");
	}
	if (it == end())
	{
		it = find("SkirmishTickRate");
	}
	if (it == end())
	{
		return LOGICFRAMES_PER_SECOND;
	}

	Int rate = atoi(it->second.str());
	if (rate <= 0)
	{
		return LOGICFRAMES_PER_SECOND;
	}

	return clamp(5, rate, 120);
}

// GeneralsX @feature Claude 14/10/2026 RenderScale is the game resolution in percent of the display size.
// Below 100 the game runs in a borderless display-size window and the DXVK swap chain upscales it with FSR 1.0.
Int OptionPreferences::getRenderScale() const
{
	OptionPreferences::const_iterator it = find("RenderScale");
	if (it == end())
		return RENDER_SCALE_OFF;

	Int scale = atoi(it->second.str());
	if (scale <= 0)
		return RENDER_SCALE_OFF;

	return clamp((Int)RENDER_SCALE_MIN, scale, (Int)RENDER_SCALE_OFF);
}

// GeneralsX @feature Claude 15/10/2026 FSRSharpness is the RCAS sharpening pass after FSR 1.0 EASU, in stops:
// 0 is the sharpest and every stop halves the sharpening (AMD's scale, 0 to 2). Missing or invalid keys give 0.2,
// the DXVK default.
Real OptionPreferences::getFSRSharpness() const
{
	OptionPreferences::const_iterator it = find("FSRSharpness");
	if (it == end())
		return 0.2f;

	Real sharpness = (Real)atof(it->second.str());
	if (!(sharpness >= 0.0f))
		return 0.2f;

	return clamp(0.0f, sharpness, 2.0f);
}

// GeneralsX @feature Claude 16/10/2026 True when Options.ini has a RenderScale entry. An explicit RenderScale
// wins over the render scale of UpscalerQuality.
Bool OptionPreferences::hasRenderScale() const
{
	OptionPreferences::const_iterator it = find("RenderScale");
	return it != end() && atoi(it->second.str()) > 0;
}

// GeneralsX @feature Claude 16/10/2026 Upscaler names, case insensitive. Unknown names give UPSCALER_DEFAULT.
OptionPreferences::UpscalerType OptionPreferences::parseUpscaler(const char *name)
{
	if (name == nullptr)
		return UPSCALER_DEFAULT;
	if (stricmp(name, "FSR2") == 0)
		return UPSCALER_FSR2;
	// GeneralsX @feature Claude 16/10/2026 FSR 3.1 upscaler, opt-in like FSR 2
	if (stricmp(name, "FSR3") == 0)
		return UPSCALER_FSR3;
	if (stricmp(name, "FSR1") == 0 || stricmp(name, "FSR") == 0)
		return UPSCALER_FSR1;
	if (stricmp(name, "OFF") == 0 || stricmp(name, "no") == 0 || stricmp(name, "none") == 0)
		return UPSCALER_OFF;
	if (stricmp(name, "DLSS") == 0)
		return UPSCALER_DLSS;
	return UPSCALER_DEFAULT;
}

const char *OptionPreferences::getUpscalerName(UpscalerType upscaler)
{
	switch (upscaler)
	{
		case UPSCALER_OFF: return "OFF";
		case UPSCALER_FSR1: return "FSR1";
		case UPSCALER_FSR2: return "FSR2";
		case UPSCALER_DLSS: return "DLSS";
		case UPSCALER_FSR3: return "FSR3";
		default: return "default";
	}
}

// GeneralsX @feature Claude 16/10/2026 Options.ini Upscaler. FSR 2 is opt-in until it has been compared against
// native resolution on real hardware, so a missing entry keeps the FSR 1.0 behaviour of RenderScale.
OptionPreferences::UpscalerType OptionPreferences::getUpscaler() const
{
	OptionPreferences::const_iterator it = find("Upscaler");
	if (it == end())
		return UPSCALER_DEFAULT;

	return parseUpscaler(it->second.str());
}

// GeneralsX @feature Claude 16/10/2026 Options.ini UpscalerQuality picks the render scale when FSR 1.0 or FSR 2
// is chosen with Upscaler and RenderScale is not set. Missing or unknown values give Quality.
Int OptionPreferences::getUpscalerQualityScale() const
{
	AsciiString quality = getUpscalerQualityName();

	if (quality.compareNoCase("Balanced") == 0)
		return UPSCALER_BALANCED_SCALE;
	if (quality.compareNoCase("Performance") == 0)
		return UPSCALER_PERFORMANCE_SCALE;
	if (quality.compareNoCase("UltraPerformance") == 0)
		return UPSCALER_ULTRA_PERFORMANCE_SCALE;
	return UPSCALER_QUALITY_SCALE;
}

AsciiString OptionPreferences::getUpscalerQualityName() const
{
	OptionPreferences::const_iterator it = find("UpscalerQuality");
	if (it == end())
		return AsciiString("Quality");

	const char *name = it->second.str();
	if (stricmp(name, "Balanced") == 0 || stricmp(name, "Performance") == 0 || stricmp(name, "UltraPerformance") == 0)
		return it->second;
	return AsciiString("Quality");
}

// GeneralsX @feature Claude 16/10/2026 Options.ini UpscalerReactiveScale: how strongly FSR 2 favours the current
// frame over its history where particles, smoke, explosions and other alpha-blended effects changed the scene.
// 0 turns the reactive mask off. The default 0.9 is the highest reactivity AMD recommends for FSR 2; it is also
// the binary value of AMD's FSR 2 sample. Missing or invalid keys give the default.
Real OptionPreferences::getUpscalerReactiveScale() const
{
	OptionPreferences::const_iterator it = find("UpscalerReactiveScale");
	if (it == end())
		return 0.9f;

	Real scale = (Real)atof(it->second.str());
	if (!(scale >= 0.0f))
		return 0.9f;

	return clamp(0.0f, scale, 1.0f);
}

// GeneralsX @feature Claude 16/10/2026 Options.ini UpscalerSharpness: FSR 2's built-in RCAS pass, 0 to 1 (1 is
// the sharpest, AMD's scale). With it, the FSR 1.0 RCAS pass of FSRSharpness only sharpens the interface, so
// nothing is sharpened twice. 0 leaves the whole frame to FSRSharpness, as before FSR 2 had its own pass. The
// default 0.5 is one stop below the RCAS maximum, milder than the FSR 1.0 default of 0.2 stops: FSR 2 already
// rebuilds detail over several frames, and strong sharpening makes its sub-pixel jitter shimmer.
Real OptionPreferences::getUpscalerSharpness() const
{
	OptionPreferences::const_iterator it = find("UpscalerSharpness");
	if (it == end())
		return 0.5f;

	Real sharpness = (Real)atof(it->second.str());
	if (!(sharpness >= 0.0f))
		return 0.5f;

	return clamp(0.0f, sharpness, 1.0f);
}

// GeneralsX @feature Claude 16/10/2026 Options.ini FrameGeneration: FSR 3 frame generation, which presents a frame
// interpolated between every two real frames. Off unless set to yes; it only takes effect with Upscaler = FSR3.
// Render only: the game logic and its frame rate do not change.
Bool OptionPreferences::getFrameGeneration() const
{
	OptionPreferences::const_iterator it = find("FrameGeneration");
	if (it == end())
		return FALSE;

	return stricmp(it->second.str(), "yes") == 0;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini PostEffects turns the DXVK present pass effects on or off:
// bloom with a light colour grade, and FXAA when anti-aliasing is off. On unless set to "no".
Bool OptionPreferences::getPostEffectsEnabled() const
{
	OptionPreferences::const_iterator it = find("PostEffects");
	if (it == end())
		return TRUE;

	return stricmp(it->second.str(), "no") != 0;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini TerrainDetail adds a tileable detail texture to the
// ground that fades in close to the camera. On unless set to "no".
Bool OptionPreferences::getTerrainDetailEnabled() const
{
	OptionPreferences::const_iterator it = find("TerrainDetail");
	if (it == end())
		return TRUE;

	return stricmp(it->second.str(), "no") != 0;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini TerrainDetailStrength, 0..1 (default 0.7): how strongly the
// terrain detail texture modulates the ground colour.
Real OptionPreferences::getTerrainDetailStrength() const
{
	OptionPreferences::const_iterator it = find("TerrainDetailStrength");
	if (it == end())
		return 0.7f;

	Real strength = (Real)atof(it->second.str());
	if (strength < 0.0f)
		strength = 0.0f;
	if (strength > 1.0f)
		strength = 1.0f;

	return strength;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini TerrainRelief lights the bumps of the terrain tiles with the
// map's sun. On unless set to "no".
Bool OptionPreferences::getTerrainReliefEnabled() const
{
	OptionPreferences::const_iterator it = find("TerrainRelief");
	if (it == end())
		return TRUE;

	return stricmp(it->second.str(), "no") != 0;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini TerrainSoftBlend breaks up the straight edges between terrain
// textures with noise. On unless set to "no".
Bool OptionPreferences::getTerrainSoftBlendEnabled() const
{
	OptionPreferences::const_iterator it = find("TerrainSoftBlend");
	if (it == end())
		return TRUE;

	return stricmp(it->second.str(), "no") != 0;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini ModelNormalMaps uses <texture>_n.dds/.tga normal and gloss
// maps on unit and building models that have them. On unless set to "no".
Bool OptionPreferences::getModelNormalMapsEnabled() const
{
	OptionPreferences::const_iterator it = find("ModelNormalMaps");
	if (it == end())
		return TRUE;

	return stricmp(it->second.str(), "no") != 0;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini ModelSpecular scales the highlight from the gloss of the
// model normal maps: 0 none, 1 default, 2 strongest.
Real OptionPreferences::getModelSpecular() const
{
	OptionPreferences::const_iterator it = find("ModelSpecular");
	if (it == end())
		return 1.0f;

	Real strength = (Real)atof(it->second.str());
	if (strength < 0.0f)
		strength = 0.0f;
	if (strength > 2.0f)
		strength = 2.0f;

	return strength;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini AmbientOcclusion turns the DXVK ambient occlusion pass
// on or off: soft darkening where units and buildings meet the ground and in creases. On unless set to "no".
Bool OptionPreferences::getAmbientOcclusionEnabled() const
{
	OptionPreferences::const_iterator it = find("AmbientOcclusion");
	if (it == end())
		return TRUE;

	return stricmp(it->second.str(), "no") != 0;
}

// GeneralsX @performance Claude 16/10/2026 Options.ini PerfOverlay = yes turns on the frame profiler: a [PERF]
// summary on stderr every PerfInterval seconds and a small text overlay in the top left corner.
Bool OptionPreferences::getPerfOverlayEnabled() const
{
	OptionPreferences::const_iterator it = find("PerfOverlay");
	if (it == end())
		return FALSE;

	return stricmp(it->second.str(), "yes") == 0;
}

// GeneralsX @performance Claude 16/10/2026 Seconds between two [PERF] summaries, 1 to 600, default 5.
Real OptionPreferences::getPerfIntervalSeconds() const
{
	OptionPreferences::const_iterator it = find("PerfInterval");
	if (it == end())
		return 5.0f;

	return clamp(1.0f, (Real)atof(it->second.str()), 600.0f);
}

// GeneralsX @performance Claude 16/10/2026 Options.ini SkinCache: keep the deformed vertices of each skinned
// mesh and skip the CPU skinning while its bones have not moved. On unless set to "no".
Bool OptionPreferences::getSkinCacheEnabled() const
{
	OptionPreferences::const_iterator it = find("SkinCache");
	if (it == end())
		return TRUE;

	return stricmp(it->second.str(), "no") != 0;
}

// GeneralsX @performance Claude 16/10/2026 Map load preloads the models and textures of the map's objects (all
// their damage and night states) and of the units the players can build, so they are not read from disk in the
// middle of a match. everything preloads every object of every side for every time of day (slow, much memory).
OptionPreferences::PreloadAssetsMode OptionPreferences::getPreloadAssetsMode() const
{
	OptionPreferences::const_iterator it = find("PreloadAssets");
	if (it == end())
		return PRELOAD_ASSETS_YES;

	if (stricmp(it->second.str(), "no") == 0)
		return PRELOAD_ASSETS_NO;
	if (stricmp(it->second.str(), "everything") == 0)
		return PRELOAD_ASSETS_EVERYTHING;
	return PRELOAD_ASSETS_YES;
}

// GeneralsX @performance Claude 16/10/2026 Shadow volume caster meshes with at least this many triangles rebuild
// their silhouette only after ShadowVolumeHighPolyAngle degrees of rotation instead of 0.2. Retail models stay
// below the default of 4000 triangles. 0 turns the throttle off.
Int OptionPreferences::getShadowVolumeHighPolyTriangles() const
{
	OptionPreferences::const_iterator it = find("ShadowVolumeHighPolyTriangles");
	if (it == end())
		return 4000;

	const Int value = atoi(it->second.str());
	return value > 0 ? value : 0;
}

// GeneralsX @performance Claude 16/10/2026 Rotation in degrees (0.2 to 30, default 3) that a high poly shadow
// caster mesh may turn before its shadow silhouette is rebuilt.
Real OptionPreferences::getShadowVolumeHighPolyAngle() const
{
	OptionPreferences::const_iterator it = find("ShadowVolumeHighPolyAngle");
	if (it == end())
		return 3.0f;

	return clamp(0.2f, (Real)atof(it->second.str()), 30.0f);
}

// GeneralsX @performance Claude 16/10/2026 Models whose shadow volume casters have more triangles than this in
// total get a ground decal shadow instead of a shadow volume. 0 (the default) keeps shadow volumes for all.
Int OptionPreferences::getShadowVolumeMaxTriangles() const
{
	OptionPreferences::const_iterator it = find("ShadowVolumeMaxTriangles");
	if (it == end())
		return 0;

	const Int value = atoi(it->second.str());
	return value > 0 ? value : 0;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini SkinnedShadows: how skinned models (and models over
// ShadowVolumeMaxTriangles) cast their shadow. Projected (default): a shadow texture of the posed model drawn onto
// the terrain. Volume: a stencil shadow volume built from the skinned vertices. Decal: the retail behaviour.
Int OptionPreferences::getSkinnedShadowMode() const
{
	OptionPreferences::const_iterator it = find("SkinnedShadows");
	if (it == end())
		return SKINNED_SHADOWS_PROJECTED;

	if (stricmp(it->second.str(), "Volume") == 0)
		return SKINNED_SHADOWS_VOLUME;
	if (stricmp(it->second.str(), "Decal") == 0 || stricmp(it->second.str(), "no") == 0)
		return SKINNED_SHADOWS_DECAL;
	return SKINNED_SHADOWS_PROJECTED;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini SkinnedShadowQuality = Low | Medium | High (0, 1, 2): shadow
// texture resolution and update rate, and the triangle budget of skinned shadow volumes. Default Medium.
Int OptionPreferences::getSkinnedShadowQuality() const
{
	OptionPreferences::const_iterator it = find("SkinnedShadowQuality");
	if (it == end())
		return 1;

	if (stricmp(it->second.str(), "Low") == 0)
		return 0;
	if (stricmp(it->second.str(), "High") == 0)
		return 2;
	return 1;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini SkinnedShadowDistance: camera distance in world units at which
// skinned shadows have faded out (they fade over the last quarter). Default 1500, 0 = no limit.
Real OptionPreferences::getSkinnedShadowDistance() const
{
	OptionPreferences::const_iterator it = find("SkinnedShadowDistance");
	if (it == end())
		return 1500.0f;

	const Real value = (Real)atof(it->second.str());
	return value > 0.0f ? clamp(100.0f, value, 100000.0f) : 0.0f;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini SkinnedShadowKeepDecal = yes keeps the model's retail decal
// shadow under the new skinned shadow. Default no, so the two do not darken the ground twice.
Bool OptionPreferences::getSkinnedShadowKeepDecal() const
{
	OptionPreferences::const_iterator it = find("SkinnedShadowKeepDecal");
	if (it == end())
		return FALSE;

	return stricmp(it->second.str(), "yes") == 0;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini SkinnedShadowMinTriangles: a skinned model that the retail data
// gives a decal shadow switches to the skinned shadow from this many caster triangles (default 2000, so retail
// infantry keep their decals). Models with a shadow volume type always switch.
Int OptionPreferences::getSkinnedShadowMinTriangles() const
{
	OptionPreferences::const_iterator it = find("SkinnedShadowMinTriangles");
	if (it == end())
		return 2000;

	const Int value = atoi(it->second.str());
	return value > 0 ? value : 0;
}

// GeneralsX @feature Claude 15/10/2026 Folder for bug report screenshots and videos. Options.ini CapturePath
// overrides the default, D:\GeneralsX\bugs on Windows. Elsewhere there is no default and the capture code
// uses a bugs folder in the user data folder.
AsciiString OptionPreferences::getCapturePath() const
{
	OptionPreferences::const_iterator it = find("CapturePath");
	if (it != end())
	{
		AsciiString path = it->second;
		path.trim();
		if (!path.isEmpty())
			return path;
	}
#ifdef _WIN32
	return AsciiString("D:\\GeneralsX\\bugs");
#else
	return AsciiString::TheEmptyString;
#endif
}

// GeneralsX @feature Claude 14/10/2026 Game resolution for a render scale: the display size scaled by
// scale percent, rounded down to even numbers, keeping the display aspect ratio and at least 600 lines.
Bool OptionPreferences::getRenderScaleResolution(Int scale, Int displayWidth, Int displayHeight, Int *xres, Int *yres)
{
	if (scale <= 0 || scale >= RENDER_SCALE_OFF || displayWidth <= 0 || displayHeight <= 0)
		return FALSE;

	Int height = displayHeight * scale / 100;
	if (height < RENDER_SCALE_MIN_HEIGHT)
		height = RENDER_SCALE_MIN_HEIGHT;
	Int width = displayWidth * height / displayHeight;

	width &= ~1;
	height &= ~1;
	if (width >= displayWidth || height >= displayHeight)
		return FALSE;

	*xres = width;
	*yres = height;
	return TRUE;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini DynamicLights: short coloured lights from explosions, burning
// buildings and vehicles, muzzle flashes, missile exhausts and superweapons on the ground, units and buildings.
// Off: only the lights the game data asks for (retail). Low: explosion, muzzle flash and superweapon lights, lit on
// the terrain vertices like retail lights. High (default): also fires and missile exhausts, more lights at once and
// a smooth light pool on the ground.
Int OptionPreferences::getDynamicLightsMode() const
{
	OptionPreferences::const_iterator it = find("DynamicLights");
	if (it == end())
		return DYNAMIC_LIGHTS_HIGH;

	if (stricmp(it->second.str(), "Off") == 0 || stricmp(it->second.str(), "no") == 0)
		return DYNAMIC_LIGHTS_OFF;
	if (stricmp(it->second.str(), "Low") == 0)
		return DYNAMIC_LIGHTS_LOW;
	return DYNAMIC_LIGHTS_HIGH;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini DynamicLightIntensity, 0 to 2 (default 1): brightness of the
// effect lights. 0 leaves only the retail lights.
Real OptionPreferences::getDynamicLightIntensity() const
{
	OptionPreferences::const_iterator it = find("DynamicLightIntensity");
	if (it == end())
		return 1.0f;

	return clamp(0.0f, (Real)atof(it->second.str()), 2.0f);
}

// GeneralsX @feature Claude 16/10/2026 Options.ini WaterReflections: Off keeps the retail water, Sky reflects the
// sky only, Full (the default) also reflects the terrain, buildings, units and trees. Numbers 0 to 2 work too.
Int OptionPreferences::getWaterReflections() const
{
	OptionPreferences::const_iterator it = find("WaterReflections");
	if (it == end())
		return 2;

	const char *value = it->second.str();
	if (stricmp(value, "off") == 0 || stricmp(value, "no") == 0 || stricmp(value, "0") == 0)
		return 0;
	if (stricmp(value, "sky") == 0 || stricmp(value, "1") == 0)
		return 1;
	return 2;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini WaterReflectionScale: size of the water reflection texture as
// a fraction of the 3D view, 0.25 to 1, default 0.5.
Real OptionPreferences::getWaterReflectionScale() const
{
	OptionPreferences::const_iterator it = find("WaterReflectionScale");
	if (it == end())
		return 0.5f;

	const Real value = (Real)atof(it->second.str());
	return value > 0.0f ? clamp(0.25f, value, 1.0f) : 0.5f;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini ShoreFoam: foam band and soft shoreline from the water depth.
// On unless set to "no".
Bool OptionPreferences::getShoreFoamEnabled() const
{
	OptionPreferences::const_iterator it = find("ShoreFoam");
	if (it == end())
		return TRUE;

	return stricmp(it->second.str(), "no") != 0;
}

// GeneralsX @feature Claude 16/10/2026 Options.ini WaterWaves: animated wave distortion of the water reflection
// and foam. On unless set to "no".
Bool OptionPreferences::getWaterWavesEnabled() const
{
	OptionPreferences::const_iterator it = find("WaterWaves");
	if (it == end())
		return TRUE;

	return stricmp(it->second.str(), "no") != 0;
}
