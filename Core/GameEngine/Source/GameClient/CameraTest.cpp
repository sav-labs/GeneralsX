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
// GeneralsX @feature Claude 15/10/2026 Close-up flight (-camclose or -camtest [seconds] close): the camera stays below
// the minimum zoom height with a lower pitch, moves along the convoy and then glides past the local player's base
// buildings, so unit and building textures and edge antialiasing fill the screen in A/B recordings. Its timeline is
// counted in logic frames (plus the render phase inside the frame), so runs with the same -seed show the same views.
// It only moves the camera; the convoy spawn is the one the regular flight already does.
// GeneralsX @feature Claude 16/10/2026 Battle flight (-camtest [seconds] battle [units] [night]): instead of the convoy, a
// column of the local player's side and a column of the first enemy player's side spawn facing each other on open ground
// in front of the local start position and attack-move through each other, one structure near the fight is damaged to
// 30% health so it burns and smokes, and the camera orbits the middle of the battle line at a medium-low height. "night"
// switches the match to night when it starts. Like the convoy, this changes the match and only happens with -camtest.
// GeneralsX @feature Claude 18/10/2026 Infantry flight (-camtest [seconds] infantry [units]): the same facing columns,
// but both sides are filled with their infantry squad instead of vehicles, no helicopters or support units, in a tight
// open-ground formation, and the orbit holds lower and closer so the small infantry fills the frame. Daytime unless
// "night" is also given. It reuses the battle spawn and orbit, so it too needs an enemy player and only runs with -camtest.
// GeneralsX @feature Claude 19/10/2026 USA lineup flight (-camtest [seconds] usa): instead of the convoy or the battle, one
// of each USA vehicle spawns stationary in a single row in front of the local start position, every unit facing the camera
// and given no order so there is no driving, combat or smoke, and the camera dollies low and close along the row so each
// detailed model fills the frame in daylight. For framing the detailed-model work; like the convoy it changes the match and
// only happens with -camtest.

#include "PreRTS.h"	// This must go first in EVERY cpp file in the GameEngine

#include "GameClient/CameraTest.h"

#include "Common/FramePacer.h"
#include "Common/GlobalData.h"
#include "Common/Player.h"
#include "Common/PlayerList.h"
#include "Common/PlayerTemplate.h"
#include "Common/ThingFactory.h"
#include "Common/ThingTemplate.h"
#include "GameClient/Drawable.h"
#include "GameClient/GameClient.h"
#include "GameClient/View.h"
#include "GameLogic/AI.h"
#include "GameLogic/Damage.h"
#include "GameLogic/GameLogic.h"
#include "GameLogic/Module/AIUpdate.h"
#include "GameLogic/Module/BodyModule.h"
#include "GameLogic/Object.h"
#include "GameLogic/PartitionManager.h"
#include "GameLogic/TerrainLogic.h"
#include "GameLogic/Weapon.h"
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

// GeneralsX @feature Claude 15/10/2026 Close-up flight. Durations are for -camtest 8 and scale with the given seconds,
// so the default close-up flight lasts 10 seconds: 5 along the convoy, then 2.5 for each of two buildings.
constexpr const Real CameraTestCloseReferenceSeconds = 8.0f;		///< -camtest duration the close-up timings below are given for
constexpr const Real CameraTestCloseConvoySeconds = 5.0f;			///< Time along the convoy
constexpr const Real CameraTestCloseGlideSeconds = 1.25f;			///< Glide from the previous shot to a building
constexpr const Real CameraTestCloseHoldSeconds = 1.25f;			///< Time circling a building
constexpr const Int CameraTestCloseMaxTargets = 2;						///< Buildings visited after the convoy
constexpr const Real CameraTestCloseHeightScale = 0.6f;				///< Camera height as a fraction of the minimum zoom height
constexpr const Real CameraTestCloseMinHeight = 40.0f;				///< Lowest camera height above the ground
constexpr const Real CameraTestCloseBuildingHeightScale = 1.1f;	///< Camera height over a building per unit of its bounding radius
constexpr const Real CameraTestClosePitch = DEG_TO_RADF(24.0f);	///< Lower than the default 37.5, so the view looks across the units
constexpr const Real CameraTestCloseOrbitSpeed = DEG_TO_RADF(9.0f);	///< Camera yaw change per second, the whole flight
constexpr const Real CameraTestCloseSearchRadius = 450.0f;		///< Buildings are picked within this distance of the start position
constexpr const Real CameraTestCloseMinRadius = 12.0f;				///< Skips fences and small props

// GeneralsX @feature Claude 16/10/2026 Battle flight. The unit count of -camtest battle <units> is the whole scene, split
// evenly between the two sides.
constexpr const Int CameraTestBattleDefaultPerSide = 10;			///< Units per side when no count is given
constexpr const Int CameraTestBattleMinPerSide = 4;
constexpr const Int CameraTestBattleMaxPerSide = 60;
constexpr const Int CameraTestBattleAirCount = 2;						///< Helicopters per side, when the side has one
constexpr const Int CameraTestBattleAirMinPerSide = 8;				///< Smaller columns get no helicopters
constexpr const Int CameraTestBattleSupportPercent = 30;			///< Share of artillery and rocket units in the rear rows
constexpr const Int CameraTestBattleMinWidth = 3;						///< Units per row across the battle line
constexpr const Int CameraTestBattleMaxWidth = 8;
constexpr const Real CameraTestBattleGap = 280.0f;						///< Distance between the two front rows at spawn
constexpr const Real CameraTestBattleRowSpacing = 40.0f;
constexpr const Real CameraTestBattleColumnSpacing = 40.0f;
constexpr const Real CameraTestBattleMapMargin = 150.0f;			///< The battle center keeps this far from the map edges
constexpr const Real CameraTestBattleBuildingRadius = 700.0f;	///< The burning structure is picked within this distance of the battle center
constexpr const Real CameraTestBattleBuildingHealth = 0.3f;		///< Health fraction left to the burning structure
constexpr const Real CameraTestBattleOrbitSpeed = DEG_TO_RADF(8.0f);	///< Camera yaw change per second around the battle center
constexpr const Real CameraTestBattleEndHeightScale = 0.8f;		///< Final camera height as a fraction of the minimum zoom height
constexpr const Real CameraTestBattlePitch = DEG_TO_RADF(30.0f);	///< Final pitch, lower than the default 37.5

