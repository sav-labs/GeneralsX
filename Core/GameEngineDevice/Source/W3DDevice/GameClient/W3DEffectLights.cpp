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

// GeneralsX @feature Claude 16/10/2026 Effect lights (see W3DEffectLights.h).

#include "WWLib/always.h"
#include "W3DDevice/GameClient/W3DEffectLights.h"

#include <algorithm>
#include <stdio.h>
#include <string.h>

#include "Common/GameUtility.h"
#include "Common/GlobalData.h"
#include "Common/MapObject.h"
#include "Common/OptionPreferences.h"
#include "Common/PerfStats.h"
#include "Common/Player.h"
#include "GameClient/Drawable.h"
#include "GameClient/GameClient.h"
#include "GameClient/ParticleSys.h"
#include "GameLogic/GameLogic.h"
#include "GameLogic/PartitionManager.h"
#include "WW3D2/camera.h"
#include "WW3D2/dx8indexbuffer.h"
#include "WW3D2/dx8vertexbuffer.h"
#include "WW3D2/dx8wrapper.h"
#include "WW3D2/lightenvironment.h"
#include "WW3D2/robjlist.h"
#include "WW3D2/texture.h"
#include "WW3D2/vertmaterial.h"
#include "WWMath/sphere.h"
#include "WWMath/wwmath.h"
#include "W3DDevice/GameClient/W3DDynamicLight.h"
#include "W3DDevice/GameClient/W3DScene.h"
#include "W3DDevice/GameClient/WorldHeightMap.h"

W3DEffectLights *TheW3DEffectLights = nullptr;

namespace
{
	/// Look of each kind of light. Radii in world units (a tank is about 30 across), times in seconds.
	struct KindLook
	{
		Real radius;
		Real intensity;
		Real attack;      ///< rise time
		Real hold;        ///< time at full strength
		Real decay;       ///< fade time
		Real red, green, blue;
		Real flicker;     ///< 0 = steady
		Real priority;    ///< weight when the budget is full
		Bool onLow;       ///< also at DynamicLights = Low
	};

	const KindLook s_kinds[EffectLights::KIND_COUNT] =
	{
		//  radius intens attack hold   decay  red   green blue  flick prio  low
		{   0.0f, 0.00f, 0.00f, 0.00f, 0.00f, 1.0f, 1.00f, 1.00f, 0.00f, 0.0f, FALSE }, // KIND_NONE
		// GeneralsX @bugfix Claude 16/10/2026 Smaller and dimmer than before: with every explosion now lit, the old
		// radii (up to 480) and strengths (up to 1.9) washed whole night scenes yellow. Local pools of light.
		{  28.0f, 0.70f, 0.00f, 0.03f, 0.10f, 1.0f, 0.78f, 0.46f, 0.00f, 0.6f, TRUE  }, // KIND_MUZZLE
		{  50.0f, 0.85f, 0.02f, 0.04f, 0.35f, 1.0f, 0.62f, 0.30f, 0.00f, 1.0f, TRUE  }, // KIND_IMPACT
		{  85.0f, 1.00f, 0.03f, 0.08f, 0.70f, 1.0f, 0.56f, 0.24f, 0.08f, 1.6f, TRUE  }, // KIND_EXPLOSION
		{ 135.0f, 1.10f, 0.05f, 0.15f, 1.20f, 1.0f, 0.52f, 0.22f, 0.10f, 2.2f, TRUE  }, // KIND_LARGE_EXPLOSION
		{ 180.0f, 1.25f, 0.15f, 0.60f, 3.00f, 1.0f, 0.80f, 0.60f, 0.05f, 4.0f, TRUE  }, // KIND_SUPERWEAPON
		{  65.0f, 0.85f, 0.05f, 0.15f, 0.45f, 1.0f, 0.55f, 0.20f, 0.30f, 1.0f, TRUE  }, // KIND_FLAME
		{  60.0f, 0.75f, 0.00f, 0.00f, 0.00f, 1.0f, 0.50f, 0.18f, 0.22f, 0.9f, FALSE }, // KIND_FIRE
		{  38.0f, 0.65f, 0.00f, 0.00f, 0.00f, 1.0f, 0.70f, 0.40f, 0.10f, 0.7f, FALSE }, // KIND_EXHAUST
	};

	const Real s_tints[EffectLights::TINT_COUNT][3] =
	{
		{ 1.00f, 1.00f, 1.00f }, // TINT_DEFAULT (unused, the kind colour)
		{ 0.45f, 1.00f, 0.25f }, // TINT_TOXIC
		{ 0.50f, 0.68f, 1.00f }, // TINT_ELECTRIC
		{ 1.00f, 0.22f, 0.22f }, // TINT_LASER
		{ 0.85f, 0.55f, 1.00f }, // TINT_PLASMA
		{ 1.00f, 0.88f, 0.70f }, // TINT_NUCLEAR
	};

	const char *const s_modeNames[] = { "Off", "Low", "High" };

	// GeneralsX @bugfix Claude 16/10/2026 Brightness caps against night over-exposure.
	/// One light (also after merging) stops here: brighter than this only saturates.
	const Real MAX_INTENSITY = 1.3f;
	/// All lights of a frame together: above this every light is scaled down, so a big battle cannot tint the screen.
	const Real MAX_TOTAL_INTENSITY = 4.0f;
	/// Light a model gets from one effect light at its centre (diffuse, after the day/night scale).
	const Real MAX_OBJECT_LIGHT = 1.0f;
	/// Share of an effect light that lights a whole nearby model evenly (WW3D folds a point light's ambient into
	/// the model's ambient): small, or night buildings turn uniformly yellow.
	const Real AMBIENT_FRACTION = 0.12f;
	// GeneralsX @bugfix Claude 17/10/2026 Several flashes at one burning tank each lit the hull up to MAX_OBJECT_LIGHT
	// and the fixed function lighting adds them up, so night hulls went flat white (fx-night15, fx-night17).
	/// Light all dynamic lights together give one model at most (brightest channel, at the model's nearest point).
	const Real MAX_MODEL_DYNAMIC_LIGHT = 0.6f;
	/// Dynamic lights considered per model.
	const Int MAX_MODEL_DYNAMIC_LIGHTS = 32;
	/// Ground light a splat adds at its centre, absolute, per channel.
	const Real MAX_SPLAT_ADD = 0.3f;
	/// The ground is brightened at most 1 + this many times at a splat's centre.
	// GeneralsX @bugfix Claude 17/10/2026 Overlapping splats multiply the ground, so ten lights of a night battle at
	// 1 + 2 each washed the frame out white (fx-night5). Smaller per splat, and only the strongest splats draw.
	const Real MAX_SPLAT_RATIO = 0.75f;
	/// Ground splats per frame at most, the strongest lights first.
	const Int MAX_SPLATS = 4;
	/// Largest light radius after size and object scaling, world units (a tank is about 30 across).
	const Real MAX_RADIUS = 200.0f;
	/// Lights closer than this fraction of the larger radius become one light.
	const Real MERGE_FRACTION = 0.5f;
	/// Splat geometry floats this far above the terrain so it wins the depth test against it and the roads.
	const Real SPLAT_FLOAT = 1.0f;
	/// Blend passes of one splat at most (ground brightened up to 2^3 = 8 times on the darkest maps).
	const Int MAX_SPLAT_PASSES = 3;
	/// Splat vertices across one light at most (bigger lights skip terrain vertices).
	const Int SPLAT_MAX_SPAN = 64;
	/// Per draw call limits of the dynamic buffers.
	const Int SPLAT_CHUNK_VERTICES = 16000;
	const Int SPLAT_CHUNK_INDICES = 60000;

