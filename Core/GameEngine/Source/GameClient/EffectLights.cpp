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

// GeneralsX @feature Claude 16/10/2026 Classification of effects that should cast a coloured light (see
// EffectLights.h). The rules only use what the data already says: camera shake strength, scorch marks, particle
// system names, blend mode and colours, and the usual naming of FXLists (WeaponFX_...Detonation, FX_...Death,
// ...MuzzleFlash). An effect that matches nothing casts no light, so unknown or modded data stays as it was.

#include "PreRTS.h"	// This must go first in EVERY cpp file in the GameEngine

#include "GameClient/EffectLights.h"
#include "GameClient/ParticleSys.h"
#include "GameClient/View.h"
#include "WWMath/wwmath.h"

namespace EffectLights
{

namespace
{
	char lowerChar(char c)
	{
		return (c >= 'A' && c <= 'Z') ? (char)(c - 'A' + 'a') : c;
	}

	/// Lower case copy, cut at the buffer size.
	void toLower(const char *src, char *dst, Int dstSize)
	{
		Int i = 0;
		if (src)
		{
			for (; src[i] && i < dstSize - 1; ++i)
				dst[i] = lowerChar(src[i]);
		}
		dst[i] = 0;
	}

	Bool containsAny(const char *lowerName, const char *const *parts)
	{
		for (Int i = 0; parts[i]; ++i)
		{
			if (strstr(lowerName, parts[i]))
				return TRUE;
		}
		return FALSE;
	}

	Bool endsWith(const char *lowerName, const char *suffix)
	{
		const size_t n = strlen(lowerName);
		const size_t m = strlen(suffix);
		return n >= m && strcmp(lowerName + n - m, suffix) == 0;
	}

	const char *const s_superWords[] = { "nuke", "nuclear", "neutron", "scudstorm", "scud_storm", "uplink",
		"particlecannon", "particlebeam", "orbital", "superweapon", "moab", "daisycutter", "fuelair", "anthraxbomb",
		nullptr };
	const char *const s_largeWords[] = { "structure", "building", "bigexplo", "largeexplo", "hugeexplo", "massive",
		"bunkerbuster", "carpet", "barrage", "cluster", "buildingdie", nullptr };
	const char *const s_explosionWords[] = { "explo", "detonat", "death", "destroy", "destruct", "blast", "boom",
		"crash", "bomb", "kaboom", nullptr };
	const char *const s_impactWords[] = { "impact", "struck", "ricochet", "_hit", "hit_", nullptr };
	const char *const s_muzzleWords[] = { "muzzle", "gunflash", "gunfire", "firefx", "launch", "shoot", "cannonfire",
		"weaponfire", nullptr };
	const char *const s_muzzleSuffixes[] = { "fire", "flash", "shot", "gun", "notracer", "tracer", nullptr };
	const char *const s_flameWords[] = { "flame", "napalm", "inferno", "incendiar", "dragon", "firestorm", "firewall",
		"molotov", "blaze", "burn", nullptr };
	const char *const s_ignoreWords[] = { "smoke", "dust", "debris", "steam", "water", "splash", "snow", "rain",
		"select", "heal", "repair", "upgrade", "promot", "veteran", "levelup", "cash", "money", "cursor", "beacon",
		"radar", "spawn", "construct", "capture", "garrison", nullptr };

	const char *const s_toxicWords[] = { "toxin", "toxic", "anthrax", "poison", "chem", "gamma", "radiation",
		"contaminat", nullptr };
	const char *const s_electricWords[] = { "fx_emp", "_emp", "emp_", "emppulse", "empblast", "empwave", "electric",
		"lightning", "tesla", nullptr };
	const char *const s_laserWords[] = { "laser", nullptr };
	const char *const s_plasmaWords[] = { "uplink", "particlecannon", "particlebeam", "orbital", nullptr };
	const char *const s_nuclearWords[] = { "nuke", "nuclear", "neutron", nullptr };

	const char *const s_psFireballWords[] = { "explo", "fireball", "blast", "flash", "burst", "detonat", "boom",
		"flare", nullptr };
	const char *const s_psFlameWords[] = { "fire", "flame", "burn", "napalm", "inferno", "ember", "blaze", nullptr };
	const char *const s_psMuzzleWords[] = { "muzzle", "gunflash", nullptr };
	const char *const s_psIgnoreWords[] = { "smoke", "dust", "debris", "steam", "splash", "water", "spark", nullptr };

	const char *const s_exhaustWords[] = { "exhaust", "thrust", "afterburn", "jet", "rocket", "missile", "engine",
		"booster", nullptr };
	const char *const s_fireWords[] = { "fire", "flame", "burn", "napalm", "inferno", "ember", "blaze", "torch",
		"molotov", nullptr };

