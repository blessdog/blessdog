"""Tests for Phase 8 — SP-404MK2 sample lane: convert, card, ledger, build."""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from phase8_sp404 import build, card, convert
from phase8_sp404.convert import (
    MAX_SAMPLE_SECS,
    SP_RATE,
    check_length,
    sp_safe_name,
)
from phase8_sp404.ledger import (
    BANKS,
    PAD_BASE_NOTE,
    PADS_PER_BANK,
    Ledger,
    LedgerEntry,
    hash_file,
    normalize_pad,
    note_to_pad,
    pad_to_note,
)

ffmpeg_required = pytest.mark.skipif(
    not convert.is_available(), reason="ffmpeg/ffprobe not on PATH"
)


@pytest.fixture
def tone(tmp_path):
    """A 1-second 44.1 kHz mono MP3 — deliberately NOT in SP format."""
    path = tmp_path / "tone.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=1",
         "-ar", "44100", "-ac", "1", "-c:a", "libmp3lame", str(path)],
        check=True, timeout=60,
    )
    return str(path)


# ---------------------------------------------------------------- naming

@pytest.mark.parametrize("raw,expected", [
    ("Amén Break!!! 174bpm", "Amen_Break_174bpm"),
    ("", "sample"),
    ("   ---___   ", "sample"),
    ("already_fine", "already_fine"),
])
def test_sp_safe_name(raw, expected):
    assert sp_safe_name(raw) == expected


def test_sp_safe_name_truncates_within_limit():
    long = "a really long title that definitely must be truncated somewhere"
    out = sp_safe_name(long)
    assert len(out) <= convert.MAX_NAME_LEN
    assert not out.endswith("_")


def test_sp_safe_name_is_ascii_and_filesystem_safe():
    out = sp_safe_name('Tëst/Tone:with*bad?chars"here')
    assert out.isascii()
    assert not set(out) & set('/:*?"<>|\\')


# ---------------------------------------------------------------- length

def test_check_length_accepts_normal():
    assert check_length(120.0) is None


def test_check_length_rejects_zero():
    assert check_length(0) is not None


def test_check_length_rejects_over_device_limit():
    assert check_length(MAX_SAMPLE_SECS + 1) is not None
    assert check_length(MAX_SAMPLE_SECS) is None


# ---------------------------------------------------------------- convert

@ffmpeg_required
def test_convert_produces_sp_format(tone, tmp_path):
    out = tmp_path / "out.wav"
    result = convert.to_sp_format(tone, str(out))
    assert result.success, result.error

    info = convert.probe(str(out))
    assert info["sample_rate"] == SP_RATE
    assert info["codec"] == "pcm_s16le"
    assert info["channels"] == 2      # stereo unless mono requested


@ffmpeg_required
def test_convert_mono_flag(tone, tmp_path):
    out = tmp_path / "mono.wav"
    assert convert.to_sp_format(tone, str(out), mono=True).success
    assert convert.probe(str(out))["channels"] == 1


def test_convert_missing_source_fails_soft(tmp_path):
    result = convert.to_sp_format(str(tmp_path / "nope.wav"), str(tmp_path / "o.wav"))
    assert not result.success and result.error


# ------------------------------------------------------------------ card

def _make_card(root, *parts):
    path = os.path.join(str(root), *parts)
    os.makedirs(path, exist_ok=True)
    return os.path.join(str(root), parts[0])


def test_card_finds_nested_roland_layout(tmp_path):
    root = _make_card(tmp_path, "Card", "ROLAND", "SP-404MKII", "IMPORT")
    assert card.find_import_folder(root).import_dir.endswith("IMPORT")


def test_card_finds_root_level_import(tmp_path):
    root = _make_card(tmp_path, "Card", "IMPORT")
    assert card.find_import_folder(root).import_dir.endswith("IMPORT")


