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
// GeneralsX @feature Claude 15/10/2026 The flight also spawns a test convoy of the local player's side
// and follows it, so recordings show moving units. Spawning changes the match (a replay recorded with
// -camtest does not play back), so it only happens with -camtest.
// GeneralsX @feature Claude 15/10/2026 The flight reports its start to the DXVK video capture
// (DXVK_CAPTURE_VIDEO_START=camtest), so recordings of different runs begin on the same frame of the
// flight however long the game took to load.

#include "PreRTS.h"	// This must go first in EVERY cpp file in the GameEngine

#include "GameClient/CameraTest.h"

#include "Common/FramePacer.h"
#include "Common/GlobalData.h"
#include "Common/Player.h"
#include "Common/PlayerList.h"
#include "Common/PlayerTemplate.h"
#include "Common/ThingFactory.h"
#include "Common/ThingTemplate.h"
#include "GameClient/View.h"
#include "GameLogic/AI.h"
#include "GameLogic/GameLogic.h"
#include "GameLogic/Module/AIUpdate.h"
#include "GameLogic/Object.h"
#include "GameLogic/PartitionManager.h"
#include "GameLogic/TerrainLogic.h"
#include "GameNetwork/GameInfo.h"

#include "PlatformEnvironment.h"

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
// GeneralsX @tweak Claude 15/10/2026 The wait is counted in logic frames, so the convoy spawns on the same logic
// frame on every run and a -skirmish match with a fixed -seed plays out the same way in every recording.
constexpr const UnsignedInt CameraTestSettleFrames = (UnsignedInt)(CameraTestSettleSeconds * LOGICFRAMES_PER_SECOND);
constexpr const Real CameraTestPanSpeed = 30.0f;								///< World units per second along the pan line (no convoy)
constexpr const Real CameraTestTurnSpeed = DEG_TO_RADF(4.0f);	///< Camera yaw change per second while panning
constexpr const Real CameraTestZoomOutSeconds = 2.5f;					///< Zoom-out from closest to default height after the pan

// Test convoy, spawned when the flight begins
constexpr const Int CameraTestGroundCount = 8;							///< Ground vehicles, in rows of two
constexpr const Int CameraTestAirCount = 2;									///< Helicopters, when the side has one
constexpr const Int CameraTestMaxConvoy = CameraTestGroundCount + CameraTestAirCount;
constexpr const Real CameraTestConvoyLead = 140.0f;					///< Distance of the first row from the start position, towards the map center
constexpr const Real CameraTestRowSpacing = 45.0f;					///< Distance between rows along the pan direction
constexpr const Real CameraTestColumnSpacing = 50.0f;				///< Distance between the two columns
constexpr const Real CameraTestSpawnSearchRadius = 60.0f;		///< Search radius for a clear spot around each slot
constexpr const Real CameraTestMinTravel = 400.0f;					///< Minimum length of the move order
constexpr const Real CameraTestFollowSeconds = 0.35f;				///< Time constant of the camera following the convoy

// GeneralsX @feature Claude 15/10/2026 Signal for the DXVK video capture started with DXVK_CAPTURE_VIDEO_START=camtest.
// DXVK reads the process environment on every present while it waits: the prepare value starts the encoder when the
// match starts, the event value starts recording with the first frame of the flight. It only affects rendering tools.
constexpr const char *CameraTestCaptureSignal = "DXVK_CAPTURE_VIDEO_SIGNAL";
constexpr const char *CameraTestCapturePrepare = "camtest.prepare";
constexpr const char *CameraTestCaptureStart = "camtest";

/// Templates of one side: a main battle tank, a fast vehicle and a helicopter (empty when there is none).
struct CameraTestSideUnits
{
	const char *baseSide;
	const char *tank;
	const char *fast;
	const char *air;
};

const CameraTestSideUnits CameraTestSides[] =
{
	{ "America", "AmericaTankCrusader", "AmericaVehicleHumvee", "AmericaVehicleComanche" },
	{ "China", "ChinaTankBattleMaster", "ChinaTankGattling", "ChinaVehicleHelix" },
	{ "GLA", "GLATankScorpion", "GLAVehicleTechnical", "" },
};

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

	ObjectID convoy[CameraTestMaxConvoy];	///< Spawned units, ground vehicles first
	Int groundCount;												///< Number of ground vehicles in convoy (the camera follows these)
	Int convoyCount;												///< Number of units in convoy
	UnsignedInt sampleFrame;								///< Logic frame of curCentroid
	Bool hasCentroid;
	Coord2D prevCentroid;										///< Ground convoy center in the previous logic frame
	Coord2D curCentroid;										///< Ground convoy center in the current logic frame
	Bool hasFollowPivot;
	Coord2D followPivot;										///< Camera pivot while following the convoy
};

CameraTestState s_cameraTest;

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

