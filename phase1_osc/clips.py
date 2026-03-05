"""Clip management — fire, stop, create, MIDI note read/write."""

from __future__ import annotations

from .connection import AbletonOSCConnection
from .types import ClipInfo, MidiNote


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

    def create(self, track: int, clip: int, length: float = 4.0) -> None:
        self._conn.send("/live/clip_slot/create_clip", track, clip, length)

    def delete(self, track: int, clip: int) -> None:
        self._conn.send("/live/clip_slot/delete_clip", track, clip)

    def get_notes(
        self,
        track: int,
        clip: int,
        start: float = 0.0,
        length: float = 128.0,
        pitch_low: int = 0,
        pitch_high: int = 127,
    ) -> list[MidiNote]:
        """Read MIDI notes from a clip.

        AbletonOSC returns flat list:
        [track, clip, pitch, start, dur, vel, mute, pitch, start, dur, vel, mute, ...]
        """
        result = self._conn.query(
            "/live/clip/get/notes",
            track, clip,
            start, length,
            pitch_low, pitch_high,
        )
        # Skip the leading track and clip indices
        data = list(result)
        offset = 2 if len(data) > 2 else 0
        notes = []
        i = offset
        while i + 4 < len(data):
            notes.append(MidiNote(
                pitch=int(data[i]),
                start_time=float(data[i + 1]),
                duration=float(data[i + 2]),
                velocity=int(data[i + 3]),
                mute=bool(data[i + 4]) if i + 4 < len(data) else False,
            ))
            i += 5
        return notes

    def add_notes(self, track: int, clip: int, notes: list[MidiNote]) -> None:
        """Add MIDI notes to a clip.

        AbletonOSC expects: /live/clip/add/notes track clip
            [pitch start dur vel mute] ...
        """
        args: list = [track, clip]
        for n in notes:
            args.extend([n.pitch, n.start_time, n.duration, n.velocity, int(n.mute)])
        self._conn.send("/live/clip/add/notes", *args)

    def remove_notes(
        self,
        track: int,
        clip: int,
        start: float = 0.0,
        length: float = 128.0,
        pitch_low: int = 0,
        pitch_high: int = 127,
    ) -> None:
        self._conn.send(
            "/live/clip/remove/notes",
            track, clip,
            start, length,
            pitch_low, pitch_high,
        )

    def replace_notes(
        self, track: int, clip: int, notes: list[MidiNote],
        start: float = 0.0, length: float = 128.0,
        pitch_low: int = 0, pitch_high: int = 127,
    ) -> None:
        """Clear existing notes in range, then add new ones."""
        self.remove_notes(track, clip, start, length, pitch_low, pitch_high)
        if notes:
            self.add_notes(track, clip, notes)
