#!/usr/bin/env python3
"""Encode a DXVK_CAPTURE_VIDEO=raw:<path> capture into an mp4 with exact frame timing.

DXVK writes <path>.bgra (concatenated BGRA frames) and <path>.txt ("w h" on the
first line, then the present time stamp of each frame in microseconds). This
script streams the frames to ffmpeg as Matroska raw video with those time
stamps, so the mp4 keeps the real presentation timing, including stutter.

Usage:
    python3 scripts/qa/dxvk_video_to_mp4.py <path> [out.mp4] [-- extra ffmpeg output args]

Example:
    python3 scripts/qa/dxvk_video_to_mp4.py ~/caps/clip clip.mp4
"""

import subprocess
import sys


def ebml_id(value):
    return value.to_bytes((value.bit_length() + 7) // 8, "big")


def ebml_size(size):
    return b"\x01" + size.to_bytes(7, "big")


def element(eid, data):
    return ebml_id(eid) + ebml_size(len(data)) + data


def uint(eid, value):
    return element(eid, value.to_bytes(8, "big"))


def header(width, height):
    ebml = (uint(0x4286, 1) + uint(0x42F7, 1) + uint(0x42F2, 4) + uint(0x42F3, 8)
            + element(0x4282, b"matroska") + uint(0x4287, 4) + uint(0x4285, 2))
    info = uint(0x2AD7B1, 1000000) + element(0x4D80, b"dxvk_video_to_mp4") + element(0x5741, b"dxvk_video_to_mp4")
    video = uint(0xB0, width) + uint(0xBA, height) + element(0x2EB524, b"BGRA")
    track = (uint(0xD7, 1) + uint(0x73C5, 1) + uint(0x83, 1) + uint(0x9C, 0)
             + element(0x86, b"V_UNCOMPRESSED") + element(0xE0, video))
    return (element(0x1A45DFA3, ebml) + ebml_id(0x18538067) + b"\x01" + b"\xff" * 7
            + element(0x1549A966, info) + element(0x1654AE6B, element(0xAE, track)))


def main():
    args = sys.argv[1:]
    extra = []
    if "--" in args:
        extra = args[args.index("--") + 1:]
        args = args[:args.index("--")]
    if not args:
        print(__doc__)
        return 2

    base = args[0]
    out = args[1] if len(args) > 1 else base + ".mp4"

    with open(base + ".txt") as f:
        width, height = (int(v) for v in f.readline().split())
        stamps = [int(line) for line in f if line.strip()]

    frame_size = width * height * 4
    if len(stamps) > 1:
        seconds = (stamps[-1] - stamps[0]) / 1e6
        print(f"{len(stamps)} frames, {width}x{height}, {seconds:.3f} s, "
              f"average {(len(stamps) - 1) / seconds:.2f} fps")

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "matroska", "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
           "-fps_mode", "passthrough", "-enc_time_base", "-1"] + extra + [out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    proc.stdin.write(header(width, height))

    block_header = b"\x81\x00\x00\x80"
    with open(base + ".bgra", "rb") as frames:
        for stamp in stamps:
            pixels = frames.read(frame_size)
            if len(pixels) < frame_size:
                print("warning: .bgra file is shorter than the time stamp list")
                break
            timecode = uint(0xE7, (stamp + 500) // 1000)
            block = ebml_id(0xA3) + ebml_size(len(block_header) + frame_size) + block_header
            cluster_size = len(timecode) + len(block) + frame_size
            proc.stdin.write(ebml_id(0x1F43B675) + ebml_size(cluster_size) + timecode + block)
            proc.stdin.write(pixels)

    proc.stdin.close()
    result = proc.wait()
    if result == 0:
        print(f"wrote {out}")
    return result


if __name__ == "__main__":
    sys.exit(main())
