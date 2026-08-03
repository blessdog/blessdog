"""Orchestrator — source in, SP-404MK2-ready sample out.

Staging is deliberately two-step: everything lands in a local library first
(`music/sp404/<kind>/`), and only then gets copied to a card. The SD card is
small and swappable; the library on disk is the durable thing. Rebuilding a
card from the ledger must always be possible without re-downloading anything.

Composes the pieces blessdog already has:
    phase5_analyzer.download   URL -> audio
    phase5_analyzer.separator  audio -> Demucs stems
    phase5_analyzer.analyzer   audio -> tempo/key/structure
and adds only the two steps that were missing: SP-format conversion and filing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .card import CardError, ImportTarget, file_to_card
from .convert import ConvertResult, sp_safe_name, to_sp_format
from .ledger import Ledger, LedgerEntry, hash_file, normalize_pad

_LIBRARY_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "music",
    "sp404",
)


# Below this, a key estimate is noise rather than a reading. Sits between the
# measured 0.287 of a drums stem and the 0.606 of a full mix.
_KEY_MIN_CONF = 0.45


def detect_tempo_key(audio_path, max_secs=120.0):
    """Estimate (bpm, key) for a file. Returns (None, "") if unavailable.

    Reuses phase5_analyzer's existing estimators rather than reimplementing
    them — they work on raw samples, so no Demucs pass is needed and this stays
    cheap enough to run on every add.

    A DJ library without tempo is barely a DJ library (MUSIC-LANE decision 3),
    and the first real run proved nothing was populating these fields: the unit
    tests passed only because they set bpm/key explicitly by hand.

    Only the first `max_secs` are analysed. A 10-minute track does not need
    full decoding to yield its tempo, and dance music does not change key
    halfway through. Never raises — metadata is a nice-to-have, and failing to
    read it must not block a sample from entering the library.
    """
    try:
        import librosa
        from phase5_analyzer.stems import _estimate_key, _estimate_tempo

        y, sr = librosa.load(str(audio_path), mono=True, duration=max_secs)
        if not len(y):
            return None, ""
        bpm, _ = _estimate_tempo(y, sr)
        root, mode, conf = _estimate_key(librosa.effects.harmonic(y), sr)
        # Percussion has no tonal centre, so a drum stem still yields a
        # confident-looking answer that is pure noise — measured: a real drums
        # stem returned "D#m" at conf 0.287, against 0.606 for a full mix and
        # 0.683 for a vocal stem. Recording that as fact would poison
        # harmonic-mixing decisions later, so report no key rather than a wrong
        # one. Pass --key to override when you actually know it.
        key = f"{root}{mode[0] if mode else ''}" if conf >= _KEY_MIN_CONF else ""
        return round(float(bpm), 1), key
    except Exception:
        return None, ""


@dataclass
class StageResult:
    success: bool
    entry: LedgerEntry | None = None
    skipped_duplicate: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "skipped_duplicate": self.skipped_duplicate,
            "entry": self.entry.to_dict() if self.entry else None,
            "error": self.error,
        }


@dataclass
class BatchResult:
    staged: list[LedgerEntry] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"staged {len(self.staged)}, "
            f"skipped {len(self.skipped)} duplicate(s), "
            f"failed {len(self.failed)}"
        ]
        for source, error in self.failed:
            lines.append(f"  FAIL {os.path.basename(source)}: {error}")
        return "\n".join(lines)


def library_path(kind: str, name: str) -> str:
    """Where a sample of `kind` named `name` is staged locally."""
    return os.path.join(_LIBRARY_ROOT, kind, f"{name}.wav")


def stage_file(
    source_path: str,
    kind: str = "oneshot",
    name: str | None = None,
    bank: str = "",
    ledger: Ledger | None = None,
    derived_from: str = "",
    source_url: str = "",
    title: str = "",
    artist: str = "",
    bpm: float | None = None,
    key: str = "",
    normalize: bool = False,
    mono: bool = False,
    source_clip_hash: str = "",
    source_in_secs: float | None = None,
    pad: str = "",
    analyze: bool = False,
) -> StageResult:
    """Convert one local audio file into the SP library and record it.

    Deduplicates on the SOURCE file's content hash — converting the same source
    twice is recognised rather than producing a second near-identical sample.

    `source_clip_hash`/`source_in_secs`/`pad` carry the clip-lane pointer (see
    CLIP-LANE.md §7): which video this came from, where inside it, and which
    device pad it sits on. All optional — the sampling lane never needs them.
    """
    source_path = os.path.abspath(source_path)
    if not os.path.isfile(source_path):
        return StageResult(success=False, error=f"source missing: {source_path}")

    # Validate the pad BEFORE converting — LedgerEntry would reject it anyway,
    # but raising after an ffmpeg pass wastes the work and breaks this
    # function's contract of failing softly so batches can carry on.
    if pad:
        try:
            pad = normalize_pad(pad)
        except ValueError as exc:
            return StageResult(success=False, error=str(exc))

    library: Ledger = ledger if ledger is not None else Ledger()

    try:
        source_hash = hash_file(source_path)
    except OSError as exc:
        return StageResult(success=False, error=f"could not hash source: {exc}")

    existing = library.by_hash(source_hash)
    if existing:
        return StageResult(success=True, entry=existing, skipped_duplicate=True)

    base = name or title or os.path.splitext(os.path.basename(source_path))[0]
    safe = sp_safe_name(base)
    dest = library_path(kind, safe)

    # Never silently overwrite a differently-sourced sample of the same name.
    counter = 2
    while os.path.exists(dest):
        dest = library_path(kind, f"{safe}_{counter}")
        counter += 1

    result: ConvertResult = to_sp_format(
        source_path, dest, normalize=normalize, mono=mono
    )
    if not result.success:
        return StageResult(success=False, error=result.error)

    # Analyse the CONVERTED file, so bpm/key describe what actually sits on the
    # pad. Explicit values win — a tempo you read off the SP or Ableton beats
    # any estimate (see media-studio beat-grid --bpm).
    if analyze and (bpm is None or not key):
        detected_bpm, detected_key = detect_tempo_key(result.file_path)
        bpm = bpm if bpm is not None else detected_bpm
        key = key or detected_key

    entry = LedgerEntry(
        source_hash=source_hash,
        name=os.path.splitext(os.path.basename(dest))[0],
        kind=kind,
        source_path=source_path,
        source_url=source_url,
        title=title or base,
        artist=artist,
        bpm=bpm,
        key=key,
        duration_secs=result.duration_secs,
        derived_from=derived_from,
        local_path=dest,
        bank=bank,
        source_clip_hash=source_clip_hash,
        source_in_secs=source_in_secs,
        pad=pad,
    )
    library.add(entry)
    return StageResult(success=True, entry=entry)


def stage_many(
    source_paths: list[str],
    kind: str = "oneshot",
    bank: str = "",
    ledger: Ledger | None = None,
    **kwargs,
) -> BatchResult:
    """Stage a list of local files, carrying on past individual failures."""
    library: Ledger = ledger if ledger is not None else Ledger()
    batch = BatchResult()

    for path in source_paths:
        outcome = stage_file(path, kind=kind, bank=bank, ledger=library, **kwargs)
        if not outcome.success:
            batch.failed.append((path, outcome.error))
        elif outcome.skipped_duplicate:
            batch.skipped.append(path)
        elif outcome.entry:
            batch.staged.append(outcome.entry)

    return batch


def stage_stems(
    stem_paths: dict[str, str],
    bank: str = "",
    ledger: Ledger | None = None,
    title: str = "",
    bpm: float | None = None,
    key: str = "",
) -> BatchResult:
    """Stage Demucs output (a {name: path} map) as individual `stem` samples.

    Pairs with phase5_analyzer.separator.StemPaths.all().
    """
    library: Ledger = ledger if ledger is not None else Ledger()
    batch = BatchResult()

    for stem_name, path in stem_paths.items():
        label = f"{title}_{stem_name}" if title else stem_name
        outcome = stage_file(
            path,
            kind="stem",
            name=label,
            bank=bank,
            ledger=library,
            derived_from=f"demucs:{stem_name}",
            title=title,
            bpm=bpm,
            key=key,
        )
        if not outcome.success:
            batch.failed.append((path, outcome.error))
        elif outcome.skipped_duplicate:
            batch.skipped.append(path)
        elif outcome.entry:
            batch.staged.append(outcome.entry)

    return batch


def push_to_card(
    entries: list[LedgerEntry],
    target: ImportTarget,
    ledger: Ledger | None = None,
    overwrite: bool = False,
) -> BatchResult:
    """Copy staged samples onto a card and record where each one landed."""
    library: Ledger = ledger if ledger is not None else Ledger()
    batch = BatchResult()

    for entry in entries:
        if not entry.local_path or not os.path.isfile(entry.local_path):
            batch.failed.append((entry.name, "staged file missing from library"))
            continue
        try:
            landed = file_to_card(
                entry.local_path,
                target,
                filename=f"{entry.name}.wav",
                overwrite=overwrite,
            )
        except CardError as exc:
            batch.failed.append((entry.name, str(exc)))
            continue

        entry.card_path = landed
        batch.staged.append(entry)

    library.save()
    return batch
