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

// GeneralsX @performance Claude 16/10/2026 Lightweight frame profiler for release builds, see PerfStats.h.

#include "PreRTS.h"

#include "Common/PerfStats.h"

#include <chrono>
#include <stdio.h>
#include <string.h>

namespace PerfStats
{

Bool s_enabled = FALSE;

namespace
{
	/// Sums over a window of frames (the stderr interval or the one second overlay refresh).
	struct Window
	{
		double startMs;
		UnsignedInt frames;
		double frameMsSum;
		double frameMsMax;
		double sectionMs[SECTION_COUNT];
		UnsignedInt64 drawCalls;
		UnsignedInt64 triangles;
		UnsignedInt64 sortedTriangles;
		UnsignedInt64 skinMeshes;
		UnsignedInt64 skinVertices;
		UnsignedInt64 skinCacheHits;
		UnsignedInt64 normalMapDraws;
		UnsignedInt64 shadowRebuilds;
		UnsignedInt64 shadowRebuildTriangles;
		UnsignedInt64 skinnedShadowUpdates;
		UnsignedInt64 skinnedShadowUpdateTriangles;
		UnsignedInt64 skinnedShadowsDrawn;
		// GeneralsX @feature Claude 16/10/2026 Effect light sums.
		UnsignedInt64 effectLights;
		UnsignedInt64 retailLights;
		UnsignedInt64 lightCandidates;
		UnsignedInt effectLightsMax;
		// GeneralsX @performance Claude 16/10/2026 Loads and creations (hitch counters).
		UnsignedInt64 textureLoads;
		double textureLoadMs;
		UnsignedInt64 modelLoads;
		double modelLoadMs;
		UnsignedInt64 shadersCreated;
		UnsignedInt64 drawablesCreated;
		// GeneralsX @performance Claude 17/10/2026 DXVK pipeline creation (hitch counters).
		UnsignedInt64 pipelines;
		double pipelineMs;
		// GeneralsX @performance Claude 17/10/2026 Main thread waits of the renderer.
		UnsignedInt64 waits[WAIT_KIND_COUNT];
		double waitMs[WAIT_KIND_COUNT];
		UnsignedInt hitches;
		UnsignedInt drawCallsMax;
		Int particlesMax;
		Int particlesOnScreenLast;
		Int particlesLast;

		void reset(double now)
		{
			memset(this, 0, sizeof(*this));
			startMs = now;
		}
	};

	Bool s_printEnabled = FALSE;
	Bool s_overlayEnabled = FALSE;
	Real s_intervalSeconds = 5.0f;

	Bool s_dumpRequested = FALSE;
	Real s_dumpSeconds = 0.0f;
	Real s_dumpDelaySeconds = 0.0f;
	char s_dumpPath[1024] = { 0 };
	FILE *s_dumpFile = nullptr;
	Bool s_dumpFinished = FALSE;
	double s_matchStartMs = -1.0;
	UnsignedInt s_dumpRows = 0;
	double s_dumpLastFlushMs = 0.0;

	double s_lastFrameEndMs = -1.0;
	double s_frameSectionMs[SECTION_COUNT];
	FrameCounters s_frameCounters;
	UnsignedInt s_frameShadowRebuilds = 0;
	UnsignedInt s_frameShadowRebuildTriangles = 0;
	// GeneralsX @feature Claude 16/10/2026 Skinned shadow counters of the current frame.
	UnsignedInt s_frameSkinnedShadowUpdates = 0;
	UnsignedInt s_frameSkinnedShadowUpdateTriangles = 0;
	UnsignedInt s_frameSkinnedShadowsDrawn = 0;
	// GeneralsX @feature Claude 16/10/2026 Effect light counters of the current frame.
	UnsignedInt s_frameEffectLights = 0;
	UnsignedInt s_frameRetailLights = 0;
	UnsignedInt s_frameLightCandidates = 0;
	// GeneralsX @performance Claude 16/10/2026 Loads and creations of the current frame (hitch counters).
	UnsignedInt s_frameTextureLoads = 0;
	double s_frameTextureLoadMs = 0.0;
	UnsignedInt s_frameModelLoads = 0;
	double s_frameModelLoadMs = 0.0;
	UnsignedInt s_frameShadersCreated = 0;
	UnsignedInt s_frameDrawablesCreated = 0;
	LoadTotalsSource s_loadTotalsSource = nullptr;
	UnsignedInt s_lastTextureLoadTotal = 0;
	double s_lastTextureLoadMsTotal = 0.0;
	// GeneralsX @performance Claude 17/10/2026 DXVK pipeline creation of the current frame and the running totals.
	UnsignedInt s_framePipelines = 0;
	UnsignedInt s_frameFullCompiles = 0;
	UnsignedInt s_frameFFShaders = 0;
	double s_framePipelineMs = 0.0;
	PipelineTotalsSource s_pipelineTotalsSource = nullptr;
	UnsignedInt s_lastPipelineTotal = 0;
	UnsignedInt s_lastFullCompileTotal = 0;
	UnsignedInt s_lastFFShaderTotal = 0;
	double s_lastPipelineMsTotal = 0.0;
	// GeneralsX @performance Claude 17/10/2026 Main thread waits of the renderer in the current frame and the totals.
	UnsignedInt s_frameWaits[WAIT_KIND_COUNT];
	double s_frameWaitMs[WAIT_KIND_COUNT];
	double s_frameSlowestWaitMs = 0.0;
	char s_frameSlowestWait[96];
	WaitTotalsSource s_waitTotalsSource = nullptr;
	WaitTotals s_lastWaitTotals;
	UnsignedInt s_frameOpenListSteps = 0;
	// GeneralsX @performance Claude 17/10/2026 The current frame loads a map, see markLoadFrame.
	Bool s_loadFrame = FALSE;
	// GeneralsX @performance Claude 17/10/2026 Game logic parts and the slowest update module of the current frame.
	double s_frameLogicMs[LOGIC_PART_COUNT];
	UnsignedInt s_frameLogicUpdates = 0;
	double s_frameSlowestUpdateMs = 0.0;
	char s_frameSlowestThing[64];
	char s_frameSlowestModule[64];
	UnsignedInt s_framePaths = 0;
	Int s_framePathCells = 0;
	double s_frameSlowestPathMs = 0.0;
	Int s_frameSlowestPathCells = 0;
	char s_frameSlowestPathThing[64];