	Real clampReal(Real v, Real lo, Real hi)
	{
		return v < lo ? lo : (v > hi ? hi : v);
	}

	/// Cheap smooth flicker in -1..1, different for each seed. Uses the effect light clock only.
	Real flickerNoise(Real t, UnsignedInt seed)
	{
		const Real phase = (Real)(seed % 997) * 0.731f;
		return 0.5f * WWMath::Sin(t * 13.0f + phase) + 0.3f * WWMath::Sin(t * 23.7f + phase * 1.9f)
			+ 0.2f * WWMath::Sin(t * 41.3f + phase * 3.1f);
	}

	/// Radial falloff of the ground light, x = distance / radius: bright core, inverse square like tail, 0 at the
	/// radius.
	// GeneralsX @bugfix Claude 16/10/2026 Steeper (1 + 8 x^2 instead of 1 + 3 x^2): a pool, not a wash.
	Real splatFalloff(Real x)
	{
		if (x >= 1.0f)
			return 0.0f;
		const Real x2 = x * x;
		const Real window = 1.0f - x2 * x2;
		return window * window / (1.0f + 8.0f * x2);
	}
}

W3DEffectLights::W3DEffectLights() :
	m_scene(nullptr),
	m_numLights(0),
	m_mode(OptionPreferences::DYNAMIC_LIGHTS_OFF),
	m_userIntensity(1.0f),
	m_loggedFirstLight(FALSE),
	m_numCandidates(0),
	m_numActive(0),
	m_timeSeconds(0.0f),
	m_lastUpdateMs(0),
	m_terrainLight(1.0f),
	m_terrainLightColor(1.0f, 1.0f, 1.0f),
	m_objectScale(1.0f),
	m_falloffTexture(nullptr),
	m_burstWatermark(0),
	m_statsStartMs(0)
{
	resetStats();
	for (Int i = 0; i < MAX_LIGHTS; ++i)
		m_lights[i] = nullptr;
	for (Int i = 0; i < MAX_PULSES; ++i)
		m_pulses[i].active = FALSE;
}

W3DEffectLights::~W3DEffectLights()
{
	shutdown();
}

void W3DEffectLights::readOptions()
{
	OptionPreferences prefs;
	m_mode = prefs.getDynamicLightsMode();
	m_userIntensity = prefs.getDynamicLightIntensity();
	if (m_userIntensity <= 0.0f)
		m_mode = OptionPreferences::DYNAMIC_LIGHTS_OFF;
	m_numLights = m_mode == OptionPreferences::DYNAMIC_LIGHTS_HIGH ? MAX_LIGHTS
		: (m_mode == OptionPreferences::DYNAMIC_LIGHTS_LOW ? MAX_LIGHTS_LOW : 0);

	fprintf(stderr, "[LIGHTS] effect lights: DynamicLights=%s DynamicLightIntensity=%.2f lights=%d ground=%s\n",
		s_modeNames[clamp(0, m_mode, 2)], m_userIntensity, m_numLights,
		m_mode == OptionPreferences::DYNAMIC_LIGHTS_HIGH ? "splat" : (m_numLights ? "vertices" : "off"));
	fflush(stderr);
}

void W3DEffectLights::init(RTS3DScene *scene)
{
	m_scene = scene;
	readOptions();
	createLights();
}

void W3DEffectLights::createLights()
{
	if (!m_scene)
		return;
	const Bool splat = m_mode == OptionPreferences::DYNAMIC_LIGHTS_HIGH;
	for (Int i = 0; i < MAX_LIGHTS; ++i)
	{
		if (!m_lights[i])
		{
			m_lights[i] = NEW_REF(W3DDynamicLight, ());
			m_scene->addDynamicLight(m_lights[i]);
		}
		m_lights[i]->setManaged(TRUE, splat);
		m_lights[i]->setEnabled(false);
	}
}

void W3DEffectLights::releaseLights()
{
	for (Int i = 0; i < MAX_LIGHTS; ++i)
	{
		if (m_lights[i])
		{
			if (m_scene)
				m_scene->removeDynamicLight(m_lights[i]);
			REF_PTR_RELEASE(m_lights[i]);
		}
	}
}

void W3DEffectLights::shutdown()
{
	releaseLights();
	REF_PTR_RELEASE(m_falloffTexture);
	m_particleProfiles.clear();
	m_scene = nullptr;
}

void W3DEffectLights::disableAll()
{
	for (Int i = 0; i < MAX_LIGHTS; ++i)
	{
		if (m_lights[i])
			m_lights[i]->setEnabled(false);
	}
	m_numActive = 0;
}

void W3DEffectLights::reset()
{
	for (Int i = 0; i < MAX_PULSES; ++i)
		m_pulses[i].active = FALSE;
	m_particleProfiles.clear();
	m_burstWatermark = 0;
	m_numCandidates = 0;
	resetStats();
	m_statsStartMs = 0;
	disableAll();
	readOptions();
	createLights();
}

