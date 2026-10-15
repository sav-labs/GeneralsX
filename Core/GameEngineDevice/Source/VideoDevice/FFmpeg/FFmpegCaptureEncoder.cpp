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

// GeneralsX @feature Claude 15/10/2026 Encoder for bug report video clips, see FFmpegCaptureEncoder.h.

#include "VideoDevice/FFmpeg/FFmpegCaptureEncoder.h"

extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/opt.h>
#include <libswscale/swscale.h>
}

#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <string>
#include <vector>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <objbase.h>
#include <shellapi.h>
#endif

namespace
{

const char *const EncodeArgument = "-captureencode";

// Matroska element IDs, with their length marker bits, as DXVK writes them.
constexpr uint64_t IdSegment = 0x18538067u;
constexpr uint64_t IdCluster = 0x1F43B675u;
constexpr uint64_t IdTracks = 0x1654AE6Bu;
constexpr uint64_t IdTrackEntry = 0xAEu;
constexpr uint64_t IdVideo = 0xE0u;
constexpr uint64_t IdPixelWidth = 0xB0u;
constexpr uint64_t IdPixelHeight = 0xBAu;
constexpr uint64_t IdTimecode = 0xE7u;
constexpr uint64_t IdSimpleBlock = 0xA3u;

// SimpleBlock header: track number (one byte), relative time stamp (two bytes), flags (one byte).
constexpr size_t BlockHeaderSize = 4u;

std::string s_log;

void logLine(const char *format, ...)
{
	char line[1024];
	va_list args;
	va_start(args, format);
	vsnprintf(line, sizeof(line), format, args);
	va_end(args);

	s_log += line;
	s_log += '\n';
	fprintf(stderr, "[CaptureEncoder] %s\n", line);
	fflush(stderr);
}

std::string errorText(int error)
{
	char text[AV_ERROR_MAX_STRING_SIZE] = {};
	av_strerror(error, text, sizeof(text));
	return text;
}

/// Reads the video stream from standard input.
class InputStream
{
public:
	InputStream()
	{
#ifdef _WIN32
		m_handle = GetStdHandle(STD_INPUT_HANDLE);
#endif
	}

	bool read(void *data, size_t size)
	{
		uint8_t *bytes = static_cast<uint8_t *>(data);
		while (size > 0)
		{
#ifdef _WIN32
			DWORD done = 0;
			const DWORD chunk = size > (1u << 30) ? (1u << 30) : (DWORD)size;
			if (m_handle == nullptr || m_handle == INVALID_HANDLE_VALUE || !ReadFile(m_handle, bytes, chunk, &done, nullptr) || done == 0)
				return false;
#else
			const size_t done = fread(bytes, 1, size, stdin);
			if (done == 0)
				return false;
#endif
			bytes += done;
			size -= done;
		}
		return true;
	}

	bool skip(uint64_t size)
	{
		uint8_t buffer[4096];
		while (size > 0)
		{
			const size_t chunk = size > sizeof(buffer) ? sizeof(buffer) : (size_t)size;
			if (!read(buffer, chunk))
				return false;
			size -= chunk;
		}
		return true;
	}

	/// Reads an EBML variable length integer. IDs keep their length marker, sizes do not.
	bool readVint(uint64_t &value, bool keepMarker, bool *unknownSize)
	{
		uint8_t first = 0;
		if (!read(&first, 1) || first == 0)
			return false;

		int length = 1;
		while (!(first & (0x80u >> (length - 1))))
			++length;

		value = keepMarker ? first : (first & (0xFFu >> length));
		bool allOnes = value == (0xFFu >> length);

		for (int i = 1; i < length; ++i)
		{
			uint8_t byte = 0;
			if (!read(&byte, 1))
				return false;
			value = (value << 8) | byte;
			allOnes = allOnes && byte == 0xFFu;
		}

		if (unknownSize)
			*unknownSize = !keepMarker && allOnes;
		return true;
	}

private:
#ifdef _WIN32
	HANDLE m_handle = nullptr;
#endif
};

/// Reads an EBML variable length integer from memory.
bool readVintFromMemory(const uint8_t *&data, const uint8_t *end, uint64_t &value, bool keepMarker)
{
	if (data >= end || *data == 0)
		return false;

	const uint8_t first = *data++;
	int length = 1;
	while (!(first & (0x80u >> (length - 1))))
		++length;

	value = keepMarker ? first : (first & (0xFFu >> length));
	for (int i = 1; i < length; ++i)
	{
		if (data >= end)
			return false;
		value = (value << 8) | *data++;
	}
	return true;
}

uint64_t readUnsigned(const uint8_t *data, uint64_t size)
{
	uint64_t value = 0;
	for (uint64_t i = 0; i < size; ++i)
		value = (value << 8) | data[i];
	return value;
}

/// Finds the frame size in the Tracks element.
void findVideoSize(const uint8_t *data, const uint8_t *end, uint64_t &width, uint64_t &height)
{
	while (data < end)
	{
		uint64_t id = 0;
		uint64_t size = 0;
		if (!readVintFromMemory(data, end, id, true) || !readVintFromMemory(data, end, size, false) || size > (uint64_t)(end - data))
			return;

		if (id == IdTrackEntry || id == IdVideo)
			findVideoSize(data, data + size, width, height);
		else if (id == IdPixelWidth)
			width = readUnsigned(data, size);
		else if (id == IdPixelHeight)
			height = readUnsigned(data, size);

		data += size;
	}
}

/// Encodes BGRA frames into an mp4 file.
class Encoder
{
public:
	~Encoder()
	{
		sws_freeContext(m_sws);
		av_frame_free(&m_frame);
		av_packet_free(&m_packet);
		avcodec_free_context(&m_codec);
		if (m_format)
		{
			if (m_format->pb)
				avio_closep(&m_format->pb);
			avformat_free_context(m_format);
		}
	}

