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

// GeneralsX @feature Claude 16/10/2026 FSR 2 camera jitter and frame hand-off to DXVK, see W3DUpscaler.h.

#include "W3DDevice/GameClient/W3DUpscaler.h"
#include "Common/GlobalData.h"
#include "Common/OptionPreferences.h"
#include "WW3D2/camera.h"
#include "WW3D2/dx8wrapper.h"
#include "WW3D2/ww3d.h"

#include <chrono>
#include <stdio.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
#endif

namespace
{

// Private render state that marks the end of the 3D scene for DXVK. D3D does not define render state 252.
const unsigned UPSCALER_SCENE_RENDER_STATE = 252;

// How often the console shows the upscaler state, in scenes
const UnsignedInt LOG_INTERVAL = 600;

// A camera move longer than this in one frame is a cut, and FSR 2 drops its history
const Real CAMERA_CUT_DISTANCE = 400.0f;

// Shared with DXVK, see D3D9UpscalerFrame in patch 0014. DXVK checks the size.
struct UpscalerFrame
{
	UnsignedInt size;
	UnsignedInt flags;
	Real jitterX;
	Real jitterY;
	Real frameTimeMs;
	Real cameraNear;
	Real cameraFar;
	Real fovY;
	Real viewport[4];
	Real view[16];
	Real projection[16];
};

static_assert(sizeof(UpscalerFrame) == 176, "UpscalerFrame must match D3D9UpscalerFrame in DXVK");
static_assert(sizeof(Matrix4x4) == 16 * sizeof(Real), "Matrix4x4 must hold 16 floats");

const UnsignedInt UPSCALER_FRAME_RESET = 0x1u;

#ifdef _WIN32
typedef BOOL (WINAPI *SubmitFrameFunc)(const void *frame);
#else
typedef bool (*SubmitFrameFunc)(const void *frame);
#endif

Bool s_lookupDone = false;
SubmitFrameFunc s_submitFrame = nullptr;

Bool s_temporalActive = false;		///< DXVK upscaled the previous frame with FSR 2, so this frame jitters
Bool s_jittered = false;				///< the camera of the current scene is jittered
Real s_jitterPixels[2] = { 0.0f, 0.0f };
UnsignedInt s_phaseIndex = 0;
UnsignedInt s_phaseCount = 1;
UnsignedInt s_sceneCount = 0;

Bool s_havePrevious = false;
Vector3 s_previousPosition;
std::chrono::steady_clock::time_point s_previousTime;

Bool isFsr2Selected()
{
	return TheGlobalData != nullptr && TheGlobalData->m_upscaler == OptionPreferences::UPSCALER_FSR2;
}

void lookupSubmitFrame()
{
	if (s_lookupDone)
		return;

	s_lookupDone = true;

#ifdef _WIN32
	HMODULE d3d9 = GetModuleHandleA("d3d9.dll");
	if (d3d9 != nullptr)
		s_submitFrame = (SubmitFrameFunc)GetProcAddress(d3d9, "GeneralsX_UpscalerSubmitFrame");
#endif

	if (s_submitFrame != nullptr)
		fprintf(stderr, "[FSR2] DXVK FSR 2 interface found, the 3D camera jitters while DXVK upscales with FSR 2\n");
	else
		fprintf(stderr, "[FSR2] d3d9.dll has no GeneralsX_UpscalerSubmitFrame (not the GeneralsX DXVK build), FSR 1.0 upscales instead\n");
	fflush(stderr);
}

// Radical inverse of index in the given base, the Halton sequence that FSR 2 uses for its jitter
Real halton(UnsignedInt index, UnsignedInt base)
{
	Real fraction = 1.0f;
	Real result = 0.0f;

	while (index > 0)
	{
		fraction /= (Real)base;
		result += fraction * (Real)(index % base);
		index /= base;
	}

	return result;
}

// Number of jitter phases for the scale factor, as ffxFsr2GetJitterPhaseCount computes it
UnsignedInt jitterPhaseCount(Int renderWidth, Int displayWidth)
{
	if (renderWidth <= 0 || displayWidth <= renderWidth)
		return 8;

	const Real ratio = (Real)displayWidth / (Real)renderWidth;
	return (UnsignedInt)(8.0f * ratio * ratio);
}

void getViewportPixels(CameraClass *camera, Real viewport[4])
{
	int width, height, bits;
	bool windowed;
	WW3D::Get_Render_Target_Resolution(width, height, bits, windowed);

	Vector2 vMin, vMax;
	camera->Get_Viewport(vMin, vMax);

	// Same rounding as CameraClass::Apply
	viewport[0] = (Real)(unsigned int)(vMin.X * (Real)width);
	viewport[1] = (Real)(unsigned int)(vMin.Y * (Real)height);
	viewport[2] = (Real)(unsigned int)((vMax.X - vMin.X) * (Real)width);
	viewport[3] = (Real)(unsigned int)((vMax.Y - vMin.Y) * (Real)height);
}

} // namespace