Vector3 W3DEffectLights::kindColor(Int kind, Int tint) const
{
	if (tint > EffectLights::TINT_DEFAULT && tint < EffectLights::TINT_COUNT)
		return Vector3(s_tints[tint][0], s_tints[tint][1], s_tints[tint][2]);
	const KindLook &look = s_kinds[kind];
	return Vector3(look.red, look.green, look.blue);
}

void W3DEffectLights::addEffect(const Coord3D *pos, const EffectLights::Profile &profile, Real objectRadius)
{
	if (m_numLights == 0 || !pos || profile.kind <= EffectLights::KIND_NONE || profile.kind >= EffectLights::KIND_COUNT)
		return;
	++m_stats.fxEvents[profile.kind];
	addPulse(pos, profile, objectRadius);
}

void W3DEffectLights::addPulse(const Coord3D *pos, const EffectLights::Profile &profile, Real objectRadius)
{
	const KindLook &look = s_kinds[profile.kind];
	if (look.decay <= 0.0f)
		return;	// continuous kinds come from particle systems
	if (m_mode == OptionPreferences::DYNAMIC_LIGHTS_LOW && !look.onLow)
		return;

	Real radius = look.radius * profile.sizeScale;
	if (objectRadius > 0.0f && profile.kind >= EffectLights::KIND_IMPACT && profile.kind <= EffectLights::KIND_LARGE_EXPLOSION)
		radius = clampReal(objectRadius * 2.0f, radius, look.radius * 1.6f);
	radius = clampReal(radius, 5.0f, MAX_RADIUS);

	Vector3 color = profile.hasColor ? Vector3(profile.red, profile.green, profile.blue) : kindColor(profile.kind, profile.tint);
	const Vector3 where(pos->x, pos->y, pos->z);

	// The same gun or the same blast again while the last light is still bright: keep one light and make it a
	// little stronger instead of stacking pulses (machine guns, artillery salvos, flame throwers).
	Int freeSlot = -1;
	Int weakestSlot = 0;
	Real weakestEnergy = 1.0e9f;
	for (Int i = 0; i < MAX_PULSES; ++i)
	{
		Pulse &pulse = m_pulses[i];
		if (!pulse.active)
		{
			if (freeSlot < 0)
				freeSlot = i;
			continue;
		}
		const KindLook &other = s_kinds[pulse.kind];
		// GeneralsX @bugfix Claude 16/10/2026 Also across kinds: an FXList and the particle burst it spawned (or
		// a muzzle flash and the shell hit next to it) are one light, the bigger of the two.
		const Real limit = 0.35f * (pulse.radius > radius ? pulse.radius : radius);
		if ((pulse.pos - where).Length2() < limit * limit && pulse.age < other.attack + other.hold + 0.5f * other.decay)
		{
			if (pulse.kind == profile.kind)
			{
				pulse.intensity = clampReal(pulse.intensity * 1.15f, 0.0f, look.intensity * 1.25f);
				if (pulse.age > other.attack)
					pulse.age = other.attack;
			}
			else if (look.radius * look.intensity > other.radius * other.intensity)
			{
				pulse.kind = profile.kind;
				pulse.color = color;
				pulse.intensity = look.intensity > pulse.intensity ? look.intensity : pulse.intensity;
				pulse.age = 0.0f;
			}
			if (radius > pulse.radius)
				pulse.radius = radius;
			return;
		}
		const Real energy = pulse.intensity * pulse.radius * (1.0f - pulse.age / (other.attack + other.hold + other.decay));
		if (energy < weakestEnergy)
		{
			weakestEnergy = energy;
			weakestSlot = i;
		}
	}

	const Int slot = freeSlot >= 0 ? freeSlot : weakestSlot;
	if (freeSlot < 0 && weakestEnergy > look.intensity * radius)
		return;	// everything alive is stronger than this one

	Pulse &pulse = m_pulses[slot];
	pulse.pos = where;
	pulse.color = color;
	pulse.radius = radius;
	pulse.intensity = look.intensity;
	pulse.age = 0.0f;
	pulse.kind = profile.kind;
	pulse.seed = (UnsignedInt)(slot * 7919) ^ (UnsignedInt)(Int)(pos->x * 13.0f + pos->y * 7.0f);
	pulse.active = TRUE;
}

Real W3DEffectLights::pulseEnvelope(const Pulse &pulse, Real *radiusScale) const
{
	const KindLook &look = s_kinds[pulse.kind];
	Real envelope;
	if (pulse.age < look.attack)
	{
		envelope = pulse.age / look.attack;
	}
	else if (pulse.age < look.attack + look.hold)
	{
		envelope = 1.0f;
	}
	else
	{
		const Real t = (pulse.age - look.attack - look.hold) / look.decay;
		if (t >= 1.0f)
			return 0.0f;
		envelope = (1.0f - t) * (1.0f - t);
	}
	// blasts grow a little while they burn out
	*radiusScale = 0.8f + 0.2f * clampReal(pulse.age / (look.attack + look.hold + 0.3f * look.decay), 0.0f, 1.0f);
	return envelope;
}

void W3DEffectLights::computeTerrainLight()
{
	// What the terrain vertex lighting gives flat ground: ambient of the first light plus each global light's
	// diffuse times its angle to the ground (BaseHeightMapRenderObjClass::doTheLight).
	Vector3 light(TheGlobalData->m_terrainAmbient[0].red, TheGlobalData->m_terrainAmbient[0].green,
		TheGlobalData->m_terrainAmbient[0].blue);
	for (Int i = 0; i < TheGlobalData->m_numGlobalLights && i < MAX_GLOBAL_LIGHTS; ++i)
	{
		Vector3 dir(TheGlobalData->m_terrainLightPos[i].x, TheGlobalData->m_terrainLightPos[i].y,
			TheGlobalData->m_terrainLightPos[i].z);
		const Real len = dir.Length();
		if (len <= 1.0e-4f)
			continue;
		const Real up = -dir.Z / len;
		if (up <= 0.0f)
			continue;
		light.X += TheGlobalData->m_terrainDiffuse[i].red * up;
		light.Y += TheGlobalData->m_terrainDiffuse[i].green * up;
		light.Z += TheGlobalData->m_terrainDiffuse[i].blue * up;
	}
	const Real lum = 0.30f * light.X + 0.59f * light.Y + 0.11f * light.Z;
	m_terrainLight = clampReal(lum, 0.2f, 1.0f);
	// per channel, so a blue moonlit map still gets an orange fire pool and not a blue one
	m_terrainLightColor.Set(clampReal(light.X, 0.15f, 1.0f), clampReal(light.Y, 0.15f, 1.0f), clampReal(light.Z, 0.15f, 1.0f));
}

