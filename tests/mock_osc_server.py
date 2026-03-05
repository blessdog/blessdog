"""Fake AbletonOSC server for offline testing.

Responds to known OSC addresses with canned data, mimicking
AbletonOSC's response format.
"""

from __future__ import annotations

import threading
from typing import Any

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient

# Canned responses: address → response args
# AbletonOSC sends responses back to the caller on port 11001
# We flip it: mock listens on 11000, responds on 11001
CANNED_RESPONSES: dict[str, tuple] = {
    "/live/test": ("ok",),
    "/live/song/get/tempo": (120.0,),
    "/live/song/get/is_playing": (0,),
    "/live/song/get/current_song_time": (0.0,),
    "/live/song/get/loop": (1,),
    "/live/song/get/loop_start": (0.0,),
    "/live/song/get/loop_length": (8.0,),
    "/live/song/get/record_mode": (0,),
    "/live/song/get/num_tracks": (4,),
    "/live/song/get/num_scenes": (8,),
    "/live/song/get/track_names": ("Bass", "Drums", "Keys", "Vox"),
    "/live/song/get/scene_names": (
        "Intro", "Verse", "Chorus", "Bridge",
        "Verse 2", "Chorus 2", "Outro", "",
    ),
    # Track queries — responses include track index prefix
    "/live/track/get/name": None,  # dynamic
    "/live/track/get/volume": None,
    "/live/track/get/panning": None,
    "/live/track/get/mute": None,
    "/live/track/get/solo": None,
    "/live/track/get/arm": None,
    "/live/track/get/sends": None,
    "/live/track/get/num_devices": None,
    "/live/track/get/device_names": None,
    # Device queries
    "/live/device/get/name": None,
    "/live/device/get/class_name": None,
    "/live/device/get/parameters/name": None,
    "/live/device/get/parameters/value": None,
    "/live/device/get/parameter/value": None,
    "/live/device/get/parameter/value_string": None,
}

# Per-track canned data
TRACK_DATA = [
    {"name": "Bass", "volume": 0.85, "panning": 0.0, "mute": 0, "solo": 0, "arm": 0,
     "sends": [0.0, 0.5], "num_devices": 2,
     "device_names": ["Simpler", "Auto Filter"]},
    {"name": "Drums", "volume": 0.9, "panning": 0.0, "mute": 0, "solo": 0, "arm": 0,
     "sends": [0.3, 0.0], "num_devices": 1,
     "device_names": ["Drum Rack"]},
    {"name": "Keys", "volume": 0.7, "panning": -0.2, "mute": 0, "solo": 0, "arm": 1,
     "sends": [0.2, 0.4], "num_devices": 1,
     "device_names": ["Wavetable"]},
    {"name": "Vox", "volume": 0.95, "panning": 0.1, "mute": 1, "solo": 0, "arm": 0,
     "sends": [0.6, 0.3], "num_devices": 0,
     "device_names": []},
]

DEVICE_DATA = {
    (0, 0): {"name": "Simpler", "class_name": "OriginalSimpler",
             "param_names": ["Device On", "Volume", "Attack", "Decay"],
             "param_values": [1.0, 0.8, 0.01, 0.3]},
    (0, 1): {"name": "Auto Filter", "class_name": "AutoFilter",
             "param_names": ["Device On", "Frequency", "Resonance"],
             "param_values": [1.0, 800.0, 0.5]},
    (1, 0): {"name": "Drum Rack", "class_name": "DrumGroupDevice",
             "param_names": ["Device On"],
             "param_values": [1.0]},
    (2, 0): {"name": "Wavetable", "class_name": "InstrumentVector",
             "param_names": ["Device On", "Osc 1 Shape", "Filter Freq", "Volume"],
             "param_values": [1.0, 0.5, 0.7, 0.85]},
}


class MockAbletonOSC:
    """Fake AbletonOSC that listens on a configurable port and responds."""

    def __init__(self, listen_port: int = 11000, response_port: int = 11001,
                 host: str = "127.0.0.1"):
        self.host = host
        self.listen_port = listen_port
        self.response_port = response_port
        self._server: ThreadingOSCUDPServer | None = None
        self._thread: threading.Thread | None = None
        self._client: SimpleUDPClient | None = None

    def start(self) -> None:
        self._client = SimpleUDPClient(self.host, self.response_port)

        dispatcher = Dispatcher()
        dispatcher.set_default_handler(self._handle)

        self._server = ThreadingOSCUDPServer(
            (self.host, self.listen_port), dispatcher
        )
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None
        self._thread = None
        self._client = None

    def _handle(self, address: str, *args: Any) -> None:
        response = self._resolve(address, args)
        if response is not None:
            self._client.send_message(address, list(response))

    def _resolve(self, address: str, args: tuple) -> tuple | None:
        # Static responses
        if address in CANNED_RESPONSES and CANNED_RESPONSES[address] is not None:
            return CANNED_RESPONSES[address]

        # Track-level queries
        if address.startswith("/live/track/get/"):
            prop = address.split("/live/track/get/")[1]
            if args and isinstance(args[0], (int, float)):
                track_idx = int(args[0])
                if 0 <= track_idx < len(TRACK_DATA):
                    td = TRACK_DATA[track_idx]
                    if prop == "name":
                        return (track_idx, td["name"])
                    elif prop == "volume":
                        return (track_idx, td["volume"])
                    elif prop == "panning":
                        return (track_idx, td["panning"])
                    elif prop == "mute":
                        return (track_idx, td["mute"])
                    elif prop == "solo":
                        return (track_idx, td["solo"])
                    elif prop == "arm":
                        return (track_idx, td["arm"])
                    elif prop == "sends":
                        return (track_idx, *td["sends"])
                    elif prop == "num_devices":
                        return (track_idx, td["num_devices"])
                    elif prop == "device_names":
                        return (track_idx, *td["device_names"])
            return None

        # Device-level queries
        if address.startswith("/live/device/get/"):
            prop = address.split("/live/device/get/")[1]
            if len(args) >= 2:
                key = (int(args[0]), int(args[1]))
                dd = DEVICE_DATA.get(key)
                if dd:
                    if prop == "name":
                        return (*key, dd["name"])
                    elif prop == "class_name":
                        return (*key, dd["class_name"])
                    elif prop == "parameters/name":
                        return (*key, *dd["param_names"])
                    elif prop == "parameters/value":
                        return (*key, *dd["param_values"])
                    elif prop == "parameter/value" and len(args) >= 3:
                        pi = int(args[2])
                        if pi < len(dd["param_values"]):
                            return (*key, pi, dd["param_values"][pi])
                    elif prop == "parameter/value_string" and len(args) >= 3:
                        pi = int(args[2])
                        if pi < len(dd["param_values"]):
                            return (*key, pi, str(dd["param_values"][pi]))
            return None

        # Fire-and-forget commands — no response
        return None

    def __enter__(self) -> MockAbletonOSC:
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.stop()
