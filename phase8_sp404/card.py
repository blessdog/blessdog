"""SD card discovery and filing for the SP-404MK2.

Roland documents the card's folder layout only as a diagram image, so the exact
import path is [UNVERIFIED] and deliberately NOT hardcoded here. The SP creates
its own folder structure when it formats a card (UTILITY -> SD CARD -> FORMAT),
so the reliable move is to *find* the import folder on a real card rather than
assume where it lives. If it isn't found we fail loudly with instructions,
instead of silently writing into a directory the device will never read.

That silent-write failure mode is exactly what this module exists to avoid.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

# Names the import folder plausibly uses, checked case-insensitively.
_IMPORT_NAMES = {"import"}

# Depth to search below the card root. Roland nests at most
# <card>/ROLAND/SP-404MKII/IMPORT, which is depth 3.
_MAX_DEPTH = 3

# A directory called "import" is not evidence of an SP card on its own —
# /usr/share/vim/vim91/import exists on every Mac, and an early version of this
# module duly "detected" the boot volume as a card. A candidate only counts if
# the folder sits at the card root or under a ROLAND/ ancestor.
_VENDOR_DIR = "roland"

_VOLUMES = "/Volumes"


class CardError(RuntimeError):
    pass


@dataclass
class ImportTarget:
    """A resolved place to write samples on a specific card."""
    card_root: str
    import_dir: str

    def to_dict(self) -> dict:
        return {"card_root": self.card_root, "import_dir": self.import_dir}


def _plausible(import_dir: str, card_root: str) -> bool:
    """Is this IMPORT folder plausibly the SP's, rather than a coincidence?

    Accept only when it sits directly at the card root, or somewhere beneath a
    ROLAND/ directory. Anything else is almost certainly an unrelated folder
    that happens to be called "import".
    """
    parent = os.path.dirname(import_dir)
    if os.path.normpath(parent) == os.path.normpath(card_root):
        return True

    relative = os.path.relpath(import_dir, card_root)
    parts = [part.lower() for part in relative.split(os.sep)]
    return _VENDOR_DIR in parts


def _walk_for_import(root: str, max_depth: int = _MAX_DEPTH) -> str | None:
    """Breadth-first search under `root` for the SP's IMPORT directory."""
    root = os.path.abspath(root)
    frontier: list[tuple[str, int]] = [(root, 0)]
    while frontier:
        current, depth = frontier.pop(0)
        if depth > max_depth:
            continue
        try:
            entries = os.listdir(current)
        except (PermissionError, FileNotFoundError, NotADirectoryError):
            continue
        for entry in entries:
            if entry.startswith("."):
                continue
            path = os.path.join(current, entry)
            if not os.path.isdir(path):
                continue
            if entry.lower() in _IMPORT_NAMES and _plausible(path, root):
                return path
            frontier.append((path, depth + 1))
    return None


def _is_boot_volume(path: str) -> bool:
    """True if `path` lives on the same device as /, i.e. is not a card."""
    try:
        return os.stat(path).st_dev == os.stat("/").st_dev
    except OSError:
        return False


def find_import_folder(card_root: str) -> ImportTarget:
    """Locate the SP's import folder on a mounted card.

    Raises CardError with a fix-it message if the card is missing or has not
    been formatted by the device.
    """
    card_root = os.path.abspath(card_root)
    if not os.path.isdir(card_root):
        raise CardError(f"card not mounted or not a directory: {card_root}")

    found = _walk_for_import(card_root)
    if not found:
        raise CardError(
            f"no IMPORT folder found under {card_root}. Format the card in the "
            "SP-404MK2 first (UTILITY -> SD CARD -> FORMAT) — the device "
            "creates its own folder structure. Nothing was written."
        )
    return ImportTarget(card_root=card_root, import_dir=found)


def detect_cards() -> list[ImportTarget]:
    """Scan /Volumes for anything that looks like an SP-404MK2 card.

    Returns every match; an empty list means none were found. Callers should
    refuse to act on an ambiguous multi-card result rather than guess.
    """
    targets: list[ImportTarget] = []
    if not os.path.isdir(_VOLUMES):
        return targets

    for entry in sorted(os.listdir(_VOLUMES)):
        if entry.startswith("."):
            continue
        volume = os.path.join(_VOLUMES, entry)
        if not os.path.isdir(volume):
            continue
        # The boot disk is never a card, and scanning it only produces
        # false positives (/usr/share/vim/vim91/import).
        if _is_boot_volume(volume):
            continue
        found = _walk_for_import(volume)
        if found:
            targets.append(ImportTarget(card_root=volume, import_dir=found))
    return targets


def _unique_path(directory: str, filename: str) -> str:
    """Return a non-colliding path in `directory` for `filename`."""
    stem, ext = os.path.splitext(filename)
    candidate = os.path.join(directory, filename)
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{stem}_{counter}{ext}")
        counter += 1
    return candidate


def file_to_card(
    wav_path: str,
    target: ImportTarget,
    filename: str | None = None,
    overwrite: bool = False,
) -> str:
    """Copy a converted WAV into the card's import folder.

    Args:
        wav_path: Converted, SP-format WAV.
        target: Resolved ImportTarget from find_import_folder/detect_cards.
        filename: Override the destination filename (extension forced to .wav).
        overwrite: Replace an existing same-named file instead of uniquifying.

    Returns:
        Absolute path of the file as written on the card.
    """
    wav_path = os.path.abspath(wav_path)
    if not os.path.isfile(wav_path):
        raise CardError(f"nothing to file — missing: {wav_path}")
    if not os.path.isdir(target.import_dir):
        raise CardError(f"import folder vanished: {target.import_dir}")

    name = filename or os.path.basename(wav_path)
    if not name.lower().endswith(".wav"):
        name = f"{os.path.splitext(name)[0]}.wav"

    dest = os.path.join(target.import_dir, name)
    if os.path.exists(dest) and not overwrite:
        dest = _unique_path(target.import_dir, name)

    shutil.copy2(wav_path, dest)
    return dest


def free_bytes(card_root: str) -> int:
    """Free space on the card, in bytes."""
    stat = os.statvfs(card_root)
    return stat.f_bavail * stat.f_frsize
