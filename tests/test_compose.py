"""Offline tests for the phase6_compose engine: theory, rhythm, groove,
generators, and lint. No Ableton/OSC required — these assert musical
invariants (in-key, in-bounds, humanized, correct counts)."""

from __future__ import annotations

import pytest

from phase6_compose import MusicalContext, build_part, lint, ROLES
from phase6_compose.generators import arp, bassline, chords, drums, melody
from phase6_compose.groove import humanize
from phase6_compose.rhythm import euclidean, onsets
from phase6_compose.theory import voice_lead
from phase1_osc.types import MidiNote


# ---------------------------------------------------------------------------
# Theory
# ---------------------------------------------------------------------------

class TestTheory:
    def test_fsharp_minor_pitch_classes(self):
        ctx = MusicalContext(key="F#", mode="minor")
        # F# G# A B C# D E -> pcs 6 8 9 11 1 2 4
        assert ctx.pitch_classes() == {6, 8, 9, 11, 1, 2, 4}

    def test_diatonic_chords_match_known(self):
        ctx = MusicalContext(key="F#", mode="minor")
        assert ctx.diatonic_chord(1, octave=4) == [66, 69, 73]   # i = F# A C#
        assert ctx.diatonic_chord(6, octave=4) == [74, 78, 81]   # VI = D F# A

    def test_is_in_key(self):
        ctx = MusicalContext(key="C", mode="major")
        assert ctx.is_in_key(60)        # C
        assert not ctx.is_in_key(61)    # C#
        assert ctx.is_in_key(72)        # C octave up

    def test_modes_differ(self):
        dorian = MusicalContext(key="D", mode="dorian").pitch_classes()
        minor = MusicalContext(key="D", mode="minor").pitch_classes()
        assert dorian != minor  # dorian has a natural 6th

    def test_unknown_mode_rejected(self):
        with pytest.raises(ValueError):
            MusicalContext(key="C", mode="bogus")

    def test_voice_leading_reduces_motion(self):
        prev = [66, 69, 73]                       # F#m
        chord = [74, 78, 81]                       # D major, root position
        led = voice_lead(prev, chord)
        root_cost = sum(abs(a - b) for a, b in zip(sorted(chord), sorted(prev)))
        led_cost = sum(abs(a - b) for a, b in zip(sorted(led), sorted(prev)))
        assert led_cost < root_cost
        # Voice-led result is the same chord (same pitch classes)
        assert {p % 12 for p in led} == {p % 12 for p in chord}


# ---------------------------------------------------------------------------
# Rhythm
# ---------------------------------------------------------------------------

class TestRhythm:
    def test_tresillo(self):
        assert onsets(euclidean(3, 8)) == [0, 3, 6]

    def test_four_on_the_floor(self):
        assert onsets(euclidean(4, 16)) == [0, 4, 8, 12]

    def test_pulse_count_preserved(self):
        for pulses, steps in [(5, 8), (7, 16), (2, 5), (9, 16)]:
            assert len(onsets(euclidean(pulses, steps))) == pulses

    def test_edge_cases(self):
        assert euclidean(0, 8) == [False] * 8
        assert euclidean(8, 8) == [True] * 8
        assert euclidean(10, 8) == [True] * 8  # clamp


# ---------------------------------------------------------------------------
# Groove / humanization
# ---------------------------------------------------------------------------

def _flat(n=8, vel=100):
    return [MidiNote(60, i * 0.5, 0.5, vel) for i in range(n)]


class TestGroove:
    def test_velocity_variance_added(self):
        out = humanize(_flat(), velocity=12, seed=1)
        vels = {n.velocity for n in out}
        assert len(vels) > 1  # no longer flat

    def test_velocity_clamped(self):
        out = humanize(_flat(vel=126), velocity=50, accent=50, seed=2)
        assert all(1 <= n.velocity <= 127 for n in out)

    def test_deterministic_with_seed(self):
        a = humanize(_flat(), velocity=12, timing=0.01, seed=5)
        b = humanize(_flat(), velocity=12, timing=0.01, seed=5)
        assert [(n.start_time, n.velocity) for n in a] == \
               [(n.start_time, n.velocity) for n in b]

    def test_swing_pushes_offbeats_only(self):
        out = humanize(_flat(), swing=1.0, seed=0)
        # On-beat 8ths (even index) unmoved; off-beats (odd) pushed later
        assert out[0].start_time == 0.0
        assert out[2].start_time == 1.0
        assert out[1].start_time > 0.5
        assert out[3].start_time > 1.5


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