	Window s_interval;
	Window s_overlay;
	Bool s_windowsStarted = FALSE;

	UnsignedInt64 s_textureBytes = 0;
	UnsignedInt64 s_freeTextureBytes = 0;
	Bool s_textureMemoryKnown = FALSE;

	char s_overlayText[704] = { 0 };

	const char *s_sectionNames[SECTION_COUNT] =
	{
		"logic_ms",
		"client_ms",
		"drawables_ms",
		"particle_update_ms",
		"draw_ms",
		"render_targets_ms",
		"scene_ms",
		"mesh_flush_ms",
		"shadows_ms",
		"particle_render_ms",
		"present_ms",
		"skinned_shadows_ms",
		"lights_ms",
		"water_reflection_ms",
		"scene_visibility_ms",
		"scene_terrain_ms",
		"scene_objects_ms",
		"scene_translucent_ms",
		"terrain_base_ms",
		"terrain_shore_ms",
		"terrain_blend_ms",
		"terrain_roads_ms",
		"terrain_props_ms",
		"terrain_scorch_ms",
		"terrain_bridges_ms",
		"terrain_tracks_ms",
		"terrain_shroud_ms",
		"terrain_bibs_ms",
		"terrain_light_vb_ms",
	};

	void accumulate(Window &w, double frameMs)
	{
		++w.frames;
		w.frameMsSum += frameMs;
		if (frameMs > w.frameMsMax)
			w.frameMsMax = frameMs;
		if (frameMs >= HitchThresholdMs)
			++w.hitches;
		w.pipelines += s_framePipelines;
		w.pipelineMs += s_framePipelineMs;
		for (Int i = 0; i < WAIT_KIND_COUNT; ++i)
		{
			w.waits[i] += s_frameWaits[i];
			w.waitMs[i] += s_frameWaitMs[i];
		}
		for (Int i = 0; i < SECTION_COUNT; ++i)
			w.sectionMs[i] += s_frameSectionMs[i];
		w.drawCalls += s_frameCounters.drawCalls;
		w.triangles += s_frameCounters.triangles;
		w.sortedTriangles += s_frameCounters.sortedTriangles;
		w.skinMeshes += s_frameCounters.skinMeshes;
		w.skinVertices += s_frameCounters.skinVertices;
		w.skinCacheHits += s_frameCounters.skinCacheHits;
		w.normalMapDraws += s_frameCounters.normalMapDraws;
		w.shadowRebuilds += s_frameShadowRebuilds;
		w.shadowRebuildTriangles += s_frameShadowRebuildTriangles;
		w.skinnedShadowUpdates += s_frameSkinnedShadowUpdates;
		w.skinnedShadowUpdateTriangles += s_frameSkinnedShadowUpdateTriangles;
		w.skinnedShadowsDrawn += s_frameSkinnedShadowsDrawn;
		w.effectLights += s_frameEffectLights;
		w.retailLights += s_frameRetailLights;
		w.lightCandidates += s_frameLightCandidates;
		w.textureLoads += s_frameTextureLoads;
		w.textureLoadMs += s_frameTextureLoadMs;
		w.modelLoads += s_frameModelLoads;
		w.modelLoadMs += s_frameModelLoadMs;
		w.shadersCreated += s_frameShadersCreated;
		w.drawablesCreated += s_frameDrawablesCreated;
		if (s_frameEffectLights > w.effectLightsMax)
			w.effectLightsMax = s_frameEffectLights;
		if (s_frameCounters.drawCalls > w.drawCallsMax)
			w.drawCallsMax = s_frameCounters.drawCalls;
		if (s_frameCounters.particles > w.particlesMax)
			w.particlesMax = s_frameCounters.particles;
		w.particlesLast = s_frameCounters.particles;
		w.particlesOnScreenLast = s_frameCounters.particlesOnScreen;
	}