/// The unit set of the player's base side (America, China or GLA), America when the side is unknown.
const CameraTestSideUnits &getCameraTestSideUnits(const Player *player)
{
	AsciiString side = player->getSide();
	const PlayerTemplate *playerTemplate = player->getPlayerTemplate();
	if (playerTemplate != nullptr && playerTemplate->getBaseSide().isNotEmpty())
		side = playerTemplate->getBaseSide();

	for (Int i = 0; i < ARRAY_SIZE(CameraTestSides); ++i)
	{
		if (side.startsWith(CameraTestSides[i].baseSide))
			return CameraTestSides[i];
	}
	return CameraTestSides[0];
}

/// First template of the list that exists, so a missing unit falls back to another one.
const ThingTemplate *findCameraTestTemplate(const char *preferred, const char *fallback1, const char *fallback2)
{
	const char *names[] = { preferred, fallback1, fallback2 };
	for (Int i = 0; i < ARRAY_SIZE(names); ++i)
	{
		if (names[i] == nullptr || names[i][0] == '\0')
			continue;
		const ThingTemplate *thingTemplate = TheThingFactory->findTemplate(names[i], FALSE);
		if (thingTemplate != nullptr)
			return thingTemplate;
	}
	return nullptr;
}

/// Creates one unit near pos, facing angle, and orders it to move to dest through the normal AI command path.
Object *spawnCameraTestUnit(const ThingTemplate *thingTemplate, Team *team, const Coord2D &pos, Real angle, const Coord2D &dest)
{
	Object *obj = TheThingFactory->newObject(thingTemplate, team);
	if (obj == nullptr)
		return nullptr;

	Coord3D wanted;
	wanted.x = pos.x;
	wanted.y = pos.y;
	wanted.z = TheTerrainLogic->getGroundHeight(pos.x, pos.y);

	// Keep clear of buildings, cliffs, water and the units spawned before this one
	FindPositionOptions options;
	options.maxRadius = CameraTestSpawnSearchRadius;
	options.startAngle = 0.0f;
	options.ignoreObject = obj;
	Coord3D spawnPos = wanted;
	if (!ThePartitionManager->findPositionAround(&wanted, &options, &spawnPos))
		spawnPos = wanted;

	obj->setOrientation(angle);
	obj->setPosition(&spawnPos);

	AIUpdateInterface *ai = obj->getAIUpdateInterface();
	if (ai != nullptr)
	{
		Coord3D moveTo;
		moveTo.x = dest.x;
		moveTo.y = dest.y;
		moveTo.z = TheTerrainLogic->getGroundHeight(dest.x, dest.y);
		ai->aiMoveToPosition(&moveTo, CMD_FROM_PLAYER);
	}
	return obj;
}

