"""Rhythm primitives — Euclidean (Bjorklund) patterns and step/beat helpers.

Euclidean rhythms distribute N pulses as evenly as possible over M steps; they
generate the tresillo/clave/world-rhythm feels that make electronic patterns
groove, and different step counts on different voices give genuine polyrhythm.
"""

from __future__ import annotations

# Note-rate name -> beat duration (4/4).
RATE_BEATS: dict[str, float] = {
    "whole": 4.0,
    "half": 2.0,
    "4th": 1.0,
    "quarter": 1.0,
    "8th": 0.5,
    "eighth": 0.5,
    "16th": 0.25,
    "sixteenth": 0.25,
    "32nd": 0.125,
    "triplet8th": 1.0 / 3.0,
}


def rate_to_beats(rate: str | float) -> float:
    if isinstance(rate, (int, float)):
        return float(rate)
    if rate not in RATE_BEATS:
        raise ValueError(f"unknown rate {rate!r}; known: {sorted(RATE_BEATS)}")
    return RATE_BEATS[rate]


def euclidean(pulses: int, steps: int, rotate: int = 0) -> list[bool]:
    """Bjorklund's algorithm: distribute `pulses` over `steps` as evenly as
    possible. Returns a list of booleans (True = onset).

    E(3,8) -> x..x..x.  (tresillo); E(4,16) -> four-on-the-floor.
    """
    if steps <= 0:
        return []
    if pulses <= 0:
        return [False] * steps
    if pulses >= steps:
        return [True] * steps

    counts: list[int] = []
    remainders: list[int] = [pulses]
    divisor = steps - pulses
    level = 0
    while True:
        counts.append(divisor // remainders[level])
        remainders.append(divisor % remainders[level])
        divisor = remainders[level]
        level += 1
        if remainders[level] <= 1:
            break
    counts.append(divisor)

    def build(lv: int) -> list[bool]:
        if lv == -1:
            return [False]
        if lv == -2:
            return [True]
        seq: list[bool] = []
        for _ in range(counts[lv]):
            seq += build(lv - 1)
        if remainders[lv] != 0:
            seq += build(lv - 2)
        return seq

    seq = build(level)
    # Rotate so the pattern starts on its first onset (canonical form).
    first = seq.index(True)
    seq = seq[first:] + seq[:first]

    if rotate:
        rotate %= len(seq)
        seq = seq[-rotate:] + seq[:-rotate]
    return seq


def onsets(pattern: list[bool]) -> list[int]:
    """Indices of True steps."""
    return [i for i, hit in enumerate(pattern) if hit]
