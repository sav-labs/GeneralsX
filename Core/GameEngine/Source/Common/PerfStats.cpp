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
		UnsignedInt64 shadowRebuilds;
		UnsignedInt64 shadowRebuildTriangles;
		UnsignedInt64 skinnedShadowUpdates;
		UnsignedInt64 skinnedShadowUpdateTriangles;
		UnsignedInt64 skinnedShadowsDrawn;
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

	Window s_interval;
	Window s_overlay;
	Bool s_windowsStarted = FALSE;

	UnsignedInt64 s_textureBytes = 0;
	UnsignedInt64 s_freeTextureBytes = 0;
	Bool s_textureMemoryKnown = FALSE;

	char s_overlayText[640] = { 0 };

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
	};

	void accumulate(Window &w, double frameMs)
	{
		++w.frames;
		w.frameMsSum += frameMs;
		if (frameMs > w.frameMsMax)
			w.frameMsMax = frameMs;
		for (Int i = 0; i < SECTION_COUNT; ++i)
			w.sectionMs[i] += s_frameSectionMs[i];
		w.drawCalls += s_frameCounters.drawCalls;
		w.triangles += s_frameCounters.triangles;
		w.sortedTriangles += s_frameCounters.sortedTriangles;
		w.skinMeshes += s_frameCounters.skinMeshes;
		w.skinVertices += s_frameCounters.skinVertices;
		w.skinCacheHits += s_frameCounters.skinCacheHits;
		w.shadowRebuilds += s_frameShadowRebuilds;
		w.shadowRebuildTriangles += s_frameShadowRebuildTriangles;
		w.skinnedShadowUpdates += s_frameSkinnedShadowUpdates;
		w.skinnedShadowUpdateTriangles += s_frameSkinnedShadowUpdateTriangles;
		w.skinnedShadowsDrawn += s_frameSkinnedShadowsDrawn;
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
			" [meshes=%.2f shadows=%.2f particles=%.2f] present=%.2f)"
			" | draws=%.0f max=%u tris=%.0fk sorted=%.0fk"
			" | skins=%.1f skinverts=%.1fk cachehits=%.1f"
			" | shadowrebuilds=%.1f (%.1fk tris)"
			" | skinshadows=%.1f updates=%.1f (%.1fk tris) skinshadow_ms=%.2f"
			" | particles=%d max=%d onscreen=%d",
			seconds, n, fps, avg(w.frameMsSum, n), w.frameMsMax,
			avg(w.sectionMs[SECTION_LOGIC], n), avg(w.sectionMs[SECTION_CLIENT], n),
			avg(w.sectionMs[SECTION_DRAWABLES], n), avg(w.sectionMs[SECTION_PARTICLE_UPDATE], n),
			avg(w.sectionMs[SECTION_DRAW], n), avg(w.sectionMs[SECTION_RENDER_TARGETS], n),
			avg(w.sectionMs[SECTION_SCENE], n), avg(w.sectionMs[SECTION_MESH_FLUSH], n),
			avg(w.sectionMs[SECTION_SHADOWS], n), avg(w.sectionMs[SECTION_PARTICLE_RENDER], n),
			avg(w.sectionMs[SECTION_PRESENT], n),
			avg((double)w.drawCalls, n), w.drawCallsMax,
			avg((double)w.triangles, n) / 1000.0, avg((double)w.sortedTriangles, n) / 1000.0,
			avg((double)w.skinMeshes, n), avg((double)w.skinVertices, n) / 1000.0, avg((double)w.skinCacheHits, n),
			avg((double)w.shadowRebuilds, n), avg((double)w.shadowRebuildTriangles, n) / 1000.0,
			avg((double)w.skinnedShadowsDrawn, n), avg((double)w.skinnedShadowUpdates, n),
			avg((double)w.skinnedShadowUpdateTriangles, n) / 1000.0, avg(w.sectionMs[SECTION_SKINNED_SHADOWS], n),
			w.particlesLast, w.particlesMax, w.particlesOnScreenLast);
		if (s_textureMemoryKnown)
		{
			fprintf(stderr, " | textures=%.0fMB vram_free=%.0fMB",
				(double)s_textureBytes / (1024.0 * 1024.0), (double)s_freeTextureBytes / (1024.0 * 1024.0));
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
			"skinned shadows %.0f  updates %.1f  %.2f ms",
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
			avg(w.sectionMs[SECTION_SKINNED_SHADOWS], n));
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
				"skinned_shadows,skinned_shadow_updates,skinned_shadow_update_triangles\n");
			fprintf(stderr, "[PERF] perfdump: recording %.0f seconds to %s\n", s_dumpSeconds, s_dumpPath);
			fflush(stderr);
			s_dumpLastFlushMs = now;
		}

		fprintf(s_dumpFile, "%.3f,%u,%.3f", sinceStart - s_dumpDelaySeconds, logicFrame, frameMs);
		for (Int i = 0; i < SECTION_COUNT; ++i)
			fprintf(s_dumpFile, ",%.3f", s_frameSectionMs[i]);
		fprintf(s_dumpFile, ",%u,%u,%u,%u,%u,%u,%u,%u,%d,%d,%.0f,%u,%u,%u\n",
			s_frameCounters.drawCalls, s_frameCounters.triangles, s_frameCounters.sortedTriangles,
			s_frameCounters.skinMeshes, s_frameCounters.skinVertices, s_frameCounters.skinCacheHits,
			s_frameShadowRebuilds, s_frameShadowRebuildTriangles,
			s_frameCounters.particles, s_frameCounters.particlesOnScreen,
			(double)s_textureBytes / (1024.0 * 1024.0),
			s_frameSkinnedShadowsDrawn, s_frameSkinnedShadowUpdates, s_frameSkinnedShadowUpdateTriangles);
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

	if (s_lastFrameEndMs >= 0.0)
	{
		const double frameMs = now - s_lastFrameEndMs;

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
