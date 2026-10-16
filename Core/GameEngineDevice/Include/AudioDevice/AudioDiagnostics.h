/*
**	Command & Conquer Generals Zero Hour(tm)
**	Copyright 2026 GeneralsX
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

// GeneralsX @bugfix Claude 15/10/2026 Release-build audio diagnostics shared by the MiniAudio and OpenAL backends.
// Every line goes to stderr and to AudioDiagnostics.txt in the user data folder, because the stderr of a
// Windows GUI executable is discarded unless the caller redirects it. The log only reads audio state and
// never feeds anything back into the game logic.

#pragma once

#include "Common/AsciiString.h"
#include "Common/GlobalData.h"

#include <stdarg.h>
#include <stdio.h>

namespace AudioDiagnostics
{

enum { MAX_REPORTED_FILE_FAILURES = 5, MAX_REPORTED_FILE_SUCCESSES = 3 };

struct State
{
	FILE *file;
	Bool fileTried;
	UnsignedInt filesPlayed;
	UnsignedInt fileFailures;
};

inline State &getState()
{
	static State state = { nullptr, false, 0, 0 };
	return state;
}

/// The log file is opened once the user data folder is known (GlobalData exists).
inline FILE *getFile()
{
	State &state = getState();
	if (!state.fileTried && TheGlobalData != nullptr)
	{
		state.fileTried = true;
		AsciiString path = TheGlobalData->getPath_UserData();
		path.concat("AudioDiagnostics.txt");
		state.file = fopen(path.str(), "w");
		if (state.file != nullptr)
		{
			fprintf(stderr, "[Audio] Diagnostics are also written to %s\n", path.str());
			fflush(stderr);
		}
	}
	return state.file;
}

inline void print(const char *format, ...)
{
	char line[1024];
	va_list args;
	va_start(args, format);
	vsnprintf(line, sizeof(line), format, args);
	va_end(args);

	fprintf(stderr, "[Audio] %s\n", line);
	fflush(stderr);

	FILE *file = getFile();
	if (file != nullptr)
	{
		fprintf(file, "[Audio] %s\n", line);
		fflush(file);
	}
}

inline void logSummary(const char *when)
{
	const State &state = getState();
	print("Summary (%s): %u sound files decoded and started, %u failed to open or decode", when, state.filesPlayed, state.fileFailures);
}

/// Report the first few failures with their path, then only count them.
inline void noteFileFailure(const char *reason, const char *path)
{
	State &state = getState();
	++state.fileFailures;
	if (state.fileFailures <= MAX_REPORTED_FILE_FAILURES)
	{
		print("Sound file failure %u: %s: '%s'", state.fileFailures, reason, path ? path : "");
		if (state.fileFailures == MAX_REPORTED_FILE_FAILURES)
			print("Further sound file failures are only counted");
	}
}

inline void noteFilePlayed(const char *path, Int sampleRate, Int channels)
{
	State &state = getState();
	++state.filesPlayed;
	if (state.filesPlayed <= MAX_REPORTED_FILE_SUCCESSES)
		print("Playing '%s' (%d Hz, %d channels)", path ? path : "", sampleRate, channels);
	if (state.filesPlayed == 10 || state.filesPlayed == 100 || state.filesPlayed == 1000)
		logSummary("running");
}

} // namespace AudioDiagnostics
