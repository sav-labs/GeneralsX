/*
**	Command & Conquer Generals Zero Hour(tm)
**	Copyright 2025 Electronic Arts Inc.
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

////////////////////////////////////////////////////////////////////////////////
//																																						//
//  (c) 2001-2003 Electronic Arts Inc.																				//
//																																						//
////////////////////////////////////////////////////////////////////////////////

// FILE: W3DTankDraw.cpp //////////////////////////////////////////////////////////////////////////
// Draw turreted tanks
// Michael S. Booth, October 2001
///////////////////////////////////////////////////////////////////////////////////////////////////

// INCLUDES ///////////////////////////////////////////////////////////////////////////////////////
#include <stdlib.h>
#include <math.h>

#include "Common/Thing.h"
#include "Common/ThingFactory.h"
#include "Common/GameAudio.h"
#include "Common/ThingTemplate.h"
#include "Common/Xfer.h"
#include "GameLogic/Weapon.h"
#include "GameLogic/GameLogic.h"
#include "GameLogic/Module/PhysicsUpdate.h"
#include "GameLogic/Module/BodyModule.h"
#include "GameLogic/ScriptEngine.h"
#include "GameLogic/Module/AIUpdate.h"
#include "GameClient/Drawable.h"
#include "GameClient/ParticleSys.h"
#include "W3DDevice/GameClient/W3DGameClient.h"
#include "W3DDevice/GameClient/Module/W3DTankDraw.h"
#include "WW3D2/matinfo.h"
#include "WW3D2/ww3d.h"
#include "WWMath/aabox.h"


class Matrix3D;

// TheSuperHackers @info Is enabled by default and therefore compatible with the Retail INI setups.
#define SHOW_DEFAULT_TANK_DEBRIS (1)

//-------------------------------------------------------------------------------------------------
W3DTankDrawModuleData::W3DTankDrawModuleData()
	: m_treadAnimationRate(0.0f)
	, m_treadPivotSpeedFraction(0.6f)
	, m_treadDriveSpeedFraction(0.3f)
{
	if constexpr (SHOW_DEFAULT_TANK_DEBRIS)
	{
		m_treadDebrisNameLeft = "TrackDebrisDirtLeft"; // TheSuperHackers @todo Remove data particle names from code
		m_treadDebrisNameRight = "TrackDebrisDirtRight";
	}
}

//-------------------------------------------------------------------------------------------------
W3DTankDrawModuleData::~W3DTankDrawModuleData()
{
}

//-------------------------------------------------------------------------------------------------
void W3DTankDrawModuleData::buildFieldParse(MultiIniFieldParse& p)
{
  W3DModelDrawModuleData::buildFieldParse(p);

	static const FieldParse dataFieldParse[] =
	{
		{ "TreadDebrisLeft", INI::parseAsciiString, nullptr, offsetof(W3DTankDrawModuleData, m_treadDebrisNameLeft) },
		{ "TreadDebrisRight", INI::parseAsciiString, nullptr, offsetof(W3DTankDrawModuleData, m_treadDebrisNameRight) },
		{ "TreadAnimationRate", INI::parseVelocityReal, nullptr, offsetof(W3DTankDrawModuleData, m_treadAnimationRate) },
		{ "TreadPivotSpeedFraction", INI::parseReal, nullptr, offsetof(W3DTankDrawModuleData, m_treadPivotSpeedFraction) },
		{ "TreadDriveSpeedFraction", INI::parseReal, nullptr, offsetof(W3DTankDrawModuleData, m_treadDriveSpeedFraction) },
		{ nullptr, nullptr, nullptr, 0 }
	};
  p.add(dataFieldParse);
}

//-------------------------------------------------------------------------------------------------
//-------------------------------------------------------------------------------------------------
W3DTankDraw::W3DTankDraw( Thing *thing, const ModuleData* moduleData )
: W3DModelDraw( thing, moduleData )
, m_prevRenderObj(nullptr)
{
	std::fill(m_treadDebrisIDs, m_treadDebrisIDs + ARRAY_SIZE(m_treadDebrisIDs), INVALID_PARTICLE_SYSTEM_ID);

	for (Int i=0; i<MAX_TREADS_PER_TANK; i++)
		m_treads[i].m_robj = nullptr;

	m_treadCount=0;
	m_gearCount = 0;
	for (Int i = 0; i < MAX_SCAN_BONES; i++)
		m_scanBones[i] = 0;
	for (Int i = 0; i < MAX_ANTENNA_BONES; i++)
		m_antennaBones[i] = 0;
	m_treadTravel[0] = m_treadTravel[1] = 0.0f;
	m_lastTreadU[0] = m_lastTreadU[1] = 0.0f;
	m_antennaAngle = 0.0f;
	m_antennaRate = 0.0f;
	m_lastSpeed = 0.0f;
	//Assume all things face along x axis when created.
	m_lastDirection.x=1.0f;
	m_lastDirection.y=0.0f;
	m_lastDirection.z=0.0f;

}

//-------------------------------------------------------------------------------------------------
//-------------------------------------------------------------------------------------------------
void W3DTankDraw::tossTreadEmitters()
{
	for (size_t i = 0; i < ARRAY_SIZE(m_treadDebrisIDs); ++i)
	{
		if (ParticleSystem *particleSys = TheParticleSystemManager->findParticleSystem(m_treadDebrisIDs[i]))
		{
			particleSys->attachToObject(nullptr);
			particleSys->destroy();
		}
		m_treadDebrisIDs[i] = INVALID_PARTICLE_SYSTEM_ID;
	}
}

//-------------------------------------------------------------------------------------------------
//-------------------------------------------------------------------------------------------------
static ParticleSystemID createParticleSystem( const AsciiString &name, const Drawable *drawable )
{
	const ParticleSystemTemplate *sysTemplate = TheParticleSystemManager->findTemplate(name);
	ParticleSystem *particleSys = TheParticleSystemManager->createParticleSystem( sysTemplate );
	if (!particleSys)
		return INVALID_PARTICLE_SYSTEM_ID;

	particleSys->attachToDrawable(drawable);
	// important: mark it as do-not-save, since we'll just re-create it when we reload.
	particleSys->setSaveable(FALSE);
	// they come into being stopped.
	particleSys->stop();

	return particleSys->getSystemID();
}

void W3DTankDraw::createTreadEmitters()
{
	if (getW3DTankDrawModuleData())
	{
		static_assert(ARRAY_SIZE(m_treadDebrisIDs) == 2, "m_treadDebrisIDs array size is expected to be 2");

		if (m_treadDebrisIDs[0] == INVALID_PARTICLE_SYSTEM_ID)
		{
			m_treadDebrisIDs[0] = createParticleSystem(getW3DTankDrawModuleData()->m_treadDebrisNameLeft, getDrawable());
		}
		if (m_treadDebrisIDs[1] == INVALID_PARTICLE_SYSTEM_ID)
		{
			m_treadDebrisIDs[1] = createParticleSystem(getW3DTankDrawModuleData()->m_treadDebrisNameRight, getDrawable());
		}
	}
}

//-------------------------------------------------------------------------------------------------
//-------------------------------------------------------------------------------------------------
W3DTankDraw::~W3DTankDraw()
{
	// TheSuperHackers @fix Mauller 16/04/2025 Delete particle systems
	tossTreadEmitters();

	for (Int i=0; i<MAX_TREADS_PER_TANK; i++)
		if (m_treads[i].m_robj)
			REF_PTR_RELEASE(m_treads[i].m_robj);
}

//-------------------------------------------------------------------------------------------------
//-------------------------------------------------------------------------------------------------
void W3DTankDraw::stopMoveDebris()
{
	for (size_t i = 0; i < ARRAY_SIZE(m_treadDebrisIDs); ++i)
	{
		if (ParticleSystem *particleSys = TheParticleSystemManager->findParticleSystem(m_treadDebrisIDs[i]))
		{
			particleSys->stop();
		}
	}
}

//-------------------------------------------------------------------------------------------------
void W3DTankDraw::setHidden(Bool h)
{
	W3DModelDraw::setHidden(h);
	if (h)
	{
		stopMoveDebris();
	}
}

//-------------------------------------------------------------------------------------------------
void W3DTankDraw::setFullyObscuredByShroud(Bool fullyObscured)
{
	if (fullyObscured != getFullyObscuredByShroud())
	{
		if (fullyObscured)
			stopMoveDebris();
	}
	W3DModelDraw::setFullyObscuredByShroud(fullyObscured);
}

/**Update uv coordinates on each tread object to simulate movement*/
void W3DTankDraw::updateTreadPositions(Real uvDelta)
{
	Real offset_u;
	TreadObjectInfo *pTread=m_treads;

	for (Int i=0; i<m_treadCount; i++)
	{
		if (pTread->m_type == TREAD_LEFT)	//this tread needs to scroll forwards
			offset_u = pTread->m_materialSettings.customUVOffset.X + uvDelta;
		else
		if (pTread->m_type == TREAD_RIGHT)	//this tread needs to scroll backwards
			offset_u = pTread->m_materialSettings.customUVOffset.X - uvDelta;
		else
		{
			DEBUG_CRASH(("Unhandled case in W3DTankDraw::updateTreadPositions"));
			offset_u = 0.0f;
		}

		// ensure coordinates of offset are in [0, 1] range:
		offset_u = offset_u - WWMath::Floor(offset_u);
		pTread->m_materialSettings.customUVOffset.Set(offset_u,0);
		pTread++;
	}
}