void W3DUpscaler::beginScene(CameraClass *camera)
{
	s_jittered = false;

	if (camera == nullptr || !isFsr2Selected() || !s_temporalActive)
		return;

	Real viewport[4];
	getViewportPixels(camera, viewport);
	if (viewport[2] < 1.0f || viewport[3] < 1.0f)
		return;

	int width, height, bits;
	bool windowed;
	WW3D::Get_Render_Target_Resolution(width, height, bits, windowed);

	s_phaseCount = jitterPhaseCount(width, TheGlobalData->m_renderScaleDisplayWidth);
	s_phaseIndex = (s_phaseIndex + 1) % s_phaseCount;

	// Pixels of the render target, y pointing down the image; the Halton sequence starts at index 1
	s_jitterPixels[0] = halton(s_phaseIndex + 1, 2) - 0.5f;
	s_jitterPixels[1] = halton(s_phaseIndex + 1, 3) - 0.5f;

	camera->Set_Projection_Jitter(2.0f * s_jitterPixels[0] / viewport[2], -2.0f * s_jitterPixels[1] / viewport[3]);
	s_jittered = true;
}

void W3DUpscaler::endScene(CameraClass *camera)
{
	if (camera == nullptr)
		return;

	camera->Set_Projection_Jitter(0.0f, 0.0f);

	if (!isFsr2Selected())
		return;

	lookupSubmitFrame();
	if (s_submitFrame == nullptr)
		return;

	UpscalerFrame frame;
	memset(&frame, 0, sizeof(frame));
	frame.size = sizeof(frame);

	if (s_jittered)
	{
		frame.jitterX = s_jitterPixels[0];
		frame.jitterY = s_jitterPixels[1];
	}

	const std::chrono::steady_clock::time_point now = std::chrono::steady_clock::now();
	const Vector3 position = camera->Get_Position();

	if (s_havePrevious)
	{
		frame.frameTimeMs = std::chrono::duration<Real, std::milli>(now - s_previousTime).count();

		const Vector3 delta = position - s_previousPosition;
		if (delta.Length2() > CAMERA_CUT_DISTANCE * CAMERA_CUT_DISTANCE)
			frame.flags |= UPSCALER_FRAME_RESET;
	}
	else
	{
		frame.frameTimeMs = 1000.0f / 30.0f;
		frame.flags |= UPSCALER_FRAME_RESET;
	}

	s_havePrevious = true;
	s_previousTime = now;
	s_previousPosition = position;

	camera->Get_Clip_Planes(frame.cameraNear, frame.cameraFar);
	frame.fovY = camera->Get_Vertical_FOV();
	getViewportPixels(camera, frame.viewport);

	// D3D matrices as DX8Wrapper sends them: the transpose of the Westwood convention
	Matrix3D view;
	camera->Get_View_Matrix(&view);
	const Matrix4x4 viewD3D = Matrix4x4(view).Transpose();

	Matrix4x4 projection;
	camera->Get_D3D_Projection_Matrix(&projection);
	const Matrix4x4 projectionD3D = projection.Transpose();

	memcpy(frame.view, &viewD3D, sizeof(frame.view));
	memcpy(frame.projection, &projectionD3D, sizeof(frame.projection));

	const Bool wasActive = s_temporalActive;
	s_temporalActive = s_submitFrame(&frame) != 0;

	// DXVK copies render target 0 and the depth buffer here, before the interface is drawn
	DX8Wrapper::Set_DX8_Render_State((D3DRENDERSTATETYPE)UPSCALER_SCENE_RENDER_STATE, 1);
	DX8Wrapper::Set_DX8_Render_State((D3DRENDERSTATETYPE)UPSCALER_SCENE_RENDER_STATE, 0);

	++s_sceneCount;

	if (s_temporalActive != wasActive || s_sceneCount == 1 || s_sceneCount % LOG_INTERVAL == 0)
	{
		fprintf(stderr, "[FSR2] scene %u: FSR 2 %s, jitter %.3f %.3f px (phase %u of %u), viewport %.0fx%.0f at %.0f,%.0f, display %dx%d, near %.1f far %.1f, frame %.1f ms%s\n",
			s_sceneCount,
			s_temporalActive ? "active" : "inactive (FSR 1.0 upscales)",
			frame.jitterX, frame.jitterY, s_phaseIndex + 1, s_phaseCount,
			frame.viewport[2], frame.viewport[3], frame.viewport[0], frame.viewport[1],
			TheGlobalData->m_renderScaleDisplayWidth, TheGlobalData->m_renderScaleDisplayHeight,
			frame.cameraNear, frame.cameraFar, frame.frameTimeMs,
			(frame.flags & UPSCALER_FRAME_RESET) ? ", history reset" : "");
		fflush(stderr);
	}
}
