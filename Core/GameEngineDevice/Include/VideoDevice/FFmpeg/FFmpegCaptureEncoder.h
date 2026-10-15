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

// GeneralsX @feature Claude 15/10/2026 Encoder for bug report video clips.
// DXVK records the presented frames (cmake/dxvk-patches/0012-present-video-capture-control.patch) and streams
// them as Matroska raw BGRA video with present time stamps to the standard input of a command. The game uses
// a helper copy of its own executable as that command, started with
//     <game executable> -captureencode <output.mp4>
// so that the clip is encoded with the FFmpeg libraries the game already ships, without an ffmpeg.exe.
// The helper handles the command line before any game initialization and exits when the stream ends.

#pragma once

/// When the command line asks for the capture encoder, encodes standard input to the given file and returns
/// true with the process exit code; otherwise returns false and the game starts normally. On Windows the
/// arguments are read from the wide process command line and argc/argv are not used.
bool FFmpegCaptureEncoder_RunFromCommandLine(int argc, char *argv[], int &exitCode);