	double avg(double sum, UnsignedInt frames)
	{
		return frames ? sum / (double)frames : 0.0;
	}

	void printSummary(const Window &w, double now)
	{
		const UnsignedInt n = w.frames;
		if (n == 0)
			return;
		const double seconds = (now - w.startMs) / 1000.0;
		const double fps = seconds > 0.0 ? (double)n / seconds : 0.0;

		fprintf(stderr,
			"[PERF] %.1fs frames=%u fps=%.1f frame_ms avg=%.2f max=%.2f"
			" | logic=%.2f client=%.2f (drawables=%.2f particles=%.2f draw=%.2f: targets=%.2f scene=%.2f"
			" [meshes=%.2f shadows=%.2f particles=%.2f] present=%.2f water_refl=%.2f)"
			" | draws=%.0f max=%u tris=%.0fk sorted=%.0fk"
			" | skins=%.1f skinverts=%.1fk cachehits=%.1f normalmapped=%.1f"
			" | shadowrebuilds=%.1f (%.1fk tris)"
			" | skinshadows=%.1f updates=%.1f (%.1fk tris) skinshadow_ms=%.2f"
			" | lights=%.1f max=%u retail=%.1f candidates=%.1f lights_ms=%.2f"
			" | particles=%d max=%d onscreen=%d",
			seconds, n, fps, avg(w.frameMsSum, n), w.frameMsMax,
			avg(w.sectionMs[SECTION_LOGIC], n), avg(w.sectionMs[SECTION_CLIENT], n),
			avg(w.sectionMs[SECTION_DRAWABLES], n), avg(w.sectionMs[SECTION_PARTICLE_UPDATE], n),
			avg(w.sectionMs[SECTION_DRAW], n), avg(w.sectionMs[SECTION_RENDER_TARGETS], n),
			avg(w.sectionMs[SECTION_SCENE], n), avg(w.sectionMs[SECTION_MESH_FLUSH], n),
			avg(w.sectionMs[SECTION_SHADOWS], n), avg(w.sectionMs[SECTION_PARTICLE_RENDER], n),
			avg(w.sectionMs[SECTION_PRESENT], n), avg(w.sectionMs[SECTION_WATER_REFLECTION], n),
			avg((double)w.drawCalls, n), w.drawCallsMax,
			avg((double)w.triangles, n) / 1000.0, avg((double)w.sortedTriangles, n) / 1000.0,
			avg((double)w.skinMeshes, n), avg((double)w.skinVertices, n) / 1000.0, avg((double)w.skinCacheHits, n),
			avg((double)w.normalMapDraws, n),
			avg((double)w.shadowRebuilds, n), avg((double)w.shadowRebuildTriangles, n) / 1000.0,
			avg((double)w.skinnedShadowsDrawn, n), avg((double)w.skinnedShadowUpdates, n),
			avg((double)w.skinnedShadowUpdateTriangles, n) / 1000.0, avg(w.sectionMs[SECTION_SKINNED_SHADOWS], n),
			avg((double)w.effectLights, n), w.effectLightsMax, avg((double)w.retailLights, n),
			avg((double)w.lightCandidates, n), avg(w.sectionMs[SECTION_EFFECT_LIGHTS], n),
			w.particlesLast, w.particlesMax, w.particlesOnScreenLast);
		if (s_textureMemoryKnown)
		{
			fprintf(stderr, " | textures=%.0fMB vram_free=%.0fMB",
				(double)s_textureBytes / (1024.0 * 1024.0), (double)s_freeTextureBytes / (1024.0 * 1024.0));
		}
		// GeneralsX @performance Claude 16/10/2026 Loads and creations over the whole window.
		fprintf(stderr, " | hitches=%u texloads=%llu (%.0f ms) modelloads=%llu (%.0f ms) shaders=%llu drawables=%llu",
			w.hitches, (unsigned long long)w.textureLoads, w.textureLoadMs, (unsigned long long)w.modelLoads, w.modelLoadMs,
			(unsigned long long)w.shadersCreated, (unsigned long long)w.drawablesCreated);
		// GeneralsX @performance Claude 17/10/2026 DXVK pipelines created for draws over the window.
		if (s_pipelineTotalsSource != nullptr)
			fprintf(stderr, " pipelines=%llu (%.0f ms)", (unsigned long long)w.pipelines, w.pipelineMs);
		// GeneralsX @performance Claude 17/10/2026 Main thread waits of the renderer, per frame.
		if (s_waitTotalsSource != nullptr)
		{
			fprintf(stderr, " | waits_ms buffer=%.2f texture=%.2f other=%.2f cs=%.2f (per frame %.1f/%.1f/%.1f/%.1f)",
				avg(w.waitMs[WAIT_BUFFER], n), avg(w.waitMs[WAIT_TEXTURE], n), avg(w.waitMs[WAIT_OTHER], n),
				avg(w.waitMs[WAIT_CS], n), avg((double)w.waits[WAIT_BUFFER], n), avg((double)w.waits[WAIT_TEXTURE], n),
				avg((double)w.waits[WAIT_OTHER], n), avg((double)w.waits[WAIT_CS], n));
		}
		fprintf(stderr, "\n");
		fflush(stderr);
	}

