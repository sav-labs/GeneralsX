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

// GeneralsX @feature Claude 15/10/2026 Screenshots and video clips for bug reports, see W3DCapture.h.

#include "W3DDevice/GameClient/W3DCapture.h"
#include "Common/GameAudio.h"
#include "Common/GlobalData.h"
#include "Common/MiscAudio.h"
#include "Common/OptionPreferences.h"
#include "GameClient/InGameUI.h"
#include "PlatformEnvironment.h"
#include "PlatformPaths.h"

#include <chrono>
#include <stdio.h>

namespace
{

// Video clips are scaled down to at most this many lines, which keeps the raw frame stream that DXVK hands
// to the encoder small enough for real time encoding on the CPU while keeping the interface readable.
constexpr Int VideoMaxHeight = 1080;

// How long to wait for DXVK to accept a clip, and for the encoder to finish one, in milliseconds.
constexpr Int VideoStartTimeoutMs = 3000;
constexpr Int VideoStopTimeoutMs = 120000;

const char *const VideoControlVariable = "DXVK_CAPTURE_VIDEO_CONTROL";
const char *const VideoStateVariable = "DXVK_CAPTURE_VIDEO_STATE";

enum VideoCaptureState
{
	VIDEO_CAPTURE_IDLE,
	VIDEO_CAPTURE_STARTING,
	VIDEO_CAPTURE_RECORDING,
	VIDEO_CAPTURE_STOPPING,
};

VideoCaptureState s_videoState = VIDEO_CAPTURE_IDLE;
AsciiString s_videoTarget;		///< DXVK_CAPTURE_VIDEO target of the current clip
AsciiString s_videoFile;			///< file the clip ends up in
std::chrono::steady_clock::time_point s_videoDeadline;

bool isSeparator(char c)
{
	return c == '\\' || c == '/';
}

AsciiString withTrailingSeparator(const AsciiString &path)
{
	AsciiString result = path;
	if (!result.isEmpty() && !isSeparator(result.getCharAt(result.getLength() - 1)))
	{
#ifdef _WIN32
		result.concat('\\');
#else
		result.concat('/');
#endif
	}
	return result;
}

Bool tryCaptureDirectory(const AsciiString &path, AsciiString &result)
{
	if (path.isEmpty())
		return FALSE;

	if (!Platform::CreateDirectoryTree(path.str()))
	{
		fprintf(stderr, "[Capture] Cannot create capture folder %s\n", path.str());
		fflush(stderr);
		return FALSE;
	}

	result = withTrailingSeparator(path);
	return TRUE;
}

Int getFileSize(const AsciiString &path)
{
	FILE *file = fopen(path.str(), "rb");
	if (file == nullptr)
		return -1;

	fseek(file, 0, SEEK_END);
	const long size = ftell(file);
	fclose(file);
	return (Int)size;
}

void setVideoControl(const char *value)
{
	Platform::SetProcessEnvironmentVariable(VideoControlVariable, value);
}

void finishVideoCapture()
{
	setVideoControl("");
	s_videoState = VIDEO_CAPTURE_IDLE;

	UnicodeString file;
	file.translate(s_videoFile);

	UnicodeString text(getFileSize(s_videoFile) > 0 ? L"Recording saved: " : L"Recording failed, nothing was written to ");
	text.concat(file);

	fprintf(stderr, "[Capture] Video clip finished: %s (%d bytes)\n", s_videoFile.str(), getFileSize(s_videoFile));
	fflush(stderr);
	W3D_ShowCaptureMessage(text);
}

void startVideoCapture()
{
	const AsciiString directory = W3D_GetCaptureDirectory();

#ifdef RTS_HAS_FFMPEG
	// The game encodes the clip itself: DXVK starts a helper copy of this executable and streams the frames
	// to its standard input (see FFmpegCaptureEncoder.h).
	char exePath[1024];
	if (!Platform::GetExecutablePath(exePath, sizeof(exePath)))
	{
		W3D_ShowCaptureMessage(UnicodeString(L"Recording failed: the game executable path is unknown"));
		return;
	}

	s_videoFile = directory;
	s_videoFile.concat(W3D_MakeCaptureFileName("video", "mp4"));
	s_videoTarget.format("\"%s\" -captureencode \"%s\"", exePath, s_videoFile.str());
#else
	// Without FFmpeg, DXVK writes raw frames (<name>.bgra plus <name>.txt with the frame times).
	// scripts/qa/dxvk_video_to_mp4.py turns them into an mp4.
	AsciiString base = directory;
	base.concat(W3D_MakeCaptureFileName("video", "raw"));
	s_videoFile = base;
	s_videoFile.concat(".bgra");
	s_videoTarget.format("raw:%s", base.str());
#endif

	AsciiString control;
	control.format("%d|%s", VideoMaxHeight, s_videoTarget.str());

	Platform::SetProcessEnvironmentVariable(VideoStateVariable, "");
	setVideoControl(control.str());

	s_videoState = VIDEO_CAPTURE_STARTING;
	s_videoDeadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(VideoStartTimeoutMs);

	fprintf(stderr, "[Capture] Video clip requested: %s\n", s_videoTarget.str());
	fflush(stderr);
}

} // namespace

