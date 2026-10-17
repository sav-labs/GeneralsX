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

// GeneralsX @performance Claude 16/10/2026 Lightweight frame profiler for release builds.
// Enabled by Options.ini PerfOverlay = yes, by -perf [seconds] or by -perfdump <seconds> [delay].
// Every PerfInterval seconds (default 5) it prints a [PERF] summary to stderr: frame time, game logic,
// client update, 3D scene, mesh flush, shadows, particles, draw calls, triangles, skinned meshes and
// vertices, skin cache hits, particle counts and texture memory. -perfdump also writes one CSV row per
// frame into the capture folder (Options.ini CapturePath). It only reads clocks and counters: game logic,
// CRCs and replays are unaffected.
// GeneralsX @performance Claude 16/10/2026 Every frame longer than HitchThresholdMs prints one [PERF] hitch line
// with that frame's sections and what was loaded or created in it (textures, models, shaders, drawables).

#pragma once

#include "Lib/BaseType.h"

namespace PerfStats
{
	enum Section
	{
		SECTION_LOGIC,            ///< TheGameLogic->update()
		SECTION_CLIENT,           ///< TheGameClient->update(), includes everything below
		SECTION_DRAWABLES,        ///< Drawable client updates (animation, model draw modules)
		SECTION_PARTICLE_UPDATE,  ///< ParticleSystemManager::update()
		SECTION_DRAW,             ///< TheDisplay->draw(), includes everything below
		SECTION_RENDER_TARGETS,   ///< Particle queueing, water and projected shadow textures before the main scene
		SECTION_SCENE,            ///< 3D views of the world (terrain, objects, shadows, particles)
		SECTION_MESH_FLUSH,       ///< DX8 mesh renderer flush (opaque meshes, CPU skinning)
		SECTION_SHADOWS,          ///< Shadow volume updates and shadow drawing
		SECTION_PARTICLE_RENDER,  ///< Particle queueing and the sorted translucent flush
		SECTION_PRESENT,          ///< WW3D::End_Render (present, waits for the GPU when it is behind)
		// GeneralsX @feature Claude 16/10/2026 Shadows of skinned models (tile updates, terrain pass, volumes); overlaps
		// render_targets and shadows.
		SECTION_SKINNED_SHADOWS,  ///< W3DSkinnedShadowManager work
		// GeneralsX @feature Claude 16/10/2026 Effect lights (light selection before the scene and the terrain light
		// pass); overlaps render_targets and scene.
		SECTION_EFFECT_LIGHTS,    ///< W3DEffectLights update and terrain light splats
		// GeneralsX @feature Claude 16/10/2026 Reflection pass of the water effects; overlaps render_targets.
		SECTION_WATER_REFLECTION, ///< WaterRenderObjClass::renderWaterReflection
		// GeneralsX @performance Claude 17/10/2026 Parts of the scene, for the hitch line; overlap scene (and the
		// mirror passes of render_targets).
		SECTION_SCENE_VISIBILITY, ///< RTS3DScene::Visibility_Check
		SECTION_SCENE_TERRAIN,    ///< Terrain render object
		SECTION_SCENE_OBJECTS,    ///< Object submission, including the delayed (occluded) objects
		SECTION_SCENE_TRANSLUCENT,///< RTS3DScene::flushTranslucentObjects
		SECTION_COUNT
	};

	/// Counters the W3D display hands over once per rendered frame.
	struct FrameCounters
	{
		UnsignedInt drawCalls;
		UnsignedInt triangles;
		UnsignedInt sortedTriangles;
		UnsignedInt skinMeshes;
		UnsignedInt skinVertices;
		UnsignedInt skinCacheHits;
		UnsignedInt normalMapDraws;	///< GeneralsX @feature Claude 16/10/2026 draws with model normal maps
		Int particles;
		Int particlesOnScreen;
	};

	// GeneralsX @performance Claude 16/10/2026 Frames at least this long print a [PERF] hitch line.
	const double HitchThresholdMs = 100.0;

	/// Running totals of synchronous texture loads, read once per frame from the renderer.
	typedef void (*LoadTotalsSource)(UnsignedInt &textureLoads, double &textureLoadMs);
	// GeneralsX @performance Claude 17/10/2026 Running totals of the pipelines DXVK created for draws (of those, the
	// ones compiled without pipeline libraries), the fixed function shaders it generated and the pipeline time.
	typedef void (*PipelineTotalsSource)(UnsignedInt &pipelines, UnsignedInt &fullCompiles, UnsignedInt &ffShaders, double &pipelineMs);

	extern Bool s_enabled;

	inline Bool isEnabled() { return s_enabled; }

	/// -perf [seconds]: enable the stderr summary, optionally with its interval.
	void enableFromCommandLine(Real intervalSeconds);
	/// -perfdump <seconds> [delay]: per frame CSV of the first seconds of a match, after delay seconds.
	void enableDump(Real seconds, Real delaySeconds);
	/// Options.ini PerfOverlay / PerfInterval, applied once when the display starts.
	void applyOptions(Bool overlay, Real intervalSeconds);
	/// True when -perfdump was given; the display then names the CSV file in the capture folder.
	Bool isDumpRequested();
	void setDumpFile(const char *path);