UnsignedInt W3DEffectLights::countRetailLights() const
{
	if (!m_scene)
		return 0;
	UnsignedInt count = 0;
	RefRenderObjListIterator it(m_scene->getDynamicLights());
	for (it.First(); !it.Is_Done(); it.Next())
	{
		W3DDynamicLight *light = (W3DDynamicLight *)it.Peek_Obj();
		if (!light->isManaged() && light->isEnabled())
			++count;
	}
	return count;
}

void W3DEffectLights::addCandidate(const Vector3 &pos, const Vector3 &color, Real radius, Real intensity, Int kind,
	CameraClass *camera)
{
	if (intensity < 0.03f || radius < 5.0f || m_numCandidates >= MAX_CANDIDATES)
		return;
	if (camera && camera->Cull_Sphere(SphereClass(pos, radius)))
		return;
	Candidate &c = m_candidates[m_numCandidates++];
	c.pos = pos;
	c.color = color;
	c.radius = radius;
	c.intensity = intensity;
	c.priority = intensity * radius * s_kinds[kind].priority;
	c.kind = kind;
	++m_stats.candidates[kind];
}

const EffectLights::Profile &W3DEffectLights::particleProfile(ParticleSystem *system)
{
	const ParticleSystemTemplate *tmpl = system->getTemplate();
	std::map<const void *, EffectLights::Profile>::iterator found = m_particleProfiles.find(tmpl);
	if (found == m_particleProfiles.end())
	{
		found = m_particleProfiles.insert(std::make_pair((const void *)tmpl, EffectLights::classifyParticleSystem(system))).first;
		// GeneralsX @bugfix Claude 16/10/2026 With -perf, name the particle systems that give off light.
		static Int s_logged = 0;
		if (PerfStats::isEnabled() && found->second.kind != EffectLights::KIND_NONE && s_logged < 200)
		{
			++s_logged;
			fprintf(stderr, "[LIGHTS] particles %s -> %s%s size %.2f\n", tmpl->getName().str(),
				EffectLights::kindName(found->second.kind), system->m_isOneShot ? " (burst)" : "", found->second.sizeScale);
			fflush(stderr);
		}
	}
	return found->second;
}

void W3DEffectLights::resetStats()
{
	memset(&m_stats, 0, sizeof(m_stats));
}

void W3DEffectLights::logStats(UnsignedInt nowMs)
{
	if (m_statsStartMs == 0)
	{
		m_statsStartMs = nowMs;
		resetStats();
		return;
	}
	const UnsignedInt elapsed = nowMs - m_statsStartMs;
	if (elapsed < 5000 || m_stats.frames == 0)
		return;
	const double frames = (double)m_stats.frames;
	char fx[256], bursts[256], cands[256], lit[256];
	Int nfx = 0, nb = 0, nc = 0, nl = 0;
	fx[0] = bursts[0] = cands[0] = lit[0] = 0;
	for (Int k = EffectLights::KIND_MUZZLE; k < EffectLights::KIND_COUNT; ++k)
	{
		const char *name = EffectLights::kindName(k);
		if (m_stats.fxEvents[k])
			nfx += snprintf(fx + nfx, sizeof(fx) - nfx, " %s=%u", name, m_stats.fxEvents[k]);
		if (m_stats.bursts[k])
			nb += snprintf(bursts + nb, sizeof(bursts) - nb, " %s=%u", name, m_stats.bursts[k]);
		if (m_stats.candidates[k])
			nc += snprintf(cands + nc, sizeof(cands) - nc, " %s=%.1f", name, m_stats.candidates[k] / frames);
		if (m_stats.lit[k])
			nl += snprintf(lit + nl, sizeof(lit) - nl, " %s=%.1f", name, m_stats.lit[k] / frames);
		if (nfx >= (Int)sizeof(fx)) nfx = (Int)sizeof(fx) - 1;
		if (nb >= (Int)sizeof(bursts)) nb = (Int)sizeof(bursts) - 1;
		if (nc >= (Int)sizeof(cands)) nc = (Int)sizeof(cands) - 1;
		if (nl >= (Int)sizeof(lit)) nl = (Int)sizeof(lit) - 1;
	}
	fprintf(stderr, "[LIGHTS] %.1fs frames=%u lit avg=%.1f max=%u candidates avg=%.1f | fx events:%s | particle bursts:%s"
		" | candidates/frame:%s | lit/frame:%s\n",
		elapsed * 0.001, m_stats.frames, m_stats.litSum / frames, m_stats.litMax, m_stats.candidateSum / frames,
		nfx ? fx : " none", nb ? bursts : " none", nc ? cands : " none", nl ? lit : " none");
	fflush(stderr);
	m_statsStartMs = nowMs;
	resetStats();
}