	void updateOverlayText(const Window &w, double now)
	{
		const UnsignedInt n = w.frames;
		if (n == 0)
			return;
		const double seconds = (now - w.startMs) / 1000.0;
		const double fps = seconds > 0.0 ? (double)n / seconds : 0.0;
		snprintf(s_overlayText, sizeof(s_overlayText),
			"PERF %.0f fps  frame %.1f ms (max %.1f)\n"
			"logic %.1f  client %.1f  draw %.1f  scene %.1f  meshes %.1f  shadows %.1f  fx %.1f  present %.1f\n"
			"draws %.0f  tris %.0fk  skins %.0f (%.0fk verts, %.0f cached)  shadow rebuilds %.0f  particles %d/%d  tex %.0f MB\n"
			"skinned shadows %.0f  updates %.1f  %.2f ms  lights %.0f (%.0f retail)  %.2f ms",
			fps, avg(w.frameMsSum, n), w.frameMsMax,
			avg(w.sectionMs[SECTION_LOGIC], n), avg(w.sectionMs[SECTION_CLIENT], n), avg(w.sectionMs[SECTION_DRAW], n),
			avg(w.sectionMs[SECTION_SCENE], n), avg(w.sectionMs[SECTION_MESH_FLUSH], n), avg(w.sectionMs[SECTION_SHADOWS], n),
			avg(w.sectionMs[SECTION_PARTICLE_RENDER], n) + avg(w.sectionMs[SECTION_PARTICLE_UPDATE], n),
			avg(w.sectionMs[SECTION_PRESENT], n),
			avg((double)w.drawCalls, n), avg((double)w.triangles, n) / 1000.0,
			avg((double)w.skinMeshes, n), avg((double)w.skinVertices, n) / 1000.0, avg((double)w.skinCacheHits, n),
			avg((double)w.shadowRebuilds, n),
			w.particlesOnScreenLast, w.particlesLast,
			(double)s_textureBytes / (1024.0 * 1024.0),
			avg((double)w.skinnedShadowsDrawn, n), avg((double)w.skinnedShadowUpdates, n),
			avg(w.sectionMs[SECTION_SKINNED_SHADOWS], n),
			avg((double)w.effectLights, n), avg((double)w.retailLights, n), avg(w.sectionMs[SECTION_EFFECT_LIGHTS], n));
	}