	/// Milliseconds from a monotonic high resolution clock.
	double nowMs();
	void addTime(Section section, double ms);
	void setFrameCounters(const FrameCounters &counters);
	/// Shadow volume silhouette rebuild of a caster mesh with this many triangles (counted per frame).
	void addShadowRebuild(UnsignedInt triangles);
	// GeneralsX @feature Claude 16/10/2026 Skinned shadow counters (W3DSkinnedShadow).
	/// A skinned shadow was redrawn (projected tile) or rebuilt (shadow volume) from a caster with this many triangles.
	void addSkinnedShadowUpdate(UnsignedInt triangles);
	/// Skinned shadows drawn this frame.
	void addSkinnedShadowsDrawn(UnsignedInt count);
	// GeneralsX @feature Claude 16/10/2026 Effect light counters (W3DEffectLights).
	/// Effect lights lit this frame, retail LightPulse lights still on, and light candidates before the budget.
	void setEffectLights(UnsignedInt active, UnsignedInt retail, UnsignedInt candidates);
	// GeneralsX @performance Claude 16/10/2026 Hitch counters: what was loaded or created during a frame.
	/// The renderer's synchronous texture load totals; endFrame turns them into per frame counts.
	void setLoadTotalsSource(LoadTotalsSource source);
	// GeneralsX @performance Claude 17/10/2026 The renderer's pipeline creation totals (DXVK d3d9.dll only).
	void setPipelineTotalsSource(PipelineTotalsSource source);
	// GeneralsX @performance Claude 17/10/2026 The current main loop iteration loads a map behind the load screen:
	// endFrame prints it as one [PERF] load line instead of a hitch and leaves it out of the summaries.
	void markLoadFrame();
	/// A .w3d file was read from disk and took this long.
	void addModelLoad(double ms);
	/// A Direct3D vertex or pixel shader was created.
	void addShaderCreated();
	/// A drawable was created.
	void addDrawableCreated();
	/// True when the next summary is due, so the display only walks the texture list then.
	Bool wantsTextureMemory();
	void setTextureMemory(UnsignedInt64 bytes, UnsignedInt64 freeBytes);

	// GeneralsX @performance Claude 17/10/2026 Parts of TheGameLogic->update(), printed as a [PERF] hitch logic line
	// when a hitch frame spent at least HitchLogicMs in game logic.
	enum LogicPart
	{
		LOGIC_SCRIPTS,    ///< TheScriptEngine->update()
		LOGIC_TERRAIN,    ///< TheTerrainLogic->update()
		LOGIC_OBJECTS,    ///< Object update modules
		LOGIC_AI,         ///< TheAI->update() (pathfinding queue, AI players)
		LOGIC_PARTITION,  ///< ThePartitionManager->update()
		// GeneralsX @performance Claude 17/10/2026 Parts of LOGIC_AI.
		LOGIC_AI_ZONES,   ///< Pathfinder zone recalculation
		LOGIC_AI_PATHS,   ///< Queued pathfind requests
		LOGIC_AI_PLAYERS, ///< ThePlayerList->update() (AI players, teams)
		LOGIC_PART_COUNT
	};
	const double HitchLogicMs = 20.0;
	void addLogicTime(LogicPart part, double ms);
	/// Counts one object update module call and says whether it is the slowest of the frame so far; the caller
	/// then names it with setSlowestLogicUpdate (thing template and module), so names are only built when needed.
	Bool isSlowestLogicUpdate(double ms);
	void setSlowestLogicUpdate(double ms, const char *thing, const char *module);
	/// One queued pathfind request took this long and examined this many cells; counted per frame, the slowest
	/// is named in the hitch logic line.
	void addPathfind(double ms, Int cells, const char *thing);

	/// Called once per main loop iteration.
	void endFrame(Bool inMatch, UnsignedInt logicFrame);
	/// Short multi-line text for the on-screen overlay, empty when the overlay is off.
	const char *getOverlayText();
	/// Closes the CSV, if any.
	void shutdown();

	class ScopedSection
	{
	public:
		explicit ScopedSection(Section section) : m_section(section), m_start(s_enabled ? nowMs() : 0.0) {}
		~ScopedSection()
		{
			if (s_enabled)
				addTime(m_section, nowMs() - m_start);
		}
	private:
		Section m_section;
		double m_start;
	};

	// GeneralsX @performance Claude 17/10/2026 Times one part of TheGameLogic->update().
	class ScopedLogicPart
	{
	public:
		explicit ScopedLogicPart(LogicPart part) : m_part(part), m_start(s_enabled ? nowMs() : 0.0) {}
		~ScopedLogicPart()
		{
			if (s_enabled)
				addLogicTime(m_part, nowMs() - m_start);
		}
	private:
		LogicPart m_part;
		double m_start;
	};
}

#define PERF_STATS_SCOPE(section) PerfStats::ScopedSection perfStatsScope_##section(PerfStats::section)
#define PERF_STATS_LOGIC(part) PerfStats::ScopedLogicPart perfStatsLogic_##part(PerfStats::part)