/// Spawns the test convoy of the local player's side in two columns between the start position and
/// the map center, turned sideways so the units have to turn before they drive towards the center.
void spawnCameraTestConvoy(Real travelDistance)
{
	CameraTestState &s = s_cameraTest;
	s.groundCount = 0;
	s.convoyCount = 0;

	if (ThePlayerList == nullptr || TheThingFactory == nullptr || ThePartitionManager == nullptr || TheTerrainLogic == nullptr)
		return;

	Player *player = ThePlayerList->getLocalPlayer();
	Team *team = player != nullptr ? player->getDefaultTeam() : nullptr;
	if (team == nullptr)
	{
		fprintf(stderr, "[CAMTEST] convoy: no local player team, nothing spawned\n");
		fflush(stderr);
		return;
	}

	const CameraTestSideUnits &side = getCameraTestSideUnits(player);
	const ThingTemplate *tank = findCameraTestTemplate(side.tank, side.fast, CameraTestSides[0].tank);
	const ThingTemplate *fast = findCameraTestTemplate(side.fast, side.tank, CameraTestSides[0].fast);
	const ThingTemplate *air = findCameraTestTemplate(side.air, nullptr, nullptr);

	const Coord2D forward = s.panDir;
	Coord2D right;
	right.x = -forward.y;
	right.y = forward.x;

	const Real forwardAngle = forward.toAngle();
	const Real travel = max(travelDistance, CameraTestMinTravel);

	Coord2D lead;
	lead.x = s.startPos.x + forward.x * CameraTestConvoyLead;
	lead.y = s.startPos.y + forward.y * CameraTestConvoyLead;

	// Ground vehicles: tanks lead, fast vehicles in the second and fourth rows
	for (Int i = 0; i < CameraTestGroundCount; ++i)
	{
		const Int row = i / 2;
		const Real columnSign = (i % 2) == 0 ? -1.0f : 1.0f;
		const ThingTemplate *thingTemplate = (row % 2) == 0 ? tank : fast;
		if (thingTemplate == nullptr)
			continue;

		Coord2D pos;
		pos.x = lead.x - forward.x * CameraTestRowSpacing * row + right.x * CameraTestColumnSpacing * 0.5f * columnSign;
		pos.y = lead.y - forward.y * CameraTestRowSpacing * row + right.y * CameraTestColumnSpacing * 0.5f * columnSign;

		Coord2D dest;
		dest.x = pos.x + forward.x * travel;
		dest.y = pos.y + forward.y * travel;

		// Face outwards from the convoy line so every unit turns before it drives off
		Object *obj = spawnCameraTestUnit(thingTemplate, team, pos, forwardAngle + columnSign * PI * 0.5f, dest);
		if (obj != nullptr)
			s.convoy[s.convoyCount++] = obj->getID();
	}
	s.groundCount = s.convoyCount;

	// Helicopters start beside the last row and overtake the convoy
	if (air != nullptr)
	{
		for (Int i = 0; i < CameraTestAirCount; ++i)
		{
			const Real columnSign = (i % 2) == 0 ? -1.0f : 1.0f;
			const Real rearOffset = CameraTestRowSpacing * (CameraTestGroundCount / 2);

			Coord2D pos;
			pos.x = lead.x - forward.x * rearOffset + right.x * CameraTestColumnSpacing * 1.5f * columnSign;
			pos.y = lead.y - forward.y * rearOffset + right.y * CameraTestColumnSpacing * 1.5f * columnSign;

			Coord2D dest;
			dest.x = pos.x + forward.x * travel;
			dest.y = pos.y + forward.y * travel;

			Object *obj = spawnCameraTestUnit(air, team, pos, forwardAngle, dest);
			if (obj != nullptr)
				s.convoy[s.convoyCount++] = obj->getID();
		}
	}

	fprintf(stderr, "[CAMTEST] convoy: side %s, %d ground (%s, %s), %d air (%s), move %.0f towards (%.2f, %.2f)\n",
		side.baseSide,
		s.groundCount,
		tank != nullptr ? tank->getName().str() : "none",
		fast != nullptr ? fast->getName().str() : "none",
		s.convoyCount - s.groundCount,
		air != nullptr ? air->getName().str() : "none",
		travel, forward.x, forward.y);
	fflush(stderr);
}

/// Center of the live ground vehicles of the convoy in the current logic frame. False when none is left.
Bool getCameraTestConvoyCenter(Coord2D *center)
{
	const CameraTestState &s = s_cameraTest;
	Coord2D sum = { 0.0f, 0.0f };
	Int count = 0;

	for (Int i = 0; i < s.groundCount; ++i)
	{
		const Object *obj = TheGameLogic->findObjectByID(s.convoy[i]);
		if (obj == nullptr || obj->isEffectivelyDead())
			continue;
		sum.x += obj->getPosition()->x;
		sum.y += obj->getPosition()->y;
		++count;
	}

	if (count == 0)
		return FALSE;

	center->x = sum.x / count;
	center->y = sum.y / count;
	return TRUE;
}

/// Camera pivot that follows the convoy. The convoy center is sampled once per logic frame and blended
/// between the last two samples by the logic frame phase, so the camera glides at any render rate and
/// never steps at the logic rate, whether SmoothMotion is on or off. A short exponential follow then
/// absorbs the jump when a vehicle of the convoy is lost. False when there is nothing to follow.
Bool getCameraTestFollowPivot(Real deltaSeconds, Coord2D *pivot)
{
	CameraTestState &s = s_cameraTest;

	const UnsignedInt frame = TheGameLogic->getFrame();
	if (!s.hasCentroid || frame != s.sampleFrame)
	{
		Coord2D center;
		if (getCameraTestConvoyCenter(&center))
		{
			s.prevCentroid = s.hasCentroid ? s.curCentroid : center;
			s.curCentroid = center;
			s.hasCentroid = TRUE;
		}
		else if (s.hasCentroid)
		{
			s.prevCentroid = s.curCentroid;
		}
		s.sampleFrame = frame;
	}

	if (!s.hasCentroid)
		return FALSE;

	const Real phase = clamp(0.0f, TheFramePacer->getLogicFramePhase(), 1.0f);
	Coord2D target;
	target.x = s.prevCentroid.x + (s.curCentroid.x - s.prevCentroid.x) * phase;
	target.y = s.prevCentroid.y + (s.curCentroid.y - s.prevCentroid.y) * phase;

	if (!s.hasFollowPivot)
	{
		s.followPivot = target;
		s.hasFollowPivot = TRUE;
	}
	else
	{
		const Real follow = 1.0f - expf(-max(deltaSeconds, 0.0f) / CameraTestFollowSeconds);
		s.followPivot.x += (target.x - s.followPivot.x) * follow;
		s.followPivot.y += (target.y - s.followPivot.y) * follow;
	}

	*pivot = s.followPivot;
	return TRUE;
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
	Real distanceToCenter = 0.0f;
	if (TheTerrainLogic != nullptr)
	{
		Region3D extent;
		TheTerrainLogic->getExtent(&extent);
		Coord2D toCenter;
		toCenter.x = (extent.lo.x + extent.hi.x) * 0.5f - s.startPos.x;
		toCenter.y = (extent.lo.y + extent.hi.y) * 0.5f - s.startPos.y;
		if (toCenter.lengthSqr() > 1.0f)
		{
			distanceToCenter = toCenter.length();
			toCenter.normalize();
			s.panDir = toCenter;
		}
	}

	fprintf(stderr, "[CAMTEST] start: pivot (%.1f, %.1f), pan %.1f s towards (%.2f, %.2f), zoom-out %.1f s\n",
		s.startPos.x, s.startPos.y, TheGlobalData->m_cameraTestSeconds, s.panDir.x, s.panDir.y, CameraTestZoomOutSeconds);
	fflush(stderr);

	// The convoy drives from near the start position to about the map center
	spawnCameraTestConvoy(distanceToCenter);
	s.hasCentroid = FALSE;
	s.hasFollowPivot = FALSE;
}

