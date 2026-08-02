"""Provenance ledger for the SP-404MK2 sample library.

A sample library without provenance becomes unattributable within a month —
you end up with 400 WAVs and no idea which came from a cleared archive rip and
which came from something you can't publish. Every sample this lane files is
recorded here with its source, its content hash, and what it was derived from.

Content-hashed so the same source converted twice is recognised rather than
duplicated onto the card.

Deliberately JSON, not SQLite: this ledger is meant to be read by a human and
diffed in git. media-studio's registry.db stays the authority for *video*
assets — only finished tracks and stems cross that boundary
(see media-studio/docs/MUSIC-LANE.md, decision 1).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

_DEFAULT_LEDGER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "music",
    "sp404-library.json",
)

# What a sample is FOR. Drives how it gets named and organised, and keeps DJ
# material distinguishable from pad material (MUSIC-LANE.md decision 3).
KINDS = ("oneshot", "loop", "track", "stem")

# Physical pad address on the device, e.g. "A5". Banks A-J, pads 1-16.
# Distinct from `bank`, which is a free-text organisational label and
# explicitly NOT a device bank index (CLIP-LANE.md §7).
_PAD_RE = re.compile(r"^([A-J])(1[0-6]|[1-9])$")

# Bank A pad 1 = MIDI note 48 (C3), contiguous upward to pad 16 = note 63
# [documented, NOT exercised]. The per-bank MIDI CHANNEL layout is genuinely
# unverified — the two Roland sources reviewed disagree — so this maps note
# numbers WITHIN a bank only. Resolving a note to a specific bank needs the
# channel, and that must be confirmed with a MIDI monitor on real hardware
# before anything depends on it.
PAD_BASE_NOTE = 48
PADS_PER_BANK = 16
BANKS = "ABCDEFGHIJ"


def normalize_pad(pad: str) -> str:
    """Validate and canonicalise a pad address ("a5" -> "A5").

    Raises ValueError on anything that is not a real pad, so an unusable
    address cannot reach the ledger and silently break a trigger map later.
    """
    candidate = pad.strip().upper()
    if not _PAD_RE.match(candidate):
        raise ValueError(
            f"invalid pad {pad!r}: expected bank A-J + pad 1-16, e.g. 'A5'"
        )
    return candidate


def pad_to_note(pad: str) -> int:
    """Pad address -> MIDI note number within its bank.

    Only the note is returned; the bank is carried by the MIDI channel, whose
    layout is unverified (see PAD_BASE_NOTE). Callers reconstructing a pad from
    live MIDI must supply the bank themselves.
    """
    canonical = normalize_pad(pad)
    return PAD_BASE_NOTE + int(canonical[1:]) - 1


def note_to_pad(note: int, bank: str = "A") -> str:
    """MIDI note number + known bank -> pad address.

    The bank must be supplied because it is NOT recoverable from the note —
    every bank reuses the same note range.
    """
    bank = bank.strip().upper()
    if bank not in BANKS:
        raise ValueError(f"invalid bank {bank!r}: expected one of {BANKS}")
    offset = note - PAD_BASE_NOTE
    if not 0 <= offset < PADS_PER_BANK:
        raise ValueError(
            f"note {note} is outside the pad range "
            f"{PAD_BASE_NOTE}-{PAD_BASE_NOTE + PADS_PER_BANK - 1}"
        )
    return f"{bank}{offset + 1}"


def hash_file(path: str, chunk: int = 1 << 20) -> str:
    """SHA-256 of a file's contents, streamed."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


@dataclass
class LedgerEntry:
    source_hash: str
    name: str
    kind: str
    source_path: str = ""
    source_url: str = ""
    title: str = ""
    artist: str = ""
    bpm: float | None = None
    key: str = ""
    duration_secs: float = 0.0
    derived_from: str = ""       # e.g. "demucs:drums", "skipback", "rave:master"
    card_path: str = ""          # where it landed on the SD card
    local_path: str = ""         # the staged copy that stays on disk
    bank: str = ""               # organisational label, not a device bank index

    # --- clip lane (CLIP-LANE.md §7) -------------------------------------
    # A sample is not a file, it is a pointer into a video at an offset. These
    # three make that expressible; without them pipelines F and G cannot work.
    source_clip_hash: str = ""       # joins to media-studio registry.db by
                                     # CONTENT HASH — neither repo imports the
                                     # other, preserving MUSIC-LANE decision 1
    source_in_secs: float | None = None   # in-point inside that clip, so the
                                          # picture can be chopped on exactly
                                          # the same in-point as the audio
    pad: str = ""                    # device pad address, e.g. "A5"; without
                                     # it a MIDI note resolves to nothing

    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str = ""

    def __post_init__(self) -> None:
        if self.pad:
            self.pad = normalize_pad(self.pad)
        if self.source_in_secs is not None and self.source_in_secs < 0:
            raise ValueError(
                f"source_in_secs must be >= 0, got {self.source_in_secs}"
            )

    def to_dict(self) -> dict:
        return asdict(self)


class Ledger:
    """Load/save/query the JSON sample ledger."""

    def __init__(self, path: str | None = None):
        self.path = os.path.abspath(path or _DEFAULT_LEDGER)
        self.entries: list[LedgerEntry] = []
        self.load()

    def load(self) -> None:
        if not os.path.isfile(self.path):
            self.entries = []
            return
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"ledger unreadable at {self.path}: {exc}") from exc

        known = set(LedgerEntry.__dataclass_fields__)
        self.entries = [
            LedgerEntry(**{k: v for k, v in item.items() if k in known})
            for item in raw.get("samples", [])
        ]

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        payload = {
            "version": 1,
            "updated": datetime.now(timezone.utc).isoformat(),
            "count": len(self.entries),
            "samples": [entry.to_dict() for entry in self.entries],
        }
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(tmp, self.path)   # atomic; a crash never truncates the ledger

    def by_hash(self, source_hash: str) -> LedgerEntry | None:
        for entry in self.entries:
            if entry.source_hash == source_hash:
                return entry
        return None

    def add(self, entry: LedgerEntry, save: bool = True) -> LedgerEntry:
        if entry.kind not in KINDS:
            raise ValueError(f"unknown kind {entry.kind!r}; expected one of {KINDS}")
        self.entries.append(entry)
        if save:
            self.save()
        return entry

    def of_kind(self, kind: str) -> list[LedgerEntry]:
        return [entry for entry in self.entries if entry.kind == kind]

    def in_bank(self, bank: str) -> list[LedgerEntry]:
        return [entry for entry in self.entries if entry.bank == bank]

    def from_clip(self, source_clip_hash: str) -> list[LedgerEntry]:
        """Every sample cut from one captured clip, earliest in-point first.

        The consumer side of pipeline G: given a clip, this is what was taken
        out of it and where.
        """
        matches = [
            entry for entry in self.entries
            if entry.source_clip_hash == source_clip_hash
        ]
        return sorted(matches, key=lambda e: e.source_in_secs or 0.0)

    def by_pad(self, pad: str) -> LedgerEntry | None:
        """The sample sitting on a pad address, or None.

        Pipeline G resolves a fired MIDI note to a pad, then a pad to this.
        Later entries win — re-recording a pad replaces what was there.
        """
        canonical = normalize_pad(pad)
        for entry in reversed(self.entries):
            if entry.pad == canonical:
                return entry
        return None

    def __len__(self) -> int:
        return len(self.entries)
