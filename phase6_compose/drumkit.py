"""Drum-Rack / General-MIDI pitch map for naming drum voices."""

from __future__ import annotations

# Ableton Drum Rack defaults to GM-style mapping with kick at C1 = MIDI 36.
DRUM_MAP: dict[str, int] = {
    "kick": 36,
    "kick2": 35,
    "rim": 37,
    "snare": 38,
    "clap": 39,
    "snare2": 40,
    "low_tom": 41,
    "closed_hat": 42,
    "hat": 42,
    "mid_tom": 45,
    "open_hat": 46,
    "hi_tom": 50,
    "crash": 49,
    "ride": 51,
    "tamb": 54,
    "cowbell": 56,
    "perc": 60,
    "conga": 62,
    "clave": 75,
    "shaker": 70,
}


def drum_pitch(name: str) -> int:
    key = name.lower().replace(" ", "_")
    if key not in DRUM_MAP:
        raise ValueError(f"unknown drum voice {name!r}; known: {sorted(DRUM_MAP)}")
    return DRUM_MAP[key]
