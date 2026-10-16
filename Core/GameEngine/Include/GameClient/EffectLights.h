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

// GeneralsX @feature Claude 16/10/2026 Classification of effects that should cast a coloured light.
// Retail data gives only a few FXLists a LightPulse, so explosions, muzzle flashes, fires and missile exhausts
// mostly light nothing. These helpers look at what an FXList or a particle system does (camera shake, scorch
// mark, particle system names, additive particles and their colours) and at its name, and return a light
// profile that the display (W3DEffectLights) turns into a short-lived point light. Client side only: nothing
// here reads or changes game logic state, consumes random numbers or takes part in CRCs.

#pragma once

#include "Lib/BaseType.h"

class ParticleSystem;

namespace EffectLights
{
	enum Kind
	{
		KIND_NONE,
		KIND_MUZZLE,           ///< weapon fire: very short, small
		KIND_IMPACT,           ///< small explosion or shell hit
		KIND_EXPLOSION,        ///< vehicle death, rocket or bomb detonation
		KIND_LARGE_EXPLOSION,  ///< building death, heavy bombs, strong camera shake
		KIND_SUPERWEAPON,      ///< nukes, particle cannon, scud storm and the like
		KIND_FLAME,            ///< flame weapons and napalm bursts: a flickering pulse
		KIND_FIRE,             ///< burning buildings, vehicles and ground (particle systems, continuous)
		KIND_EXHAUST,          ///< missile and rocket exhausts (particle systems, follow the projectile)
		KIND_COUNT
	};

	enum Tint
	{
		TINT_DEFAULT,   ///< the kind's own fire colour
		TINT_TOXIC,     ///< toxin, anthrax: green
		TINT_ELECTRIC,  ///< EMP, electric: blue white
		TINT_LASER,     ///< lasers: red
		TINT_PLASMA,    ///< particle cannon: violet white
		TINT_NUCLEAR,   ///< nuclear: hot white
		TINT_COUNT
	};

	/// What an FXList does, collected from its nuggets.
	struct FXTraits
	{
		FXTraits();

		// GeneralsX @bugfix Claude 16/10/2026 A LightPulse is the data saying "this flashes", not "already lit":
		// retail pulses are mostly 15 units or less, which W3DDisplay::createLightPulse drops as invisible.
		Bool hasLightPulse;          ///< retail LightPulse nugget: the effect gives off light
		Real pulseRadius;            ///< largest LightPulse radius
		Real pulseRed, pulseGreen, pulseBlue; ///< colour of that LightPulse (0..1)
		Int strongestShake;          ///< View::CameraShakeType, -1 without a ViewShake
		Real scorchRadius;           ///< largest TerrainScorch radius, 0 without one
		Int particleSystems;         ///< ParticleSystem nuggets
		Int fireballParticles;       ///< particle systems named like explosions, fireballs or flashes
		Int flameParticles;          ///< particle systems named like fire or flames
		Int muzzleParticles;         ///< particle systems named like muzzle flashes
		Int tint;                    ///< Tint from the particle system names, TINT_DEFAULT when none
	};

	/// The light an effect should cast. kind KIND_NONE means none.
	struct Profile
	{
		Profile();

		Int kind;           ///< Kind
		Int tint;           ///< Tint
		Real sizeScale;     ///< scales the kind's radius (scorch size, particle size)
		Bool hasColor;      ///< color comes from the effect itself (particle colours)
		Real red, green, blue;
	};

	/// Adds what a ParticleSystem nugget with this particle system name contributes to an FXList.
	void addParticleSystemName(FXTraits &traits, const char *particleSystemName);

	/// Profile of an FXList from its name and what it does.
	Profile classifyFXList(const char *fxListName, const FXTraits &traits);

	/// Profile of a particle system from its template: KIND_FIRE or KIND_EXHAUST for continuous systems,
	/// KIND_MUZZLE, KIND_IMPACT or KIND_EXPLOSION for one-shot bursts, KIND_NONE when it gives off no light.
	/// Uses the blend mode, colours and particle size first and the name only as a hint, so mods work too.
	Profile classifyParticleSystem(ParticleSystem *system);

	/// Short name of a kind for logs.
	const char *kindName(Int kind);

	/// Case-insensitive substring search.
	Bool nameContains(const char *name, const char *part);
}