def test_card_rejects_unrelated_import_folder(tmp_path):
    """Regression: /usr/share/vim/vim91/import made this 'detect' the boot disk."""
    root = _make_card(tmp_path, "Decoy", "usr", "share", "vim", "import")
    with pytest.raises(card.CardError):
        card.find_import_folder(root)


def test_card_rejects_unformatted(tmp_path):
    root = _make_card(tmp_path, "Blank", "junk")
    with pytest.raises(card.CardError):
        card.find_import_folder(root)


def test_card_rejects_unmounted(tmp_path):
    with pytest.raises(card.CardError):
        card.find_import_folder(str(tmp_path / "absent"))


def test_file_to_card_uniquifies_collisions(tmp_path):
    root = _make_card(tmp_path, "Card", "IMPORT")
    target = card.find_import_folder(root)
    src = tmp_path / "s.wav"
    src.write_bytes(b"RIFF-not-really")

    first = card.file_to_card(str(src), target, filename="kick.wav")
    second = card.file_to_card(str(src), target, filename="kick.wav")
    assert os.path.basename(first) == "kick.wav"
    assert os.path.basename(second) == "kick_2.wav"


# ---------------------------------------------------------------- ledger

def test_ledger_roundtrip(tmp_path):
    path = str(tmp_path / "led.json")
    ledger = Ledger(path)
    ledger.add(LedgerEntry(source_hash="abc", name="kick", kind="oneshot"))

    assert len(Ledger(path)) == 1
    assert Ledger(path).by_hash("abc").name == "kick"


def test_ledger_rejects_unknown_kind(tmp_path):
    ledger = Ledger(str(tmp_path / "led.json"))
    with pytest.raises(ValueError):
        ledger.add(LedgerEntry(source_hash="x", name="n", kind="nonsense"))


def test_ledger_tolerates_unknown_fields(tmp_path):
    """A ledger written by a newer version must still load."""
    path = tmp_path / "led.json"
    path.write_text(json.dumps({
        "version": 99,
        "samples": [{"source_hash": "h", "name": "n", "kind": "loop",
                     "field_from_the_future": True}],
    }))
    assert len(Ledger(str(path))) == 1


def test_hash_file_is_content_based(tmp_path):
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    a.write_bytes(b"same"); b.write_bytes(b"same")
    assert hash_file(str(a)) == hash_file(str(b))


# ----------------------------------------------------------------- build

@ffmpeg_required
def test_stage_file_converts_and_records(tone, tmp_path, monkeypatch):
    monkeypatch.setattr(build, "_LIBRARY_ROOT", str(tmp_path / "lib"))
    ledger = Ledger(str(tmp_path / "led.json"))

    result = build.stage_file(tone, kind="loop", bank="rave", ledger=ledger)
    assert result.success, result.error
    assert result.entry.kind == "loop" and result.entry.bank == "rave"
    assert convert.probe(result.entry.local_path)["sample_rate"] == SP_RATE
    assert len(ledger) == 1


@ffmpeg_required
def test_stage_file_deduplicates_same_source(tone, tmp_path, monkeypatch):
    monkeypatch.setattr(build, "_LIBRARY_ROOT", str(tmp_path / "lib"))
    ledger = Ledger(str(tmp_path / "led.json"))

    build.stage_file(tone, ledger=ledger)
    again = build.stage_file(tone, ledger=ledger)
    assert again.skipped_duplicate
    assert len(ledger) == 1


@ffmpeg_required
def test_push_to_card_records_destination(tone, tmp_path, monkeypatch):
    monkeypatch.setattr(build, "_LIBRARY_ROOT", str(tmp_path / "lib"))
    ledger = Ledger(str(tmp_path / "led.json"))
    staged = build.stage_file(tone, kind="oneshot", ledger=ledger)

    root = _make_card(tmp_path, "Card", "IMPORT")
    target = card.find_import_folder(root)
    batch = build.push_to_card([staged.entry], target, ledger=ledger)

    assert not batch.failed and len(batch.staged) == 1
    assert os.path.isfile(staged.entry.card_path)
    assert Ledger(str(tmp_path / "led.json")).entries[0].card_path


