"""Audio -> SP-404MK2 import format, via ffmpeg.

The SP-404MK2 accepts 16-bit linear WAV/AIFF/MP3 from the SD card and converts
everything to 48 kHz/16-bit on import [verified: Roland support docs, 2026-08-02].
Doing that conversion here rather than letting the device do it means what lands
on the card is byte-for-byte what the SP will play — no surprises at import time,
and the file is already in the same format the SP records and resamples at.

Max sample length is 16 minutes / ~176 MB [verified], so full-length tracks for
DJ mode fit comfortably; `check_length` flags anything that would be refused.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass

# SP-404MK2 native sample format. Not configurable — the device converts to
# this on import regardless, so writing anything else only adds a conversion.
SP_RATE = 48000
SP_BITS = 16
SP_CODEC = "pcm_s16le"

# Roland documents a 16 minute / ~176 MB ceiling per sample [verified].
MAX_SAMPLE_SECS = 16 * 60

# Filename cap. The exact on-device display limit is NOT documented and is
# [UNVERIFIED] — 32 is deliberately conservative. Widen once the hardware is
# here and the real limit has been observed.
MAX_NAME_LEN = 32


class ConvertError(RuntimeError):
    pass


@dataclass
class ConvertResult:
    success: bool
    file_path: str = ""
    source_path: str = ""
    duration_secs: float = 0.0
    size_bytes: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "file_path": self.file_path,
            "source_path": self.source_path,
            "duration_secs": round(self.duration_secs, 2),
            "size_bytes": self.size_bytes,
            "error": self.error,
        }


def is_available() -> bool:
    """True if ffmpeg and ffprobe are both callable."""
    for binary in ("ffmpeg", "ffprobe"):
        try:
            proc = subprocess.run(
                [binary, "-version"], capture_output=True, timeout=10
            )
            if proc.returncode != 0:
                return False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    return True


def probe(audio_path: str) -> dict:
    """ffprobe an audio file -> {duration_secs, sample_rate, channels, codec}.

    Raises ConvertError if the file is missing or ffprobe cannot read it.
    """
    audio_path = os.path.abspath(audio_path)
    if not os.path.isfile(audio_path):
        raise ConvertError(f"audio missing: {audio_path}")

    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=sample_rate,channels,codec_name:format=duration",
            "-of", "json",
            audio_path,
        ],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise ConvertError(f"ffprobe failed on {audio_path}: {proc.stderr[:300]}")

    try:
        data = json.loads(proc.stdout)
        stream = (data.get("streams") or [{}])[0]
        duration = float(data.get("format", {}).get("duration", 0.0))
    except (json.JSONDecodeError, ValueError, IndexError) as exc:
        raise ConvertError(f"could not parse ffprobe output: {exc}") from exc

    if not stream:
        raise ConvertError(f"no audio stream in {audio_path}")

    return {
        "duration_secs": duration,
        "sample_rate": int(stream.get("sample_rate", 0) or 0),
        "channels": int(stream.get("channels", 0) or 0),
        "codec": stream.get("codec_name", ""),
    }


def sp_safe_name(name: str, max_len: int = MAX_NAME_LEN) -> str:
    """Reduce a title to something safe for the SP's SD card and display.

    ASCII only, no filesystem-hostile characters, single spaces collapsed to
    underscores, truncated on a word boundary where possible. The SP's own
    display limit is [UNVERIFIED]; see MAX_NAME_LEN.
    """
    # Strip accents rather than dropping the characters outright.
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^A-Za-z0-9 _\-]+", "", name)
    name = re.sub(r"\s+", "_", name.strip())
    name = re.sub(r"_{2,}", "_", name).strip("_-")

    if not name:
        name = "sample"
    if len(name) <= max_len:
        return name

    cut = name[:max_len]
    if "_" in cut[max_len // 2:]:
        cut = cut.rsplit("_", 1)[0]
    return cut.strip("_-") or name[:max_len]


def check_length(duration_secs: float) -> str | None:
    """Return an error string if the SP would refuse this sample, else None."""
    if duration_secs <= 0:
        return "duration is zero — file may be empty or unreadable"
    if duration_secs > MAX_SAMPLE_SECS:
        return (
            f"{duration_secs:.0f}s exceeds the SP-404MK2 limit of "
            f"{MAX_SAMPLE_SECS}s ({MAX_SAMPLE_SECS // 60} min) per sample"
        )
    return None


def to_sp_format(
    audio_path: str,
    output_path: str,
    normalize: bool = False,
    mono: bool = False,
) -> ConvertResult:
    """Convert any ffmpeg-readable audio into SP-404MK2 import format.

    Args:
        audio_path: Source file (WAV, MP3, FLAC, stem output, anything ffmpeg reads).
        output_path: Destination .wav path. Parent directories are created.
        normalize: Apply EBU R128 loudness normalisation. Off by default —
                   normalising a one-shot destroys its transient, and the SP's
                   own gain staging is usually the better place to fix level.
        mono: Downmix to mono. Off by default; the SP handles stereo samples.

    Returns:
        ConvertResult. `success=False` with `error` set rather than raising,
        so batch callers can carry on past one bad file.
    """
    audio_path = os.path.abspath(audio_path)
    output_path = os.path.abspath(output_path)

    try:
        info = probe(audio_path)
    except ConvertError as exc:
        return ConvertResult(success=False, source_path=audio_path, error=str(exc))

    too_long = check_length(info["duration_secs"])
    if too_long:
        return ConvertResult(
            success=False,
            source_path=audio_path,
            duration_secs=info["duration_secs"],
            error=too_long,
        )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    cmd = ["ffmpeg", "-y", "-v", "error", "-i", audio_path]
    filters = []
    if normalize:
        filters.append("loudnorm=I=-14:TP=-1.5:LRA=11")
    if filters:
        cmd += ["-af", ",".join(filters)]
    cmd += [
        "-ar", str(SP_RATE),
        "-ac", "1" if mono else "2",
        "-c:a", SP_CODEC,
        "-map_metadata", "-1",   # the SP reads none of it; keep files lean
        output_path,
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        return ConvertResult(
            success=False,
            source_path=audio_path,
            error=f"ffmpeg failed: {proc.stderr[:400]}",
        )

    if not os.path.isfile(output_path):
        return ConvertResult(
            success=False,
            source_path=audio_path,
            error="ffmpeg reported success but no output file exists",
        )

    return ConvertResult(
        success=True,
        file_path=output_path,
        source_path=audio_path,
        duration_secs=info["duration_secs"],
        size_bytes=os.path.getsize(output_path),
    )