void W3DEffectLights::collectParticleLights(CameraClass *camera, Real timeSeconds)
{
	if (!TheParticleSystemManager || !TheGameClient)
		return;
	Player *player = rts::getObservedOrLocalPlayer_Safe();
	const Int playerIndex = player ? player->getPlayerIndex() : -1;

	ParticleSystemManager::ParticleSystemList &systems = TheParticleSystemManager->getAllParticleSystems();
	Int newWatermark = m_burstWatermark;
	for (ParticleSystemManager::ParticleSystemListIt it = systems.begin(); it != systems.end(); ++it)
	{
		ParticleSystem *system = *it;
		if (!system || !system->getTemplate())
			continue;
		const UnsignedInt count = system->getParticleCount();
		if (count == 0)
			continue;
		// GeneralsX @bugfix Claude 16/10/2026 Slave systems used to be skipped outright, which lost every fire that
		// is the slave of a smoke master. A slave counts when its master gives off no light; it sits where the
		// master is.
		ParticleSystem *anchor = system->getMaster() ? system->getMaster() : system;
		if (anchor != system && (!anchor->getTemplate() || particleProfile(anchor).kind != EffectLights::KIND_NONE))
			continue;
		const EffectLights::Profile &profile = particleProfile(system);
		const Bool burst = profile.kind == EffectLights::KIND_MUZZLE || profile.kind == EffectLights::KIND_IMPACT
			|| profile.kind == EffectLights::KIND_EXPLOSION;
		if (!burst && profile.kind != EffectLights::KIND_FIRE && profile.kind != EffectLights::KIND_EXHAUST)
			continue;
		// GeneralsX @bugfix Claude 16/10/2026 A one-shot burst lights once, when it is first seen with particles
		// (explosions of death modules and object creation lists do not always go through an FXList).
		const Int systemID = (Int)system->getSystemID();
		if (burst)
		{
			if (systemID <= m_burstWatermark)
				continue;
			if (systemID > newWatermark)
				newWatermark = systemID;
		}
		Coord3D pos;
		anchor->getWorldPosition(&pos);
		const DrawableID drawableID = anchor->getAttachedDrawable();
		if (drawableID != INVALID_DRAWABLE_ID)
		{
			Drawable *draw = TheGameClient->findDrawableByID(drawableID);
			if (!draw || draw->getFullyObscuredByShroud() || draw->isDrawableEffectivelyHidden())
				continue;
		}
		else if (ThePartitionManager && playerIndex >= 0
			&& ThePartitionManager->getShroudStatusForPlayer(playerIndex, &pos) != CELLSHROUD_CLEAR)
		{
			continue;
		}

		if (burst)
		{
			++m_stats.bursts[profile.kind];
			addPulse(&pos, profile, 0.0f);
			continue;
		}
		const KindLook &look = s_kinds[profile.kind];
		const Real radius = look.radius * profile.sizeScale;
		// fade in with the first particles and out with the last ones
		const Real fullCount = profile.kind == EffectLights::KIND_EXHAUST ? 3.0f : 6.0f;
		Real intensity = look.intensity * clampReal((Real)count / fullCount, 0.0f, 1.0f);
		intensity *= 1.0f + look.flicker * flickerNoise(timeSeconds, (UnsignedInt)system->getSystemID());

		Vector3 color = profile.hasColor
			? Vector3(0.5f * (profile.red + look.red), 0.5f * (profile.green + look.green), 0.5f * (profile.blue + look.blue))
			: kindColor(profile.kind, profile.tint);
		addCandidate(Vector3(pos.x, pos.y, pos.z + 0.15f * radius), color, radius, intensity, profile.kind, camera);
	}
	m_burstWatermark = newWatermark;
}

void W3DEffectLights::update(CameraClass *camera)
{
	if (m_numLights == 0 || !m_scene || !TheGlobalData)
	{
		if (PerfStats::isEnabled())
			PerfStats::setEffectLights(0, countRetailLights(), 0);
		return;
	}
	PERF_STATS_SCOPE(SECTION_EFFECT_LIGHTS);

	// clock: real time, standing still while the game is paused
	const UnsignedInt nowMs = (UnsignedInt)PerfStats::nowMs();
	Real dt = m_lastUpdateMs ? (Real)(nowMs - m_lastUpdateMs) * 0.001f : 0.0f;
	m_lastUpdateMs = nowMs;
	if (dt > 0.1f)
		dt = 0.1f;
	if (TheGameLogic && TheGameLogic->isGamePaused())
		dt = 0.0f;
	m_timeSeconds += dt;
	if (m_timeSeconds > 100000.0f)
		m_timeSeconds -= 100000.0f;

	computeTerrainLight();
	// full strength at night, about half in bright daylight where the sun already saturates most surfaces
	m_objectScale = clampReal(1.35f - 0.8f * m_terrainLight, 0.55f, 1.0f) * m_userIntensity;

	m_numCandidates = 0;
	for (Int i = 0; i < MAX_PULSES; ++i)
	{
		Pulse &pulse = m_pulses[i];
		if (!pulse.active)
			continue;
		pulse.age += dt;
		Real radiusScale = 1.0f;
		const Real envelope = pulseEnvelope(pulse, &radiusScale);
		if (envelope <= 0.0f)
		{
			pulse.active = FALSE;
			continue;
		}
		const KindLook &look = s_kinds[pulse.kind];
		Real intensity = pulse.intensity * envelope;
		if (look.flicker > 0.0f)
			intensity *= 1.0f + look.flicker * flickerNoise(m_timeSeconds, pulse.seed);
		const Real radius = pulse.radius * radiusScale;
		addCandidate(Vector3(pulse.pos.X, pulse.pos.Y, pulse.pos.Z + 0.15f * radius), pulse.color, radius, intensity,
			pulse.kind, camera);
	}

	if (m_mode == OptionPreferences::DYNAMIC_LIGHTS_HIGH)
		collectParticleLights(camera, m_timeSeconds);

	const UnsignedInt candidateCount = (UnsignedInt)m_numCandidates;

	// strongest first, then merge close ones into one light until the budget is used
	struct ByPriority
	{
		bool operator()(const Candidate &a, const Candidate &b) const { return a.priority > b.priority; }
	};
	std::sort(m_candidates, m_candidates + m_numCandidates, ByPriority());

	m_numActive = 0;
	for (Int c = 0; c < m_numCandidates; ++c)
	{
		const Candidate &cand = m_candidates[c];
		Bool merged = FALSE;
		for (Int a = 0; a < m_numActive; ++a)
		{
			ActiveLight &light = m_active[a];
			const Real larger = light.radius > cand.radius ? light.radius : cand.radius;
			const Real limit = MERGE_FRACTION * larger;
			const Real dist2 = (light.pos - cand.pos).Length2();
			if (dist2 < limit * limit)
			{
				const Real total = light.intensity + cand.intensity;
				light.color = (light.color * light.intensity + cand.color * cand.intensity) / total;
				light.intensity = clampReal(light.intensity + 0.25f * cand.intensity, 0.0f, MAX_INTENSITY);
				const Real reach = WWMath::Sqrt(dist2) + cand.radius;
				if (reach > light.radius)
					light.radius = reach < 1.15f * larger ? reach : 1.15f * larger;
				merged = TRUE;
				break;
			}
		}
		if (merged || m_numActive >= m_numLights)
			continue;
		ActiveLight &light = m_active[m_numActive++];
		light.pos = cand.pos;
		light.color = cand.color;
		light.radius = cand.radius;
		light.intensity = clampReal(cand.intensity, 0.0f, MAX_INTENSITY);
		light.kind = cand.kind;
	}

	// cap on the light of all effects together
	Real totalIntensity = 0.0f;
	for (Int a = 0; a < m_numActive; ++a)
		totalIntensity += m_active[a].intensity;
	if (totalIntensity > MAX_TOTAL_INTENSITY)
	{
		const Real scale = MAX_TOTAL_INTENSITY / totalIntensity;
		for (Int a = 0; a < m_numActive; ++a)
			m_active[a].intensity *= scale;
	}

	for (Int i = 0; i < MAX_LIGHTS; ++i)
	{
		W3DDynamicLight *light = m_lights[i];
		if (!light)
			continue;
		if (i >= m_numActive)
		{
			light->setEnabled(false);
			continue;
		}
		const ActiveLight &active = m_active[i];
		const Real objectLight = active.intensity * m_objectScale;
		const Vector3 diffuse = active.color * (objectLight < MAX_OBJECT_LIGHT ? objectLight : MAX_OBJECT_LIGHT);
		light->setEnabled(true);
		light->Set_Diffuse(diffuse);
		light->Set_Ambient(diffuse * AMBIENT_FRACTION);
		// range before position: moving the light refreshes its cached bounding sphere from the range
		light->Set_Flag(LightClass::FAR_ATTENUATION, true);
		light->Set_Far_Attenuation_Range(0.25f * active.radius, active.radius);
		light->Set_Position(active.pos);
	}

	if (!m_loggedFirstLight && m_numActive > 0)
	{
		m_loggedFirstLight = TRUE;
		fprintf(stderr, "[LIGHTS] first effect lights: %d lit from %u candidates, terrain light %.2f, object scale %.2f\n",
			m_numActive, candidateCount, m_terrainLight, m_objectScale);
		fflush(stderr);
	}

	if (PerfStats::isEnabled())
	{
		PerfStats::setEffectLights((UnsignedInt)m_numActive, countRetailLights(), candidateCount);
		++m_stats.frames;
		m_stats.litSum += (UnsignedInt)m_numActive;
		if ((UnsignedInt)m_numActive > m_stats.litMax)
			m_stats.litMax = (UnsignedInt)m_numActive;
		m_stats.candidateSum += candidateCount;
		for (Int a = 0; a < m_numActive; ++a)
			++m_stats.lit[m_active[a].kind];
		logStats(nowMs);
	}
}

