"""Track management — CRUD, volume, pan, mute, solo, arm, sends."""

from __future__ import annotations

from .connection import AbletonOSCConnection
from .errors import TrackNotFound
from .types import SendInfo, TrackInfo


class Tracks:
    def __init__(self, conn: AbletonOSCConnection):
        self._conn = conn

    def count(self) -> int:
        result = self._conn.query("/live/song/get/num_tracks")
        return int(result[0])

    def get_names(self) -> list[str]:
        result = self._conn.query("/live/song/get/track_names")
        return list(result)

    def get_info(self, index: int) -> TrackInfo:
        self._validate_index(index)
        name_result = self._conn.query("/live/track/get/name", index)
        vol_result = self._conn.query("/live/track/get/volume", index)
        pan_result = self._conn.query("/live/track/get/panning", index)
        mute_result = self._conn.query("/live/track/get/mute", index)
        solo_result = self._conn.query("/live/track/get/solo", index)
        arm_result = self._conn.query("/live/track/get/arm", index)

        return TrackInfo(
            index=index,
            name=str(name_result[-1]),
            volume=float(vol_result[-1]),
            panning=float(pan_result[-1]),
            mute=bool(mute_result[-1]),
            solo=bool(solo_result[-1]),
            arm=bool(arm_result[-1]),
        )

    def get_all(self) -> list[TrackInfo]:
        names = self.get_names()
        return [
            TrackInfo(index=i, name=name)
            for i, name in enumerate(names)
        ]

    def set_volume(self, index: int, value: float) -> None:
        self._conn.send("/live/track/set/volume", index, value)

    def set_panning(self, index: int, value: float) -> None:
        self._conn.send("/live/track/set/panning", index, value)

    def set_mute(self, index: int, on: bool) -> None:
        self._conn.send("/live/track/set/mute", index, int(on))

    def set_solo(self, index: int, on: bool) -> None:
        self._conn.send("/live/track/set/solo", index, int(on))

    def set_arm(self, index: int, on: bool) -> None:
        self._conn.send("/live/track/set/arm", index, int(on))

    def set_send(self, track_index: int, send_index: int, value: float) -> None:
        self._conn.send("/live/track/set/send", track_index, send_index, value)

    def get_send(self, track_index: int, send_index: int) -> float:
        result = self._conn.query("/live/track/get/send", track_index, send_index)
        return float(result[-1])

    def get_sends(self, track_index: int) -> list[SendInfo]:
        result = self._conn.query("/live/track/get/sends", track_index)
        # AbletonOSC returns flat list: [track_index, val0, val1, ...]
        values = result[1:] if len(result) > 1 else result
        return [
            SendInfo(index=i, name=f"Send {chr(65 + i)}", value=float(v))
            for i, v in enumerate(values)
        ]

    def create_midi_track(self, index: int = -1) -> None:
        self._conn.send("/live/song/create_midi_track", index)

    def create_audio_track(self, index: int = -1) -> None:
        self._conn.send("/live/song/create_audio_track", index)

    def delete(self, index: int) -> None:
        self._conn.send("/live/song/delete_track", index)

    def _validate_index(self, index: int) -> None:
        num = self.count()
        if index < 0 or index >= num:
            raise TrackNotFound(f"Track {index} not found (have {num} tracks)")
