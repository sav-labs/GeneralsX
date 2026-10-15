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
// player's start position at the closest zoom, pans and turns slowly over a fixed path and finally
// zooms out. The path is a function of real elapsed time only, so recordings made at different
// frame rates (for example with and without a texture pack) show identical camera motion.
// The flight only drives the client view and never touches the game logic.
void UpdateCameraTest();
