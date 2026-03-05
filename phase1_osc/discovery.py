"""Session discovery — full structure snapshots for the agent."""

from __future__ import annotations

from .connection import AbletonOSCConnection
from .devices import Devices
from .scenes import Scenes
from .tracks import Tracks
from .transport import Transport
from .types import SessionStructure, TrackInfo


class Discovery:
    def __init__(self, conn: AbletonOSCConnection):
        self._conn = conn
        self._transport = Transport(conn)
        self._tracks = Tracks(conn)
        self._scenes = Scenes(conn)
        self._devices = Devices(conn)

    def get_session_structure(self) -> SessionStructure:
        """Complete snapshot of the current Live Set."""
        state = self._transport.get_state()
        track_names = self._tracks.get_names()
        scene_names = self._scenes.get_names()

        # Return track count
        result = self._conn.query("/live/song/get/num_tracks")
        num_tracks = int(result[0])

        tracks = [
            TrackInfo(index=i, name=name)
            for i, name in enumerate(track_names)
        ]

        return SessionStructure(
            tempo=state.tempo,
            time_signature_num=state.time_signature_num,
            time_signature_den=state.time_signature_den,
            track_count=num_tracks,
            scene_count=len(scene_names),
            return_track_count=0,
            tracks=tracks,
            scene_names=scene_names,
        )

    def get_track_with_devices(self, track_index: int) -> TrackInfo:
        """Detailed track info including all devices and parameters."""
        info = self._tracks.get_info(track_index)

        device_count = self._devices.count(track_index)
        for d in range(device_count):
            device = self._devices.get_info(track_index, d)
            device.parameters = self._devices.get_parameters(track_index, d)
            info.devices.append(device)

        info.sends = self._tracks.get_sends(track_index)
        return info
