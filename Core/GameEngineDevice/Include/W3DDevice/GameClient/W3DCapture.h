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

// GeneralsX @feature Claude 15/10/2026 Screenshots and video clips for bug reports.
// Both are saved with a date and time file name into Options.ini CapturePath (default D:\GeneralsX\bugs on
// Windows), or into a bugs folder in the user data folder or the game folder when that cannot be created.
// Video clips are recorded by DXVK (cmake/dxvk-patches/0012-present-video-capture-control.patch) from the
// presented frames; with FFmpeg the game itself, started as a helper process, encodes them to mp4.

#pragma once

#include "Lib/BaseType.h"
#include "Common/AsciiString.h"
#include "Common/UnicodeString.h"

/// Folder for captures, with a trailing separator. Created if missing; falls back as described above.
AsciiString W3D_GetCaptureDirectory();

/// File name of the form <prefix>_YYYY-MM-DD_HH-MM-SS-mmm.<extension>, from the local time.
AsciiString W3D_MakeCaptureFileName(const char *prefix, const char *extension);

/// Shows a capture message in game and plays the GUI click sound. Main thread only.
void W3D_ShowCaptureMessage(const UnicodeString &text);

/// Starts or stops a video clip.
void W3D_ToggleVideoCapture();

/// Called once per frame on the main thread to follow the state of the video clip.
void W3D_UpdateVideoCapture();
