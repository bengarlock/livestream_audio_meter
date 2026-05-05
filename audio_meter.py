from __future__ import annotations

import argparse
import array
import json
import math
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass


DEFAULT_STREAM_URL = "rtsps://192.168.1.1:7441/ufgIVAE3C4ZeCNQy?enableSrtp"
SAMPLE_WIDTH_BYTES = 2
INT16_FULL_SCALE = 32768.0
DB_FLOOR = -120.0


@dataclass(frozen=True)
class AudioLevel:
    timestamp: float
    samples: int
    rms_dbfs: float
    peak_dbfs: float
    average_rms_dbfs: float
    loudness_label: str


def dbfs(amplitude: float) -> float:
    if amplitude <= 0:
        return DB_FLOOR
    return max(DB_FLOOR, 20.0 * math.log10(amplitude))


def classify_loudness(rms_dbfs: float) -> str:
    if rms_dbfs >= -12.0:
        return "Very Loud"
    if rms_dbfs >= -24.0:
        return "Loud"
    if rms_dbfs >= -40.0:
        return "Moderate"
    return "Quiet"


def pcm16le_to_levels(chunk: bytes, rolling_rms: deque[float]) -> AudioLevel | None:
    if len(chunk) < SAMPLE_WIDTH_BYTES:
        return None

    usable_length = len(chunk) - (len(chunk) % SAMPLE_WIDTH_BYTES)
    samples = array.array("h")
    samples.frombytes(chunk[:usable_length])

    if sys.byteorder != "little":
        samples.byteswap()

    if not samples:
        return None

    sum_squares = 0
    peak = 0
    for sample in samples:
        abs_sample = abs(sample)
        peak = max(peak, abs_sample)
        sum_squares += sample * sample

    rms = math.sqrt(sum_squares / len(samples)) / INT16_FULL_SCALE
    peak_amplitude = peak / INT16_FULL_SCALE
    rolling_rms.append(rms)

    average_rms = sum(rolling_rms) / len(rolling_rms)

    return AudioLevel(
        timestamp=time.time(),
        samples=len(samples),
        rms_dbfs=dbfs(rms),
        peak_dbfs=dbfs(peak_amplitude),
        average_rms_dbfs=dbfs(average_rms),
        loudness_label=classify_loudness(dbfs(rms)),
    )


def build_ffmpeg_command(
    ffmpeg_path: str,
    stream_url: str,
    sample_rate: int,
    channels: int,
    rtsp_transport: str,
) -> list[str]:
    return [
        ffmpeg_path,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "warning",
        "-rtsp_transport",
        rtsp_transport,
        "-i",
        stream_url,
        "-vn",
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "pipe:1",
    ]


def drain_stderr(process: subprocess.Popen[bytes]) -> None:
    assert process.stderr is not None
    for raw_line in iter(process.stderr.readline, b""):
        line = raw_line.decode(errors="replace").strip()
        if line:
            print(f"ffmpeg: {line}", file=sys.stderr)


def format_level(level: AudioLevel) -> str:
    stamp = time.strftime("%H:%M:%S", time.localtime(level.timestamp))
    return (
        f"{stamp}  "
        f"RMS {level.rms_dbfs:7.2f} dBFS  "
        f"Peak {level.peak_dbfs:7.2f} dBFS  "
        f"Avg {level.average_rms_dbfs:7.2f} dBFS  "
        f"Level: {level.loudness_label}"
    )


def read_exactly(stream, byte_count: int) -> bytes:
    chunks: list[bytes] = []
    bytes_read = 0

    while bytes_read < byte_count:
        chunk = stream.read(byte_count - bytes_read)
        if not chunk:
            break

        chunks.append(chunk)
        bytes_read += len(chunk)

    return b"".join(chunks)


def stream_levels(args: argparse.Namespace) -> int:
    ffmpeg_path = shutil.which(args.ffmpeg)
    if not ffmpeg_path:
        print(
            f"Could not find FFmpeg executable '{args.ffmpeg}'. Install FFmpeg and make sure it is on PATH.",
            file=sys.stderr,
        )
        return 2

    bytes_per_window = int(args.sample_rate * args.channels * SAMPLE_WIDTH_BYTES * args.window_seconds)
    if bytes_per_window <= 0:
        print("--window-seconds must be greater than 0.", file=sys.stderr)
        return 2

    rolling_windows = max(1, int(args.average_seconds / args.window_seconds))
    rolling_rms: deque[float] = deque(maxlen=rolling_windows)

    command = build_ffmpeg_command(
        ffmpeg_path=ffmpeg_path,
        stream_url=args.stream_url,
        sample_rate=args.sample_rate,
        channels=args.channels,
        rtsp_transport=args.rtsp_transport,
    )

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )

    stderr_thread = threading.Thread(target=drain_stderr, args=(process,), daemon=True)
    stderr_thread.start()

    assert process.stdout is not None
    print("Listening for audio levels. Press Ctrl+C to stop.", file=sys.stderr)

    try:
        while True:
            chunk = read_exactly(process.stdout, bytes_per_window)
            if not chunk:
                break

            level = pcm16le_to_levels(chunk, rolling_rms)
            if level is None:
                continue

            if args.json:
                print(json.dumps(level.__dict__), flush=True)
            else:
                print(format_level(level), flush=True)
    except KeyboardInterrupt:
        print("\nStopping.", file=sys.stderr)
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()

    return process.returncode or 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure realtime RTSP/RTSPS livestream audio level in dBFS.")
    parser.add_argument("stream_url", nargs="?", default=DEFAULT_STREAM_URL, help="RTSP/RTSPS stream URL.")
    parser.add_argument("--rtsp-transport", choices=("tcp", "udp"), default="tcp", help="RTSP transport mode.")
    parser.add_argument("--sample-rate", type=int, default=48_000, help="PCM sample rate used for analysis.")
    parser.add_argument("--channels", type=int, default=1, help="Number of audio channels to decode.")
    parser.add_argument("--window-seconds", type=float, default=1.0, help="Measurement interval in seconds.")
    parser.add_argument("--average-seconds", type=float, default=1.0, help="Rolling average duration in seconds.")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="FFmpeg executable name or path.")
    parser.add_argument("--json", action="store_true", help="Print each measurement as JSON.")
    return parser.parse_args()


def main() -> int:
    return stream_levels(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
