"""YouTube audio downloader via yt-dlp.

Downloads the best quality audio from a YouTube URL, converts to WAV
for analysis or keeps as high-bitrate format for reference listening.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass


_MUSIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "music",
)


@dataclass
class DownloadResult:
    success: bool
    file_path: str = ""
    title: str = ""
    artist: str = ""
    duration_secs: float = 0.0
    format_info: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "file_path": self.file_path,
            "title": self.title,
            "artist": self.artist,
            "duration_secs": round(self.duration_secs, 1),
            "format_info": self.format_info,
            "error": self.error,
        }


def _sanitize_filename(name: str) -> str:
    """Remove/replace characters that cause filesystem issues."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def _parse_metadata(url: str) -> dict:
    """Extract metadata from URL without downloading."""
    result = subprocess.run(
        [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def download(
    url: str,
    output_dir: str | None = None,
    wav: bool = True,
    filename: str | None = None,
) -> DownloadResult:
    """Download best quality audio from a YouTube URL.

    Args:
        url: YouTube URL.
        output_dir: Where to save. Defaults to blessdog/music/.
        wav: If True, convert to WAV for analysis. If False, keep best lossy.
        filename: Override output filename (without extension).

    Returns:
        DownloadResult with file path and metadata.
    """
    out_dir = output_dir or _MUSIC_DIR
    os.makedirs(out_dir, exist_ok=True)

    # Get metadata first
    meta = _parse_metadata(url)
    if not meta:
        return DownloadResult(success=False, error="Could not fetch metadata")

    title = meta.get("title", "Unknown")
    artist = meta.get("artist") or meta.get("uploader") or meta.get("channel", "Unknown")
    duration = meta.get("duration", 0)

    # Build output filename
    if filename:
        safe_name = _sanitize_filename(filename)
    else:
        # Try "Artist - Title" format, fall back to just title
        clean_title = _sanitize_filename(title)
        clean_artist = _sanitize_filename(artist)
        safe_name = f"{clean_artist} - {clean_title}" if clean_artist != "Unknown" else clean_title

    if wav:
        ext = "wav"
        output_template = os.path.join(out_dir, f"{safe_name}.%(ext)s")
        cmd = [
            "yt-dlp",
            "-x",                        # extract audio
            "--audio-format", "wav",     # convert to WAV
            "--audio-quality", "0",      # best quality
            "-o", output_template,
            "--no-playlist",
            url,
        ]
        expected_path = os.path.join(out_dir, f"{safe_name}.wav")
    else:
        ext = "best"
        output_template = os.path.join(out_dir, f"{safe_name}.%(ext)s")
        cmd = [
            "yt-dlp",
            "-x",                        # extract audio
            "--audio-quality", "0",      # best quality
            "-o", output_template,
            "--no-playlist",
            url,
        ]
        expected_path = ""  # unknown ext until download completes

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        return DownloadResult(
            success=False,
            title=title,
            artist=artist,
            error=f"yt-dlp failed: {result.stderr[:500]}",
        )

    # Find the actual output file
    if expected_path and os.path.isfile(expected_path):
        file_path = expected_path
    else:
        # Search for the file (extension might differ)
        for f in os.listdir(out_dir):
            if f.startswith(safe_name) and not f.endswith(".part"):
                file_path = os.path.join(out_dir, f)
                break
        else:
            return DownloadResult(
                success=False,
                title=title,
                artist=artist,
                error="Download completed but output file not found",
            )

    # Get format info from the downloaded file
    fmt = f"WAV" if wav else "best available"

    return DownloadResult(
        success=True,
        file_path=file_path,
        title=title,
        artist=artist,
        duration_secs=float(duration),
        format_info=fmt,
    )
