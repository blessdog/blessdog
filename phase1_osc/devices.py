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

    @staticmethod
    def _strip_prefix(result) -> list:
        """AbletonOSC prefixes bulk parameter responses with (track, device)."""
        data = list(result)
        return data[2:] if len(data) >= 2 and isinstance(data[0], int) else data

    def get_parameters(self, track: int, device: int) -> list[ParameterInfo]:
        """Get all parameters for a device, with names, values, ranges, and
        quantization flags.

        AbletonOSC exposes these as bulk getters, each prefixed by
        (track, device): parameters/name, /value, /min, /max, /is_quantized.
        Ranges are required to set a parameter safely or by a normalized amount.
        """
        names = self._strip_prefix(
            self._conn.query("/live/device/get/parameters/name", track, device))
        values = self._strip_prefix(
            self._conn.query("/live/device/get/parameters/value", track, device))
        mins = self._strip_prefix(
            self._conn.query("/live/device/get/parameters/min", track, device))
        maxs = self._strip_prefix(
            self._conn.query("/live/device/get/parameters/max", track, device))
        quant = self._strip_prefix(
            self._conn.query("/live/device/get/parameters/is_quantized", track, device))

        params = []
        for i, name in enumerate(names):
            params.append(ParameterInfo(
                index=i,
                name=str(name),
                value=float(values[i]) if i < len(values) else 0.0,
                min_value=float(mins[i]) if i < len(mins) else 0.0,
                max_value=float(maxs[i]) if i < len(maxs) else 1.0,
                is_quantized=bool(int(quant[i])) if i < len(quant) else False,
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
        """Set a raw parameter value (no clamping — escape hatch)."""
        self._conn.send(
            "/live/device/set/parameter/value", track, device, param, value
        )

    def get_parameter_display(self, track: int, device: int, param: int) -> str:
        result = self._conn.query(
            "/live/device/get/parameter/value_string", track, device, param
        )
        return str(result[-1])

    # ------------------------------------------------------------------
    # Safe / normalized parameter control
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_to_raw(info: ParameterInfo, norm: float) -> float:
        """Map a normalized 0..1 amount to the parameter's raw value.

        Quantized params snap to the nearest valid step. min==max is guarded.
        """
        norm = max(0.0, min(1.0, norm))
        span = info.max_value - info.min_value
        if abs(span) < 1e-9:
            return info.min_value
        raw = info.min_value + norm * span
        if info.is_quantized:
            raw = float(round(raw))
            raw = max(info.min_value, min(info.max_value, raw))
        return raw

    @staticmethod
    def raw_to_normalized(info: ParameterInfo, raw: float) -> float:
        """Inverse of normalize_to_raw — report a raw value as 0..1."""
        span = info.max_value - info.min_value
        if abs(span) < 1e-9:
            return 0.0
        return max(0.0, min(1.0, (raw - info.min_value) / span))

    def set_parameter_verified(
        self, track: int, device: int, param: int, raw: float
    ) -> dict:
        """Set a raw value, then read it back to confirm it landed.

        Read-back is the only confirmation AbletonOSC offers (no write-ack),
        same pattern as the verified note writes.
        """
        self.set_parameter_value(track, device, param, raw)
        actual = self.get_parameter_value(track, device, param)
        try:
            display = self.get_parameter_display(track, device, param)
        except Exception:
            display = ""
        return {
            "param": param,
            "requested": round(raw, 4),
            "actual": round(actual, 4),
            "display": display,
            "match": abs(actual - raw) < 1e-3,
        }

    def _validate(self, track: int, device: int) -> None:
        num = self.count(track)
        if device < 0 or device >= num:
            raise DeviceNotFound(
                f"Device {device} not found on track {track} (have {num})"
            )
