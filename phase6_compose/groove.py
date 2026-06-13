"""Humanization — turn a stiff, flat grid into something that breathes.

Applies swing, micro-timing jitter, velocity variation, and downbeat accents.
Deterministic given a seed (so tests and reproducible sessions work). This is
the layer that fixes the "robotic / flat-velocity" complaint.
"""

from __future__ import annotations

import numpy as np

from phase1_osc.types import MidiNote

# Classic triplet swing pushes the off-beat 8th by up to 1/3 of an 8th note.
_MAX_SWING_PUSH = 0.5 / 3.0


def _is_offbeat_eighth(start: float, tol: float = 1e-3) -> bool:
    """True if the note sits on an 'and' (odd 8th-note position)."""
    eighths = start / 0.5
    return abs(eighths - round(eighths)) < tol and round(eighths) % 2 == 1


def humanize(
    notes: list[MidiNote],
    *,
    swing: float = 0.0,
    timing: float = 0.0,
    velocity: float = 0.0,
    accent: float = 0.0,
    accent_beats: tuple[float, ...] = (0.0,),
    beats_per_bar: int = 4,
    seed: int = 0,
) -> list[MidiNote]:
    """Return a humanized copy of `notes`.

    swing    0..1   amount of triplet swing on off-beat 8ths
    timing   beats  std-dev of gaussian micro-timing jitter (e.g. 0.01)
    velocity        std-dev of gaussian velocity variation (e.g. 12)
    accent          velocity added to notes on `accent_beats` of the bar
    """
    rng = np.random.default_rng(seed)
    out: list[MidiNote] = []

    for n in notes:
        start = n.start_time
        vel = float(n.velocity)

        if swing > 0.0 and _is_offbeat_eighth(start):
            start += swing * _MAX_SWING_PUSH

        if timing > 0.0:
            start = max(0.0, start + float(rng.normal(0.0, timing)))

        if velocity > 0.0:
            vel += float(rng.normal(0.0, velocity))

        if accent > 0.0:
            beat_in_bar = round(start % beats_per_bar, 3)
            if any(abs(beat_in_bar - b) < 1e-2 for b in accent_beats):
                vel += accent

        out.append(MidiNote(
            pitch=n.pitch,
            start_time=round(start, 4),
            duration=n.duration,
            velocity=int(min(127, max(1, round(vel)))),
            mute=n.mute,
        ))

    return out