/// Places the camera for the given flight time. Every value except the convoy follow is set directly
/// (no easing towards it), so the camera turn and zoom only depend on the time, never on the frame rate.
void applyCameraTestPose(Real flightSeconds, Real deltaSeconds)
{
	const CameraTestState &s = s_cameraTest;
	const Real panSeconds = TheGlobalData->m_cameraTestSeconds;

	const Real panTime = min(flightSeconds, panSeconds);
	const Real zoomTime = clamp(0.0f, flightSeconds - panSeconds, CameraTestZoomOutSeconds);
	const Real zoomFactor = zoomTime / CameraTestZoomOutSeconds;

	Coord2D pivot2D;
	if (!getCameraTestFollowPivot(deltaSeconds, &pivot2D))
	{
		// No convoy: fixed pan from the start position towards the map center
		pivot2D.x = s.startPos.x + s.panDir.x * CameraTestPanSpeed * panTime;
		pivot2D.y = s.startPos.y + s.panDir.y * CameraTestPanSpeed * panTime;
	}

	Coord3D pivot;
	pivot.x = pivot2D.x;
	pivot.y = pivot2D.y;
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
		s.groundCount = 0;
		s.convoyCount = 0;
		s.hasCentroid = FALSE;
		s.hasFollowPivot = FALSE;
		return;
	}

	if (s.phase == CAMERA_TEST_DONE)
		return;

	if (s.phase == CAMERA_TEST_IDLE)
	{
		s.phase = CAMERA_TEST_SETTLING;
		s.elapsedSeconds = 0.0f;
		fprintf(stderr, "[CAMTEST] match started, flight begins at logic frame %u\n", CameraTestSettleFrames);
		fflush(stderr);
		Platform::SetProcessEnvironmentVariable(CameraTestCaptureSignal, CameraTestCapturePrepare);
		return;
	}

	// Real time of the frame about to be drawn, measured by the frame pacer
	const Real deltaSeconds = TheFramePacer->getUpdateTime();
	s.elapsedSeconds += deltaSeconds;

	if (s.phase == CAMERA_TEST_SETTLING)
	{
		if (TheGameLogic->getFrame() < CameraTestSettleFrames)
			return;

		s.elapsedSeconds = CameraTestSettleSeconds;

		beginCameraTestFlight();
		s.phase = CAMERA_TEST_FLYING;

		// The frame drawn right after this update shows the first pose of the flight
		Platform::SetProcessEnvironmentVariable(CameraTestCaptureSignal, CameraTestCaptureStart);
		fprintf(stderr, "[CAMTEST] capture signal: %s=%s\n", CameraTestCaptureSignal, CameraTestCaptureStart);
		fflush(stderr);
	}

	const Real flightSeconds = s.elapsedSeconds - CameraTestSettleSeconds;
	const Real totalSeconds = TheGlobalData->m_cameraTestSeconds + CameraTestZoomOutSeconds;

	applyCameraTestPose(min(flightSeconds, totalSeconds), deltaSeconds);

	if (flightSeconds >= totalSeconds)
	{
		s.phase = CAMERA_TEST_DONE;
		if (s.hasCentroid)
		{
			const Real travelled = (s.curCentroid.x - s.startPos.x) * s.panDir.x + (s.curCentroid.y - s.startPos.y) * s.panDir.y;
			fprintf(stderr, "[CAMTEST] convoy: center (%.1f, %.1f), %.1f along the pan direction from the start position\n",
				s.curCentroid.x, s.curCentroid.y, travelled);
			fflush(stderr);
		}
		fprintf(stderr, "[CAMTEST] stop: flight finished after %.2f s\n", flightSeconds);
		fflush(stderr);
	}
}