# ------------------------------------------------- clip lane (CLIP-LANE §7)

@pytest.mark.parametrize("raw,expected", [
    ("a5", "A5"), ("A5", "A5"), (" j16 ", "J16"), ("A1", "A1"), ("A16", "A16"),
])
def test_normalize_pad_accepts_valid(raw, expected):
    assert normalize_pad(raw) == expected


@pytest.mark.parametrize("bad", ["A0", "A17", "K1", "5A", "", "A", "1", "AA1"])
def test_normalize_pad_rejects_invalid(bad):
    with pytest.raises(ValueError):
        normalize_pad(bad)


def test_pad_note_roundtrip_across_a_bank():
    for index in range(1, PADS_PER_BANK + 1):
        pad = f"C{index}"
        assert note_to_pad(pad_to_note(pad), bank="C") == pad


def test_pad_one_is_base_note():
    assert pad_to_note("A1") == PAD_BASE_NOTE
    assert pad_to_note("A16") == PAD_BASE_NOTE + PADS_PER_BANK - 1


def test_note_to_pad_needs_a_bank_and_validates_it():
    assert note_to_pad(PAD_BASE_NOTE, bank="B") == "B1"
    with pytest.raises(ValueError):
        note_to_pad(PAD_BASE_NOTE, bank="Z")


def test_note_to_pad_rejects_out_of_range():
    with pytest.raises(ValueError):
        note_to_pad(PAD_BASE_NOTE - 1)
    with pytest.raises(ValueError):
        note_to_pad(PAD_BASE_NOTE + PADS_PER_BANK)


def test_every_bank_letter_is_accepted():
    for bank in BANKS:
        assert normalize_pad(f"{bank}1") == f"{bank}1"


def test_entry_normalises_pad_on_construction():
    assert LedgerEntry(source_hash="h", name="n", kind="loop", pad="b7").pad == "B7"


def test_entry_rejects_bad_pad_and_negative_in_point():
    with pytest.raises(ValueError):
        LedgerEntry(source_hash="h", name="n", kind="loop", pad="Z9")
    with pytest.raises(ValueError):
        LedgerEntry(source_hash="h", name="n", kind="loop", source_in_secs=-0.5)


def test_clip_fields_survive_ledger_roundtrip(tmp_path):
    path = str(tmp_path / "led.json")
    ledger = Ledger(path)
    ledger.add(LedgerEntry(source_hash="h1", name="stab", kind="oneshot",
                           source_clip_hash="clipA", source_in_secs=2.1, pad="A5"))

    back = Ledger(path).entries[0]
    assert back.source_clip_hash == "clipA"
    assert back.source_in_secs == 2.1
    assert back.pad == "A5"


def test_from_clip_returns_in_point_order(tmp_path):
    ledger = Ledger(str(tmp_path / "led.json"))
    for name, at in [("c", 5.0), ("a", 1.0), ("b", 3.0)]:
        ledger.add(LedgerEntry(source_hash=name, name=name, kind="oneshot",
                               source_clip_hash="clipA", source_in_secs=at))
    ledger.add(LedgerEntry(source_hash="other", name="other", kind="oneshot",
                           source_clip_hash="clipB", source_in_secs=0.5))

    assert [e.name for e in ledger.from_clip("clipA")] == ["a", "b", "c"]
    assert [e.name for e in ledger.from_clip("clipB")] == ["other"]
    assert ledger.from_clip("nope") == []


def test_by_pad_returns_latest_assignment(tmp_path):
    ledger = Ledger(str(tmp_path / "led.json"))
    ledger.add(LedgerEntry(source_hash="1", name="old", kind="loop", pad="A5"))
    ledger.add(LedgerEntry(source_hash="2", name="new", kind="loop", pad="A5"))

    assert ledger.by_pad("a5").name == "new"     # re-recording a pad replaces it
    assert ledger.by_pad("A6") is None