	bool open(const char *path, int width, int height)
	{
		m_width = width;
		m_height = height;

		int result = avformat_alloc_output_context2(&m_format, nullptr, "mp4", path);
		if (result < 0 || !m_format)
		{
			logLine("Cannot create the mp4 container: %s", errorText(result).c_str());
			return false;
		}

		if (!openCodec())
			return false;

		m_stream = avformat_new_stream(m_format, nullptr);
		if (!m_stream)
		{
			logLine("Cannot create the video stream");
			return false;
		}
		m_stream->time_base = m_codec->time_base;
		avcodec_parameters_from_context(m_stream->codecpar, m_codec);

		result = avio_open(&m_format->pb, path, AVIO_FLAG_WRITE);
		if (result < 0)
		{
			logLine("Cannot create %s: %s", path, errorText(result).c_str());
			return false;
		}

		result = avformat_write_header(m_format, nullptr);
		if (result < 0)
		{
			logLine("Cannot write the mp4 header: %s", errorText(result).c_str());
			return false;
		}

		m_sws = sws_getContext(width, height, AV_PIX_FMT_BGRA, width, height, m_codec->pix_fmt, SWS_POINT, nullptr, nullptr, nullptr);
		m_frame = av_frame_alloc();
		m_packet = av_packet_alloc();
		if (!m_sws || !m_frame || !m_packet)
		{
			logLine("Cannot create the pixel converter");
			return false;
		}

		m_frame->format = m_codec->pix_fmt;
		m_frame->width = width;
		m_frame->height = height;
		result = av_frame_get_buffer(m_frame, 0);
		if (result < 0)
		{
			logLine("Cannot allocate a video frame: %s", errorText(result).c_str());
			return false;
		}

		logLine("Encoding %dx%d with %s to %s", width, height, m_codec->codec->name, path);
		return true;
	}

	bool encode(const uint8_t *bgra, int64_t timeMs)
	{
		int result = av_frame_make_writable(m_frame);
		if (result < 0)
		{
			logLine("Cannot write a video frame: %s", errorText(result).c_str());
			return false;
		}

		const uint8_t *const source[1] = { bgra };
		const int sourceStride[1] = { m_width * 4 };
		sws_scale(m_sws, source, sourceStride, 0, m_height, m_frame->data, m_frame->linesize);

		// Present time stamps are in milliseconds; two presents within the same millisecond still need
		// increasing time stamps.
		if (timeMs <= m_lastPts)
			timeMs = m_lastPts + 1;
		m_lastPts = timeMs;
		m_frame->pts = timeMs;

		result = avcodec_send_frame(m_codec, m_frame);
		if (result < 0)
		{
			logLine("Cannot encode a video frame: %s", errorText(result).c_str());
			return false;
		}
		++m_frames;
		return writePackets();
	}

