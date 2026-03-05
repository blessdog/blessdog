"""Transport control — play, stop, tempo, loop, record, undo."""

from __future__ import annotations

from .connection import AbletonOSCConnection
from .types import TransportState


class Transport:
    def __init__(self, conn: AbletonOSCConnection):
        self._conn = conn

    def play(self) -> None:
        self._conn.send("/live/song/start_playing")

    def stop(self) -> None:
        self._conn.send("/live/song/stop_playing")

    def continue_playing(self) -> None:
        self._conn.send("/live/song/continue_playing")

    def get_tempo(self) -> float:
        result = self._conn.query("/live/song/get/tempo")
        return float(result[0])

    def set_tempo(self, bpm: float) -> None:
        self._conn.send("/live/song/set/tempo", bpm)

    def get_is_playing(self) -> bool:
        result = self._conn.query("/live/song/get/is_playing")
        return bool(result[0])

    def get_time(self) -> float:
        result = self._conn.query("/live/song/get/current_song_time")
        return float(result[0])

    def set_time(self, beats: float) -> None:
        self._conn.send("/live/song/set/current_song_time", beats)

    def get_loop_on(self) -> bool:
        result = self._conn.query("/live/song/get/loop")
        return bool(result[0])

    def set_loop(self, on: bool) -> None:
        self._conn.send("/live/song/set/loop", int(on))

    def get_loop_start(self) -> float:
        result = self._conn.query("/live/song/get/loop_start")
        return float(result[0])

    def set_loop_start(self, beats: float) -> None:
        self._conn.send("/live/song/set/loop_start", beats)

    def get_loop_length(self) -> float:
        result = self._conn.query("/live/song/get/loop_length")
        return float(result[0])

    def set_loop_length(self, beats: float) -> None:
        self._conn.send("/live/song/set/loop_length", beats)

    def get_record_mode(self) -> bool:
        result = self._conn.query("/live/song/get/record_mode")
        return bool(result[0])

    def set_record_mode(self, on: bool) -> None:
        self._conn.send("/live/song/set/record_mode", int(on))

    def undo(self) -> None:
        self._conn.send("/live/song/undo")

    def redo(self) -> None:
        self._conn.send("/live/song/redo")

    def capture_midi(self) -> None:
        self._conn.send("/live/song/capture_midi")

    def trigger_record(self) -> None:
        """Start session record (triggers armed clips)."""
        self._conn.send("/live/song/trigger_session_record")

    def get_state(self) -> TransportState:
        """Snapshot of transport state."""
        return TransportState(
            is_playing=self.get_is_playing(),
            tempo=self.get_tempo(),
            song_time=self.get_time(),
            loop_on=self.get_loop_on(),
            loop_start=self.get_loop_start(),
            loop_length=self.get_loop_length(),
            record_mode=self.get_record_mode(),
        )
