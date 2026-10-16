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

#pragma once

// GeneralsX @feature Claude 16/10/2026 Display-only remap of W3D model and animation names.
// The remaster's content pack swaps unit and building art without touching the retail Draw modules:
// an ArtRemap block maps a retail model (and its animations) to a model of the pack. Only what is drawn
// changes. Bones that game logic reads (weapon launch points, turrets, docks, rope and exit points) keep
// coming from the retail model, so a match with or without the pack, and retail replays, simulate the same.
//
//   ArtRemap
//     Model     = AVCRUSADER   AVGXMBT        ; draw AVGXMBT where the retail INI says AVCRUSADER
//     Model     = ABPWRPLANT_A1 NONE           ; draw nothing for this retail piece
//     Animation = AVCOMANCHE.AVCOMANCHE AVGXAPACHE.AVGXAPACHE
//   End
//
// A remapped model plays only the animations mapped here; a retail animation never runs on pack art.
// The table is rebuilt before every match together with the rest of Data\INI\GeneralsX.

class AsciiString;

class ArtRemap
{
public:
	static void reset();
	static void addModel(const char* retailName, const char* displayName);
	static void addAnimation(const char* retailName, const char* displayName);

	/// True when the model is drawn with other art; displayName is then that model, or empty for none.
	static bool findModel(const AsciiString& retailName, AsciiString& displayName);
	/// True when the animation has a replacement; displayName is then that animation, or empty for none.
	static bool findAnimation(const AsciiString& retailName, AsciiString& displayName);
	static bool isEmpty();
};
