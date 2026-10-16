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

// GeneralsX @feature Claude 14/10/2026 Input-free camera flight requested with -camtest [seconds].
// Once a match is running, the tactical camera waits for the world to settle, snaps to the local
// player's start position at the closest zoom, pans and turns slowly and finally zooms out. Turn and zoom
// are a function of real elapsed time only, so recordings made at different frame rates (for example with
// and without a texture pack) show the same camera motion.
// GeneralsX @feature Claude 15/10/2026 When the flight begins, a test convoy of the local player's side
// (ground vehicles plus helicopters when the side has them) is spawned between the start position and the
// map center and ordered to drive towards the center; the camera follows the convoy instead of a fixed pan.
// This changes the match, so it only happens with -camtest; without it nothing is spawned or moved.
// GeneralsX @feature Claude 15/10/2026 With -camclose (or -camtest [seconds] close) the flight is a close-up instead:
// below the minimum zoom height, with a lower pitch and no zoom-out, along the convoy and then past the local
// player's base buildings. It is timed in logic frames, about 10 seconds for -camtest 8.
// GeneralsX @feature Claude 16/10/2026 With -camtest [seconds] battle [units] [night] a column of the local player's side
// and a column of the first enemy player's side (artillery and rocket units in the rear rows) spawn facing each other in
// front of the local start position and attack-move through each other, a structure near the fight is damaged to 30%
// health so it burns, and the camera orbits the battle line for the given seconds. units is the whole scene, split
// evenly between both sides (default 20, at most 120). night switches the match to night when it starts. Without an
// enemy player the regular flight runs instead.
void UpdateCameraTest();