/**Grab pointers to the sub-meshes for each tread*/
void W3DTankDraw::updateTreadObjects()
{
	RenderObjClass *robj=getRenderObject();

	//clear all previous tread pointers
	for (Int i=0; i<m_treadCount; i++)
		REF_PTR_RELEASE(m_treads[i].m_robj);
	m_treadCount = 0;

	//Make sure this object has defined a speed for tread scrolling.
	if (getW3DTankDrawModuleData() && getW3DTankDrawModuleData()->m_treadAnimationRate && robj)
	{
		for (Int i=0; i < robj->Get_Num_Sub_Objects() && m_treadCount < MAX_TREADS_PER_TANK; i++)
		{
			RenderObjClass *subObj=robj->Get_Sub_Object(i);
			const char *meshName;
			//Check if subobject name starts with "TREADS".
			if (subObj && subObj->Class_ID() == RenderObjClass::CLASSID_MESH && subObj->Get_Name() &&
				( (meshName=strchr(subObj->Get_Name(),'.') ) != nullptr && *(meshName++)) &&
				_strnicmp(meshName,"TREADS", 6) == 0)
			{
				//check if sub-object has the correct material to do texture scrolling.
				MaterialInfoClass *mat=subObj->Get_Material_Info();
				if (mat)
				{	for (Int j=0; j<mat->Vertex_Material_Count(); j++)
					{
						VertexMaterialClass *vmaterial=mat->Peek_Vertex_Material(j);
						LinearOffsetTextureMapperClass *mapper=(LinearOffsetTextureMapperClass *)vmaterial->Peek_Mapper();
						if (mapper && mapper->Mapper_ID() == TextureMapperClass::MAPPER_ID_LINEAR_OFFSET)
						{	mapper->Set_UV_Offset_Delta(Vector2(0,0));	//disable automatic scrolling
							subObj->Add_Ref();	//increase reference since we're storing the pointer
							m_treads[m_treadCount].m_robj=subObj;
							m_treads[m_treadCount].m_type = TREAD_MIDDLE;	//default type
							subObj->Set_User_Data(&m_treads[m_treadCount].m_materialSettings);	//tell W3D about custom material settings
							m_treads[m_treadCount].m_materialSettings.customUVOffset=Vector2(0,0);
							switch (meshName[6])	//check next character after 'TREADS'
							{
								case 'L':
								case 'l':	m_treads[m_treadCount].m_type = TREAD_LEFT;
										break;
								case 'R':
								case 'r':	m_treads[m_treadCount].m_type = TREAD_RIGHT;
										break;
							}
							m_treadCount++;
						}
					}
					REF_PTR_RELEASE(mat);
				}
			}
			REF_PTR_RELEASE(subObj);
		}
	}

	findMovingParts();
	m_prevRenderObj = robj;
}

