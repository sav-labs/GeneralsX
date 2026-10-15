/*
**	Command & Conquer Generals Zero Hour(tm)
**	Copyright 2025 TheSuperHackers
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

#include "W3DDevice/GameClient/W3DScreenshot.h"
#include "W3DDevice/GameClient/W3DCapture.h"
#include "WW3D2/dx8wrapper.h"
#include "WW3D2/surfaceclass.h"
#include "WWLib/mpsc_intrusive_queue.h"
#include <stb_image_write.h>

#ifndef _WIN32
#include <thread>
#endif

struct ScreenshotThreadData
{
	ScreenshotThreadData()
		: pixelData(nullptr)
	{
	}

	~ScreenshotThreadData()
	{
		delete[] pixelData;
	}

	unsigned char* pixelData; // is owner
	unsigned int width;
	unsigned int height;
	unsigned int pitch;
	bool is16Bit;
	// GeneralsX @feature Claude 15/10/2026 Full path of the file, in the bug report capture folder.
	char pathname[_MAX_PATH];
	int quality;
	ScreenshotFormat format;
};

// TheInGameUI is not thread safe, so the screenshot threads cannot show the success message
// themselves. Each thread pushes the written filename onto this queue and the main thread
// shows all pending messages in W3D_UpdateScreenshotMessages, so no message is lost when
// multiple screenshot threads finish within the same frame.
struct ScreenshotWrittenMessage
{
	ScreenshotWrittenMessage* next;
	char pathname[_MAX_PATH];
	bool success;
};
static MPSCIntrusiveQueue<ScreenshotWrittenMessage> s_screenshotWrittenQueue;

#ifdef _WIN32
static DWORD WINAPI screenshotThreadFunc(LPVOID param)
{
	ScreenshotThreadData* data = static_cast<ScreenshotThreadData*>(param);
#else
static void screenshotThreadFunc(ScreenshotThreadData* data)
{
#endif

	// GeneralsX @feature Claude 15/10/2026 Screenshots go to the bug report capture folder (Options.ini
	// CapturePath), which the main thread resolved and created; see W3D_GetCaptureDirectory.
	const char* pathname = data->pathname;

	const unsigned int width = data->width;
	const unsigned int height = data->height;

	// Convert to R8G8B8 for stb_image_write.
	unsigned char* image = new unsigned char[3 * width * height];

	if (!data->is16Bit)
	{
		// Convert A8R8G8B8/X8R8G8B8 to R8G8B8
		for (unsigned int y = 0; y < height; ++y)
		{
			const unsigned int* srcLine = reinterpret_cast<const unsigned int*>(data->pixelData + y * data->pitch);
			for (unsigned int x = 0; x < width; ++x)
			{
				const unsigned int argb = srcLine[x];
				const unsigned int index = 3 * (x + y * width);
				image[index + 0] = (unsigned char)(argb >> 16); // r
				image[index + 1] = (unsigned char)(argb >> 8);  // g
				image[index + 2] = (unsigned char)(argb >> 0);  // b
			}
		}
	}
	else
	{
		// Convert R5G6B5 to R8G8B8
		for (unsigned int y = 0; y < height; ++y)
		{
			const unsigned short* srcLine = reinterpret_cast<const unsigned short*>(data->pixelData + y * data->pitch);
			for (unsigned int x = 0; x < width; ++x)
			{
				const unsigned short rgb = srcLine[x];
				const unsigned int index = 3 * (x + y * width);
				image[index + 0] = (unsigned char)((rgb & 0xF800) >> 8); // r
				image[index + 1] = (unsigned char)((rgb & 0x07E0) >> 3); // g
				image[index + 2] = (unsigned char)((rgb & 0x001F) << 3); // b
			}
		}
	}

	int success = 0;
	switch (data->format)
	{
		case SCREENSHOT_JPEG:
			success = stbi_write_jpg(pathname, width, height, 3, image, data->quality);
			break;
		case SCREENSHOT_PNG:
			success = stbi_write_png(pathname, width, height, 3, image, width * 3);
			break;
	}

	// GeneralsX @feature Claude 15/10/2026 Report failures as well, so a missing capture folder is noticed.
	ScreenshotWrittenMessage* message = new ScreenshotWrittenMessage;
	strlcpy(message->pathname, pathname, ARRAY_SIZE(message->pathname));
	message->success = success != 0;
	s_screenshotWrittenQueue.Push(message);

	fprintf(stderr, "[Capture] Screenshot %s: %s\n", success ? "saved" : "failed", pathname);
	fflush(stderr);

	delete[] image;
	delete data;

#ifdef _WIN32
	return success;
#endif
}

void W3D_UpdateScreenshotMessages()
{
	ScreenshotWrittenMessage* message = s_screenshotWrittenQueue.Flush();
	while (message != nullptr)
	{
		// GeneralsX @feature Claude 15/10/2026 Show the full path and play a click, so the player knows where
		// the file is even when the message is not visible (for example in the menus).
		UnicodeString ufileName;
		ufileName.translate(message->pathname);
		UnicodeString text(message->success ? L"Screenshot saved: " : L"Screenshot failed: ");
		text.concat(ufileName);
		W3D_ShowCaptureMessage(text);
		ScreenshotWrittenMessage* next = message->next;
		delete message;
		message = next;
	}
}

void W3D_TakeCompressedScreenshot(ScreenshotFormat format, Int jpegQuality)
{
	static constexpr const char* const ScreenshotFormatExtensions[] = { "jpg", "png" };
	static_assert(ARRAY_SIZE(ScreenshotFormatExtensions) == SCREENSHOT_FORMAT_COUNT, "Incorrect array size");

	// The filename is created here so the timestamp matches the capture time.
	// GeneralsX @feature Claude 15/10/2026 Date and time file name in the bug report capture folder.
	AsciiString pathname = W3D_GetCaptureDirectory();
	pathname.concat(W3D_MakeCaptureFileName("screenshot", ScreenshotFormatExtensions[format]));

	// TheSuperHackers @bugfix xezon 21/05/2025 Get the back buffer and create a copy of the surface.
	// Originally this code took the front buffer and tried to lock it. This does not work when the
	// render view clips outside the desktop boundaries. It crashed the game.
	SurfaceClass* surface = DX8Wrapper::_Get_DX8_Back_Buffer();
	SurfaceClass::SurfaceDescription surfaceDesc;
	surface->Get_Description(surfaceDesc);

	// TheSuperHackers @bugfix bobtista 08/07/2026 Support the 16 bit back buffer format that the
	// game uses when running in 16 bit color mode. Reading it with the 32 bit stride read garbage.
	const bool is32Bit = surfaceDesc.Format == WW3D_FORMAT_A8R8G8B8 || surfaceDesc.Format == WW3D_FORMAT_X8R8G8B8;
	const bool is16Bit = surfaceDesc.Format == WW3D_FORMAT_R5G6B5;

	if (!is32Bit && !is16Bit)
	{
		DEBUG_LOG(("Screenshot does not support back buffer format %d", (int)surfaceDesc.Format));
		surface->Release_Ref();
		return;
	}

	SurfaceClass* surfaceCopy = NEW_REF(SurfaceClass, (DX8Wrapper::_Create_DX8_Surface(surfaceDesc.Width, surfaceDesc.Height, surfaceDesc.Format)));
	DX8Wrapper::_Copy_DX8_Rects(surface->Peek_D3D_Surface(), nullptr, 0, surfaceCopy->Peek_D3D_Surface(), nullptr);

	surface->Release_Ref();
	surface = nullptr;

	struct Rect
	{
		int Pitch;
		void* pBits;
	} lrect;

	lrect.pBits = surfaceCopy->Lock(&lrect.Pitch);
	if (lrect.pBits == nullptr)
	{
		surfaceCopy->Release_Ref();
		return;
	}

	ScreenshotThreadData* threadData = new ScreenshotThreadData();
	threadData->width = surfaceDesc.Width;
	threadData->height = surfaceDesc.Height;
	threadData->pitch = lrect.Pitch;
	threadData->is16Bit = is16Bit;
	threadData->quality = jpegQuality;
	threadData->format = format;
	strlcpy(threadData->pathname, pathname.str(), ARRAY_SIZE(threadData->pathname));

	// Copy the locked surface with a single memcpy, including any row padding. The pixel
	// conversion and all file operations are done on the screenshot thread to keep the
	// main thread cheap.
	threadData->pixelData = new unsigned char[threadData->pitch * threadData->height];
	memcpy(threadData->pixelData, lrect.pBits, threadData->pitch * threadData->height);

	surfaceCopy->Unlock();
	surfaceCopy->Release_Ref();
	surfaceCopy = nullptr;

#ifdef _WIN32
	const HANDLE hThread = CreateThread(nullptr, 0, screenshotThreadFunc, threadData, 0, nullptr);
	if (hThread)
	{
		CloseHandle(hThread);
	}
	else
	{
		delete threadData;
	}
#else
	std::thread t(screenshotThreadFunc, threadData);
	t.detach();
#endif
}
