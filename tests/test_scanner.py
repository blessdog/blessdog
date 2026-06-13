"""Tests for phase3_library.scanner — filesystem walker and category derivation."""

import os
import tempfile

import pytest

from phase3_library.config import LibraryConfig
from phase3_library.scanner import (
    FileEntry,
    _classify_library_source,
    _derive_category,
    scan,
)


@pytest.fixture
def library_tree(tmp_path):
    """Create a realistic library directory tree with dummy files."""
    # NI Library structure
    ni = tmp_path / "NI Libraries"
    ni.mkdir()
    (ni / "Session Strings 2 Library" / "Samples").mkdir(parents=True)
    (ni / "Session Strings 2 Library" / "Samples" / "Sustain_C3.wav").write_bytes(b"\x00" * 100)

    # Drum kit structure
    kits = ni / "Drum Kits" / "808 Mafia" / "Kicks"
    kits.mkdir(parents=True)
    (kits / "hard_kick.wav").write_bytes(b"\x00" * 200)

    snares = ni / "Drum Kits" / "808 Mafia" / "Snares"
    snares.mkdir(parents=True)
    (snares / "trap_snare.wav").write_bytes(b"\x00" * 150)

    # Ableton factory structure
    ableton = tmp_path / "Ableton" / "Presets" / "Instruments" / "Wavetable"
    ableton.mkdir(parents=True)
    (ableton / "Warm Pad.adg").write_bytes(b"\x00" * 50)

    # Hidden and skip dirs
    skip = ni / ".previews"
    skip.mkdir()
    (skip / "preview.wav").write_bytes(b"\x00" * 10)

    macosx = ni / "__MACOSX"
    macosx.mkdir()
    (macosx / "junk.wav").write_bytes(b"\x00" * 10)

    # MIDI file
    midi_dir = tmp_path / "MIDI"
    midi_dir.mkdir()
    (midi_dir / "chord_prog.mid").write_bytes(b"\x00" * 30)

    # Unsupported extension (should be skipped)
    (tmp_path / "readme.txt").write_text("ignore me")

    return tmp_path


def test_scan_yields_file_entries(library_tree):
    """Scanner yields FileEntry objects for supported files."""
    config = LibraryConfig(
        scan_paths=[str(library_tree)],
        db_path=":memory:",
    )
    entries = list(scan(config))
    names = {e.name for e in entries}

    assert "hard_kick" in names
    assert "trap_snare" in names
    assert "Sustain_C3" in names
    assert "Warm Pad" in names
    assert "chord_prog" in names

    # Should NOT include files from .previews or __MACOSX
    assert "preview" not in names
    assert "junk" not in names

    # Should NOT include unsupported extensions
    assert "readme" not in names


def test_scan_file_entry_fields(library_tree):
    """FileEntry fields are populated correctly."""
    config = LibraryConfig(
        scan_paths=[str(library_tree)],
        db_path=":memory:",
    )
    entries = {e.name: e for e in scan(config)}

    kick = entries["hard_kick"]
    assert kick.extension == ".wav"
    assert kick.size == 200
    assert kick.file_type == "sample"
    assert kick.mtime > 0

    pad = entries["Warm Pad"]
    assert pad.extension == ".adg"
    assert pad.file_type == "instrument"

    midi = entries["chord_prog"]
    assert midi.extension == ".mid"
    assert midi.file_type == "midi"


def test_classify_drum_kit(library_tree):
    """Drum kit files get drum_kit source and kit name."""
    root = str(library_tree / "NI Libraries")
    kick_path = str(library_tree / "NI Libraries" / "Drum Kits" / "808 Mafia" / "Kicks" / "hard_kick.wav")
    source, name = _classify_library_source(root, kick_path)
    assert source == "drum_kit"
    assert name == "808 Mafia"


def test_classify_ni_library(library_tree):
    """NI library files get ni_library source."""
    root = str(library_tree / "NI Libraries")
    sample_path = str(library_tree / "NI Libraries" / "Session Strings 2 Library" / "Samples" / "Sustain_C3.wav")
    source, name = _classify_library_source(root, sample_path)
    assert source == "ni_library"
    assert name == "Session Strings 2"


def test_derive_category_from_path():
    """Category is derived from path segments."""
    assert _derive_category("/lib/Drum Kits/808/kicks/kick.wav", "sample") == "drums/kicks"
    assert _derive_category("/lib/packs/Bass/deep.wav", "sample") == "bass"
    assert _derive_category("/lib/Synth/pads/warm.wav", "sample") == "synth/pads"


def test_derive_category_fallback():
    """Falls back to file_type when no keywords match."""
    assert _derive_category("/lib/unknown/thing.wav", "sample") == "sample"


def test_scan_skips_missing_paths():
    """Scanner gracefully skips paths that don't exist."""
    config = LibraryConfig(
        scan_paths=["/nonexistent/path/that/does/not/exist"],
        db_path=":memory:",
    )
    entries = list(scan(config))
    assert entries == []


def test_scan_skip_patterns(library_tree):
    """Files in skip-pattern directories are excluded."""
    config = LibraryConfig(
        scan_paths=[str(library_tree)],
        db_path=":memory:",
        skip_patterns=[".previews", "__MACOSX", ".DS_Store"],
    )
    entries = list(scan(config))
    paths = [e.path for e in entries]

    for p in paths:
        assert ".previews" not in p
        assert "__MACOSX" not in p


def test_scan_hidden_files_skipped(library_tree):
    """Files starting with . are skipped."""
    hidden = library_tree / "NI Libraries" / ".hidden_sample.wav"
    hidden.write_bytes(b"\x00" * 50)

    config = LibraryConfig(
        scan_paths=[str(library_tree)],
        db_path=":memory:",
    )
    entries = list(scan(config))
    names = {e.name for e in entries}
    assert ".hidden_sample" not in names
