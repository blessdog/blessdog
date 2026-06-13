"""phase6_compose — intent-driven, theory-aware MIDI generation.

The composition engine: the LLM picks musical intent (key, mode, degrees,
register, feel) and these deterministic primitives produce in-key, voice-led,
groovy MIDI as MidiNote lists — so nothing is ever off-key, octave-slipped, or
robotically flat. Output flows straight into the reliable OSC write path.
"""

from __future__ import annotations

from phase1_osc.types import MidiNote

from .generators import arp, bassline, chords, drums, melody
from .groove import humanize
from .lint import lint
from .theory import MusicalContext, voice_lead

__all__ = [
    "MusicalContext",
    "voice_lead",
    "chords",
    "bassline",
    "arp",
    "melody",
    "drums",
    "humanize",
    "lint",
    "build_part",
    "ROLES",
]

ROLES = ("chords", "bass", "arp", "melody", "drums")

_GENERATORS = {
    "chords": chords,
    "bass": bassline,
    "arp": arp,
    "melody": melody,
    "drums": drums,
}

# Sensible default humanization per role; callers can override via `groove`.
_DEFAULT_GROOVE: dict[str, dict] = {
    "chords": dict(timing=0.008, velocity=6, accent=8, accent_beats=(0.0,)),
    "bass": dict(timing=0.006, velocity=8, accent=10, accent_beats=(0.0,)),
    "arp": dict(timing=0.006, velocity=10),
    "melody": dict(timing=0.012, velocity=12),
    "drums": dict(timing=0.004, velocity=10, swing=0.12, accent=14,
                  accent_beats=(0.0, 2.0)),
}

_DEFAULT_DEGREES = [1, 6, 4, 5]


def build_part(
    role: str,
    ctx: MusicalContext,
    *,
    degrees: list[int] | None = None,
    bars: int = 4,
    groove: dict | None = None,
    seed: int = 0,
    **gen_opts,
) -> list[MidiNote]:
    """One call: generate a part for `role`, then humanize it.

    role in ROLES. Returns a list[MidiNote] ready for the reliable write path.
    """
    if role not in _GENERATORS:
        raise ValueError(f"unknown role {role!r}; choose from {ROLES}")

    gen = _GENERATORS[role]
    if role in ("chords", "bass", "arp"):
        notes = gen(ctx, degrees or _DEFAULT_DEGREES, bars, **gen_opts)
    elif role == "melody":
        notes = gen(ctx, degrees, bars, seed=seed, **gen_opts)
    else:  # drums
        notes = gen(ctx, bars, **gen_opts)

    g = dict(_DEFAULT_GROOVE[role])
    if groove:
        g.update(groove)
    g.setdefault("beats_per_bar", ctx.beats_per_bar)
    return humanize(notes, seed=seed, **g)