	// GeneralsX @performance Claude 16/10/2026 One line for a frame of at least HitchThresholdMs: where the time
	// went and what was loaded or created in that frame.
	// GeneralsX @performance Claude 17/10/2026 The same line names a map load frame "load" instead of "hitch".
	void printHitch(double frameMs, Bool inMatch, UnsignedInt logicFrame, const char *kind)
	{
		fprintf(stderr,
			"[PERF] %s frame_ms=%.1f %s logic_frame=%u"
			" | logic=%.1f client=%.1f (drawables=%.1f particles=%.1f draw=%.1f: targets=%.1f scene=%.1f"
			" [meshes=%.1f shadows=%.1f particles=%.1f vis=%.1f terrain=%.1f objects=%.1f translucent=%.1f]"
			" present=%.1f water_refl=%.1f lights=%.1f skinshadow=%.1f)"
			" untracked=%.1f"
			" | texloads=%u (%.1f ms) modelloads=%u (%.1f ms) shaders=%u drawables=%u"
			" pipelines=%u (%.1f ms, %u full) ffshaders=%u"
			" | draws=%u tris=%.0fk particles=%d\n",
			kind, frameMs, inMatch ? "match" : "shell", logicFrame,
			s_frameSectionMs[SECTION_LOGIC], s_frameSectionMs[SECTION_CLIENT],
			s_frameSectionMs[SECTION_DRAWABLES], s_frameSectionMs[SECTION_PARTICLE_UPDATE],
			s_frameSectionMs[SECTION_DRAW], s_frameSectionMs[SECTION_RENDER_TARGETS],
			s_frameSectionMs[SECTION_SCENE], s_frameSectionMs[SECTION_MESH_FLUSH],
			s_frameSectionMs[SECTION_SHADOWS], s_frameSectionMs[SECTION_PARTICLE_RENDER],
			s_frameSectionMs[SECTION_SCENE_VISIBILITY], s_frameSectionMs[SECTION_SCENE_TERRAIN],
			s_frameSectionMs[SECTION_SCENE_OBJECTS], s_frameSectionMs[SECTION_SCENE_TRANSLUCENT],
			s_frameSectionMs[SECTION_PRESENT], s_frameSectionMs[SECTION_WATER_REFLECTION],
			s_frameSectionMs[SECTION_EFFECT_LIGHTS], s_frameSectionMs[SECTION_SKINNED_SHADOWS],
			frameMs - s_frameSectionMs[SECTION_LOGIC] - s_frameSectionMs[SECTION_CLIENT],
			s_frameTextureLoads, s_frameTextureLoadMs, s_frameModelLoads, s_frameModelLoadMs,
			s_frameShadersCreated, s_frameDrawablesCreated,
			s_framePipelines, s_framePipelineMs, s_frameFullCompiles, s_frameFFShaders,
			s_frameCounters.drawCalls, (double)s_frameCounters.triangles / 1000.0, s_frameCounters.particles);
		// GeneralsX @performance Claude 17/10/2026 Main thread waits of the renderer and the parts of a slow terrain.
		if (s_waitTotalsSource != nullptr)
		{
			fprintf(stderr,
				"[PERF] hitch waits logic_frame=%u | buffer=%u (%.1f ms) texture=%u (%.1f ms) other=%u (%.1f ms) cs=%u (%.1f ms)"
				" | slowest %.1f ms: %s\n",
				logicFrame, s_frameWaits[WAIT_BUFFER], s_frameWaitMs[WAIT_BUFFER], s_frameWaits[WAIT_TEXTURE],
				s_frameWaitMs[WAIT_TEXTURE], s_frameWaits[WAIT_OTHER], s_frameWaitMs[WAIT_OTHER], s_frameWaits[WAIT_CS],
				s_frameWaitMs[WAIT_CS], s_frameSlowestWaitMs, s_frameSlowestWait);
		}
		if (s_frameSectionMs[SECTION_SCENE_TERRAIN] >= HitchLogicMs)
		{
			fprintf(stderr,
				"[PERF] hitch terrain logic_frame=%u | base=%.1f shore=%.1f blend=%.1f roads=%.1f props=%.1f scorch=%.1f"
				" bridges=%.1f tracks=%.1f shroud=%.1f bibs=%.1f | light_vb=%.1f\n",
				logicFrame, s_frameSectionMs[SECTION_TERRAIN_BASE], s_frameSectionMs[SECTION_TERRAIN_SHORE],
				s_frameSectionMs[SECTION_TERRAIN_BLEND], s_frameSectionMs[SECTION_TERRAIN_ROADS],
				s_frameSectionMs[SECTION_TERRAIN_PROPS], s_frameSectionMs[SECTION_TERRAIN_SCORCH],
				s_frameSectionMs[SECTION_TERRAIN_BRIDGES], s_frameSectionMs[SECTION_TERRAIN_TRACKS],
				s_frameSectionMs[SECTION_TERRAIN_SHROUD], s_frameSectionMs[SECTION_TERRAIN_BIBS],
				s_frameSectionMs[SECTION_TERRAIN_LIGHT_VB]);
		}
		// GeneralsX @performance Claude 17/10/2026 Where a slow game logic frame went.
		if (s_frameSectionMs[SECTION_LOGIC] >= HitchLogicMs)
		{
			fprintf(stderr,
				"[PERF] hitch logic logic_frame=%u | scripts=%.1f terrain=%.1f objects=%.1f (%u updates) ai=%.1f partition=%.1f"
				" other=%.1f | slowest update %.1f ms: %s %s\n",
				logicFrame, s_frameLogicMs[LOGIC_SCRIPTS], s_frameLogicMs[LOGIC_TERRAIN], s_frameLogicMs[LOGIC_OBJECTS],
				s_frameLogicUpdates, s_frameLogicMs[LOGIC_AI], s_frameLogicMs[LOGIC_PARTITION],
				s_frameSectionMs[SECTION_LOGIC] - s_frameLogicMs[LOGIC_SCRIPTS] - s_frameLogicMs[LOGIC_TERRAIN]
					- s_frameLogicMs[LOGIC_OBJECTS] - s_frameLogicMs[LOGIC_AI] - s_frameLogicMs[LOGIC_PARTITION],
				s_frameSlowestUpdateMs, s_frameSlowestThing, s_frameSlowestModule);
			fprintf(stderr,
				"[PERF] hitch ai logic_frame=%u | zones=%.1f paths=%.1f (%u paths, %d cells, %u open list steps, slowest %.1f ms"
				" %d cells: %s) players=%.1f\n",
				logicFrame, s_frameLogicMs[LOGIC_AI_ZONES], s_frameLogicMs[LOGIC_AI_PATHS], s_framePaths, s_framePathCells,
				s_frameOpenListSteps, s_frameSlowestPathMs, s_frameSlowestPathCells, s_frameSlowestPathThing,
				s_frameLogicMs[LOGIC_AI_PLAYERS]);
		}
		fflush(stderr);
	}

	/// Turns the renderer's running texture load totals into this frame's counts.
	void readLoadTotals()
	{
		if (s_loadTotalsSource == nullptr)
			return;
		UnsignedInt loads = 0;
		double ms = 0.0;
		s_loadTotalsSource(loads, ms);
		s_frameTextureLoads = loads - s_lastTextureLoadTotal;
		s_frameTextureLoadMs = ms - s_lastTextureLoadMsTotal;
		s_lastTextureLoadTotal = loads;
		s_lastTextureLoadMsTotal = ms;
	}

