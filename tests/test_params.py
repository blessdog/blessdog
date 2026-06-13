"""Range-aware device parameter control: fetching min/max/quantized,
normalized<->raw mapping, and verified (read-back) sets."""

from __future__ import annotations

import pytest

from phase1_osc.devices import Devices
from phase1_osc.types import ParameterInfo


@pytest.fixture
def devices(conn, mock_server):
    mock_server._param_overrides.clear()
    return Devices(conn)


class TestGetParameters:
    def test_includes_ranges_and_quantization(self, devices):
        # Auto Filter on track 0, device 1: Device On (quantized), Frequency 20-20000
        params = devices.get_parameters(0, 1)
        by_name = {p.name: p for p in params}
        assert by_name["Frequency"].min_value == 20.0
        assert by_name["Frequency"].max_value == 20000.0
        assert by_name["Device On"].is_quantized is True
        assert by_name["Frequency"].is_quantized is False

    def test_indices_sequential(self, devices):
        params = devices.get_parameters(2, 0)  # Wavetable
        assert [p.index for p in params] == list(range(len(params)))


class TestNormalize:
    def test_normalize_to_raw_midpoint(self):
        info = ParameterInfo(index=1, name="Frequency", value=800.0,
                             min_value=20.0, max_value=20000.0)
        assert Devices.normalize_to_raw(info, 0.5) == pytest.approx(10010.0)

    def test_normalize_clamps(self):
        info = ParameterInfo(index=0, name="X", value=0, min_value=0.0, max_value=1.0)
        assert Devices.normalize_to_raw(info, 2.0) == 1.0
        assert Devices.normalize_to_raw(info, -1.0) == 0.0

    def test_quantized_rounds_to_step(self):
        # 5-position enum 0..4
        info = ParameterInfo(index=0, name="Mode", value=0,
                             min_value=0.0, max_value=4.0, is_quantized=True)
        assert Devices.normalize_to_raw(info, 0.4) == 2.0   # 0.4*4 = 1.6 -> 2
        assert Devices.normalize_to_raw(info, 0.0) == 0.0
        assert Devices.normalize_to_raw(info, 1.0) == 4.0

    def test_min_equals_max_guarded(self):
        info = ParameterInfo(index=0, name="Fixed", value=5, min_value=5.0, max_value=5.0)
        assert Devices.normalize_to_raw(info, 0.7) == 5.0

    def test_raw_to_normalized_inverse(self):
        info = ParameterInfo(index=1, name="Frequency", value=0,
                             min_value=20.0, max_value=20000.0)
        for norm in (0.0, 0.25, 0.5, 0.9, 1.0):
            raw = Devices.normalize_to_raw(info, norm)
            assert Devices.raw_to_normalized(info, raw) == pytest.approx(norm, abs=1e-6)


class TestVerifiedSet:
    def test_set_lands_and_verifies(self, devices):
        result = devices.set_parameter_verified(0, 1, 1, 5000.0)  # Auto Filter Frequency
        assert result["match"] is True
        assert result["actual"] == pytest.approx(5000.0)
        # And a subsequent read reflects the override
        assert devices.get_parameter_value(0, 1, 1) == pytest.approx(5000.0)

    def test_normalized_then_verify_roundtrip(self, devices):
        params = devices.get_parameters(0, 1)
        freq = next(p for p in params if p.name == "Frequency")
        raw = Devices.normalize_to_raw(freq, 0.25)  # 20 + 0.25*19980 = 5015
        result = devices.set_parameter_verified(0, 1, freq.index, raw)
        assert result["match"] is True
        # Re-fetch params; normalized value should reflect the set
        updated = devices.get_parameters(0, 1)[freq.index]
        assert Devices.raw_to_normalized(updated, updated.value) == pytest.approx(0.25, abs=1e-3)