void W3DEffectLights::ensureFalloffTexture()
{
	if (m_falloffTexture)
		return;
	m_falloffTexture = MSGNEW("TextureClass") TextureClass(FALLOFF_TEXTURE_SIZE, FALLOFF_TEXTURE_SIZE,
		WW3D_FORMAT_A8R8G8B8, MIP_LEVELS_1, TextureBaseClass::POOL_MANAGED, false, false);
	IDirect3DTexture8 *tex = m_falloffTexture->Peek_D3D_Texture();
	if (!tex)
	{
		REF_PTR_RELEASE(m_falloffTexture);
		return;
	}
	D3DLOCKED_RECT locked;
	if (SUCCEEDED(tex->LockRect(0, &locked, nullptr, 0)))
	{
		const Real half = 0.5f * (Real)FALLOFF_TEXTURE_SIZE;
		for (Int y = 0; y < FALLOFF_TEXTURE_SIZE; ++y)
		{
			UnsignedInt *dst = (UnsignedInt *)((UnsignedByte *)locked.pBits + y * locked.Pitch);
			for (Int x = 0; x < FALLOFF_TEXTURE_SIZE; ++x)
			{
				const Real dx = ((Real)x + 0.5f - half) / half;
				const Real dy = ((Real)y + 0.5f - half) / half;
				const Real f = splatFalloff(WWMath::Sqrt(dx * dx + dy * dy));
				const UnsignedInt v = (UnsignedInt)clampReal(f * 255.0f + 0.5f, 0.0f, 255.0f);
				dst[x] = 0xFF000000u | (v << 16) | (v << 8) | v;
			}
		}
		tex->UnlockRect(0);
	}
	m_falloffTexture->Get_Filter().Set_U_Addr_Mode(TextureFilterClass::TEXTURE_ADDRESS_CLAMP);
	m_falloffTexture->Get_Filter().Set_V_Addr_Mode(TextureFilterClass::TEXTURE_ADDRESS_CLAMP);
}

