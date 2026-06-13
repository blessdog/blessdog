"""Reliable clip note write/read path: chunking, range-correct read-back,
resilient (split-on-timeout) reads, and write verification.

The range-filter test is a regression guard for the AbletonOSC parameter-order
bug (get/notes is pitch_start, pitch_span, time_start, time_span — NOT
start_time first).
"""

from __future__ import annotations

import pytest

from phase1_osc.clips import Clips
from phase1_osc.errors import QueryTimeout
from phase1_osc.types import MidiNote


@pytest.fixture
def clips(conn, mock_server):
    mock_server._clip_notes.clear()
    return Clips(conn)


def _grid(n: int, pitch: int = 60, step: float = 0.25):
    return [
        MidiNote(pitch=pitch, start_time=i * step, duration=step, velocity=100)
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Round-trip through the mock server
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_add_then_get(self, clips):
        clips.add_notes(0, 0, _grid(8))
        got = clips.get_notes(0, 0, 0.0, 8.0, 0, 127)
        assert len(got) == 8
        assert {n.pitch for n in got} == {60}

    def test_large_pattern_survives(self, clips):
        # 200 notes >> chunk size; with chunking, all must land
        notes = _grid(200, pitch=42, step=0.25)
        clips.add_notes(0, 1, notes)
        got = clips.get_notes(0, 1, 0.0, 200 * 0.25 + 1, 0, 127)
        assert len(got) == 200

    def test_verified_write_reports_match(self, clips):
        result = clips.add_notes_verified(0, 2, _grid(64, pitch=48))
        assert result["match"] is True
        assert result["written"] == 64
        assert result["found"] == 64
        assert result["missing"] == []
        assert result["extra"] == []

    def test_verified_write_empty(self, clips):
        result = clips.add_notes_verified(0, 3, [])
        assert result == {"written": 0, "found": 0, "match": True,
                          "missing": [], "extra": []}


# ---------------------------------------------------------------------------
# Range correctness — guards the parameter-order bug
# ---------------------------------------------------------------------------

class TestRangeFilter:
    def test_pitch_and_time_windows(self, clips):
        clips.add_notes(0, 4, [
            MidiNote(pitch=36, start_time=0.0, duration=0.25, velocity=100),
            MidiNote(pitch=72, start_time=4.0, duration=0.25, velocity=100),
        ])
        # Pitch window around 36 only
        low = clips.get_notes(0, 4, 0.0, 8.0, 30, 40)
        assert [n.pitch for n in low] == [36]
        # Time window around beat 4 only
        late = clips.get_notes(0, 4, 3.5, 2.0, 0, 127)
        assert [n.pitch for n in late] == [72]


# ---------------------------------------------------------------------------
# Chunking + resilient read — unit level with fake connections
# ---------------------------------------------------------------------------

class _CapturingConn:
    def __init__(self):
        self.sends = []

    def send(self, address, *args):
        self.sends.append((address, args))

    def query(self, *a, **k):  # pragma: no cover - should not be called
        raise AssertionError("query should not be called")


class _TimeoutOnWideConn:
    """Times out when pitch_span exceeds `limit`; else returns one canned note
    at the window's low pitch."""

    def __init__(self, limit: int = 64):
        self.limit = limit
        self.calls = []

    def send(self, *a, **k):
        pass

    def query(self, address, *args, timeout=None):
        track, clip, p_start, p_span, t_start, t_span = args
        self.calls.append((int(p_start), int(p_span)))
        if p_span > self.limit:
            raise QueryTimeout("response too large")
        return (track, clip, int(p_start), float(t_start), 0.25, 100, 0)


class TestChunkingAndResilience:
    def test_add_notes_splits_into_messages(self):
        conn = _CapturingConn()
        Clips(conn).add_notes(0, 0, _grid(130), chunk_size=64)
        # 130 -> 64 + 64 + 2 == 3 messages
        assert len(conn.sends) == 3
        first_args = conn.sends[0][1]
        assert first_args[0] == 0 and first_args[1] == 0
        assert (len(first_args) - 2) == 64 * 5  # 5 OSC args per note

    def test_get_notes_splits_on_timeout(self):
        conn = _TimeoutOnWideConn(limit=64)
        notes = Clips(conn).get_notes(0, 0, 0.0, 8.0, 0, 127)  # span 128 -> split
        # 0-63 and 64-127, each returns one note
        assert len(notes) == 2
        assert {n.pitch for n in notes} == {0, 64}

    def test_get_notes_reraises_when_unsplittable(self):
        # limit 0 forces timeout even on a 1-pitch span
        conn = _TimeoutOnWideConn(limit=0)
        with pytest.raises(QueryTimeout):
            Clips(conn).get_notes(0, 0, 0.0, 8.0, 60, 60)
