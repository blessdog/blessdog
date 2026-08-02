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
from phase8_sp404.ledger import Ledger, LedgerEntry, hash_file

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


def test_push_reports_missing_staged_file(tmp_path):
    ledger = Ledger(str(tmp_path / "led.json"))
    entry = LedgerEntry(source_hash="h", name="ghost", kind="loop",
                        local_path=str(tmp_path / "gone.wav"))
    root = _make_card(tmp_path, "Card", "IMPORT")
    batch = build.push_to_card([entry], card.find_import_folder(root), ledger=ledger)
    assert batch.failed and "missing" in batch.failed[0][1]