//-------------------------------------------------------------------------------------------------
// GeneralsX @feature Claude 16/10/2026 The detailed content models hang each road wheel, sprocket and
// idler on its own bone named after its mesh (WHEELL01, SPROCKETR, IDLERL...), with the track side as
// the letter after the prefix, and carry RWS / CITV sensor bones and ANTENNA01/02 whip bones.
//-------------------------------------------------------------------------------------------------
void W3DTankDraw::findMovingParts()
{
	RenderObjClass *robj = getRenderObject();
	m_gearCount = 0;
	for (Int i = 0; i < MAX_SCAN_BONES; i++)
		m_scanBones[i] = 0;
	for (Int i = 0; i < MAX_ANTENNA_BONES; i++)
		m_antennaBones[i] = 0;
	if (robj == nullptr)
		return;

	static const char *const prefixes[] = { "WHEEL", "SPROCKET", "IDLER" };
	for (Int i = 0; i < robj->Get_Num_Sub_Objects() && m_gearCount < MAX_GEAR_BONES; i++)
	{
		RenderObjClass *subObj = robj->Get_Sub_Object(i);
		if (subObj == nullptr)
			continue;
		const char *meshName = subObj->Get_Name() ? strchr(subObj->Get_Name(), '.') : nullptr;
		if (meshName != nullptr)
		{
			meshName++;
			for (size_t p = 0; p < ARRAY_SIZE(prefixes); p++)
			{
				const size_t len = strlen(prefixes[p]);
				if (_strnicmp(meshName, prefixes[p], len) != 0)
					continue;
				const char side = meshName[len];
				const Int bone = robj->Get_Bone_Index(meshName);
				if (bone <= 0 || (side != 'L' && side != 'l' && side != 'R' && side != 'r'))
					break;
				AABoxClass box;
				subObj->Get_Obj_Space_Bounding_Box(box);
				const Real radius = box.Extent.Z;
				if (radius > 0.05f)
				{
					m_gear[m_gearCount].m_bone = bone;
					m_gear[m_gearCount].m_side = (side == 'L' || side == 'l') ? 0 : 1;
					m_gear[m_gearCount].m_radius = radius;
					m_gearCount++;
				}
				break;
			}
		}
		REF_PTR_RELEASE(subObj);
	}

	m_scanBones[0] = robj->Get_Bone_Index("RWS");
	m_scanBones[1] = robj->Get_Bone_Index("CITV");
	m_antennaBones[0] = robj->Get_Bone_Index("ANTENNA01");
	m_antennaBones[1] = robj->Get_Bone_Index("ANTENNA02");
	for (Int t = 0; t < m_treadCount; t++)
	{
		const Int side = m_treads[t].m_type == TREAD_RIGHT ? 1 : 0;
		m_lastTreadU[side] = m_treads[t].m_materialSettings.customUVOffset.X;
	}
}