	Int tintFromName(const char *lowerName)
	{
		if (containsAny(lowerName, s_plasmaWords))
			return TINT_PLASMA;
		if (containsAny(lowerName, s_nuclearWords))
			return TINT_NUCLEAR;
		if (containsAny(lowerName, s_toxicWords))
			return TINT_TOXIC;
		if (containsAny(lowerName, s_electricWords))
			return TINT_ELECTRIC;
		if (containsAny(lowerName, s_laserWords))
			return TINT_LASER;
		return TINT_DEFAULT;
	}

	Real clampReal(Real v, Real lo, Real hi)
	{
		return v < lo ? lo : (v > hi ? hi : v);
	}

	Real maxReal(Real a, Real b)
	{
		return a > b ? a : b;
	}
}

FXTraits::FXTraits() :
	hasLightPulse(FALSE),
	strongestShake(-1),
	scorchRadius(0.0f),
	particleSystems(0),
	fireballParticles(0),
	flameParticles(0),
	muzzleParticles(0),
	tint(TINT_DEFAULT)
{
}

Profile::Profile() :
	kind(KIND_NONE),
	tint(TINT_DEFAULT),
	sizeScale(1.0f),
	hasColor(FALSE),
	red(1.0f),
	green(1.0f),
	blue(1.0f)
{
}

Bool nameContains(const char *name, const char *part)
{
	char lowerName[256];
	char lowerPart[64];
	toLower(name, lowerName, (Int)sizeof(lowerName));
	toLower(part, lowerPart, (Int)sizeof(lowerPart));
	return strstr(lowerName, lowerPart) != nullptr;
}

void addParticleSystemName(FXTraits &traits, const char *particleSystemName)
{
	char name[256];
	toLower(particleSystemName, name, (Int)sizeof(name));
	++traits.particleSystems;
	if (traits.tint == TINT_DEFAULT)
		traits.tint = tintFromName(name);
	if (containsAny(name, s_psIgnoreWords) && !containsAny(name, s_psFireballWords))
		return;
	if (containsAny(name, s_psMuzzleWords))
		++traits.muzzleParticles;
	else if (containsAny(name, s_psFireballWords))
		++traits.fireballParticles;
	else if (containsAny(name, s_psFlameWords))
		++traits.flameParticles;
}

Profile classifyFXList(const char *fxListName, const FXTraits &traits)
{
	Profile profile;
	if (traits.hasLightPulse)
		return profile;	// the data lights this one itself

	char name[256];
	toLower(fxListName, name, (Int)sizeof(name));

	profile.tint = tintFromName(name);
	if (profile.tint == TINT_DEFAULT)
		profile.tint = traits.tint;

	const Int shake = traits.strongestShake;
	const Bool hasScorch = traits.scorchRadius > 0.0f;
	const Bool fireEvidence = traits.fireballParticles > 0 || traits.flameParticles > 0 || hasScorch
		|| shake >= View::SHAKE_SUBTLE;

	// Superweapons: named so, or a camera shake only the biggest blasts use.
	if (containsAny(name, s_superWords) || shake >= View::SHAKE_SEVERE)
	{
		if (!fireEvidence && traits.particleSystems == 0)
			return profile;	// sound or speech only
		profile.kind = KIND_SUPERWEAPON;
		profile.sizeScale = shake >= View::SHAKE_CINE_EXTREME ? 1.25f : 1.0f;
		return profile;
	}

	if (containsAny(name, s_ignoreWords) && shake < View::SHAKE_STRONG && !hasScorch)
		return profile;

	const Bool explosionName = containsAny(name, s_explosionWords) || containsAny(name, s_largeWords);

	// Flame weapons and napalm: flickering fire light, unless the effect is mostly an explosion.
	if ((containsAny(name, s_flameWords) || (traits.flameParticles > 0 && traits.fireballParticles == 0 && !explosionName))
		&& shake < View::SHAKE_NORMAL)
	{
		if (traits.particleSystems == 0)
			return profile;
		profile.kind = KIND_FLAME;
		return profile;
	}

	if (explosionName || shake >= View::SHAKE_SUBTLE || hasScorch)
	{
		if (containsAny(name, s_largeWords) || shake >= View::SHAKE_STRONG || traits.scorchRadius >= 40.0f)
		{
			profile.kind = KIND_LARGE_EXPLOSION;
			if (hasScorch)
				profile.sizeScale = clampReal(traits.scorchRadius / 45.0f, 0.8f, 1.6f);
			return profile;
		}
		if (shake >= View::SHAKE_NORMAL || traits.scorchRadius >= 15.0f
			|| (explosionName && (traits.fireballParticles > 0 || hasScorch || shake >= View::SHAKE_SUBTLE)))
		{
			profile.kind = KIND_EXPLOSION;
			if (hasScorch)
				profile.sizeScale = clampReal(traits.scorchRadius / 22.0f, 0.75f, 1.5f);
			return profile;
		}
		if (fireEvidence)
		{
			profile.kind = KIND_IMPACT;
			return profile;
		}
		return profile;	// "explosion" sound without anything to see
	}

	if (containsAny(name, s_impactWords) || endsWith(name, "hit"))
	{
		if (traits.fireballParticles > 0 || traits.flameParticles > 0 || traits.muzzleParticles > 0)
			profile.kind = KIND_IMPACT;
		return profile;
	}

	Bool muzzleName = containsAny(name, s_muzzleWords);
	for (Int i = 0; !muzzleName && s_muzzleSuffixes[i]; ++i)
		muzzleName = endsWith(name, s_muzzleSuffixes[i]);
	if (muzzleName || traits.muzzleParticles > 0)
	{
		profile.kind = KIND_MUZZLE;
		return profile;
	}

	if (traits.fireballParticles > 0)
		profile.kind = KIND_IMPACT;

	return profile;
}

Profile classifyParticleSystem(ParticleSystem *system)
{
	Profile profile;
	if (!system || !system->getTemplate())
		return profile;

	// One-shot bursts belong to the FXList (or death effect) that made them, which has its own light.
	if (system->m_isOneShot)
		return profile;
	if (system->m_particleType != ParticleSystemInfo::PARTICLE
		&& system->m_particleType != ParticleSystemInfo::VOLUME_PARTICLE
		&& system->m_particleType != ParticleSystemInfo::STREAK)
		return profile;
	const Bool additive = system->m_shaderType == ParticleSystemInfo::ADDITIVE;
	if (!additive && system->m_shaderType != ParticleSystemInfo::ALPHA)
		return profile;

	char name[256];
	toLower(system->getTemplate()->getName().str(), name, (Int)sizeof(name));
	if (containsAny(name, s_psIgnoreWords) && !containsAny(name, s_fireWords))
		return profile;

	// Brightest colour key: for additive particles that is the light they give off.
	Real bestRed = 0.0f, bestGreen = 0.0f, bestBlue = 0.0f, bestLum = 0.0f;
	for (Int i = 0; i < MAX_KEYFRAMES; ++i)
	{
		const RGBColorKeyframe &key = system->m_colorKey[i];
		if (i > 0 && key.frame == 0)
			break;
		const Real lum = 0.30f * key.color.red + 0.59f * key.color.green + 0.11f * key.color.blue;
		if (lum > bestLum)
		{
			bestLum = lum;
			bestRed = key.color.red;
			bestGreen = key.color.green;
			bestBlue = key.color.blue;
		}
	}
	const Real bestMax = maxReal(bestRed, maxReal(bestGreen, bestBlue));
	const Bool warm = bestMax > 0.0f && bestRed >= 0.6f * bestMax && bestBlue <= 0.75f * bestRed;

	const Bool attached = system->getAttachedDrawable() != INVALID_DRAWABLE_ID || system->getAttachedObject() != INVALID_ID;
	if (containsAny(name, s_exhaustWords) && !containsAny(name, s_psIgnoreWords))
	{
		profile.kind = KIND_EXHAUST;
	}
	else if (containsAny(name, s_fireWords))
	{
		// alpha blended fire is usually the smoky part: only take it when its colours are fire coloured
		if (!additive && !(warm && bestLum > 0.35f))
			return profile;
		profile.kind = KIND_FIRE;
	}
	else if (additive && attached && warm && bestLum > 0.45f)
	{
		// unnamed but glowing warm and attached to something: an engine or a burning part
		profile.kind = KIND_EXHAUST;
	}
	else
	{
		return profile;
	}

	profile.tint = tintFromName(name);
	if (bestMax > 0.05f && profile.tint == TINT_DEFAULT)
	{
		profile.hasColor = TRUE;
		profile.red = bestRed / bestMax;
		profile.green = bestGreen / bestMax;
		profile.blue = bestBlue / bestMax;
	}

	// Bigger particles, bigger light.
	const Real size = system->m_startSize.getMaximumValue() * system->getSizeMultiplier();
	profile.sizeScale = clampReal(WWMath::Sqrt(maxReal(size, 1.0f) / 12.0f), 0.6f, 1.8f);
	if (!additive)
		profile.sizeScale *= 0.8f;
	return profile;
}

} // namespace EffectLights
