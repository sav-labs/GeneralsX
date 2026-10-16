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

#pragma once

class CameraClass;

class W3DUpscaler
{
public:
	/// Before the 3D scene of the tactical view: jitters the camera when FSR 2 is active
	static void beginScene(CameraClass *camera);
	/// After the 3D scene, before the interface: removes the jitter and hands the frame to DXVK
	static void endScene(CameraClass *camera);
};
