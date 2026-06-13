"""Clip management — fire, stop, create, MIDI note read/write.

Note writing is chunked and the read path is range-correct + resilient, because
AbletonOSC packs notes into OSC/UDP datagrams that exceed the packet size on
dense clips (see ideoforms/AbletonOSC#88 — `OSError: [Errno 40] Message too
long`). A single oversized add silently drops; a single oversized read times
out. We split both.
"""

from __future__ import annotations

from collections import Counter

from .connection import AbletonOSCConnection
from .errors import QueryTimeout
from .types import ClipInfo, MidiNote

# Max notes per /live/clip/add/notes message. Each note is 5 OSC args (~40-60
# bytes typed); 64 notes ≈ a few KB, comfortably under the UDP datagram limit
# that AbletonOSC hits. Conservative on purpose; raise only if a build tolerates
# more.
DEFAULT_NOTE_CHUNK = 64


class Clips:
    def __init__(self, conn: AbletonOSCConnection):
        self._conn = conn

    def fire(self, track: int, clip: int) -> None:
        self._conn.send("/live/clip/fire", track, clip)

    def stop(self, track: int, clip: int) -> None:
        self._conn.send("/live/clip/stop", track, clip)

    def get_info(self, track: int, clip: int) -> ClipInfo:
        name = self._conn.query("/live/clip/get/name", track, clip)
        length = self._conn.query("/live/clip/get/length", track, clip)
        return ClipInfo(
            track_index=track,
            clip_index=clip,
            name=str(name[-1]),
            length=float(length[-1]),
        )

    def set_name(self, track: int, clip: int, name: str) -> None:
        self._conn.send("/live/clip/set/name", track, clip, name)

    def create(self, track: int, clip: int, length: float = 4.0) -> None:
        self._conn.send("/live/clip_slot/create_clip", track, clip, length)

    def delete(self, track: int, clip: int) -> None:
        self._conn.send("/live/clip_slot/delete_clip", track, clip)

    # ------------------------------------------------------------------
    # Reading notes
    # ------------------------------------------------------------------

    def get_notes(
        self,
        track: int,
        clip: int,
        start: float = 0.0,
        length: float = 128.0,
        pitch_low: int = 0,
        pitch_high: int = 127,
    ) -> list[MidiNote]:
        """Read MIDI notes from a clip within a time + pitch window.

        AbletonOSC `/live/clip/get/notes` expects, after track/clip:
            pitch_start, pitch_span, time_start, time_span
        (NOT start_time first — getting this order wrong silently reads the
        wrong region). pitch_high is inclusive, so span = high - low + 1.

        On a dense clip the response can exceed one datagram and never arrives
        (QueryTimeout). We then split the pitch range and recurse so the read
        still completes.
        """
        pitch_span = pitch_high - pitch_low + 1
        try:
            result = self._conn.query(
                "/live/clip/get/notes",
                track, clip,
                pitch_low, pitch_span,   # pitch_start, pitch_span
                start, length,           # time_start, time_span
            )
        except QueryTimeout:
            if pitch_high - pitch_low <= 1:
                raise  # can't split further — genuine failure
            mid = (pitch_low + pitch_high) // 2
            return (
                self.get_notes(track, clip, start, length, pitch_low, mid)
                + self.get_notes(track, clip, start, length, mid + 1, pitch_high)
            )
        return self._parse_notes_response(result)

    @staticmethod
    def _parse_notes_response(result) -> list[MidiNote]:
        """Parse AbletonOSC's flat note response.

        Format: [track, clip, pitch, start, dur, vel, mute, pitch, start, ...].
        """
        data = list(result)
        offset = 2 if len(data) > 2 else 0
        notes: list[MidiNote] = []
        i = offset
        while i + 4 < len(data):
            notes.append(MidiNote(
                pitch=int(data[i]),
                start_time=float(data[i + 1]),
                duration=float(data[i + 2]),
                velocity=int(data[i + 3]),
                mute=bool(data[i + 4]),
            ))
            i += 5
        return notes

    # ------------------------------------------------------------------
    # Writing notes
    # ------------------------------------------------------------------

    def add_notes(
        self,
        track: int,
        clip: int,
        notes: list[MidiNote],
        chunk_size: int = DEFAULT_NOTE_CHUNK,
    ) -> None:
        """Add MIDI notes to a clip, chunked across multiple OSC messages.

        AbletonOSC expects: /live/clip/add/notes track clip
            [pitch start dur vel mute] ...
        A single datagram with too many notes exceeds the OSC/UDP packet size
        and AbletonOSC drops it with no error surfaced, so we send in batches.
        """
        for batch_start in range(0, len(notes), chunk_size):
            batch = notes[batch_start:batch_start + chunk_size]
            args: list[object] = [track, clip]
            for n in batch:
                args.extend([n.pitch, n.start_time, n.duration, n.velocity, int(n.mute)])
            self._conn.send("/live/clip/add/notes", *args)

    def add_notes_verified(
        self,
        track: int,
        clip: int,
        notes: list[MidiNote],
        chunk_size: int = DEFAULT_NOTE_CHUNK,
    ) -> dict:
        """Add notes, then read them back and confirm they landed.

        Returns a verification dict: {written, found, match, missing, extra}.
        Identity is (pitch, start, duration) rounded — velocity/mute are not
        part of the structural check. This is the reliable write path: the
        agent learns whether a write actually succeeded instead of writing
        blind.
        """
        self.add_notes(track, clip, notes, chunk_size=chunk_size)
        if not notes:
            return {"written": 0, "found": 0, "match": True, "missing": [], "extra": []}

        span = max(n.start_time + n.duration for n in notes)
        found = self.get_notes(track, clip, 0.0, span + 1.0, 0, 127)
        return self._compare(notes, found)

    @staticmethod
    def _compare(expected: list[MidiNote], found: list[MidiNote]) -> dict:
        def key(n: MidiNote):
            return (n.pitch, round(n.start_time, 4), round(n.duration, 4))

        exp = Counter(key(n) for n in expected)
        got = Counter(key(n) for n in found)
        missing = exp - got
        extra = got - exp
        return {
            "written": len(expected),
            "found": len(found),
            "match": not missing and not extra,
            "missing": [list(k) for k in missing.elements()],
            "extra": [list(k) for k in extra.elements()],
        }

    def remove_notes(
        self,
        track: int,
        clip: int,
        start: float = 0.0,
        length: float = 128.0,
        pitch_low: int = 0,
        pitch_high: int = 127,
    ) -> None:
        """Remove notes in a time + pitch window.

        Same parameter order as get_notes: pitch_start, pitch_span,
        time_start, time_span.
        """
        pitch_span = pitch_high - pitch_low + 1
        self._conn.send(
            "/live/clip/remove/notes",
            track, clip,
            pitch_low, pitch_span,
            start, length,
        )

    def replace_notes(
        self, track: int, clip: int, notes: list[MidiNote],
        start: float = 0.0, length: float = 128.0,
        pitch_low: int = 0, pitch_high: int = 127,
    ) -> None:
        """Clear existing notes in range, then add new ones (chunked)."""
        self.remove_notes(track, clip, start, length, pitch_low, pitch_high)
        if notes:
            self.add_notes(track, clip, notes)