	// GeneralsX @performance Claude 17/10/2026 Turns the renderer's running wait totals into this frame's counts.
	void readWaitTotals()
	{
		if (s_waitTotalsSource == nullptr)
			return;
		WaitTotals totals;
		memset(&totals, 0, sizeof(totals));
		s_waitTotalsSource(totals);
		for (Int i = 0; i < WAIT_KIND_COUNT; ++i)
		{
			s_frameWaits[i] = totals.waits[i] - s_lastWaitTotals.waits[i];
			s_frameWaitMs[i] = totals.waitMs[i] - s_lastWaitTotals.waitMs[i];
		}
		s_frameSlowestWaitMs = totals.slowestMs;
		snprintf(s_frameSlowestWait, sizeof(s_frameSlowestWait), "%s", totals.slowest);
		s_lastWaitTotals = totals;
	}

	// GeneralsX @performance Claude 17/10/2026 Turns DXVK's running pipeline totals into this frame's counts.
	void readPipelineTotals()
	{
		if (s_pipelineTotalsSource == nullptr)
			return;
		UnsignedInt pipelines = 0;
		UnsignedInt fullCompiles = 0;
		UnsignedInt ffShaders = 0;
		double ms = 0.0;
		s_pipelineTotalsSource(pipelines, fullCompiles, ffShaders, ms);
		s_framePipelines = pipelines - s_lastPipelineTotal;
		s_frameFullCompiles = fullCompiles - s_lastFullCompileTotal;
		s_frameFFShaders = ffShaders - s_lastFFShaderTotal;
		s_framePipelineMs = ms - s_lastPipelineMsTotal;
		s_lastPipelineTotal = pipelines;
		s_lastFullCompileTotal = fullCompiles;
		s_lastFFShaderTotal = ffShaders;
		s_lastPipelineMsTotal = ms;
	}

	void closeDump(const char *reason)
	{
		if (s_dumpFile)
		{
			fclose(s_dumpFile);
			s_dumpFile = nullptr;
			fprintf(stderr, "[PERF] perfdump %s: %u frames written to %s\n", reason, s_dumpRows, s_dumpPath);
			fflush(stderr);
		}
		s_dumpFinished = TRUE;
	}

	void writeDumpRow(double now, UnsignedInt logicFrame, double frameMs)
	{
		if (s_dumpFinished || s_matchStartMs < 0.0)
			return;

		const double sinceStart = (now - s_matchStartMs) / 1000.0;
		if (sinceStart < s_dumpDelaySeconds)
			return;

		if (!s_dumpFile)
		{
			if (s_dumpPath[0] == 0)
			{
				fprintf(stderr, "[PERF] perfdump: no capture folder, CSV disabled\n");
				fflush(stderr);
				s_dumpFinished = TRUE;
				return;
			}
			s_dumpFile = fopen(s_dumpPath, "w");
			if (!s_dumpFile)
			{
				fprintf(stderr, "[PERF] perfdump: cannot open %s\n", s_dumpPath);
				fflush(stderr);
				s_dumpFinished = TRUE;
				return;
			}
			fprintf(s_dumpFile, "time_s,logic_frame,frame_ms");
			for (Int i = 0; i < SECTION_COUNT; ++i)
				fprintf(s_dumpFile, ",%s", s_sectionNames[i]);
			fprintf(s_dumpFile, ",draw_calls,triangles,sorted_triangles,skin_meshes,skin_vertices,skin_cache_hits,"
				"shadow_rebuilds,shadow_rebuild_triangles,particles,particles_on_screen,texture_mb,"
				"skinned_shadows,skinned_shadow_updates,skinned_shadow_update_triangles,"
				"effect_lights,retail_lights,light_candidates\n");
			fprintf(stderr, "[PERF] perfdump: recording %.0f seconds to %s\n", s_dumpSeconds, s_dumpPath);
			fflush(stderr);
			s_dumpLastFlushMs = now;
		}

		fprintf(s_dumpFile, "%.3f,%u,%.3f", sinceStart - s_dumpDelaySeconds, logicFrame, frameMs);
		for (Int i = 0; i < SECTION_COUNT; ++i)
			fprintf(s_dumpFile, ",%.3f", s_frameSectionMs[i]);
		fprintf(s_dumpFile, ",%u,%u,%u,%u,%u,%u,%u,%u,%d,%d,%.0f,%u,%u,%u,%u,%u,%u\n",
			s_frameCounters.drawCalls, s_frameCounters.triangles, s_frameCounters.sortedTriangles,
			s_frameCounters.skinMeshes, s_frameCounters.skinVertices, s_frameCounters.skinCacheHits,
			s_frameShadowRebuilds, s_frameShadowRebuildTriangles,
			s_frameCounters.particles, s_frameCounters.particlesOnScreen,
			(double)s_textureBytes / (1024.0 * 1024.0),
			s_frameSkinnedShadowsDrawn, s_frameSkinnedShadowUpdates, s_frameSkinnedShadowUpdateTriangles,
			s_frameEffectLights, s_frameRetailLights, s_frameLightCandidates);
		++s_dumpRows;

		if (now - s_dumpLastFlushMs >= 1000.0)
		{
			fflush(s_dumpFile);
			s_dumpLastFlushMs = now;
		}

		if (sinceStart >= s_dumpDelaySeconds + s_dumpSeconds)
			closeDump("done");
	}