AsciiString W3D_GetCaptureDirectory()
{
	AsciiString result;

	OptionPreferences prefs;
	if (tryCaptureDirectory(prefs.getCapturePath(), result))
		return result;

	AsciiString userData = withTrailingSeparator(TheGlobalData->getPath_UserData());
	userData.concat("bugs");
	if (tryCaptureDirectory(userData, result))
		return result;

	if (tryCaptureDirectory(AsciiString("bugs"), result))
		return result;

	return AsciiString::TheEmptyString;
}

AsciiString W3D_MakeCaptureFileName(const char *prefix, const char *extension)
{
	SYSTEMTIME st;
	GetLocalTime(&st);

	AsciiString name;
	name.format("%s_%04d-%02d-%02d_%02d-%02d-%02d-%03d.%s", prefix,
		st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond, st.wMilliseconds, extension);
	return name;
}

void W3D_ShowCaptureMessage(const UnicodeString &text)
{
	if (TheInGameUI)
		TheInGameUI->messageNoFormat(text);

	if (TheAudio)
		TheAudio->addAudioEvent(&TheAudio->getMiscAudio()->m_guiClickSound);
}

void W3D_ToggleVideoCapture()
{
	switch (s_videoState)
	{
		case VIDEO_CAPTURE_IDLE:
			startVideoCapture();
			break;

		case VIDEO_CAPTURE_STARTING:
		case VIDEO_CAPTURE_RECORDING:
			setVideoControl("");
			s_videoState = VIDEO_CAPTURE_STOPPING;
			s_videoDeadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(VideoStopTimeoutMs);
			W3D_ShowCaptureMessage(UnicodeString(L"Recording stopped, saving..."));
			break;

		case VIDEO_CAPTURE_STOPPING:
			W3D_ShowCaptureMessage(UnicodeString(L"Still saving the previous recording"));
			break;
	}
}

void W3D_UpdateVideoCapture()
{
	if (s_videoState == VIDEO_CAPTURE_IDLE)
		return;

	char state[2048];
	Platform::GetProcessEnvironmentVariable(VideoStateVariable, state, sizeof(state));

	AsciiString recording("recording|");
	recording.concat(s_videoTarget);
	AsciiString stopped("stopped|");
	stopped.concat(s_videoTarget);

	const Bool isRecording = recording.compare(state) == 0;
	const Bool isStopped = stopped.compare(state) == 0;
	const Bool timedOut = std::chrono::steady_clock::now() >= s_videoDeadline;

	switch (s_videoState)
	{
		case VIDEO_CAPTURE_STARTING:
			if (isRecording)
			{
				s_videoState = VIDEO_CAPTURE_RECORDING;
				W3D_ShowCaptureMessage(UnicodeString(L"Recording started, press F11 or Ctrl+Shift+R to stop"));
			}
			else if (isStopped)
			{
				finishVideoCapture();
			}
			else if (timedOut || strncmp(state, "invalid|", 8) == 0)
			{
				setVideoControl("");
				s_videoState = VIDEO_CAPTURE_IDLE;
				fprintf(stderr, "[Capture] DXVK did not accept the video clip (state '%s')\n", state);
				fflush(stderr);
				W3D_ShowCaptureMessage(UnicodeString(L"Recording is not available: it needs the DXVK d3d8.dll and d3d9.dll from the GeneralsX package"));
			}
			break;

		case VIDEO_CAPTURE_RECORDING:
			// DXVK ends a clip by itself when the swap chain is recreated, the encoder fails or the clip
			// reaches its 30 minute limit.
			if (isStopped)
				finishVideoCapture();
			break;

		case VIDEO_CAPTURE_STOPPING:
			if (isStopped || timedOut)
				finishVideoCapture();
			break;

		case VIDEO_CAPTURE_IDLE:
			break;
	}
}