	bool finish()
	{
		avcodec_send_frame(m_codec, nullptr);
		if (!writePackets())
			return false;

		const int result = av_write_trailer(m_format);
		if (result < 0)
		{
			logLine("Cannot finish the mp4 file: %s", errorText(result).c_str());
			return false;
		}
		logLine("Wrote %d frames, %.1f s", m_frames, m_lastPts > 0 ? m_lastPts / 1000.0 : 0.0);
		return true;
	}

private:
	bool openCodec()
	{
		// H.264 when this FFmpeg build has an encoder for it, otherwise MPEG-4 Part 2, which FFmpeg always
		// includes and which common players (VLC, Windows Media Player, mpv) play.
		struct Candidate
		{
			const char *name;
			AVPixelFormat pixelFormat;
		};
		static const Candidate candidates[] =
		{
			{ "libx264", AV_PIX_FMT_YUV420P },
			{ "h264_mf", AV_PIX_FMT_NV12 },
			{ "libopenh264", AV_PIX_FMT_YUV420P },
			{ "mpeg4", AV_PIX_FMT_YUV420P },
		};

		// About 8 Mbit/s for 1080p, scaled by the frame area, for encoders without a quality mode.
		const int64_t bitRate = (int64_t)8000000 * m_width * m_height / (1920 * 1080);

		for (const Candidate &candidate : candidates)
		{
			const AVCodec *codec = avcodec_find_encoder_by_name(candidate.name);
			if (!codec)
				continue;

			m_codec = avcodec_alloc_context3(codec);
			if (!m_codec)
				continue;

			m_codec->width = m_width;
			m_codec->height = m_height;
			m_codec->pix_fmt = candidate.pixelFormat;
			m_codec->time_base = AVRational{ 1, 1000 };
			m_codec->framerate = AVRational{ 60, 1 };
			m_codec->gop_size = 120;
			m_codec->max_b_frames = 0;
			m_codec->bit_rate = bitRate > 2000000 ? bitRate : 2000000;
			m_codec->thread_count = 0;
			if (m_format->oformat->flags & AVFMT_GLOBALHEADER)
				m_codec->flags |= AV_CODEC_FLAG_GLOBAL_HEADER;

			if (strcmp(candidate.name, "libx264") == 0)
			{
				av_opt_set(m_codec->priv_data, "preset", "veryfast", 0);
				av_opt_set(m_codec->priv_data, "crf", "20", 0);
			}
			else if (strcmp(candidate.name, "mpeg4") == 0)
			{
				// Constant quality; 3 keeps small interface text readable.
				m_codec->flags |= AV_CODEC_FLAG_QSCALE;
				m_codec->global_quality = FF_QP2LAMBDA * 3;
			}

			const int result = avcodec_open2(m_codec, codec, nullptr);
			if (result >= 0)
				return true;

			logLine("Encoder %s is not usable: %s", candidate.name, errorText(result).c_str());
			avcodec_free_context(&m_codec);
		}

		logLine("No usable video encoder in this FFmpeg build");
		return false;
	}

	bool writePackets()
	{
		while (true)
		{
			int result = avcodec_receive_packet(m_codec, m_packet);
			if (result == AVERROR(EAGAIN) || result == AVERROR_EOF)
				return true;
			if (result < 0)
			{
				logLine("Cannot encode a video frame: %s", errorText(result).c_str());
				return false;
			}

			av_packet_rescale_ts(m_packet, m_codec->time_base, m_stream->time_base);
			m_packet->stream_index = m_stream->index;
			result = av_interleaved_write_frame(m_format, m_packet);
			if (result < 0)
			{
				logLine("Cannot write to the mp4 file: %s", errorText(result).c_str());
				return false;
			}
		}
	}