	void enable()
	{
		s_enabled = TRUE;
	}
}

void enableFromCommandLine(Real intervalSeconds)
{
	s_printEnabled = TRUE;
	if (intervalSeconds > 0.0f)
		s_intervalSeconds = intervalSeconds;
	enable();
}

void enableDump(Real seconds, Real delaySeconds)
{
	if (seconds <= 0.0f)
		return;
	s_dumpRequested = TRUE;
	s_dumpSeconds = seconds;
	s_dumpDelaySeconds = delaySeconds > 0.0f ? delaySeconds : 0.0f;
	s_printEnabled = TRUE;
	enable();
}

void applyOptions(Bool overlay, Real intervalSeconds)
{
	if (intervalSeconds > 0.0f)
		s_intervalSeconds = intervalSeconds;
	if (overlay)
	{
		s_overlayEnabled = TRUE;
		s_printEnabled = TRUE;
		enable();
	}
	if (s_enabled)
	{
		fprintf(stderr, "[PERF] frame profiler on: summary every %.1f s%s%s\n", s_intervalSeconds,
			s_overlayEnabled ? ", on-screen overlay" : "", s_dumpRequested ? ", CSV dump" : "");
		fflush(stderr);
	}
}

Bool isDumpRequested()
{
	return s_dumpRequested;
}

void setDumpFile(const char *path)
{
	if (path)
		snprintf(s_dumpPath, sizeof(s_dumpPath), "%s", path);
}

double nowMs()
{
	using namespace std::chrono;
	return duration<double, std::milli>(steady_clock::now().time_since_epoch()).count();
}

void addTime(Section section, double ms)
{
	s_frameSectionMs[section] += ms;
}

// GeneralsX @performance Claude 16/10/2026 Hitch counters.
void setLoadTotalsSource(LoadTotalsSource source)
{
	s_loadTotalsSource = source;
	if (source != nullptr)
		source(s_lastTextureLoadTotal, s_lastTextureLoadMsTotal);
}

// GeneralsX @performance Claude 17/10/2026 DXVK pipeline counters and the map load frame.
void setPipelineTotalsSource(PipelineTotalsSource source)
{
	s_pipelineTotalsSource = source;
	if (source != nullptr)
		source(s_lastPipelineTotal, s_lastFullCompileTotal, s_lastFFShaderTotal, s_lastPipelineMsTotal);
}

void setWaitTotalsSource(WaitTotalsSource source)
{
	s_waitTotalsSource = source;
	memset(&s_lastWaitTotals, 0, sizeof(s_lastWaitTotals));
	if (source != nullptr)
		source(s_lastWaitTotals);
}

void addOpenListSteps(UnsignedInt steps)
{
	s_frameOpenListSteps += steps;
}

void markLoadFrame()
{
	s_loadFrame = TRUE;
}

void addModelLoad(double ms)
{
	if (!s_enabled)
		return;
	++s_frameModelLoads;
	s_frameModelLoadMs += ms;
}

void addShaderCreated()
{
	if (!s_enabled)
		return;
	++s_frameShadersCreated;
}

void addDrawableCreated()
{
	if (!s_enabled)
		return;
	++s_frameDrawablesCreated;
}

void setFrameCounters(const FrameCounters &counters)
{
	s_frameCounters = counters;
}

void addShadowRebuild(UnsignedInt triangles)
{
	if (!s_enabled)
		return;
	++s_frameShadowRebuilds;
	s_frameShadowRebuildTriangles += triangles;
}

void addSkinnedShadowUpdate(UnsignedInt triangles)
{
	if (!s_enabled)
		return;
	++s_frameSkinnedShadowUpdates;
	s_frameSkinnedShadowUpdateTriangles += triangles;
}

void addSkinnedShadowsDrawn(UnsignedInt count)
{
	if (!s_enabled)
		return;
	s_frameSkinnedShadowsDrawn += count;
}

// GeneralsX @feature Claude 16/10/2026 Effect light counters, set once per rendered frame by W3DEffectLights.
void setEffectLights(UnsignedInt active, UnsignedInt retail, UnsignedInt candidates)
{
	if (!s_enabled)
		return;
	s_frameEffectLights = active;
	s_frameRetailLights = retail;
	s_frameLightCandidates = candidates;
}

Bool wantsTextureMemory()
{
	if (!s_enabled)
		return FALSE;
	if (!s_textureMemoryKnown)
		return TRUE;
	// refresh with the overlay once a second, otherwise right before the stderr summary
	const double now = nowMs();
	if (s_overlayEnabled)
		return now - s_overlay.startMs >= 1000.0 - 50.0;
	return now - s_interval.startMs >= s_intervalSeconds * 1000.0 - 100.0;
}

void setTextureMemory(UnsignedInt64 bytes, UnsignedInt64 freeBytes)
{
	s_textureBytes = bytes;
	s_freeTextureBytes = freeBytes;
	s_textureMemoryKnown = TRUE;
}

void addLogicTime(LogicPart part, double ms)
{
	if (!s_enabled)
		return;
	s_frameLogicMs[part] += ms;
}

Bool isSlowestLogicUpdate(double ms)
{
	++s_frameLogicUpdates;
	return ms > s_frameSlowestUpdateMs;
}

void setSlowestLogicUpdate(double ms, const char *thing, const char *module)
{
	s_frameSlowestUpdateMs = ms;
	snprintf(s_frameSlowestThing, sizeof(s_frameSlowestThing), "%s", thing != nullptr ? thing : "");
	snprintf(s_frameSlowestModule, sizeof(s_frameSlowestModule), "%s", module != nullptr ? module : "");
}

void addPathfind(double ms, Int cells, const char *thing)
{
	if (!s_enabled)
		return;
	++s_framePaths;
	s_framePathCells += cells;
	if (ms > s_frameSlowestPathMs)
	{
		s_frameSlowestPathMs = ms;
		s_frameSlowestPathCells = cells;
		snprintf(s_frameSlowestPathThing, sizeof(s_frameSlowestPathThing), "%s", thing != nullptr ? thing : "");
	}
}

void endFrame(Bool inMatch, UnsignedInt logicFrame)
{
	if (!s_enabled)
		return;

	const double now = nowMs();
	if (!s_windowsStarted)
	{
		s_interval.reset(now);
		s_overlay.reset(now);
		s_windowsStarted = TRUE;
	}

	readLoadTotals();
	readPipelineTotals();
	readWaitTotals();

	// GeneralsX @performance Claude 17/10/2026 A map load runs inside one main loop iteration behind the load screen.
	// Print what it loaded and created, and start the summaries after it, so that the match frames stay separate.
	if (s_loadFrame && s_lastFrameEndMs >= 0.0)
	{
		if (s_printEnabled)
			printHitch(now - s_lastFrameEndMs, inMatch, logicFrame, "load");
		s_interval.reset(now);
		s_overlay.reset(now);
	}
	else if (s_lastFrameEndMs >= 0.0)
	{
		const double frameMs = now - s_lastFrameEndMs;

		if (s_printEnabled && frameMs >= HitchThresholdMs)
			printHitch(frameMs, inMatch, logicFrame, "hitch");

		if (inMatch && s_dumpRequested)
		{
			if (s_matchStartMs < 0.0)
				s_matchStartMs = now;
			writeDumpRow(now, logicFrame, frameMs);
		}
		else if (!inMatch && s_dumpFile)
		{
			closeDump("match ended");
		}

		accumulate(s_interval, frameMs);
		accumulate(s_overlay, frameMs);
	}
	s_lastFrameEndMs = now;

	if (s_printEnabled && now - s_interval.startMs >= s_intervalSeconds * 1000.0)
	{
		printSummary(s_interval, now);
		s_interval.reset(now);
	}
	if (s_overlayEnabled && now - s_overlay.startMs >= 1000.0)
	{
		updateOverlayText(s_overlay, now);
		s_overlay.reset(now);
	}

	memset(s_frameSectionMs, 0, sizeof(s_frameSectionMs));
	memset(&s_frameCounters, 0, sizeof(s_frameCounters));
	s_frameShadowRebuilds = 0;
	s_frameShadowRebuildTriangles = 0;
	s_frameSkinnedShadowUpdates = 0;
	s_frameSkinnedShadowUpdateTriangles = 0;
	s_frameSkinnedShadowsDrawn = 0;
	s_frameEffectLights = 0;
	s_frameRetailLights = 0;
	s_frameLightCandidates = 0;
	s_frameTextureLoads = 0;
	s_frameTextureLoadMs = 0.0;
	s_frameModelLoads = 0;
	s_frameModelLoadMs = 0.0;
	s_frameShadersCreated = 0;
	s_frameDrawablesCreated = 0;
	s_framePipelines = 0;
	s_frameFullCompiles = 0;
	s_frameFFShaders = 0;
	s_framePipelineMs = 0.0;
	s_loadFrame = FALSE;
	memset(s_frameLogicMs, 0, sizeof(s_frameLogicMs));
	s_frameLogicUpdates = 0;
	s_frameSlowestUpdateMs = 0.0;
	s_frameSlowestThing[0] = '\0';
	s_frameSlowestModule[0] = '\0';
	s_framePaths = 0;
	s_framePathCells = 0;
	s_frameSlowestPathMs = 0.0;
	s_frameOpenListSteps = 0;
	s_frameSlowestPathCells = 0;
	s_frameSlowestPathThing[0] = '\0';
}

const char *getOverlayText()
{
	return s_overlayEnabled ? s_overlayText : "";
}

void shutdown()
{
	if (s_dumpFile)
		closeDump("stopped at exit");
}

} // namespace PerfStats
