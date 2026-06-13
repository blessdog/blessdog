"""Stem separation via Meta's Demucs (htdemucs model).

Splits a mixed audio file into four stems: drums, bass, vocals, other.
Runs Demucs as a subprocess for stability and GPU/CPU flexibility.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StemPaths:
    """Paths to the four separated stems."""
    drums: str
    bass: str
    vocals: str
    other: str
    source: str  # original file

    def all(self) -> dict[str, str]:
        return {
            "drums": self.drums,
            "bass": self.bass,
            "vocals": self.vocals,
            "other": self.other,
        }


_DEFAULT_MODEL = "htdemucs"
_DEFAULT_OUTPUT = os.path.join(
    tempfile.gettempdir(), "blessdog_stems"
)


def separate(
    audio_path: str,
    output_dir: str | None = None,
    model: str = _DEFAULT_MODEL,
    two_stems: str | None = None,
) -> StemPaths:
    """Run Demucs stem separation on an audio file.

    Args:
        audio_path: Path to the source audio file.
        output_dir: Where to write stems. Defaults to a temp directory.
        model: Demucs model name (htdemucs, htdemucs_ft, mdx_extra).
        two_stems: If set, only separate into this stem + remainder
                   (e.g. "vocals" gives vocals + no_vocals).

    Returns:
        StemPaths with absolute paths to each stem WAV file.

    Raises:
        FileNotFoundError: If the audio file doesn't exist.
        RuntimeError: If Demucs fails.
    """
    audio_path = os.path.abspath(audio_path)
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    out = output_dir or _DEFAULT_OUTPUT
    os.makedirs(out, exist_ok=True)

    cmd = [
        sys.executable, "-m", "demucs",
        "--out", out,
        "-n", model,
    ]
    if two_stems:
        cmd += ["--two-stems", two_stems]

    cmd.append(audio_path)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,  # 10 min max
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Demucs failed (exit {result.returncode}):\n{result.stderr}"
        )

    track_name = Path(audio_path).stem
    stem_dir = os.path.join(out, model, track_name)

    if not os.path.isdir(stem_dir):
        raise RuntimeError(
            f"Demucs output directory not found: {stem_dir}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    return StemPaths(
        drums=os.path.join(stem_dir, "drums.wav"),
        bass=os.path.join(stem_dir, "bass.wav"),
        vocals=os.path.join(stem_dir, "vocals.wav"),
        other=os.path.join(stem_dir, "other.wav"),
        source=audio_path,
    )


def is_available() -> bool:
    """Check if Demucs is installed."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "demucs", "--help"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