	AVFormatContext *m_format = nullptr;
	AVCodecContext *m_codec = nullptr;
	AVStream *m_stream = nullptr;
	SwsContext *m_sws = nullptr;
	AVFrame *m_frame = nullptr;
	AVPacket *m_packet = nullptr;
	int m_width = 0;
	int m_height = 0;
	int m_frames = 0;
	int64_t m_lastPts = -1;
};

/// Reads the Matroska stream from standard input and encodes every frame.
bool encodeStream(const char *path)
{
	InputStream input;
	Encoder encoder;
	bool encoderOpen = false;
	uint64_t width = 0;
	uint64_t height = 0;
	uint64_t clusterTime = 0;
	std::vector<uint8_t> pixels;

	while (true)
	{
		uint64_t id = 0;
		uint64_t size = 0;
		bool unknownSize = false;
		if (!input.readVint(id, true, nullptr))
			break; // end of the stream
		if (!input.readVint(size, false, &unknownSize))
		{
			logLine("The video stream ended inside an element");
			break;
		}

		if (id == IdSegment || id == IdCluster)
			continue; // master elements: read their children in place

		if (unknownSize)
		{
			logLine("Unexpected element 0x%llx of unknown size", (unsigned long long)id);
			return false;
		}

		if (id == IdTracks)
		{
			if (size > (1u << 20))
			{
				logLine("The track description is too large");
				return false;
			}
			std::vector<uint8_t> tracks((size_t)size);
			if (!input.read(tracks.data(), tracks.size()))
				break;
			findVideoSize(tracks.data(), tracks.data() + tracks.size(), width, height);

			if (width == 0 || height == 0 || width > 16384 || height > 16384)
			{
				logLine("Invalid video size %llux%llu", (unsigned long long)width, (unsigned long long)height);
				return false;
			}
			pixels.resize((size_t)(width * height * 4u));
			if (!encoder.open(path, (int)width, (int)height))
				return false;
			encoderOpen = true;
		}
		else if (id == IdTimecode)
		{
			uint8_t value[8] = {};
			if (size > sizeof(value) || !input.read(value, (size_t)size))
				break;
			clusterTime = readUnsigned(value, size);
		}
		else if (id == IdSimpleBlock && encoderOpen && size == BlockHeaderSize + pixels.size())
		{
			uint8_t header[BlockHeaderSize];
			if (!input.read(header, sizeof(header)) || !input.read(pixels.data(), pixels.size()))
			{
				logLine("The video stream ended inside a frame");
				break;
			}
			const int16_t relativeTime = (int16_t)((header[1] << 8) | header[2]);
			if (!encoder.encode(pixels.data(), (int64_t)clusterTime + relativeTime))
				return false;
		}
		else if (!input.skip(size))
		{
			break;
		}
	}

	if (!encoderOpen)
	{
		logLine("The video stream had no frames");
		return false;
	}
	return encoder.finish();
}

#ifdef _WIN32
std::string toUtf8(const wchar_t *text)
{
	const int size = WideCharToMultiByte(CP_UTF8, 0, text, -1, nullptr, 0, nullptr, nullptr);
	if (size <= 0)
		return std::string();
	std::string result((size_t)size, '\0');
	WideCharToMultiByte(CP_UTF8, 0, text, -1, &result[0], size, nullptr, nullptr);
	result.resize((size_t)size - 1);
	return result;
}
#endif

void writeFailureLog(const std::string &outputPath)
{
	// The helper has no window; leave the reason next to the missing video.
	const std::string logPath = outputPath + ".log";
#ifdef _WIN32
	const int size = MultiByteToWideChar(CP_UTF8, 0, logPath.c_str(), -1, nullptr, 0);
	std::vector<wchar_t> widePath(size > 0 ? (size_t)size : 1u, L'\0');
	MultiByteToWideChar(CP_UTF8, 0, logPath.c_str(), -1, widePath.data(), size);
	FILE *file = _wfopen(widePath.data(), L"w");
#else
	FILE *file = fopen(logPath.c_str(), "w");
#endif
	if (file)
	{
		fputs(s_log.c_str(), file);
		fclose(file);
	}
}

} // namespace

bool FFmpegCaptureEncoder_RunFromCommandLine(int argc, char *argv[], int &exitCode)
{
	std::string outputPath;
	bool requested = false;

#ifdef _WIN32
	(void)argc;
	(void)argv;
	int wideCount = 0;
	LPWSTR *wideArgs = CommandLineToArgvW(GetCommandLineW(), &wideCount);
	if (wideArgs)
	{
		for (int i = 1; i < wideCount; ++i)
		{
			if (_wcsicmp(wideArgs[i], L"-captureencode") == 0)
			{
				requested = true;
				if (i + 1 < wideCount)
					outputPath = toUtf8(wideArgs[i + 1]);
				break;
			}
		}
		LocalFree(wideArgs);
	}
#else
	for (int i = 1; i < argc; ++i)
	{
		if (strcmp(argv[i], EncodeArgument) == 0)
		{
			requested = true;
			if (i + 1 < argc)
				outputPath = argv[i + 1];
			break;
		}
	}
#endif

	if (!requested)
		return false;

	if (outputPath.empty())
	{
		logLine("Usage: %s <output.mp4>", EncodeArgument);
		exitCode = 2;
		return true;
	}

#ifdef _WIN32
	// h264_mf runs on Media Foundation, which needs COM on this thread.
	const HRESULT comResult = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
#endif

	const bool success = encodeStream(outputPath.c_str());
	if (!success)
		writeFailureLog(outputPath);

#ifdef _WIN32
	if (SUCCEEDED(comResult))
		CoUninitialize();
#endif

	exitCode = success ? 0 : 1;
	return true;
}