// GeneralsX @feature Claude 18/10/2026 Infantry flight. Squads stand in a tight open-ground formation, no helicopters or
// support rows, and the camera orbits lower and closer so the small infantry fills the frame.
constexpr const Real CameraTestInfantryGap = 130.0f;				///< Distance between the two infantry fronts at spawn
constexpr const Real CameraTestInfantryRowSpacing = 24.0f;
constexpr const Real CameraTestInfantryColumnSpacing = 24.0f;
constexpr const Real CameraTestInfantryHeightScale = 0.5f;		///< Infantry orbit height as a fraction of the battle height

// GeneralsX @feature Claude 19/10/2026 USA lineup flight. One stationary row of vehicles, the camera dollies along it.
constexpr const Int CameraTestLineupMax = 12;							///< Upper bound on vehicles in the row
constexpr const Real CameraTestLineupSpacing = 60.0f;				///< Distance between neighbouring vehicles along the row
constexpr const Real CameraTestLineupLead = 170.0f;					///< Distance of the row ahead of the start position, towards the map center
constexpr const Real CameraTestLineupHeightScale = 0.55f;		///< Camera height as a fraction of the minimum zoom height
constexpr const Real CameraTestLineupMinHeight = 45.0f;			///< Lowest camera height above the ground
constexpr const Real CameraTestLineupPitch = DEG_TO_RADF(22.0f);	///< Lower than the default 37.5, so the view looks across the vehicles
constexpr const Real CameraTestLineupMargin = 0.65f;				///< The dolly starts and ends this far short of the row ends, so no shot is half a vehicle

/// GeneralsX @feature Claude 19/10/2026 The detailed USA vehicles, in display order. Each row lists the retail ThingTemplate
/// names (in HD this slot draws the detailed model) with fallbacks, so a name the game does not know is skipped.
struct CameraTestLineupUnit
{
	const char *preferred;
	const char *fallback1;
	const char *fallback2;
};

const CameraTestLineupUnit CameraTestUsaLineup[] =
{
	{ "AmericaTankCrusader", "", "" },											///< Abrams (AVLeopard slot)
	{ "AmericaVehicleMicrowaveTank", "AmericaVehicleMicrowave", "" },	///< Stryker (AVTHUNDRBLT slot)
	{ "AmericaTankPaladin", "AmericaVehiclePaladin", "" },			///< M109 (AVPaladin slot)
	{ "AmericaVehicleTomahawk", "", "" },										///< M270 MLRS (AVTomahawk slot)
	{ "AmericaVehicleAvenger", "", "" },										///< Avenger (AVAVNGER slot)
	{ "AmericaVehicleHumvee", "", "" },											///< JLTV (AVHUMMER slot)
	{ "AmericaVehicleAmbulance", "AmericaVehicleMedic", "" },		///< Ambulance (AVAmbulance slot)
	{ "AmericaVehicleDozer", "AmericaDozer", "AmericaVehicleBulldozer" },	///< Dozer (AVCONSTDOZ slot)
};

// GeneralsX @feature Claude 15/10/2026 Signal for the DXVK video capture started with DXVK_CAPTURE_VIDEO_START=camtest.
// DXVK reads the process environment on every present while it waits: the prepare value starts the encoder when the
// match starts, the event value starts recording with the first frame of the flight. It only affects rendering tools.
constexpr const char *CameraTestCaptureSignal = "DXVK_CAPTURE_VIDEO_SIGNAL";
constexpr const char *CameraTestCapturePrepare = "camtest.prepare";
constexpr const char *CameraTestCaptureStart = "camtest";

/// Templates of one side: a main battle tank, a fast vehicle and a helicopter (empty when there is none).
// GeneralsX @feature Claude 16/10/2026 Plus the artillery and rocket units the battle flight puts in its rear rows
// (retail template names; a name the game does not know is skipped, America has the Tomahawk for both).
// GeneralsX @feature Claude 18/10/2026 "infantry" holds the squad template the infantry flight fills both columns with.
struct CameraTestSideUnits
{
	const char *baseSide;
	const char *tank;
	const char *fast;
	const char *air;
	const char *artillery;
	const char *rocket;
	const char *infantry;
};

