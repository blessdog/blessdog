"""Phase 8 — Roland SP-404MK2 sample library lane.

Turns anything blessdog can already produce (downloaded audio, Demucs stems,
restored archive rips) into SP-404MK2-ready WAV files filed onto the device's
SD card, with provenance recorded so a library stays attributable.

The device converts everything to 48 kHz/16-bit on import; this lane does that
conversion up front so what lands on the card is exactly what the SP will play.

See media-studio/docs/MUSIC-LANE.md for the plan this implements.
"""

from .convert import SP_RATE, SP_BITS, ConvertResult, to_sp_format, probe
from .card import CardError, ImportTarget, find_import_folder, file_to_card
from .ledger import (
    BANKS,
    PAD_BASE_NOTE,
    Ledger,
    LedgerEntry,
    hash_file,
    normalize_pad,
    note_to_pad,
    pad_to_note,
)

# NOTE: nothing here may be named `convert`, `card`, `ledger` or `build` — a
# package-level export with a submodule's name shadows the module itself, so
# `phase8_sp404.convert.probe` would resolve against the function. Caught by
# exercising, not by import success.
__all__ = [
    "SP_RATE",
    "SP_BITS",
    "ConvertResult",
    "to_sp_format",
    "probe",
    "CardError",
    "ImportTarget",
    "find_import_folder",
    "file_to_card",
    "Ledger",
    "LedgerEntry",
    "hash_file",
    "normalize_pad",
    "pad_to_note",
    "note_to_pad",
    "PAD_BASE_NOTE",
    "BANKS",
]
