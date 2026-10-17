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

// GeneralsX @feature Claude 16/10/2026 Effect lights: short-lived coloured point lights from explosions, muzzle
// flashes, flame bursts, superweapons (FXLists without a LightPulse, see GameClient/EffectLights.h) and continuous
// lights from burning objects and missile exhausts (running fire and exhaust particle systems).
//
// Every drawn frame the candidates are faded, culled against the camera, merged when close together and the
// strongest ones (the budget) are put on a fixed set of W3DDynamicLights owned by this class. Units, buildings and
// trees get them through their W3D light environment like any other scene light (the strongest point light per
// mesh in the fixed function slot next to the map's global lights). The ground gets them either from the retail
// terrain vertex lighting (DynamicLights = Low) or, at High, from a light splat pass: the terrain cells under each
// light drawn once more right after the scorch marks with a radial falloff texture and the blend
// dest * (1 + light / terrain light) per colour channel, which equals albedo * (sun and ambient + light). Lights
// that need more than doubling the ground (dark night maps) get two or three such passes. Rendering only: no game
// logic state, random numbers or CRCs.
//
// Options.ini: DynamicLights = Off | Low | High (default High), DynamicLightIntensity = 0..2 (default 1).
// Off leaves only the retail LightPulse lights.

#pragma once

#include "Lib/BaseType.h"
#include "WWMath/vector3.h"
#include "GameClient/EffectLights.h"

#include <map>

class CameraClass;
class LightEnvironmentClass;
class SphereClass;
class ParticleSystem;
class RTS3DScene;
class TextureClass;
class W3DDynamicLight;
class WorldHeightMap;
struct Coord3D;

class W3DEffectLights
{
public:
	W3DEffectLights();
	~W3DEffectLights();

	/// Reads Options.ini and creates the lights in the scene. Called once the 3D scene exists.
	void init(RTS3DScene *scene);
	/// Map change: forgets every light and reads the options again.
	void reset();
	/// Releases the lights and the falloff texture.
	void shutdown();

	/// An effect without a LightPulse went off at pos (FXList). objectRadius is the size of the object it
	/// happened to, 0 when unknown.
	void addEffect(const Coord3D *pos, const EffectLights::Profile &profile, Real objectRadius);

	/// Once per drawn frame before the scene: ages the pulses, collects fire and exhaust lights and puts the
	/// strongest on the scene lights.
	void update(CameraClass *camera);

	/// Light pools on the ground (DynamicLights = High). Called by the terrain right after the scorch marks.
	void drawTerrainSplats(WorldHeightMap &map);

	Int getMode() const { return m_mode; }

	// GeneralsX @bugfix Claude 17/10/2026 Night hulls washed out white next to hits and muzzle flashes.
	/// Adds the enabled dynamic lights of the scene (effect lights and retail LightPulse lights) that reach a model
	/// to its light environment. Their light at the model together stays below MAX_MODEL_DYNAMIC_LIGHT: when several
	/// flashes overlap on one model, all of them are scaled down for that model.
	static void addModelDynamicLights(LightEnvironmentClass &env, const SphereClass &bounds, RTS3DScene &scene);

private:
	enum
	{
		MAX_LIGHTS = 16,            ///< scene lights at High
		MAX_LIGHTS_LOW = 6,         ///< scene lights at Low
		MAX_PULSES = 96,            ///< effect pulses alive at once
		MAX_CANDIDATES = 256,       ///< lights considered per frame
		FALLOFF_TEXTURE_SIZE = 64
	};

	struct Pulse
	{
		Vector3 pos;
		Vector3 color;
		Real radius;
		Real intensity;
		Real age;
		Int kind;
		UnsignedInt seed;
		Bool active;
	};

	struct Candidate
	{
		Vector3 pos;
		Vector3 color;      ///< normalised colour
		Real radius;
		Real intensity;     ///< current strength, 1 = a typical explosion at its peak
		Real priority;
		Int kind;           ///< EffectLights::Kind, for the -perf summary
	};

	/// What the lights of this frame are, kept for the terrain splat pass.
	struct ActiveLight
	{
		Vector3 pos;
		Vector3 color;
		Real radius;
		Real intensity;
		Int kind;
	};

	// GeneralsX @bugfix Claude 16/10/2026 -perf summary of what the effect lights see and light, per kind.
	struct Stats
	{
		UnsignedInt frames;
		UnsignedInt litSum;
		UnsignedInt litMax;
		UnsignedInt candidateSum;
		UnsignedInt fxEvents[EffectLights::KIND_COUNT];     ///< addEffect calls from FXLists
		UnsignedInt bursts[EffectLights::KIND_COUNT];       ///< one-shot particle bursts turned into pulses
		UnsignedInt candidates[EffectLights::KIND_COUNT];   ///< candidates per kind, summed over the frames
		UnsignedInt lit[EffectLights::KIND_COUNT];          ///< lit lights per kind, summed over the frames
	};

	void resetStats();
	void logStats(UnsignedInt nowMs);
	void addPulse(const Coord3D *pos, const EffectLights::Profile &profile, Real objectRadius);
	void createLights();
	void releaseLights();
	void readOptions();
	void disableAll();
	void ensureFalloffTexture();

	Real pulseEnvelope(const Pulse &pulse, Real *radiusScale) const;
	void collectParticleLights(CameraClass *camera, Real timeSeconds);
	void addCandidate(const Vector3 &pos, const Vector3 &color, Real radius, Real intensity, Int kind, CameraClass *camera);
	const EffectLights::Profile &particleProfile(ParticleSystem *system);
	Vector3 kindColor(Int kind, Int tint) const;
	void computeTerrainLight();
	UnsignedInt countRetailLights() const;

	RTS3DScene *m_scene;
	W3DDynamicLight *m_lights[MAX_LIGHTS];
	Int m_numLights;
	Int m_mode;                 ///< OptionPreferences::DynamicLightsMode
	Real m_userIntensity;       ///< Options.ini DynamicLightIntensity
	Bool m_loggedFirstLight;

	Pulse m_pulses[MAX_PULSES];
	Candidate m_candidates[MAX_CANDIDATES];
	Int m_numCandidates;
	ActiveLight m_active[MAX_LIGHTS];
	Int m_numActive;

	Real m_timeSeconds;         ///< effect light clock, stands still while the game is paused
	UnsignedInt m_lastUpdateMs;
	Real m_terrainLight;        ///< luminance of the sun and ambient light on flat ground (0.2 .. 1)
	Vector3 m_terrainLightColor; ///< the same per colour channel (0.15 .. 1)
	Real m_objectScale;         ///< weaker lights in daylight, full at night

	TextureClass *m_falloffTexture;

	/// Particle system templates already classified (fire, exhaust or nothing).
	std::map<const void *, EffectLights::Profile> m_particleProfiles;
	/// Highest particle system id already checked for a one-shot burst light.
	Int m_burstWatermark;
	Stats m_stats;
	UnsignedInt m_statsStartMs;
};

extern W3DEffectLights *TheW3DEffectLights;
