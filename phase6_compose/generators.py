"""Pattern generators — intent in, in-key MIDI out.

Every generator is deterministic, pure (no OSC), and returns a list of the
existing MidiNote dataclass so output flows straight into the write path. The
LLM picks intent (key, mode, degrees, register, feel); these build the notes,
so nothing is ever off-key or octave-slipped.

Aesthetic bias: melodic house/techno, ambient, cinematic.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from phase1_osc.types import MidiNote

from .drumkit import drum_pitch
from .rhythm import euclidean, onsets, rate_to_beats
from .theory import MusicalContext, voice_lead


@dataclass
class ChordRegion:
    degree: int
    start: float   # beats
    length: float  # beats


def chord_regions(degrees: list[int], bars: int, beats_per_bar: int = 4) -> list[ChordRegion]:
    """Split `bars` evenly across the progression degrees."""
    total = bars * beats_per_bar
    seg = total / len(degrees)
    return [ChordRegion(d, i * seg, seg) for i, d in enumerate(degrees)]


# ---------------------------------------------------------------------------
# Harmony
# ---------------------------------------------------------------------------

def chords(
    ctx: MusicalContext,
    degrees: list[int],
    bars: int = 4,
    *,
    octave: int = 4,
    size: int = 3,
    rhythm: str | float = "whole",
    gate: float = 0.95,
    velocity: int = 88,
    voice_leading: bool = True,
) -> list[MidiNote]:
    """Voice-led diatonic chord progression.

    `degrees` are scale degrees (1-7), e.g. [1, 6, 4, 5] = i-VI-iv-v in minor.
    `rhythm` re-triggers the chord at that rate within each region ("whole" =
    one sustained hit per chord).
    """
    regions = chord_regions(degrees, bars, ctx.beats_per_bar)
    step = rate_to_beats(rhythm)
    notes: list[MidiNote] = []
    prev: list[int] | None = None

    for region in regions:
        voicing = ctx.diatonic_chord(region.degree, octave=octave, size=size)
        if voice_leading:
            voicing = voice_lead(prev, voicing)
        prev = voicing

        t = region.start
        end = region.start + region.length
        while t < end - 1e-6:
            dur = min(step, end - t) * gate
            for pitch in voicing:
                notes.append(MidiNote(pitch, round(t, 4), round(dur, 4), velocity))
            t += step

    return notes


# ---------------------------------------------------------------------------
# Bass
# ---------------------------------------------------------------------------

def bassline(
    ctx: MusicalContext,
    degrees: list[int],
    bars: int = 4,
    *,
    octave: int = 2,
    pattern: str = "root_octave",
    rhythm: str | float = "8th",
    gate: float = 0.5,
    velocity: int = 104,
) -> list[MidiNote]:
    """Bass locked to the progression.

    pattern: 'root' | 'root_fifth' | 'root_octave' | 'walking'. rhythm sets the
    pulse (driving 8ths suit melodic techno).
    """
    regions = chord_regions(degrees, bars, ctx.beats_per_bar)
    step = rate_to_beats(rhythm)
    notes: list[MidiNote] = []

    for region in regions:
        chord = ctx.diatonic_chord(region.degree, octave=octave, size=3)
        root, fifth = chord[0], chord[2]
        scale = ctx.scale_midi(root - 1, root + 13)

        idx = 0
        t = region.start
        end = region.start + region.length
        while t < end - 1e-6:
            if pattern == "root":
                pitch = root
            elif pattern == "root_fifth":
                pitch = (root, fifth)[idx % 2]
            elif pattern == "root_octave":
                pitch = (root, root + 12)[idx % 2]
            elif pattern == "walking":
                pitch = scale[idx % len(scale)]
            else:
                raise ValueError(f"unknown bass pattern {pattern!r}")
            dur = step * gate
            notes.append(MidiNote(pitch, round(t, 4), round(dur, 4), velocity))
            idx += 1
            t += step

    return notes


# ---------------------------------------------------------------------------
# Arp
# ---------------------------------------------------------------------------

def arp(
    ctx: MusicalContext,
    degrees: list[int],
    bars: int = 4,
    *,
    octave: int = 4,
    size: int = 3,
    style: str = "up",
    rate: str | float = "16th",
    gate: float = 0.5,
    velocity: int = 84,
    octaves: int = 1,
) -> list[MidiNote]:
    """Arpeggiate each chord across its region. style: up|down|updown|random."""
    regions = chord_regions(degrees, bars, ctx.beats_per_bar)
    step = rate_to_beats(rate)
    rng = np.random.default_rng(0)
    notes: list[MidiNote] = []

    for region in regions:
        chord = ctx.diatonic_chord(region.degree, octave=octave, size=size)
        pool = [p + 12 * o for o in range(octaves) for p in chord]
        pool = sorted(pool)
        if style == "up":
            order = pool
        elif style == "down":
            order = list(reversed(pool))
        elif style == "updown":
            order = pool + list(reversed(pool[1:-1])) if len(pool) > 2 else pool
        elif style == "random":
            order = [pool[i] for i in rng.integers(0, len(pool), size=64)]
        else:
            raise ValueError(f"unknown arp style {style!r}")

        i = 0
        t = region.start
        end = region.start + region.length
        while t < end - 1e-6:
            pitch = order[i % len(order)]
            notes.append(MidiNote(pitch, round(t, 4), round(step * gate, 4), velocity))
            i += 1
            t += step

    return notes


# ---------------------------------------------------------------------------
# Melody
# ---------------------------------------------------------------------------

def melody(
    ctx: MusicalContext,
    degrees: list[int] | None = None,
    bars: int = 4,
    *,
    octave: int = 5,
    rate: str | float = "8th",
    density: float = 0.6,
    contour: str = "arch",
    velocity: int = 80,
    seed: int = 0,
) -> list[MidiNote]:
    """Scale-constrained motif melody — a constrained random walk that only
    ever lands on in-key notes, biased toward chord tones on strong beats and
    shaped by `contour` (arch | rising | falling | wave). `density` is the
    fraction of grid slots that sound (the rest are rests).
    """
    rng = np.random.default_rng(seed)
    step = rate_to_beats(rate)
    total = bars * ctx.beats_per_bar
    n_steps = int(round(total / step))
    regions = chord_regions(degrees or [1], bars, ctx.beats_per_bar)
    scale = ctx.scale_midi(ctx.tonic_midi(octave) - 7, ctx.tonic_midi(octave) + 14)

    def contour_bias(frac: float) -> float:
        if contour == "rising":
            return (frac - 0.5) * 2
        if contour == "falling":
            return (0.5 - frac) * 2
        if contour == "wave":
            return float(np.sin(frac * 2 * np.pi))
        # arch: up then down
        return float(np.sin(frac * np.pi)) * 2 - 1

    # Start near the middle of the scale.
    pos = len(scale) // 2
    notes: list[MidiNote] = []

    for s in range(n_steps):
        t = s * step
        if rng.random() > density:
            continue  # rest

        frac = t / total
        # Bias the step direction by contour; step size 1-2 scale degrees.
        drift = contour_bias(frac)
        move = int(round(float(rng.normal(drift, 1.2))))
        pos = max(0, min(len(scale) - 1, pos + move))

        # On strong beats, pull toward a chord tone for harmonic grounding.
        if abs(t % ctx.beats_per_bar) < 1e-6 or abs((t % 1.0)) < 1e-6:
            region = next((r for r in regions if r.start <= t < r.start + r.length), regions[-1])
            chord = ctx.diatonic_chord(region.degree, octave=octave, size=3)
            target = min(chord, key=lambda c: abs(c - scale[pos]))
            pos = min(range(len(scale)), key=lambda i: abs(scale[i] - target))

        notes.append(MidiNote(scale[pos], round(t, 4), round(step * 0.9, 4), velocity))

    return notes


# ---------------------------------------------------------------------------
# Drums
# ---------------------------------------------------------------------------

# Default melodic-house kit: four-on-floor kick, off-beat open hat, busy closed
# hats, backbeat clap. Voices can use different step counts -> polyrhythm.
DEFAULT_KIT: dict[str, tuple] = {
    "kick": ("euclid", 4, 16),
    "clap": ("steps", [4, 12]),
    "closed_hat": ("euclid", 11, 16),
    "open_hat": ("steps", [2, 6, 10, 14]),
}


def drums(
    ctx: MusicalContext,
    bars: int = 4,
    *,
    voices: dict[str, tuple] | None = None,
    velocity: int = 100,
) -> list[MidiNote]:
    """Build a drum pattern from per-voice specs, repeated each bar.

    A voice spec is either ("euclid", pulses, steps) or ("steps", [indices]).
    Different `steps` values across voices produce genuine polyrhythm.
    """
    kit = voices or DEFAULT_KIT
    bpb = ctx.beats_per_bar
    notes: list[MidiNote] = []

    for name, spec in kit.items():
        pitch = drum_pitch(name)
        if spec[0] == "euclid":
            _, pulses, steps = spec
            hit_idxs = onsets(euclidean(pulses, steps))
        elif spec[0] == "steps":
            steps = max(spec[1]) + 1 if spec[1] else 1
            steps = max(steps, 16)
            hit_idxs = list(spec[1])
        else:
            raise ValueError(f"unknown drum spec {spec!r}")

        step_beats = bpb / steps
        for bar in range(bars):
            bar_start = bar * bpb
            for idx in hit_idxs:
                t = bar_start + idx * step_beats
                notes.append(MidiNote(pitch, round(t, 4), round(step_beats * 0.5, 4), velocity))

    return notes
