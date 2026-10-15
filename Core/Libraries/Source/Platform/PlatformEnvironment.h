/*
**	Command & Conquer(tm)
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

// PlatformEnvironment.h - Cross-platform process environment access
// GeneralsX @feature Claude 15/10/2026 Platform abstraction for setting a process environment variable
// that other modules of the process (for example the DXVK d3d8/d3d9 libraries) can read.

#pragma once

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <stdlib.h>
#include <string.h>
#endif

#include <stddef.h>

namespace Platform {

/// Sets an environment variable of the running process. On Windows every module has its own C runtime
/// with its own copy of the environment, so this writes the process environment block, which all
/// modules read with GetEnvironmentVariable. Elsewhere all modules share the C library environment.
inline bool SetProcessEnvironmentVariable(const char *name, const char *value)
{
	if ( !name || name[0] == '\0' || !value ) {
		return false;
	}
#if defined(_WIN32)
	return SetEnvironmentVariableA( name, value ) != FALSE;
#else
	return setenv( name, value, 1 ) == 0;
#endif
}

// GeneralsX @feature Claude 15/10/2026 Reads an environment variable of the running process, including values
// that other modules (for example the DXVK libraries) set with SetProcessEnvironmentVariable or their own
// equivalent. Returns false and an empty buffer when the variable is missing or does not fit.
inline bool GetProcessEnvironmentVariable(const char *name, char *buffer, size_t bufferSize)
{
	if ( !buffer || bufferSize == 0 ) {
		return false;
	}
	buffer[0] = '\0';
	if ( !name || name[0] == '\0' ) {
		return false;
	}
#if defined(_WIN32)
	const DWORD length = GetEnvironmentVariableA( name, buffer, (DWORD)bufferSize );
	if ( length == 0 || length >= bufferSize ) {
		buffer[0] = '\0';
		return false;
	}
	return true;
#else
	const char *value = getenv( name );
	if ( !value ) {
		return false;
	}
	const size_t length = strlen( value );
	if ( length >= bufferSize ) {
		return false;
	}
	memcpy( buffer, value, length + 1 );
	return true;
#endif
}

} // namespace Platform