//-------------------------------------------------------------------------------------------------
void W3DTankDraw::updateMovingParts(Real speed)
{
	RenderObjClass *robj = getRenderObject();
	if (robj == nullptr)
		return;

	// Running gear turns with the track: the content's track texture repeats every TREAD_WORLD_PER_U
	// world units along the band (blend/abrams.py track_loop links=3.0).
	const Real TREAD_WORLD_PER_U = 3.0f;
	if (m_gearCount > 0)
	{
		for (Int t = 0; t < m_treadCount; t++)
		{
			if (m_treads[t].m_type == TREAD_MIDDLE)
				continue;
			const Int side = m_treads[t].m_type == TREAD_RIGHT ? 1 : 0;
			Real du = m_treads[t].m_materialSettings.customUVOffset.X - m_lastTreadU[side];
			du -= WWMath::Floor(du + 0.5f);	// the offset wraps in [0, 1]
			m_lastTreadU[side] = m_treads[t].m_materialSettings.customUVOffset.X;
			m_treadTravel[side] -= du * TREAD_WORLD_PER_U;
		}
		for (Int i = 0; i < m_gearCount; i++)
		{
			Matrix3D xfrm(1);
			xfrm.Rotate_Y(m_treadTravel[m_gear[i].m_side] / m_gear[i].m_radius);
			robj->Capture_Bone(m_gear[i].m_bone);
			robj->Control_Bone(m_gear[i].m_bone, xfrm);
		}
	}

	// Sensors sweep slowly, each at its own pace.
	const Real seconds = WW3D::Get_Sync_Time() * 0.001f;
	for (Int i = 0; i < MAX_SCAN_BONES; i++)
	{
		if (m_scanBones[i] <= 0)
			continue;
		Matrix3D xfrm(1);
		xfrm.Rotate_Z(WWMath::Sin(seconds * (0.35f + 0.17f * i) + i * 1.7f) * (i == 0 ? 0.7f : 1.4f));
		robj->Capture_Bone(m_scanBones[i]);
		robj->Control_Bone(m_scanBones[i], xfrm);
	}

	// Whip antennas lean back when the tank speeds up and spring forward when it brakes.
	if (m_antennaBones[0] > 0 || m_antennaBones[1] > 0)
	{
		const Real accel = speed - m_lastSpeed;
		m_lastSpeed = speed;
		m_antennaRate += -0.12f * m_antennaAngle - 0.08f * m_antennaRate - 0.25f * accel;
		m_antennaAngle = WWMath::Clamp(m_antennaAngle + m_antennaRate, -0.45f, 0.45f);
		for (Int i = 0; i < MAX_ANTENNA_BONES; i++)
		{
			if (m_antennaBones[i] <= 0)
				continue;
			Matrix3D xfrm(1);
			xfrm.Rotate_Y(m_antennaAngle * (1.0f - 0.2f * i) + 0.02f * WWMath::Sin(seconds * 2.3f + i));
			robj->Capture_Bone(m_antennaBones[i]);
			robj->Control_Bone(m_antennaBones[i], xfrm);
		}
	}
}