void W3DEffectLights::drawTerrainSplats(WorldHeightMap &map)
{
	if (m_mode != OptionPreferences::DYNAMIC_LIGHTS_HIGH || m_numActive == 0)
		return;
	PERF_STATS_SCOPE(SECTION_EFFECT_LIGHTS);
	ensureFalloffTexture();
	if (!m_falloffTexture)
		return;

	// Ground light of each splat relative to what the sun and ambient give the ground, per colour channel:
	// dest * (1 + L / V) = albedo * (V + L). One blend pass multiplies the ground by up to 2, so lights that need
	// more (dark night maps) get two or three passes of the n-th root; they are sorted first so each pass count
	// draws one leading index range of the chunk.
	struct Splat
	{
		Int light;
		Vector3 ratio;     ///< per pass factor at the centre
		Int passes;
	};
	Splat splats[MAX_LIGHTS];
	Int numSplats = 0;
	// the strongest lights get the splats
	Bool splatLight[MAX_LIGHTS];
	for (Int i = 0; i < MAX_LIGHTS; ++i)
		splatLight[i] = FALSE;
	for (Int n = 0; n < MAX_SPLATS && n < m_numActive; ++n)
	{
		Int best = -1;
		for (Int i = 0; i < m_numActive; ++i)
		{
			if (!splatLight[i] && (best < 0 || m_active[i].intensity > m_active[best].intensity))
				best = i;
		}
		splatLight[best] = TRUE;
	}
	const Real terrainScale = 1.0f * m_objectScale;
	for (Int wantPasses = MAX_SPLAT_PASSES; wantPasses >= 1; --wantPasses)
	{
		for (Int i = 0; i < m_numActive; ++i)
		{
			if (!splatLight[i])
				continue;
			const ActiveLight &light = m_active[i];
			const Real scale = light.intensity * terrainScale;
			// GeneralsX @bugfix Claude 16/10/2026 Absolute added light and ratio capped: dividing by the dark night
			// ground light used to brighten it up to 8 times over the whole radius.
			Vector3 ratio(
				clampReal(clampReal(light.color.X * scale, 0.0f, MAX_SPLAT_ADD) / m_terrainLightColor.X, 0.0f, MAX_SPLAT_RATIO),
				clampReal(clampReal(light.color.Y * scale, 0.0f, MAX_SPLAT_ADD) / m_terrainLightColor.Y, 0.0f, MAX_SPLAT_RATIO),
				clampReal(clampReal(light.color.Z * scale, 0.0f, MAX_SPLAT_ADD) / m_terrainLightColor.Z, 0.0f, MAX_SPLAT_RATIO));
			Real largest = ratio.X > ratio.Y ? ratio.X : ratio.Y;
			if (ratio.Z > largest)
				largest = ratio.Z;
			const Int passes = largest <= 1.0f ? 1 : (largest <= 3.0f ? 2 : 3);
			if (passes != wantPasses)
				continue;
			Splat &splat = splats[numSplats++];
			splat.light = i;
			splat.passes = passes;
			if (passes > 1)
			{
				const Real root = 1.0f / (Real)passes;
				ratio.X = WWMath::PowOrigin(1.0f + ratio.X, root) - 1.0f;
				ratio.Y = WWMath::PowOrigin(1.0f + ratio.Y, root) - 1.0f;
				ratio.Z = WWMath::PowOrigin(1.0f + ratio.Z, root) - 1.0f;
			}
			splat.ratio = ratio;
		}
	}

	const UnsignedByte *heights = map.getDataPtr();
	const Int border = map.getBorderSizeInline();
	const Int xExtent = map.getXExtent();
	const Int yExtent = map.getYExtent();
	if (!heights || xExtent < 2 || yExtent < 2)
		return;

	VertexMaterialClass *material = VertexMaterialClass::Get_Preset(VertexMaterialClass::PRELIT_DIFFUSE);
	ShaderClass shader = ShaderClass::_PresetAdditiveShader;
	shader.Set_Cull_Mode(ShaderClass::CULL_MODE_DISABLE);

	Int s = 0;
	while (s < numSplats)
	{
		DynamicVBAccessClass vbAccess(BUFFER_TYPE_DYNAMIC_DX8, DX8_FVF_XYZNDUV2, SPLAT_CHUNK_VERTICES);
		DynamicIBAccessClass ibAccess(BUFFER_TYPE_DYNAMIC_DX8, SPLAT_CHUNK_INDICES);
		Int vertexCount = 0;
		Int indexCount = 0;
		Int passIndexCount[MAX_SPLAT_PASSES + 1] = { 0, 0, 0, 0 };
		{
			DynamicVBAccessClass::WriteLockClass vbLock(&vbAccess);
			DynamicIBAccessClass::WriteLockClass ibLock(&ibAccess);
			VertexFormatXYZNDUV2 *vb = vbLock.Get_Formatted_Vertex_Array();
			UnsignedShort *ib = ibLock.Get_Index_Array();
			if (!vb || !ib)
				break;

			for (; s < numSplats; ++s)
			{
				const Splat &splat = splats[s];
				const ActiveLight &light = m_active[splat.light];
				const Real radius = light.radius;

				// terrain vertices under the light, in map coordinates without the border
				Int minX = (Int)WWMath::Floor((light.pos.X - radius) / MAP_XY_FACTOR);
				Int minY = (Int)WWMath::Floor((light.pos.Y - radius) / MAP_XY_FACTOR);
				Int maxX = (Int)WWMath::Ceil((light.pos.X + radius) / MAP_XY_FACTOR);
				Int maxY = (Int)WWMath::Ceil((light.pos.Y + radius) / MAP_XY_FACTOR);
				minX = clamp(-border, minX, xExtent - border - 1);
				maxX = clamp(-border, maxX, xExtent - border - 1);
				minY = clamp(-border, minY, yExtent - border - 1);
				maxY = clamp(-border, maxY, yExtent - border - 1);
				if (maxX <= minX || maxY <= minY)
					continue;
				Int span = maxX - minX;
				if (maxY - minY > span)
					span = maxY - minY;
				const Int step = (span + SPLAT_MAX_SPAN - 1) / SPLAT_MAX_SPAN;
				const Int countX = (maxX - minX) / step + 1;
				const Int countY = (maxY - minY) / step + 1;
				if (countX < 2 || countY < 2)
					continue;
				const Int needVertices = countX * countY;
				const Int needIndices = (countX - 1) * (countY - 1) * 6;
				if (vertexCount + needVertices > SPLAT_CHUNK_VERTICES || indexCount + needIndices > SPLAT_CHUNK_INDICES)
				{
					if (vertexCount == 0)
						continue;	// cannot happen with the span limit, but never loop forever
					break;	// next chunk
				}

				// a lifted light point so slopes facing it get more than slopes facing away
				const Vector3 lightPoint(light.pos.X, light.pos.Y, light.pos.Z + 0.35f * radius);
				const Real invDiameter = 1.0f / (2.0f * radius);
				const Real floatHeight = SPLAT_FLOAT * (Real)step;
				const Int first = vertexCount;
				for (Int j = 0; j < countY; ++j)
				{
					const Int my = minY + j * step;
					const Int dataY = clamp(0, my + border, yExtent - 1);
					const Int dataYm = clamp(0, dataY - 1, yExtent - 1);
					const Int dataYp = clamp(0, dataY + 1, yExtent - 1);
					for (Int i = 0; i < countX; ++i)
					{
						const Int mx = minX + i * step;
						const Int dataX = clamp(0, mx + border, xExtent - 1);
						const Int dataXm = clamp(0, dataX - 1, xExtent - 1);
						const Int dataXp = clamp(0, dataX + 1, xExtent - 1);
						const Real h = heights[dataX + dataY * xExtent] * MAP_HEIGHT_SCALE;
						Vector3 normal(
							(heights[dataXm + dataY * xExtent] - heights[dataXp + dataY * xExtent]) * MAP_HEIGHT_SCALE,
							(heights[dataX + dataYm * xExtent] - heights[dataX + dataYp * xExtent]) * MAP_HEIGHT_SCALE,
							2.0f * MAP_XY_FACTOR);
						normal.Normalize();
						const Real wx = (Real)mx * MAP_XY_FACTOR;
						const Real wy = (Real)my * MAP_XY_FACTOR;
						Vector3 toLight(lightPoint.X - wx, lightPoint.Y - wy, lightPoint.Z - h);
						toLight.Normalize();
						const Real facing = Vector3::Dot_Product(normal, toLight);
						const Real shade = 0.4f + 0.6f * (facing > 0.0f ? facing : 0.0f);

						VertexFormatXYZNDUV2 &v = vb[vertexCount++];
						v.x = wx;
						v.y = wy;
						v.z = h + floatHeight;
						v.nx = normal.X;
						v.ny = normal.Y;
						v.nz = normal.Z;
						v.diffuse = DX8Wrapper::Convert_Color_Clamp(Vector4(splat.ratio.X * shade, splat.ratio.Y * shade,
							splat.ratio.Z * shade, 1.0f));
						v.u1 = (wx - light.pos.X) * invDiameter + 0.5f;
						v.v1 = (wy - light.pos.Y) * invDiameter + 0.5f;
						v.u2 = 0.0f;
						v.v2 = 0.0f;
					}
				}
				for (Int j = 0; j < countY - 1; ++j)
				{
					for (Int i = 0; i < countX - 1; ++i)
					{
						const UnsignedShort v0 = (UnsignedShort)(first + j * countX + i);
						const UnsignedShort v1 = (UnsignedShort)(v0 + 1);
						const UnsignedShort v2 = (UnsignedShort)(v0 + countX + 1);
						const UnsignedShort v3 = (UnsignedShort)(v0 + countX);
						// same diagonal as the terrain cell under it (W3DScorch)
						const Int cellX = clamp(0, minX + i * step + border, xExtent - 1);
						const Int cellY = clamp(0, minY + j * step + border, yExtent - 1);
						if (map.getFlipState(cellX, cellY))
						{
							ib[indexCount++] = v1; ib[indexCount++] = v3; ib[indexCount++] = v0;
							ib[indexCount++] = v1; ib[indexCount++] = v2; ib[indexCount++] = v3;
						}
						else
						{
							ib[indexCount++] = v0; ib[indexCount++] = v2; ib[indexCount++] = v3;
							ib[indexCount++] = v0; ib[indexCount++] = v1; ib[indexCount++] = v2;
						}
					}
				}
				for (Int p = 1; p <= splat.passes; ++p)
					passIndexCount[p] = indexCount;
			}
		}

		if (indexCount == 0)
			continue;

		DX8Wrapper::Set_Transform(D3DTS_WORLD, Matrix3D(true));
		DX8Wrapper::Set_Index_Buffer(ibAccess, 0);
		DX8Wrapper::Set_Vertex_Buffer(vbAccess);
		DX8Wrapper::Set_Material(material);
		DX8Wrapper::Set_Shader(shader);
		DX8Wrapper::Set_Texture(0, m_falloffTexture);
		DX8Wrapper::Set_Texture(1, nullptr);
		DX8Wrapper::Apply_Render_State_Changes();
		// dest * (1 + light ratio): brightens the ground the way extra light would, keeps its texture and colour
		DX8Wrapper::Set_DX8_Render_State(D3DRS_SRCBLEND, D3DBLEND_DESTCOLOR);
		DX8Wrapper::Set_DX8_Render_State(D3DRS_DESTBLEND, D3DBLEND_ONE);
		DX8Wrapper::Set_DX8_Texture_Stage_State(1, D3DTSS_COLOROP, D3DTOP_DISABLE);
		DX8Wrapper::Set_DX8_Texture_Stage_State(1, D3DTSS_ALPHAOP, D3DTOP_DISABLE);
		for (Int p = 1; p <= MAX_SPLAT_PASSES; ++p)
		{
			if (passIndexCount[p] > 0)
				DX8Wrapper::Draw_Triangles(0, passIndexCount[p] / 3, 0, vertexCount);
		}
		// we changed blend states behind the shader's back
		ShaderClass::Invalidate();
	}

	REF_PTR_RELEASE(material);
	DX8Wrapper::Set_Texture(0, nullptr);
	ShaderClass::Invalidate();
}