const CameraTestSideUnits CameraTestSides[] =
{
	{ "America", "AmericaTankCrusader", "AmericaVehicleHumvee", "AmericaVehicleComanche", "AmericaVehicleTomahawk", "", "AmericaInfantryRanger" },
	{ "China", "ChinaTankBattleMaster", "ChinaTankGattling", "ChinaVehicleHelix", "ChinaVehicleInfernoCannon", "ChinaVehicleNukeLauncher", "ChinaInfantryRedguard" },
	{ "GLA", "GLATankScorpion", "GLAVehicleTechnical", "", "GLAVehicleScudLauncher", "GLAVehicleRocketBuggy", "GLAInfantryRebel" },
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

	// GeneralsX @feature Claude 15/10/2026 Close-up flight state
	UnsignedInt flightFrame;								///< Logic frame the flight began on
	Coord2D closeTarget[CameraTestCloseMaxTargets];		///< Buildings visited after the convoy
	Real closeTargetHeight[CameraTestCloseMaxTargets];
	AsciiString closeTargetName[CameraTestCloseMaxTargets];
	Int closeTargetCount;
	Int closeShot;													///< Last logged shot, -1 before the first

	// GeneralsX @feature Claude 16/10/2026 Battle flight state
	Bool battle;														///< The battle was spawned, the camera orbits battleCenter
	Coord2D battleCenter;										///< Middle of the two front rows at spawn
	ObjectID battleUnits[2][CameraTestBattleMaxPerSide];	///< Local column, enemy column
	Int battleCount[2];

	// GeneralsX @feature Claude 19/10/2026 USA lineup flight state
	Bool lineup;														///< The lineup was spawned, the camera dollies along it
	Coord2D lineupCenter;										///< Middle of the row
	Coord2D lineupDir;											///< Unit direction along the row (the camera's "right")
	Real lineupHalf;												///< Half the length of the row
	ObjectID lineupUnits[CameraTestLineupMax];	///< Spawned vehicles, left to right
	Int lineupCount;
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
// GeneralsX @feature Claude 16/10/2026 attackMove gives an attack-move order instead, so the battle columns shoot what
// they meet on the way.
// GeneralsX @feature Claude 19/10/2026 hold gives no order at all, so the lineup vehicles keep their spawn position and
// facing and do not drive or fight.
Object *spawnCameraTestUnit(const ThingTemplate *thingTemplate, Team *team, const Coord2D &pos, Real angle, const Coord2D &dest,
	Bool attackMove = FALSE, Bool hold = FALSE)
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
	if (ai != nullptr && !hold)
	{
		Coord3D moveTo;
		moveTo.x = dest.x;
		moveTo.y = dest.y;
		moveTo.z = TheTerrainLogic->getGroundHeight(dest.x, dest.y);
		if (attackMove)
			ai->aiAttackMoveToPosition(&moveTo, NO_MAX_SHOTS_LIMIT, CMD_FROM_PLAYER);
		else
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
// GeneralsX @refactor Claude 15/10/2026 The sampled and interpolated convoy center is shared with the close-up flight.
/// Convoy center sampled once per logic frame and blended between the last two samples by the logic frame
/// phase. It only depends on the logic state and the phase, never on the render rate. False when there is no convoy.
Bool getCameraTestConvoyPivot(Coord2D *pivot)
{
	CameraTestState &s = s_cameraTest;

	const UnsignedInt frame = TheGameLogic->getFrame();
	if (!s.hasCentroid || frame != s.sampleFrame)
	{
		Coord2D center;
		if (getCameraTestConvoyCenter(&center))
		{
			// After a skipped logic frame the previous sample is too old to blend from
			const Bool consecutive = s.hasCentroid && frame == s.sampleFrame + 1;
			s.prevCentroid = consecutive ? s.curCentroid : center;
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
	pivot->x = s.prevCentroid.x + (s.curCentroid.x - s.prevCentroid.x) * phase;
	pivot->y = s.prevCentroid.y + (s.curCentroid.y - s.prevCentroid.y) * phase;
	return TRUE;
}

Bool getCameraTestFollowPivot(Real deltaSeconds, Coord2D *pivot)
{
	CameraTestState &s = s_cameraTest;

	Coord2D target;
	if (!getCameraTestConvoyPivot(&target))
		return FALSE;

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

/// GeneralsX @feature Claude 15/10/2026 Picks the buildings the close-up flight visits after the convoy: the local
/// player's command center first, then the nearest other structures around the start position that the player owns
/// or can see. Only reads the world; ties are broken by object ID so every run picks the same buildings.
void chooseCameraTestCloseTargets()
{
	CameraTestState &s = s_cameraTest;
	s.closeTargetCount = 0;

	if (TheGameLogic == nullptr || ThePlayerList == nullptr)
		return;

	const Player *player = ThePlayerList->getLocalPlayer();
	if (player == nullptr)
		return;
	const Int playerIndex = player->getPlayerIndex();

	struct Candidate
	{
		const Object *obj;
		Int rank;				///< 0 own command center, 1 own structure, 2 visible structure of another player
		Real distSqr;
	};
	Candidate best[CameraTestCloseMaxTargets];
	Int bestCount = 0;

	const Real searchSqr = CameraTestCloseSearchRadius * CameraTestCloseSearchRadius;
	for (Object *obj = TheGameLogic->getFirstObject(); obj != nullptr; obj = obj->getNextObject())
	{
		if (obj->isEffectivelyDead() || !obj->isKindOf(KINDOF_STRUCTURE)
			|| obj->isKindOf(KINDOF_BRIDGE) || obj->isKindOf(KINDOF_BRIDGE_TOWER) || obj->isKindOf(KINDOF_WALK_ON_TOP_OF_WALL))
			continue;
		if (obj->getGeometryInfo().getBoundingCircleRadius() < CameraTestCloseMinRadius)
			continue;

		const Real dx = obj->getPosition()->x - s.startPos.x;
		const Real dy = obj->getPosition()->y - s.startPos.y;
		const Real distSqr = dx * dx + dy * dy;
		if (distSqr > searchSqr)
			continue;

		Candidate c;
		c.obj = obj;
		c.distSqr = distSqr;
		if (obj->getControllingPlayer() == player)
		{
			c.rank = obj->isKindOf(KINDOF_COMMANDCENTER) ? 0 : 1;
		}
		else
		{
			const ObjectShroudStatus shroud = obj->getShroudedStatus(playerIndex);
			if (shroud != OBJECTSHROUD_CLEAR && shroud != OBJECTSHROUD_PARTIAL_CLEAR)
				continue;
			c.rank = 2;
		}

		// Insertion into the short sorted list of the best candidates
		Int at = bestCount;
		while (at > 0)
		{
			const Candidate &prev = best[at - 1];
			const Bool before = c.rank != prev.rank ? c.rank < prev.rank
				: c.distSqr != prev.distSqr ? c.distSqr < prev.distSqr
				: c.obj->getID() < prev.obj->getID();
			if (!before)
				break;
			--at;
		}
		if (at >= CameraTestCloseMaxTargets)
			continue;
		for (Int i = min(bestCount, CameraTestCloseMaxTargets - 1); i > at; --i)
			best[i] = best[i - 1];
		best[at] = c;
		bestCount = min(bestCount + 1, CameraTestCloseMaxTargets);
	}

	const Real closeHeight = max(s.minHeight * CameraTestCloseHeightScale, CameraTestCloseMinHeight);
	for (Int i = 0; i < bestCount; ++i)
	{
		const Object *obj = best[i].obj;
		s.closeTarget[i].x = obj->getPosition()->x;
		s.closeTarget[i].y = obj->getPosition()->y;
		// Large buildings get a little more height, never above the minimum zoom height
		const Real wanted = obj->getGeometryInfo().getBoundingCircleRadius() * CameraTestCloseBuildingHeightScale;
		s.closeTargetHeight[i] = clamp(closeHeight, wanted, max(closeHeight, s.minHeight));
		s.closeTargetName[i] = obj->getTemplate()->getName();
		fprintf(stderr, "[CAMTEST] close target %d: %s at (%.1f, %.1f), height %.1f\n",
			i, s.closeTargetName[i].str(), s.closeTarget[i].x, s.closeTarget[i].y, s.closeTargetHeight[i]);
		fflush(stderr);
	}
	s.closeTargetCount = bestCount;
}

/// GeneralsX @feature Claude 15/10/2026 Smooth start and stop of a glide.
Real getCameraTestSmoothStep(Real t)
{
	const Real x = clamp(0.0f, t, 1.0f);
	return x * x * (3.0f - 2.0f * x);
}

/// GeneralsX @feature Claude 16/10/2026 Units per side of the battle flight: half the -camtest battle count, clamped.
Int getCameraTestBattlePerSide()
{
	const Int units = TheGlobalData->m_cameraTestBattleUnits;
	if (units <= 0)
		return CameraTestBattleDefaultPerSide;
	return clamp(CameraTestBattleMinPerSide, (units + 1) / 2, CameraTestBattleMaxPerSide);
}

/// GeneralsX @feature Claude 16/10/2026 Layout of one battle column: helicopters, ground units, units per row and rows.
struct CameraTestBattleLayout
{
	Int air;
	Int ground;
	Int width;
	Int rows;
};

CameraTestBattleLayout getCameraTestBattleLayout(Int perSide, Bool hasAir)
{
	CameraTestBattleLayout layout;
	layout.air = (hasAir && perSide >= CameraTestBattleAirMinPerSide) ? CameraTestBattleAirCount : 0;
	layout.ground = perSide - layout.air;
	// About one and a half times as wide as deep
	layout.width = CameraTestBattleMinWidth;
	while (layout.width < CameraTestBattleMaxWidth && layout.width * layout.width < layout.ground * 3 / 2)
		++layout.width;
	layout.rows = (layout.ground + layout.width - 1) / layout.width;
	return layout;
}

/// GeneralsX @feature Claude 16/10/2026 The first active player the local player considers an enemy, by player index.
Player *findCameraTestEnemyPlayer(const Player *localPlayer)
{
	for (Int i = 0; i < ThePlayerList->getPlayerCount(); ++i)
	{
		Player *player = ThePlayerList->getNthPlayer(i);
		if (player == nullptr || player == localPlayer || !player->isPlayerActive())
			continue;
		const Team *team = player->getDefaultTeam();
		if (team != nullptr && localPlayer->getRelationship(team) == ENEMIES)
			return player;
	}
	return nullptr;
}

/// GeneralsX @feature Claude 16/10/2026 Spawns one battle column. Its front row lies gap/2 before the center, against
/// toEnemy, the rows extend backwards, tanks and fast vehicles lead, artillery and rocket units fill the rear rows and the
/// helicopters fly in behind the flanks. Every unit attack-moves to its mirror image behind the other column.
Int spawnCameraTestBattleColumn(Player *player, const Coord2D &center, const Coord2D &toEnemy, ObjectID *ids,
	AsciiString *summary)
{
	Team *team = player->getDefaultTeam();
	if (team == nullptr)
		return 0;

	// GeneralsX @feature Claude 18/10/2026 Infantry mode fills both front and rear rows with the side's infantry squad,
	// drops the helicopters and support units, and packs the formation tighter so the squads read as a close line.
	const Bool isInfantry = TheGlobalData->m_cameraTestInfantry;
	const CameraTestSideUnits &side = getCameraTestSideUnits(player);
	const ThingTemplate *infantry = isInfantry
		? findCameraTestTemplate(side.infantry, CameraTestSides[0].infantry, nullptr) : nullptr;
	const ThingTemplate *tank = isInfantry ? infantry : findCameraTestTemplate(side.tank, side.fast, CameraTestSides[0].tank);
	const ThingTemplate *fast = isInfantry ? infantry : findCameraTestTemplate(side.fast, side.tank, CameraTestSides[0].fast);
	const ThingTemplate *air = isInfantry ? nullptr : findCameraTestTemplate(side.air, nullptr, nullptr);
	const ThingTemplate *artillery = isInfantry ? nullptr : findCameraTestTemplate(side.artillery, side.rocket, nullptr);
	const ThingTemplate *rocket = isInfantry ? nullptr : findCameraTestTemplate(side.rocket, side.artillery, nullptr);

	const Real gap = isInfantry ? CameraTestInfantryGap : CameraTestBattleGap;
	const Real rowSpacing = isInfantry ? CameraTestInfantryRowSpacing : CameraTestBattleRowSpacing;
	const Real colSpacing = isInfantry ? CameraTestInfantryColumnSpacing : CameraTestBattleColumnSpacing;

	const CameraTestBattleLayout layout = getCameraTestBattleLayout(getCameraTestBattlePerSide(), air != nullptr);
	const Int support = artillery != nullptr ? layout.ground * CameraTestBattleSupportPercent / 100 : 0;
	const Int front = layout.ground - support;

	Coord2D right;
	right.x = -toEnemy.y;
	right.y = toEnemy.x;
	const Real angle = toEnemy.toAngle();

	Coord2D frontRow;
	frontRow.x = center.x - toEnemy.x * gap * 0.5f;
	frontRow.y = center.y - toEnemy.y * gap * 0.5f;

	Int count = 0;
	Int counts[5] = { 0, 0, 0, 0, 0 };	// tank, fast, artillery, rocket, air
	for (Int i = 0; i < layout.ground; ++i)
	{
		const Int row = i / layout.width;
		const Int inRow = min(layout.width, layout.ground - row * layout.width);
		const Real lateral = ((Real)(i % layout.width) - (Real)(inRow - 1) * 0.5f) * colSpacing;

		Int kind;
		if (i < front)
			kind = (i % 3) == 2 ? 1 : 0;
		else
			kind = ((i - front) % 2) == 0 ? 2 : 3;
		const ThingTemplate *thingTemplate = kind == 0 ? tank : kind == 1 ? fast : kind == 2 ? artillery : rocket;
		if (thingTemplate == nullptr)
			continue;

		const Real back = rowSpacing * row;
		Coord2D pos;
		pos.x = frontRow.x - toEnemy.x * back + right.x * lateral;
		pos.y = frontRow.y - toEnemy.y * back + right.y * lateral;

		Coord2D dest;
		dest.x = pos.x + toEnemy.x * (gap + 2.0f * back);
		dest.y = pos.y + toEnemy.y * (gap + 2.0f * back);

		Object *obj = spawnCameraTestUnit(thingTemplate, team, pos, angle, dest, TRUE);
		if (obj != nullptr)
		{
			ids[count++] = obj->getID();
			++counts[kind];
		}
	}

	for (Int i = 0; i < layout.air; ++i)
	{
		const Real columnSign = (i % 2) == 0 ? -1.0f : 1.0f;
		const Real back = CameraTestBattleRowSpacing * layout.rows;
		const Real lateral = CameraTestBattleColumnSpacing * (layout.width * 0.5f + 1.0f) * columnSign;

		Coord2D pos;
		pos.x = frontRow.x - toEnemy.x * back + right.x * lateral;
		pos.y = frontRow.y - toEnemy.y * back + right.y * lateral;

		Coord2D dest;
		dest.x = pos.x + toEnemy.x * (CameraTestBattleGap + 2.0f * back);
		dest.y = pos.y + toEnemy.y * (CameraTestBattleGap + 2.0f * back);

		Object *obj = spawnCameraTestUnit(air, team, pos, angle, dest, TRUE);
		if (obj != nullptr)
		{
			ids[count++] = obj->getID();
			++counts[4];
		}
	}

	summary->format("%s %d units (%d %s, %d %s, %d %s, %d %s, %d %s)", side.baseSide, count,
		counts[0], tank != nullptr ? tank->getName().str() : "none",
		counts[1], fast != nullptr ? fast->getName().str() : "none",
		counts[2], artillery != nullptr ? artillery->getName().str() : "none",
		counts[3], rocket != nullptr ? rocket->getName().str() : "none",
		counts[4], air != nullptr ? air->getName().str() : "none");
	return count;
}

/// GeneralsX @feature Claude 16/10/2026 Damages the structure nearest the battle center to 30% health through its body
/// module, so it burns and smokes in frame. Structures of the two fighting players come first, then any other one.
/// Ties are broken by object ID so every run picks the same structure.
void burnCameraTestBattleBuilding(const Coord2D &center, const Player *localPlayer, const Player *enemyPlayer,
	AsciiString *summary)
{
	*summary = "none";

	Object *best = nullptr;
	Int bestRank = 0;
	Real bestDistSqr = 0.0f;
	const Real searchSqr = CameraTestBattleBuildingRadius * CameraTestBattleBuildingRadius;
	for (Object *obj = TheGameLogic->getFirstObject(); obj != nullptr; obj = obj->getNextObject())
	{
		if (obj->isEffectivelyDead() || !obj->isKindOf(KINDOF_STRUCTURE)
			|| obj->isKindOf(KINDOF_BRIDGE) || obj->isKindOf(KINDOF_BRIDGE_TOWER) || obj->isKindOf(KINDOF_WALK_ON_TOP_OF_WALL))
			continue;
		if (obj->getGeometryInfo().getBoundingCircleRadius() < CameraTestCloseMinRadius)
			continue;
		const BodyModuleInterface *body = obj->getBodyModule();
		if (body == nullptr || body->getMaxHealth() <= 0.0f)
			continue;

		const Real dx = obj->getPosition()->x - center.x;
		const Real dy = obj->getPosition()->y - center.y;
		const Real distSqr = dx * dx + dy * dy;
		if (distSqr > searchSqr)
			continue;

		const Player *owner = obj->getControllingPlayer();
		const Int rank = (owner == localPlayer || owner == enemyPlayer) ? 0 : 1;
		const Bool better = best == nullptr
			|| (rank != bestRank ? rank < bestRank
			: distSqr != bestDistSqr ? distSqr < bestDistSqr
			: obj->getID() < best->getID());
		if (better)
		{
			best = obj;
			bestRank = rank;
			bestDistSqr = distSqr;
		}
	}

	if (best == nullptr)
		return;

	BodyModuleInterface *body = best->getBodyModule();
	const Real maxHealth = body->getMaxHealth();
	const Real damage = body->getHealth() - maxHealth * CameraTestBattleBuildingHealth;
	if (damage > 0.0f)
	{
		DamageInfo damageInfo;
		damageInfo.in.m_damageType = DAMAGE_UNRESISTABLE;
		damageInfo.in.m_deathType = DEATH_NORMAL;
		damageInfo.in.m_sourceID = INVALID_ID;
		damageInfo.in.m_amount = damage;
		best->attemptDamage(&damageInfo);
	}

	summary->format("%s at (%.1f, %.1f), health %.0f/%.0f", best->getTemplate()->getName().str(),
		best->getPosition()->x, best->getPosition()->y, body->getHealth(), maxHealth);
}

/// GeneralsX @feature Claude 16/10/2026 Spawns the battle in front of the local start position, towards the map center.
/// False when the match has no enemy player, so the regular flight takes over.
Bool beginCameraTestBattle()
{
	CameraTestState &s = s_cameraTest;
	s.battle = FALSE;
	s.battleCount[0] = 0;
	s.battleCount[1] = 0;

	if (ThePlayerList == nullptr || TheThingFactory == nullptr || ThePartitionManager == nullptr || TheTerrainLogic == nullptr)
		return FALSE;

	Player *localPlayer = ThePlayerList->getLocalPlayer();
	if (localPlayer == nullptr || localPlayer->getDefaultTeam() == nullptr)
	{
		fprintf(stderr, "[CAMTEST] battle: no local player team\n");
		fflush(stderr);
		return FALSE;
	}

	Player *enemyPlayer = findCameraTestEnemyPlayer(localPlayer);
	if (enemyPlayer == nullptr)
	{
		fprintf(stderr, "[CAMTEST] battle: no enemy player\n");
		fflush(stderr);
		return FALSE;
	}

	// The local column's rear row stands where the regular convoy leads, the battle center lies past its front row
	// GeneralsX @feature Claude 18/10/2026 Infantry columns carry no helicopters and pack tighter, so match the layout here.
	const Bool isInfantry = TheGlobalData->m_cameraTestInfantry;
	const Bool localHasAir = !isInfantry && findCameraTestTemplate(getCameraTestSideUnits(localPlayer).air, nullptr, nullptr) != nullptr;
	const CameraTestBattleLayout localLayout = getCameraTestBattleLayout(getCameraTestBattlePerSide(), localHasAir);
	const Real rowSpacing = isInfantry ? CameraTestInfantryRowSpacing : CameraTestBattleRowSpacing;
	const Real gap = isInfantry ? CameraTestInfantryGap : CameraTestBattleGap;
	const Real lead = CameraTestConvoyLead + rowSpacing * (localLayout.rows - 1) + gap * 0.5f;

	Coord2D center;
	center.x = s.startPos.x + s.panDir.x * lead;
	center.y = s.startPos.y + s.panDir.y * lead;

	Region3D extent;
	TheTerrainLogic->getExtent(&extent);
	if (extent.hi.x - extent.lo.x > 2.0f * CameraTestBattleMapMargin && extent.hi.y - extent.lo.y > 2.0f * CameraTestBattleMapMargin)
	{
		center.x = clamp(extent.lo.x + CameraTestBattleMapMargin, center.x, extent.hi.x - CameraTestBattleMapMargin);
		center.y = clamp(extent.lo.y + CameraTestBattleMapMargin, center.y, extent.hi.y - CameraTestBattleMapMargin);
	}
	s.battleCenter = center;

	Coord2D toLocal;
	toLocal.x = -s.panDir.x;
	toLocal.y = -s.panDir.y;

	AsciiString localSummary;
	AsciiString enemySummary;
	s.battleCount[0] = spawnCameraTestBattleColumn(localPlayer, center, s.panDir, s.battleUnits[0], &localSummary);
	s.battleCount[1] = spawnCameraTestBattleColumn(enemyPlayer, center, toLocal, s.battleUnits[1], &enemySummary);

	AsciiString buildingSummary;
	burnCameraTestBattleBuilding(center, localPlayer, enemyPlayer, &buildingSummary);

	s.battle = TRUE;
	fprintf(stderr, "[CAMTEST] battle start: center (%.1f, %.1f), local %s, enemy %s (player %d), burning %s, night %s, %.1f s orbit\n",
		center.x, center.y, localSummary.str(), enemySummary.str(), enemyPlayer->getPlayerIndex(), buildingSummary.str(),
		TheGlobalData->m_timeOfDay == TIME_OF_DAY_NIGHT ? "on" : "off", TheGlobalData->m_cameraTestSeconds);
	fflush(stderr);
	return TRUE;
}

/// GeneralsX @feature Claude 16/10/2026 Live units of one battle column.
Int countCameraTestBattleAlive(Int column)
{
	const CameraTestState &s = s_cameraTest;
	Int alive = 0;
	for (Int i = 0; i < s.battleCount[column]; ++i)
	{
		const Object *obj = TheGameLogic->findObjectByID(s.battleUnits[column][i]);
		if (obj != nullptr && !obj->isEffectivelyDead())
			++alive;
	}
	return alive;
}

/// GeneralsX @feature Claude 16/10/2026 Places the battle camera for the given flight time, counted in logic frames:
/// a slow orbit around the battle center that glides from the minimum zoom height and the default pitch down to a
/// medium-low height (never below the close-up flight's height) and a lower pitch.
void applyCameraTestBattlePose(Real flightSeconds)
{
	const CameraTestState &s = s_cameraTest;
	const Real total = TheGlobalData->m_cameraTestSeconds;
	const Real blend = getCameraTestSmoothStep(total > 0.0f ? flightSeconds / total : 1.0f);

	const Real closeHeight = max(s.minHeight * CameraTestCloseHeightScale, CameraTestCloseMinHeight);
	const Real endHeight = clamp(closeHeight, s.minHeight * CameraTestBattleEndHeightScale, max(closeHeight, s.minHeight));
	Real height = s.minHeight + (endHeight - s.minHeight) * blend;
	// GeneralsX @feature Claude 18/10/2026 Infantry is small, so the orbit holds much lower to keep the squads in frame.
	if (TheGlobalData->m_cameraTestInfantry)
		height = max(CameraTestCloseMinHeight, height * CameraTestInfantryHeightScale);

	Coord3D pivot;
	pivot.x = s.battleCenter.x;
	pivot.y = s.battleCenter.y;
	pivot.z = TheTerrainLogic != nullptr ? TheTerrainLogic->getGroundHeight(pivot.x, pivot.y) : 0.0f;

	TheTacticalView->lookAt(&pivot);
	TheTacticalView->setAngle(s.startAngle + CameraTestBattleOrbitSpeed * flightSeconds);
	TheTacticalView->setPitch(s.pitch + (CameraTestBattlePitch - s.pitch) * blend);
	if (s.maxHeight > 0.0f)
	{
		// setZoom is not clamped to the minimum zoom height, so the medium-low height holds
		TheTacticalView->setZoom(height / s.maxHeight);
	}
}

/// GeneralsX @feature Claude 16/10/2026 -camtest night: switches the match to night the way the debug time of day
/// command does (global lighting, then the drawables, water, shadows and terrain through the game client).
void applyCameraTestNight()
{
	const TimeOfDay previous = TheGlobalData->m_timeOfDay;
	// GeneralsX @tweak Claude 17/10/2026 The map now loads at night (W3DTerrainLogic::loadMap). Switching again
	// mid-match would rebuild the lighting of every drawable and the terrain, which cost a 1.2 s frame.
	if (previous == TIME_OF_DAY_NIGHT)
	{
		fprintf(stderr, "[CAMTEST] night: map loaded at night\n");
		fflush(stderr);
		return;
	}
	if (!TheWritableGlobalData->setTimeOfDay(TIME_OF_DAY_NIGHT))
		return;

	if (TheGameClient != nullptr)
	{
		TheGameClient->setTimeOfDay(TheGlobalData->m_timeOfDay);
		if (TheGlobalData->m_forceModelsToFollowTimeOfDay)
		{
			for (Object *obj = TheGameLogic->getFirstObject(); obj != nullptr; obj = obj->getNextObject())
			{
				Drawable *draw = obj->getDrawable();
				if (draw != nullptr)
				{
					// Forces a refresh of the model condition, which includes the night state
					ModelConditionFlags empty;
					draw->clearAndSetModelConditionFlags(empty, empty);
				}
			}
		}
	}

	fprintf(stderr, "[CAMTEST] night: time of day %s -> %s\n",
		(previous >= TIME_OF_DAY_FIRST && previous < TIME_OF_DAY_COUNT) ? TimeOfDayNames[previous] : "unknown",
		TimeOfDayNames[TIME_OF_DAY_NIGHT]);
	fflush(stderr);
}

/// GeneralsX @feature Claude 19/10/2026 Spawns one of each USA vehicle in a single row centred ahead of the local start
/// position, every vehicle facing back towards the start position (towards the camera) and held in place so there is no
/// driving, combat or smoke. False when there is no local player team or none of the templates exist.
Bool spawnCameraTestLineup()
{
	CameraTestState &s = s_cameraTest;
	s.lineup = FALSE;
	s.lineupCount = 0;

	if (ThePlayerList == nullptr || TheThingFactory == nullptr || ThePartitionManager == nullptr || TheTerrainLogic == nullptr)
		return FALSE;

	Player *player = ThePlayerList->getLocalPlayer();
	Team *team = player != nullptr ? player->getDefaultTeam() : nullptr;
	if (team == nullptr)
	{
		fprintf(stderr, "[CAMTEST] lineup: no local player team, nothing spawned\n");
		fflush(stderr);
		return FALSE;
	}

	const Coord2D forward = s.panDir;	// start position -> map center
	Coord2D right;
	right.x = -forward.y;
	right.y = forward.x;

	// The vehicles face back towards the start position, so the camera (between the start position and the row) sees their fronts
	Coord2D back;
	back.x = -forward.x;
	back.y = -forward.y;
	const Real faceAngle = back.toAngle();

	Coord2D center;
	center.x = s.startPos.x + forward.x * CameraTestLineupLead;
	center.y = s.startPos.y + forward.y * CameraTestLineupLead;

	// Collect the templates that exist, so a missing unit just leaves a shorter row
	const ThingTemplate *templates[CameraTestLineupMax];
	Int count = 0;
	for (Int i = 0; i < ARRAY_SIZE(CameraTestUsaLineup) && count < CameraTestLineupMax; ++i)
	{
		const ThingTemplate *thingTemplate = findCameraTestTemplate(
			CameraTestUsaLineup[i].preferred, CameraTestUsaLineup[i].fallback1, CameraTestUsaLineup[i].fallback2);
		if (thingTemplate != nullptr)
			templates[count++] = thingTemplate;
	}

	if (count == 0)
	{
		fprintf(stderr, "[CAMTEST] lineup: no USA vehicle templates found, nothing spawned\n");
		fflush(stderr);
		return FALSE;
	}

	const Real half = (Real)(count - 1) * 0.5f * CameraTestLineupSpacing;
	for (Int i = 0; i < count; ++i)
	{
		const Real offset = (Real)i * CameraTestLineupSpacing - half;
		Coord2D pos;
		pos.x = center.x + right.x * offset;
		pos.y = center.y + right.y * offset;

		// dest == pos and hold == TRUE: no order is given, the vehicle keeps its spawn position and facing
		Object *obj = spawnCameraTestUnit(templates[i], team, pos, faceAngle, pos, FALSE, TRUE);
		if (obj != nullptr)
		{
			s.lineupUnits[s.lineupCount++] = obj->getID();
			fprintf(stderr, "[CAMTEST] lineup %d: %s at (%.1f, %.1f)\n", i, templates[i]->getName().str(), pos.x, pos.y);
		}
	}

	s.lineupCenter = center;
	s.lineupDir = right;
	s.lineupHalf = half;
	s.lineup = s.lineupCount > 0;

	fprintf(stderr, "[CAMTEST] lineup start: %d vehicles, center (%.1f, %.1f), spacing %.0f, facing the start position\n",
		s.lineupCount, center.x, center.y, CameraTestLineupSpacing);
	fflush(stderr);
	return s.lineup;
}

/// GeneralsX @feature Claude 19/10/2026 Dollies the camera along the row for the given flight time, counted in logic frames:
/// the pivot slides from one end of the row to the other at a low, close height with a low pitch and a fixed yaw (the default
/// start angle, which looks from the start position across the row the vehicles face), so each vehicle passes large through
/// the frame. The camera never zooms out.
void applyCameraTestLineupPose(Real flightSeconds)
{
	const CameraTestState &s = s_cameraTest;
	const Real total = TheGlobalData->m_cameraTestSeconds;
	const Real t = getCameraTestSmoothStep(total > 0.0f ? flightSeconds / total : 1.0f);

	// Slide from one end to the other, kept a little inside the ends so no shot is half a vehicle
	const Real reach = s.lineupHalf * CameraTestLineupMargin;
	const Real along = -reach + 2.0f * reach * t;

	Coord3D pivot;
	pivot.x = s.lineupCenter.x + s.lineupDir.x * along;
	pivot.y = s.lineupCenter.y + s.lineupDir.y * along;
	pivot.z = TheTerrainLogic != nullptr ? TheTerrainLogic->getGroundHeight(pivot.x, pivot.y) : 0.0f;

	const Real height = max(s.minHeight * CameraTestLineupHeightScale, CameraTestLineupMinHeight);

	TheTacticalView->lookAt(&pivot);
	TheTacticalView->setAngle(s.startAngle);
	TheTacticalView->setPitch(CameraTestLineupPitch);
	if (s.maxHeight > 0.0f)
	{
		// setZoom is not clamped to the minimum zoom height, so the close-up height holds
		TheTacticalView->setZoom(height / s.maxHeight);
	}
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

	// GeneralsX @feature Claude 19/10/2026 The USA lineup spawns one stationary row of vehicles instead of the convoy or battle
	const Bool lineup = TheGlobalData->m_cameraTestUsa && spawnCameraTestLineup();

	// GeneralsX @feature Claude 16/10/2026 The battle flight spawns two hostile columns instead of the convoy; without an
	// enemy player it falls back to the regular flight
	const Bool battle = !lineup && TheGlobalData->m_cameraTestBattle && beginCameraTestBattle();

	// The convoy drives from near the start position to about the map center
	if (!battle && !lineup)
		spawnCameraTestConvoy(distanceToCenter);
	s.hasCentroid = FALSE;
	s.hasFollowPivot = FALSE;

	// GeneralsX @feature Claude 15/10/2026 The close-up flight picks its buildings when the flight begins
	s.flightFrame = TheGameLogic->getFrame();
	s.closeShot = -1;
	s.closeTargetCount = 0;
	if (TheGlobalData->m_cameraTestClose && !battle && !lineup)
	{
		chooseCameraTestCloseTargets();
		fprintf(stderr, "[CAMTEST] close start: logic frame %u, %.1f s along the convoy, %d building(s), height %.1f (min zoom %.1f), pitch %.1f\n",
			s.flightFrame, CameraTestCloseConvoySeconds * TheGlobalData->m_cameraTestSeconds / CameraTestCloseReferenceSeconds,
			s.closeTargetCount, max(s.minHeight * CameraTestCloseHeightScale, CameraTestCloseMinHeight), s.minHeight,
			CameraTestClosePitch * 180.0f / PI);
		fflush(stderr);
	}
}

/// GeneralsX @feature Claude 15/10/2026 Length of the close-up flight in seconds.
Real getCameraTestCloseTotalSeconds()
{
	const Real scale = TheGlobalData->m_cameraTestSeconds / CameraTestCloseReferenceSeconds;
	// Without buildings the convoy shot takes the whole flight
	const Int shots = s_cameraTest.closeTargetCount > 0 ? s_cameraTest.closeTargetCount : CameraTestCloseMaxTargets;
	return scale * (CameraTestCloseConvoySeconds + shots * (CameraTestCloseGlideSeconds + CameraTestCloseHoldSeconds));
}

/// GeneralsX @feature Claude 15/10/2026 Places the close-up camera for the given flight time, counted in logic frames.
/// Shot 0 follows the convoy, then shots 1, 3, ... glide to a building and shots 2, 4, ... circle it. The camera never
/// zooms out: it stays at the close-up height (below the minimum zoom height) with a low pitch while it keeps turning.
void applyCameraTestClosePose(Real flightSeconds)
{
	CameraTestState &s = s_cameraTest;
	const Real scale = TheGlobalData->m_cameraTestSeconds / CameraTestCloseReferenceSeconds;
	const Real convoySeconds = s.closeTargetCount > 0 ? CameraTestCloseConvoySeconds * scale : getCameraTestCloseTotalSeconds();
	const Real glideSeconds = CameraTestCloseGlideSeconds * scale;
	const Real holdSeconds = CameraTestCloseHoldSeconds * scale;
	const Real closeHeight = max(s.minHeight * CameraTestCloseHeightScale, CameraTestCloseMinHeight);

	// The convoy pivot is sampled on every frame so its interpolation stays continuous into the first glide
	Coord2D convoyPivot;
	if (!getCameraTestConvoyPivot(&convoyPivot))
	{
		convoyPivot.x = s.startPos.x + s.panDir.x * CameraTestPanSpeed * flightSeconds;
		convoyPivot.y = s.startPos.y + s.panDir.y * CameraTestPanSpeed * flightSeconds;
	}

	Int shot = 0;
	Coord2D pivot2D = convoyPivot;
	Real height = closeHeight;

	if (flightSeconds >= convoySeconds && s.closeTargetCount > 0)
	{
		const Real buildingTime = flightSeconds - convoySeconds;
		const Int target = min((Int)(buildingTime / (glideSeconds + holdSeconds)), s.closeTargetCount - 1);
		const Real local = buildingTime - target * (glideSeconds + holdSeconds);

		const Coord2D from = target == 0 ? convoyPivot : s.closeTarget[target - 1];
		const Real fromHeight = target == 0 ? closeHeight : s.closeTargetHeight[target - 1];
		const Real blend = getCameraTestSmoothStep(glideSeconds > 0.0f ? local / glideSeconds : 1.0f);

		pivot2D.x = from.x + (s.closeTarget[target].x - from.x) * blend;
		pivot2D.y = from.y + (s.closeTarget[target].y - from.y) * blend;
		height = fromHeight + (s.closeTargetHeight[target] - fromHeight) * blend;
		shot = 1 + target * 2 + (local >= glideSeconds ? 1 : 0);
	}

	if (shot != s.closeShot)
	{
		s.closeShot = shot;
		const UnsignedInt frame = TheGameLogic->getFrame() - s.flightFrame;
		if (shot == 0)
		{
			fprintf(stderr, "[CAMTEST] close phase: convoy at flight frame %u, pivot (%.1f, %.1f)\n", frame, pivot2D.x, pivot2D.y);
		}
		else
		{
			const Int target = (shot - 1) / 2;
			fprintf(stderr, "[CAMTEST] close phase: %s %s at flight frame %u, pivot (%.1f, %.1f)\n",
				(shot % 2) == 1 ? "glide to" : "circle", s.closeTargetName[target].str(), frame, pivot2D.x, pivot2D.y);
		}
		fflush(stderr);
	}

	Coord3D pivot;
	pivot.x = pivot2D.x;
	pivot.y = pivot2D.y;
	pivot.z = TheTerrainLogic != nullptr ? TheTerrainLogic->getGroundHeight(pivot.x, pivot.y) : 0.0f;

	TheTacticalView->lookAt(&pivot);
	TheTacticalView->setAngle(s.startAngle + CameraTestCloseOrbitSpeed * flightSeconds);
	TheTacticalView->setPitch(CameraTestClosePitch);
	if (s.maxHeight > 0.0f)
	{
		// setZoom is not clamped to the minimum zoom height, so this temporary close-up height holds
		TheTacticalView->setZoom(height / s.maxHeight);
	}
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
		s.closeTargetCount = 0;
		s.battle = FALSE;
		s.battleCount[0] = 0;
		s.battleCount[1] = 0;
		s.lineup = FALSE;
		s.lineupCount = 0;
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
		// GeneralsX @feature Claude 16/10/2026 Night for the whole recorded flight, set before the settle wait
		if (TheGlobalData->m_cameraTestNight)
			applyCameraTestNight();
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

	// GeneralsX @feature Claude 19/10/2026 The USA lineup flight is timed in logic frames and lasts the given seconds.
	if (s.lineup)
	{
		const Real phase = clamp(0.0f, TheFramePacer->getLogicFramePhase(), 1.0f);
		const Real lineupSeconds = ((Real)(TheGameLogic->getFrame() - s.flightFrame) + phase) / (Real)LOGICFRAMES_PER_SECOND;
		const Real lineupTotal = TheGlobalData->m_cameraTestSeconds;

		applyCameraTestLineupPose(min(lineupSeconds, lineupTotal));

		if (lineupSeconds >= lineupTotal)
		{
			s.phase = CAMERA_TEST_DONE;
			fprintf(stderr, "[CAMTEST] lineup stop: flight finished after %u logic frames (%.2f s)\n",
				TheGameLogic->getFrame() - s.flightFrame, lineupSeconds);
			fflush(stderr);
		}
		return;
	}

	// GeneralsX @feature Claude 16/10/2026 The battle flight is timed like the close-up flight and lasts the given seconds.
	if (s.battle)
	{
		const Real phase = clamp(0.0f, TheFramePacer->getLogicFramePhase(), 1.0f);
		const Real battleSeconds = ((Real)(TheGameLogic->getFrame() - s.flightFrame) + phase) / (Real)LOGICFRAMES_PER_SECOND;
		const Real battleTotal = TheGlobalData->m_cameraTestSeconds;

		applyCameraTestBattlePose(min(battleSeconds, battleTotal));

		if (battleSeconds >= battleTotal)
		{
			s.phase = CAMERA_TEST_DONE;
			fprintf(stderr, "[CAMTEST] battle stop: flight finished after %u logic frames (%.2f s), alive local %d/%d, enemy %d/%d\n",
				TheGameLogic->getFrame() - s.flightFrame, battleSeconds,
				countCameraTestBattleAlive(0), s.battleCount[0], countCameraTestBattleAlive(1), s.battleCount[1]);
			fflush(stderr);
		}
		return;
	}

	// GeneralsX @feature Claude 15/10/2026 The close-up flight is timed in logic frames plus the render phase inside the
	// current frame, so a given game moment always gets the same camera pose.
	if (TheGlobalData->m_cameraTestClose)
	{
		const Real phase = clamp(0.0f, TheFramePacer->getLogicFramePhase(), 1.0f);
		const Real closeSeconds = ((Real)(TheGameLogic->getFrame() - s.flightFrame) + phase) / (Real)LOGICFRAMES_PER_SECOND;
		const Real closeTotal = getCameraTestCloseTotalSeconds();

		applyCameraTestClosePose(min(closeSeconds, closeTotal));

		if (closeSeconds >= closeTotal)
		{
			s.phase = CAMERA_TEST_DONE;
			fprintf(stderr, "[CAMTEST] close stop: flight finished after %u logic frames (%.2f s)\n",
				TheGameLogic->getFrame() - s.flightFrame, closeSeconds);
			fflush(stderr);
		}
		return;
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