//-------------------------------------------------------------------------------------------------
void W3DTankDraw::onRenderObjRecreated()
{
	updateTreadObjects();
}

//-------------------------------------------------------------------------------------------------
/** Map behavior states into W3D animations. */
//-------------------------------------------------------------------------------------------------
void W3DTankDraw::doDrawModule(const Matrix3D* transformMtx)
{
	W3DModelDraw::doDrawModule(transformMtx);

	// TheSuperHackers @tweak Update the draw on every WW Sync only.
	// All calculations are originally catered to a 30 fps logic step.
	if (WW3D::Get_Sync_Frame_Time() == 0)
		return;

	const Real DEBRIS_THRESHOLD = 0.00001f;

	if (getRenderObject()==nullptr) return;
	if (getRenderObject() != m_prevRenderObj) {
		updateTreadObjects();
	}

	// get object from logic
	Object *obj = getDrawable()->getObject();
	if (obj == nullptr)
		return;

	// get object physics state
	PhysicsBehavior *physics = obj->getPhysics();
	if (physics == nullptr)
		return;

	const Coord3D *vel = physics->getVelocity();

	// if tank is moving, kick up dust and debris
	Real velMag = vel->x*vel->x + vel->y*vel->y;		// only care about moving on the ground

	const Bool doStartMoveDebris = velMag > DEBRIS_THRESHOLD && !getDrawable()->isDrawableEffectivelyHidden() && !getFullyObscuredByShroud();

	// kick debris higher the faster we move
	Coord3D velMult;
	velMag = (Real)sqrt( velMag );

	velMult.x = 0.5f * velMag + 0.1f;
	if (velMult.x > 1.0f)
		velMult.x = 1.0f;

	velMult.y = velMult.x;

	velMult.z = velMag + 0.1f;
	if (velMult.z > 1.0f)
		velMult.z = 1.0f;

	// TheSuperHackers @bugfix stephanmeesters 18/04/2026 Delay emitter creation until draw, to ensure that the particle
	// systems are not created before ParticleManager has xfer-loaded.
	createTreadEmitters();

	for (size_t i = 0; i < ARRAY_SIZE(m_treadDebrisIDs); ++i)
	{
		if (ParticleSystem *particleSys = TheParticleSystemManager->findParticleSystem(m_treadDebrisIDs[i]))
		{
			if (doStartMoveDebris)
				particleSys->start();
			else
				particleSys->stop();

			particleSys->setVelocityMultiplier( &velMult );
			particleSys->setBurstCountMultiplier( velMult.z );
		}
	}

	//Update movement of treads
	if (m_treadCount)
	{
		PhysicsTurningType turn=physics->getTurning();
		Real offset_u;
		Real treadScrollSpeed=getW3DTankDrawModuleData()->m_treadAnimationRate;
		TreadObjectInfo *pTread=m_treads;
		Real maxSpeed=obj->getAIUpdateInterface()->getCurLocomotorSpeed();

		//For optimization sake, we only do complex tread scrolling when tank
		//is mostly stationary and turning
		if (turn != TURN_NONE && physics->getVelocityMagnitude()/maxSpeed < getW3DTankDrawModuleData()->m_treadPivotSpeedFraction)
		{
				//Check if we have turned enough since last draw to require animation
				Coord3D dir;
				obj->getUnitDirectionVector2D(dir);
				Real angleToGoal = dir.x * m_lastDirection.x + dir.y * m_lastDirection.y;

				if (fabs(1.0f-angleToGoal) > 0.00001f)	//check if difference in angle cosines is greater than some cutoff.
				{
					if (turn == TURN_NEGATIVE)	//turning right
						updateTreadPositions(-treadScrollSpeed);
					else	//turning left
						updateTreadPositions(treadScrollSpeed);
				}
				m_lastDirection=dir;	//update for next frame
		}
		else
		if (physics->isMotive() && physics->getVelocityMagnitude()/maxSpeed >= getW3DTankDrawModuleData()->m_treadDriveSpeedFraction)
		{
			//do simple scrolling based only on speed when tank is moving straight at high speed.
			//we stop scrolling when tank slows down to reduce the appearance of sliding
			//tread scrolling speed was not directly tied into tank velocity because it looked odd
			//under certain situations when tank moved sideways.
			for (Int i=0; i<m_treadCount; i++)
			{
				offset_u = pTread->m_materialSettings.customUVOffset.X - treadScrollSpeed;
				// ensure coordinates of offset are in [0, 1] range:
				offset_u = offset_u - WWMath::Floor(offset_u);
				pTread->m_materialSettings.customUVOffset.Set(offset_u,0);
				pTread++;
			}
		}
	}

	updateMovingParts((Real)sqrt(vel->x*vel->x + vel->y*vel->y));
}

// ------------------------------------------------------------------------------------------------
/** CRC */
// ------------------------------------------------------------------------------------------------
void W3DTankDraw::crc( Xfer *xfer )
{

	// extend base class
	W3DModelDraw::crc( xfer );

}

// ------------------------------------------------------------------------------------------------
/** Xfer method
	* Version Info:
	* 1: Initial version */
// ------------------------------------------------------------------------------------------------
void W3DTankDraw::xfer( Xfer *xfer )
{

	// version
	XferVersion currentVersion = 1;
	XferVersion version = currentVersion;
	xfer->xferVersion( &version, currentVersion );

	// extend base class
	W3DModelDraw::xfer( xfer );

	// John A and Mark W say there is no data to save here

}

// ------------------------------------------------------------------------------------------------
/** Load post process */
// ------------------------------------------------------------------------------------------------
void W3DTankDraw::loadPostProcess()
{

	// extend base class
	W3DModelDraw::loadPostProcess();

}