//-------------------------------------------------------------------------------------------------
// GeneralsX @bugfix Claude 17/10/2026 Dynamic lights of one model, with a cap on their sum.
// The fixed function point lights fade as 1 / (1 + 6 d^2 / r^2) (DX8Wrapper, enhanced falloff), so the light a
// model gets is estimated at its point nearest to each light. Lights only change how a model is drawn: no logic or
// CRC impact.
//-------------------------------------------------------------------------------------------------
void W3DEffectLights::addModelDynamicLights(LightEnvironmentClass &env, const SphereClass &bounds, RTS3DScene &scene)
{
	W3DDynamicLight *reaching[MAX_MODEL_DYNAMIC_LIGHTS];
	Int count = 0;
	Real total = 0.0f;

	RefRenderObjListIterator it(scene.getDynamicLights());
	for (it.First(); !it.Is_Done() && count < MAX_MODEL_DYNAMIC_LIGHTS; it.Next())
	{
		W3DDynamicLight *light = (W3DDynamicLight *)it.Peek_Obj();
		if (!light->isEnabled())
			continue;
		if (light->Get_Type() == LightClass::POINT && !Spheres_Intersect(bounds, light->Get_Bounding_Sphere()))
			continue;
		reaching[count++] = light;

		Vector3 diffuse;
		light->Get_Diffuse(&diffuse);
		Real peak = diffuse.X > diffuse.Y ? diffuse.X : diffuse.Y;
		if (diffuse.Z > peak)
			peak = diffuse.Z;
		peak *= light->Get_Intensity();
		if (light->Get_Type() == LightClass::POINT)
		{
			double start, end;
			light->Get_Far_Attenuation_Range(start, end);
			Real dist = (light->Get_Position() - bounds.Center).Length() - bounds.Radius;
			if (dist < 0.0f)
				dist = 0.0f;
			if (end > 1e-5)
				peak /= 1.0f + 6.0f * dist * dist / (Real)(end * end);
		}
		total += peak;
	}

	if (total <= MAX_MODEL_DYNAMIC_LIGHT)
	{
		for (Int i = 0; i < count; ++i)
			env.Add_Light(*reaching[i]);
		return;
	}

	// LightEnvironmentClass copies the colours, so the lights are dimmed for this model only and restored
	const Real scale = MAX_MODEL_DYNAMIC_LIGHT / total;
	for (Int i = 0; i < count; ++i)
	{
		W3DDynamicLight *light = reaching[i];
		Vector3 diffuse, ambient;
		light->Get_Diffuse(&diffuse);
		light->Get_Ambient(&ambient);
		light->Set_Diffuse(diffuse * scale);
		light->Set_Ambient(ambient * scale);
		env.Add_Light(*light);
		light->Set_Diffuse(diffuse);
		light->Set_Ambient(ambient);
	}
}
