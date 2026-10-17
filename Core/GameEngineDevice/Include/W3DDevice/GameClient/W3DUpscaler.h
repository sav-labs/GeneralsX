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

// GeneralsX @feature Claude 16/10/2026 Game side of the FSR 2 temporal upscaler in the patched DXVK
// (cmake/dxvk-patches/0013 and 0014). While the swap chain upscales with FSR 2, the 3D camera of the
// tactical view gets a Halton(2,3) sub-pixel jitter. After the 3D scene, and before the interface, the
// unjittered camera is passed to DXVK through the exported GeneralsX_UpscalerSubmitFrame, and render
// state 252 tells DXVK to copy the scene colour and depth. Only the projection sent to the GPU changes;
// game logic, culling and picking never see the jitter.
// GeneralsX @feature Claude 16/10/2026 Render state 251 marks the end of the opaque scene, before particles and
// other alpha-blended effects; DXVK builds FSR 2's reactive mask from that copy and the final scene (patch 0015).
// GeneralsX @feature Claude 16/10/2026 FSR 3 (Upscaler = FSR3, patches 0016 and 0017) uses the same jitter, camera
// hand-off and render states; log lines then start with [FSR3]. Frame generation happens entirely in DXVK.

#pragma once

class CameraClass;

class W3DUpscaler
{
public:
	/// Before the 3D scene of the tactical view: jitters the camera when FSR 2 is active
	static void beginScene(CameraClass *camera);
	/// After the 3D scene, before the interface: removes the jitter and hands the frame to DXVK
	static void endScene(CameraClass *camera);
	// GeneralsX @feature Claude 16/10/2026 FSR 2 reactive mask, see W3DUpscaler.cpp
	/// Before particles and other alpha-blended effects: render state 251 lets DXVK copy the opaque scene,
	/// which FSR 2 compares with the final scene to find the pixels those effects changed
	static void markOpaqueScene();
	// GeneralsX @performance Claude 17/10/2026 Scenes rendered while suspended are not handed to DXVK and do not jitter:
	// the renderer warm-up draws the scene behind the load screen and never presents it.
	static void setSuspended(Bool suspended);
};
