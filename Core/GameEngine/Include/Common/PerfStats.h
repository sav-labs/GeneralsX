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
		Int particles;
		Int particlesOnScreen;
	};

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
	/// True when the next summary is due, so the display only walks the texture list then.
	Bool wantsTextureMemory();
	void setTextureMemory(UnsignedInt64 bytes, UnsignedInt64 freeBytes);

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
}

#define PERF_STATS_SCOPE(section) PerfStats::ScopedSection perfStatsScope_##section(PerfStats::section)