@ffmpeg_required
def test_stage_file_carries_clip_pointer(tone, tmp_path, monkeypatch):
    monkeypatch.setattr(build, "_LIBRARY_ROOT", str(tmp_path / "lib"))
    ledger = Ledger(str(tmp_path / "led.json"))

    result = build.stage_file(tone, kind="oneshot", ledger=ledger,
                              source_clip_hash="clipA", source_in_secs=2.1,
                              pad="a5")
    assert result.success, result.error
    assert result.entry.source_clip_hash == "clipA"
    assert result.entry.source_in_secs == 2.1
    assert result.entry.pad == "A5"


@ffmpeg_required
def test_stage_file_rejects_bad_pad_without_converting(tone, tmp_path, monkeypatch):
    """Must fail SOFT and BEFORE ffmpeg runs — batches carry on, work isn't wasted."""
    lib = tmp_path / "lib"
    monkeypatch.setattr(build, "_LIBRARY_ROOT", str(lib))
    ledger = Ledger(str(tmp_path / "led.json"))

    result = build.stage_file(tone, ledger=ledger, pad="Z9")
    assert not result.success and "invalid pad" in result.error
    assert len(ledger) == 0
    assert not lib.exists()          # nothing was converted


# --------------------------------------------------- tempo / key detection

def test_detect_tempo_key_never_raises_on_bad_input(tmp_path):
    """Metadata is a nice-to-have; failing to read it must not block a sample."""
    assert build.detect_tempo_key(str(tmp_path / "nope.wav")) == (None, "")
    junk = tmp_path / "junk.wav"
    junk.write_bytes(b"not audio at all")
    assert build.detect_tempo_key(str(junk)) == (None, "")


@ffmpeg_required
def test_stage_file_leaves_bpm_unset_without_analyze(tone, tmp_path, monkeypatch):
    """The real-run gap: nothing populated bpm/key until --analyze existed."""
    monkeypatch.setattr(build, "_LIBRARY_ROOT", str(tmp_path / "lib"))
    ledger = Ledger(str(tmp_path / "led.json"))
    r = build.stage_file(tone, ledger=ledger)          # analyze defaults False
    assert r.entry.bpm is None and r.entry.key == ""


@ffmpeg_required
def test_explicit_bpm_key_beat_detection(tone, tmp_path, monkeypatch):
    """A tempo read off the SP or Ableton must win over any estimate."""
    monkeypatch.setattr(build, "_LIBRARY_ROOT", str(tmp_path / "lib"))
    monkeypatch.setattr(build, "detect_tempo_key", lambda *a, **k: (99.9, "Zz"))
    ledger = Ledger(str(tmp_path / "led.json"))
    r = build.stage_file(tone, ledger=ledger, analyze=True, bpm=174.0, key="Am")
    assert r.entry.bpm == 174.0 and r.entry.key == "Am"


@ffmpeg_required
def test_analyze_fills_only_missing_fields(tone, tmp_path, monkeypatch):
    monkeypatch.setattr(build, "_LIBRARY_ROOT", str(tmp_path / "lib"))
    monkeypatch.setattr(build, "detect_tempo_key", lambda *a, **k: (120.0, "Cm"))
    ledger = Ledger(str(tmp_path / "led.json"))
    r = build.stage_file(tone, ledger=ledger, analyze=True, bpm=174.0)
    assert r.entry.bpm == 174.0      # explicit kept
    assert r.entry.key == "Cm"       # missing one filled


def test_push_reports_missing_staged_file(tmp_path):
    ledger = Ledger(str(tmp_path / "led.json"))
    entry = LedgerEntry(source_hash="h", name="ghost", kind="loop",
                        local_path=str(tmp_path / "gone.wav"))
    root = _make_card(tmp_path, "Card", "IMPORT")
    batch = build.push_to_card([entry], card.find_import_folder(root), ledger=ledger)
    assert batch.failed and "missing" in batch.failed[0][1]
