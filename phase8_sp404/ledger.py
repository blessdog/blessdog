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
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str = ""

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

    def __len__(self) -> int:
        return len(self.entries)
