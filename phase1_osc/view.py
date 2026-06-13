"""View state — track/scene/clip/device selection in Ableton's UI."""

from __future__ import annotations

from .connection import AbletonOSCConnection


class View:
    def __init__(self, conn: AbletonOSCConnection):
        self._conn = conn

    def get_selected_track(self) -> int:
        result = self._conn.query("/live/view/get/selected_track")
        return int(result[0])

    def set_selected_track(self, index: int) -> None:
        self._conn.send("/live/view/set/selected_track", index)

    def get_selected_scene(self) -> int:
        result = self._conn.query("/live/view/get/selected_scene")
        return int(result[0])

    def set_selected_scene(self, index: int) -> None:
        self._conn.send("/live/view/set/selected_scene", index)

    def get_selected_clip(self) -> tuple[int, int]:
        result = self._conn.query("/live/view/get/selected_clip")
        return int(result[0]), int(result[1])

    def set_selected_clip(self, track_index: int, scene_index: int) -> None:
        self._conn.send("/live/view/set/selected_clip", track_index, scene_index)

    def get_selected_device(self) -> tuple[int, int]:
        result = self._conn.query("/live/view/get/selected_device")
        return int(result[0]), int(result[1])

    def set_selected_device(self, track_index: int, device_index: int) -> None:
        self._conn.send("/live/view/set/selected_device", track_index, device_index)