DEGREES = [1, 6, 4, 5]


class TestGenerators:
    @pytest.fixture
    def ctx(self):
        return MusicalContext(key="F#", mode="minor", beats_per_bar=4)

    def test_melodic_roles_in_key(self, ctx):
        for role in ("chords", "bass", "arp", "melody"):
            notes = build_part(role, ctx, degrees=DEGREES, bars=4, seed=3)
            assert notes, f"{role} produced no notes"
            off = [n.pitch for n in notes if not ctx.is_in_key(n.pitch)]
            assert off == [], f"{role} produced off-key pitches {off}"

    def test_within_bounds(self, ctx):
        clip_len = 16.0
        for role in ROLES:
            notes = build_part(role, ctx, degrees=DEGREES, bars=4, seed=3)
            assert all(0 <= n.start_time < clip_len for n in notes)
            assert all(n.start_time + n.duration <= clip_len + 1e-3 for n in notes)

    def test_drums_use_drum_pitches(self, ctx):
        notes = drums(ctx, bars=4)
        assert notes
        assert all(35 <= n.pitch <= 81 for n in notes)  # GM drum range-ish

    def test_polyrhythm_distinct_grids(self, ctx):
        notes = drums(ctx, bars=1, voices={
            "closed_hat": ("euclid", 4, 16),   # step 0.25 beat
            "perc": ("euclid", 3, 12),         # step 0.333 beat
        })
        perc_pitch = 60
        perc_starts = sorted({round(n.start_time, 3) for n in notes if n.pitch == perc_pitch})
        # A 12-step grid lands on thirds of a beat — not all multiples of 0.25
        assert any(abs((t / 0.25) - round(t / 0.25)) > 1e-3 for t in perc_starts)

    def test_chords_voice_count(self, ctx):
        notes = chords(ctx, [1, 5], bars=2, size=3, rhythm="whole")
        # 2 chords x 3 notes each, one hit per region
        assert len(notes) == 6

    def test_bass_pattern_and_rhythm(self, ctx):
        notes = bassline(ctx, [1], bars=1, rhythm="8th", pattern="root")
        assert len(notes) == 8       # 8 eighths in a 4-beat bar
        assert {n.pitch for n in notes} == {ctx.diatonic_chord(1, octave=2)[0]}

    def test_arp_fills_region(self, ctx):
        notes = arp(ctx, [1], bars=1, rate="16th")
        assert len(notes) == 16

    def test_melody_density_creates_rests(self, ctx):
        dense = melody(ctx, [1], bars=4, rate="8th", density=1.0, seed=1)
        sparse = melody(ctx, [1], bars=4, rate="8th", density=0.3, seed=1)
        assert len(sparse) < len(dense)


# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------

class TestLint:
    @pytest.fixture
    def ctx(self):
        return MusicalContext(key="C", mode="major")

    def test_clean_passes(self, ctx):
        notes = [MidiNote(60, 0.0, 1.0, 100), MidiNote(64, 1.0, 1.0, 90)]
        assert lint(notes, ctx, 4.0)["ok"]

    def test_catches_off_key(self, ctx):
        rep = lint([MidiNote(61, 0.0, 1.0, 100)], ctx, 4.0)
        assert not rep["ok"]
        assert any(i["problem"] == "off_key" for i in rep["issues"])

    def test_catches_out_of_bounds(self, ctx):
        rep = lint([MidiNote(60, 8.0, 1.0, 100)], ctx, 4.0)
        assert any(i["problem"] == "start_out_of_bounds" for i in rep["issues"])

    def test_catches_bad_velocity_and_duration(self, ctx):
        rep = lint([MidiNote(60, 0.0, 0.0, 200)], ctx, 4.0)
        problems = {i["problem"] for i in rep["issues"]}
        assert "velocity_out_of_range" in problems
        assert "non_positive_duration" in problems

    def test_drums_skip_key_check(self, ctx):
        # Drum pitch 36 (C1) is in C major by coincidence; use 37 (C#) which is not
        rep = lint([MidiNote(37, 0.0, 0.25, 100)], ctx, 4.0, check_key=False)
        assert rep["ok"]
