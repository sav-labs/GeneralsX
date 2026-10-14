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

// GeneralsX @feature Claude 14/10/2026 Input-free camera flight requested with -camtest [seconds].
// Client-side only: it reads the map, the game setup and the clock, and writes nothing but the view.

#include "PreRTS.h"	// This must go first in EVERY cpp file in the GameEngine

#include "GameClient/CameraTest.h"

#include "Common/FramePacer.h"
#include "Common/GlobalData.h"
#include "GameClient/View.h"
#include "GameLogic/GameLogic.h"
#include "GameLogic/TerrainLogic.h"
#include "GameNetwork/GameInfo.h"

namespace
{

enum CameraTestPhase
{
	CAMERA_TEST_IDLE,			///< No match running
	CAMERA_TEST_SETTLING,	///< Match started, waiting for the world to finish loading
	CAMERA_TEST_FLYING,		///< Pan and zoom-out in progress
	CAMERA_TEST_DONE			///< Flight finished for this match, the camera is left alone
};

constexpr const Real CameraTestSettleSeconds = 2.0f;						///< Wait after the match starts before the flight
constexpr const Real CameraTestPanSpeed = 30.0f;								///< World units per second along the pan line
constexpr const Real CameraTestTurnSpeed = DEG_TO_RADF(4.0f);	///< Camera yaw change per second while panning
constexpr const Real CameraTestZoomOutSeconds = 2.5f;					///< Zoom-out from closest to default height after the pan

struct CameraTestState
{
	CameraTestPhase phase;
	Real elapsedSeconds;		///< Real time since the match started
	Coord2D startPos;				///< Pivot at the start of the flight
	Coord2D panDir;					///< Unit direction of the pan, towards the map center
	Real startAngle;
	Real pitch;
	Real minHeight;
	Real maxHeight;
};

CameraTestState s_cameraTest = { CAMERA_TEST_IDLE, 0.0f, { 0.0f, 0.0f }, { 1.0f, 0.0f }, 0.0f, 0.0f, 0.0f, 0.0f };

/// The local player's start position, the same waypoint GameLogic points the camera at on match start.
/// Falls back to the current camera pivot when the match has no such waypoint (e.g. campaign maps).
Coord2D getCameraTestStartPos()
{
	Coord2D pos = TheTacticalView->getPosition2D();

	if (TheGameInfo == nullptr || TheTerrainLogic == nullptr)
		return pos;

	const Int localSlot = TheGameInfo->getLocalSlotNum();
	if (localSlot < 0)
		return pos;

	const GameSlot *slot = TheGameInfo->getSlot(localSlot);
	if (slot == nullptr || slot->getStartPos() < 0)
		return pos;

	AsciiString waypointName;
	waypointName.format("Player_%d_Start", slot->getStartPos() + 1); // start pos waypoints are 1-based
	const Waypoint *waypoint = TheTerrainLogic->getWaypointByName(waypointName);
	if (waypoint == nullptr)
		return pos;

	pos.x = waypoint->getLocation()->x;
	pos.y = waypoint->getLocation()->y;
	return pos;
}

void beginCameraTestFlight()
{
	CameraTestState &s = s_cameraTest;

	s.startPos = getCameraTestStartPos();
	s.startAngle = TheTacticalView->getDefaultAngle();
	s.pitch = TheTacticalView->getDefaultPitch();
	s.minHeight = TheTacticalView->getMinHeightAboveGround();
	s.maxHeight = TheTacticalView->getMaxHeightAboveGround();

	// Start positions sit near the map borders, so pan towards the map center to stay clear of
	// the camera area constraints, which would otherwise stop the camera at the border.
	s.panDir.x = 1.0f;
	s.panDir.y = 0.0f;
	if (TheTerrainLogic != nullptr)
	{
		Region3D extent;
		TheTerrainLogic->getExtent(&extent);
		Coord2D toCenter;
		toCenter.x = (extent.lo.x + extent.hi.x) * 0.5f - s.startPos.x;
		toCenter.y = (extent.lo.y + extent.hi.y) * 0.5f - s.startPos.y;
		if (toCenter.lengthSqr() > 1.0f)
		{
			toCenter.normalize();
			s.panDir = toCenter;
		}
	}

	fprintf(stderr, "[CAMTEST] start: pivot (%.1f, %.1f), pan %.1f s towards (%.2f, %.2f), zoom-out %.1f s\n",
		s.startPos.x, s.startPos.y, TheGlobalData->m_cameraTestSeconds, s.panDir.x, s.panDir.y, CameraTestZoomOutSeconds);
	fflush(stderr);
}

/// Places the camera for the given flight time. Every value is set directly (no easing towards it),
/// so the picture only depends on the time and never on the frame rate.
void applyCameraTestPose(Real flightSeconds)
{
	const CameraTestState &s = s_cameraTest;
	const Real panSeconds = TheGlobalData->m_cameraTestSeconds;

	const Real panTime = min(flightSeconds, panSeconds);
	const Real zoomTime = clamp(0.0f, flightSeconds - panSeconds, CameraTestZoomOutSeconds);
	const Real zoomFactor = zoomTime / CameraTestZoomOutSeconds;

	Coord3D pivot;
	pivot.x = s.startPos.x + s.panDir.x * CameraTestPanSpeed * panTime;
	pivot.y = s.startPos.y + s.panDir.y * CameraTestPanSpeed * panTime;
	pivot.z = TheTerrainLogic != nullptr ? TheTerrainLogic->getGroundHeight(pivot.x, pivot.y) : 0.0f;

	const Real height = s.minHeight + (s.maxHeight - s.minHeight) * zoomFactor;

	TheTacticalView->lookAt(&pivot);
	TheTacticalView->setAngle(s.startAngle + CameraTestTurnSpeed * panTime);
	TheTacticalView->setPitch(s.pitch);
	if (s.maxHeight > 0.0f)
	{
		// setZoom applies the height immediately, unlike setHeightAboveGround which eases towards it
		TheTacticalView->setZoom(height / s.maxHeight);
	}
}

} // namespace

