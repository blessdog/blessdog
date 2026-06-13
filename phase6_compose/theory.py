"""Music theory primitives — the single source of truth for "what's in key".

Scales and diatonic chords are computed from interval tables (deterministic,
fast, mode-agnostic). music21 is used only to parse the tonic (so "F#", "Bb",
"Db" all resolve correctly) and is available for validation/MIDI export
elsewhere.

MIDI octave convention: C4 = 60 (standard MIDI). Ableton's UI labels that note
"C3" — same wire value, different label.
"""

from __future__ import annotations

from dataclasses import dataclass

import music21 as m21

# Semitone offsets from the tonic for each supported mode (7 scale degrees).
MODE_INTERVALS: dict[str, list[int]] = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "ionian": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],      # natural minor
    "aeolian": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
}


def tonic_pitch_class(key: str) -> int:
    """Pitch class 0-11 for a tonic name like 'F#', 'Bb', 'Db'."""
    return m21.pitch.Pitch(key).pitchClass


@dataclass
class MusicalContext:
    """The harmonic + metric frame a generator composes within."""

    key: str = "C"
    mode: str = "minor"
    tempo: float = 120.0
    beats_per_bar: int = 4

    def __post_init__(self) -> None:
        if self.mode not in MODE_INTERVALS:
            raise ValueError(
                f"unknown mode {self.mode!r}; supported: {sorted(MODE_INTERVALS)}"
            )

    @property
    def intervals(self) -> list[int]:
        return MODE_INTERVALS[self.mode]

    @property
    def tonic_pc(self) -> int:
        return tonic_pitch_class(self.key)

    def pitch_classes(self) -> set[int]:
        """The set of in-key pitch classes."""
        return {(self.tonic_pc + iv) % 12 for iv in self.intervals}

    def is_in_key(self, midi: int) -> bool:
        return (midi % 12) in self.pitch_classes()

    def tonic_midi(self, octave: int = 4) -> int:
        """MIDI number of the tonic at a given octave (C4 = 60)."""
        return 12 * (octave + 1) + self.tonic_pc

    def _scale_semitone(self, degree_index: int) -> int:
        """Semitone offset above the tonic for a 0-based scale-degree index,
        wrapping across octaves (index 7 == tonic one octave up)."""
        return self.intervals[degree_index % 7] + 12 * (degree_index // 7)

    def scale_midi(self, low: int = 36, high: int = 96) -> list[int]:
        """All in-key MIDI notes in the inclusive range, ascending."""
        pcs = self.pitch_classes()
        return [m for m in range(low, high + 1) if (m % 12) in pcs]

    def diatonic_chord(
        self, degree: int, octave: int = 4, size: int = 3
    ) -> list[int]:
        """Build a diatonic chord on a scale degree (1-7) by stacking scale
        thirds. size=3 triad, 4 seventh, 5 ninth. Works for any mode."""
        if not 1 <= degree <= 7:
            raise ValueError(f"degree must be 1-7, got {degree}")
        base = self.tonic_midi(octave)
        return [base + self._scale_semitone((degree - 1) + 2 * k) for k in range(size)]

    def nearest_scale_midi(self, midi: int) -> int:
        """Snap an arbitrary MIDI note to the closest in-key note."""
        if self.is_in_key(midi):
            return midi
        for delta in range(1, 7):
            if self.is_in_key(midi - delta):
                return midi - delta
            if self.is_in_key(midi + delta):
                return midi + delta
        return midi


# ---------------------------------------------------------------------------
# Voice leading
# ---------------------------------------------------------------------------

def _inversions(chord: list[int]) -> list[list[int]]:
    """All inversions of a chord (rotating the lowest note up an octave),
    plus the same set shifted down an octave — candidate voicings."""
    base = sorted(chord)
    rotations = []
    c = list(base)
    for _ in range(len(c)):
        rotations.append(sorted(c))
        c = c[1:] + [c[0] + 12]
    return rotations + [[m - 12 for m in inv] for inv in rotations]


def voice_lead(prev: list[int] | None, chord: list[int]) -> list[int]:
    """Pick the voicing of `chord` closest to `prev` (smallest total motion),
    so progressions move smoothly instead of leaping. Returns sorted MIDI."""
    if not prev:
        return sorted(chord)
    target = sorted(prev)
    candidates = _inversions(chord)

    def cost(cand: list[int]) -> int:
        n = min(len(cand), len(target))
        return sum(abs(a - b) for a, b in zip(sorted(cand)[:n], target[:n]))

    return sorted(min(candidates, key=cost))
