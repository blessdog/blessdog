"""Device enumeration and parameter control."""

from __future__ import annotations

from .connection import AbletonOSCConnection
from .errors import DeviceNotFound
from .types import DeviceInfo, ParameterInfo


class Devices:
    def __init__(self, conn: AbletonOSCConnection):
        self._conn = conn

    def count(self, track: int) -> int:
        result = self._conn.query("/live/track/get/num_devices", track)
        return int(result[-1])

    def get_names(self, track: int) -> list[str]:
        result = self._conn.query("/live/track/get/device_names", track)
        # First element may be track index
        names = result[1:] if len(result) > 1 and isinstance(result[0], int) else result
        return [str(n) for n in names]

    def get_info(self, track: int, device: int) -> DeviceInfo:
        name = self._conn.query("/live/device/get/name", track, device)
        class_name = self._conn.query("/live/device/get/class_name", track, device)
        return DeviceInfo(
            track_index=track,
            device_index=device,
            name=str(name[-1]),
            class_name=str(class_name[-1]),
        )

    def get_parameters(self, track: int, device: int) -> list[ParameterInfo]:
        """Get all parameter names and values for a device.

        AbletonOSC returns flat: [track, device, name0, val0, min0, max0, name1, val1, ...]
        The exact format varies — we parse name/value pairs.
        """
        names_result = self._conn.query(
            "/live/device/get/parameters/name", track, device
        )
        values_result = self._conn.query(
            "/live/device/get/parameters/value", track, device
        )

        # Strip leading track/device indices
        names = list(names_result)
        values = list(values_result)
        if names and isinstance(names[0], int):
            names = names[2:]  # skip track, device
        if values and isinstance(values[0], int):
            values = values[2:]  # skip track, device

        params = []
        for i, name in enumerate(names):
            val = float(values[i]) if i < len(values) else 0.0
            params.append(ParameterInfo(
                index=i,
                name=str(name),
                value=val,
            ))
        return params

    def get_parameter_value(self, track: int, device: int, param: int) -> float:
        result = self._conn.query(
            "/live/device/get/parameter/value", track, device, param
        )
        return float(result[-1])

    def set_parameter_value(
        self, track: int, device: int, param: int, value: float
    ) -> None:
        self._conn.send(
            "/live/device/set/parameter/value", track, device, param, value
        )

    def get_parameter_display(self, track: int, device: int, param: int) -> str:
        result = self._conn.query(
            "/live/device/get/parameter/value_string", track, device, param
        )
        return str(result[-1])

    def _validate(self, track: int, device: int) -> None:
        num = self.count(track)
        if device < 0 or device >= num:
            raise DeviceNotFound(
                f"Device {device} not found on track {track} (have {num})"
            )
