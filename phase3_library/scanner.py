"""Filesystem walker — scans configured paths, yields FileEntry records."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterator

from .config import LibraryConfig

# ── File type mapping ──────────────────────────────────────────────────

_EXT_TYPE: dict[str, str] = {
    ".wav": "sample",
    ".aif": "sample",
    ".aiff": "sample",
    ".mp3": "sample",
    ".flac": "sample",
    ".ogg": "sample",
    ".adg": "instrument",   # refined by metadata (could be effect)
    ".adv": "preset",
    ".nksf": "preset",
    ".nki": "instrument",
    ".mid": "midi",
    ".midi": "midi",
    ".als": "project",
}

# ── Category keywords ─────────────────────────────────────────────────

_CATEGORY_KEYWORDS: dict[str, str] = {
    "kicks": "drums/kicks",
    "kick": "drums/kicks",
    "snares": "drums/snares",
    "snare": "drums/snares",
    "hats": "drums/hats",
    "hihat": "drums/hats",
    "hi-hat": "drums/hats",
    "hihats": "drums/hats",
    "hi-hats": "drums/hats",
    "cymbals": "drums/cymbals",
    "cymbal": "drums/cymbals",
    "claps": "drums/claps",
    "clap": "drums/claps",
    "percs": "drums/percussion",
    "percussion": "drums/percussion",
    "808s": "drums/808s",
    "808": "drums/808s",
    "bass": "bass",
    "sub": "bass",
    "pads": "synth/pads",
    "pad": "synth/pads",
    "leads": "synth/leads",
    "lead": "synth/leads",
    "keys": "keys",
    "piano": "keys",
    "strings": "strings",
    "guitar": "guitar",
    "vocals": "vocals",
    "vocal": "vocals",
    "vox": "vocals",
    "fx": "fx",
    "effects": "fx",
    "sfx": "fx",
    "risers": "fx/risers",
    "impacts": "fx/impacts",
    "loops": "loops",
    "one shots": "one-shots",
    "oneshots": "one-shots",
    "one-shots": "one-shots",
    "instruments": "instruments",
    "synths": "synth",
    "synth": "synth",
    "wavetable": "instruments/wavetable",
    "operator": "instruments/operator",
    "simpler": "instruments/simpler",
    "sampler": "instruments/sampler",
    "analog": "instruments/analog",
    "drift": "instruments/drift",
    "tension": "instruments/tension",
    "collision": "instruments/collision",
    "electric": "instruments/electric",
}

# ── Library source detection ───────────────────────────────────────────

# Regex for NI library folders: "Session Strings 2 Library", "Massive X Library"
_NI_LIBRARY_RE = re.compile(r"^(.+?)\s+Library$", re.IGNORECASE)

# Known drum kit folder names
_DRUM_KIT_NAMES = {
    "808 mafia", "southside", "kanye", "metro boomin", "tm88",
    "zaytoven", "lex luger", "drum kits",
}


@dataclass
class FileEntry:
    path: str
    name: str           # filename without extension
    extension: str      # ".wav", ".adg", ".nksf"
    size: int
    mtime: float
    file_type: str      # "sample", "instrument", "effect", "preset", "midi", "project"
    category: str       # derived from path: "drums/kicks", "bass", "synth/pads"
    library_source: str # "ni_library", "ableton_factory", "drum_kit", "user_collection"
    library_name: str   # "Session Strings 2", "808 Mafia", "Wavetable"


def _classify_library_source(root_path: str, file_path: str) -> tuple[str, str]:
    """Determine library_source and library_name from the file path."""
    rel = os.path.relpath(file_path, root_path)
    parts = rel.split(os.sep)

    # Check if under a drum kit folder
    for i, part in enumerate(parts):
        if part.lower() in _DRUM_KIT_NAMES or "drum kit" in part.lower():
            # Library name is this folder or the next meaningful one
            if part.lower() == "drum kits" and i + 1 < len(parts):
                return "drum_kit", parts[i + 1]
            return "drum_kit", part

    # Check for NI library pattern
    for part in parts:
        m = _NI_LIBRARY_RE.match(part)
        if m:
            return "ni_library", m.group(1)

    # Ableton factory detection
    if "Ableton" in root_path or "App-Resources" in root_path:
        return "ableton_factory", parts[0] if parts else "Ableton"

    # Check for Ableton Packs in path
    for i, part in enumerate(parts):
        if part.lower() in ("packs", "factory packs"):
            if i + 1 < len(parts):
                return "ableton_factory", parts[i + 1]

    # Native Instruments application support
    if "Native Instruments" in root_path or "Native Instruments" in rel:
        for part in parts:
            if part != "Native Instruments" and not part.startswith("."):
                return "ni_library", part
                break

    return "user_collection", parts[0] if parts else "Unknown"


def _derive_category(file_path: str, file_type: str) -> str:
    """Derive a category from path segments."""
    lower_path = file_path.lower()
    parts = lower_path.replace("\\", "/").split("/")

    # Check path segments against category keywords
    for part in reversed(parts[:-1]):  # skip filename
        part_clean = part.strip()
        if part_clean in _CATEGORY_KEYWORDS:
            return _CATEGORY_KEYWORDS[part_clean]

    # Fall back to file_type as category
    return file_type


def scan(config: LibraryConfig) -> Iterator[FileEntry]:
    """Walk all configured paths, yielding FileEntry for each supported file."""
    skip_set = set(config.skip_patterns)

    for root_path in config.scan_paths:
        if not os.path.isdir(root_path):
            continue

        for dirpath, dirnames, filenames in os.walk(root_path):
            # Prune skipped directories in-place
            dirnames[:] = [
                d for d in dirnames
                if d not in skip_set and not d.startswith(".")
            ]

            for fname in filenames:
                if fname.startswith("."):
                    continue

                name, ext = os.path.splitext(fname)
                ext_lower = ext.lower()

                if ext_lower not in _EXT_TYPE:
                    continue

                full_path = os.path.join(dirpath, fname)

                try:
                    stat = os.stat(full_path)
                except OSError:
                    continue

                file_type = _EXT_TYPE[ext_lower]
                library_source, library_name = _classify_library_source(
                    root_path, full_path,
                )
                category = _derive_category(full_path, file_type)

                yield FileEntry(
                    path=full_path,
                    name=name,
                    extension=ext_lower,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    file_type=file_type,
                    category=category,
                    library_source=library_source,
                    library_name=library_name,
                )