void UpdateCameraTest()
{
	if (TheGlobalData->m_cameraTestSeconds <= 0.0f || TheTacticalView == nullptr || TheGameLogic == nullptr)
		return;

	CameraTestState &s = s_cameraTest;

	const Bool matchRunning = rts::isInteractiveGame(TheGameLogic->getGameMode())
		&& !TheGameLogic->isLoadingMap()
		&& TheGameLogic->getFrame() > 0;

	if (!matchRunning)
	{
		if (s.phase == CAMERA_TEST_FLYING)
		{
			fprintf(stderr, "[CAMTEST] stop: match ended during the flight\n");
			fflush(stderr);
		}
		s.phase = CAMERA_TEST_IDLE;
		return;
	}

	if (s.phase == CAMERA_TEST_DONE)
		return;

	if (s.phase == CAMERA_TEST_IDLE)
	{
		s.phase = CAMERA_TEST_SETTLING;
		s.elapsedSeconds = 0.0f;
		fprintf(stderr, "[CAMTEST] match started, flight begins in %.1f s\n", CameraTestSettleSeconds);
		fflush(stderr);
		return;
	}

	// Real time of the frame about to be drawn, measured by the frame pacer
	s.elapsedSeconds += TheFramePacer->getUpdateTime();

	if (s.phase == CAMERA_TEST_SETTLING)
	{
		if (s.elapsedSeconds < CameraTestSettleSeconds)
			return;

		beginCameraTestFlight();
		s.phase = CAMERA_TEST_FLYING;
	}

	const Real flightSeconds = s.elapsedSeconds - CameraTestSettleSeconds;
	const Real totalSeconds = TheGlobalData->m_cameraTestSeconds + CameraTestZoomOutSeconds;

	applyCameraTestPose(min(flightSeconds, totalSeconds));

	if (flightSeconds >= totalSeconds)
	{
		s.phase = CAMERA_TEST_DONE;
		fprintf(stderr, "[CAMTEST] stop: flight finished after %.2f s\n", flightSeconds);
		fflush(stderr);
	}
}
