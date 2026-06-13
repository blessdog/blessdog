"""Tests for the virtual macro layer (phase7_sound.macros)."""

from __future__ import annotations

import pytest

from phase1_osc.devices import Devices
from phase1_osc.types import DeviceInfo, ParameterInfo
from phase7_sound import apply_macro, design_macros, find_macro, match_parameters


def _dev(name, klass, params):
    return DeviceInfo(
        track_index=0, device_index=0, name=name, class_name=klass,
        parameters=[
            ParameterInfo(index=i, name=pn, value=v, min_value=lo, max_value=hi)
            for i, (pn, v, lo, hi) in enumerate(params)
        ],
    )


def _filter_matches(freq=2000.0):
    devs = [_dev("Auto Filter", "AutoFilter", [
        ("Frequency", freq, 20.0, 20000.0),
        ("Resonance", 0.3, 0.0, 1.25),
    ])]
    return match_parameters(0, devs)


def _full_matches():
    devs = [
        _dev("Auto Filter", "AutoFilter", [
            ("Frequency", 2000.0, 20.0, 20000.0),
            ("Resonance", 0.3, 0.0, 1.25),
        ]),
        _dev("Reverb", "Reverb", [("Dry/Wet", 0.1, 0.0, 1.0)]),
    ]
    return match_parameters(0, devs)


class TestDesign:
    def test_only_applicable_macros(self):
        # Filter-only track: brightness/energy/warmth apply (filter_cutoff/reso),
        # but space (reverb/delay) does not.
        names = {m.name for m in design_macros(_filter_matches())}
        assert "brightness" in names
        assert "energy" in names
        assert "space" not in names

    def test_space_appears_with_reverb(self):
        names = {m.name for m in design_macros(_full_matches())}
        assert "space" in names

    def test_find_macro(self):
        assert find_macro("brightness", _filter_matches()).name == "brightness"
        assert find_macro("space", _filter_matches()) is None


class TestApply:
    @pytest.fixture
    def devices(self, conn, mock_server):
        mock_server._param_overrides.clear()
        return Devices(conn)

    def _live_filter_matches(self, devices):
        d = devices.get_info(0, 1)          # Auto Filter
        d.parameters = devices.get_parameters(0, 1)
        return match_parameters(0, [d])

    def test_value_endpoints_differ(self, devices):
        matches = self._live_filter_matches(devices)
        macro = find_macro("brightness", matches)

        apply_macro(devices, macro, matches, 0.0)
        low = devices.get_parameter_value(0, 1, 1)  # Frequency
        apply_macro(devices, macro, self._live_filter_matches(devices), 1.0)
        high = devices.get_parameter_value(0, 1, 1)
        assert high > low  # brightness up -> filter opens

    def test_warmth_inverts_cutoff(self, devices):
        matches = self._live_filter_matches(devices)
        macro = find_macro("warmth", matches)
        apply_macro(devices, macro, matches, 1.0)  # full warmth -> darker
        cutoff_norm = Devices.raw_to_normalized(
            ParameterInfo(0, "Frequency", 0, 20.0, 20000.0),
            devices.get_parameter_value(0, 1, 1))
        assert cutoff_norm == pytest.approx(0.40, abs=0.02)  # warmth high endpoint

    def test_apply_reports_and_snapshots(self, devices):
        matches = self._live_filter_matches(devices)
        macro = find_macro("energy", matches)
        result = apply_macro(devices, macro, matches, 0.7)
        assert result["changed"] >= 1
        assert all(c["ok"] for c in result["changes"])
        assert len(result["undo"]) == result["changed"]

    def test_pure_lerp_endpoints(self):
        from phase7_sound.macros import _lerp
        assert _lerp(0.2, 0.9, 0.0) == pytest.approx(0.2)
        assert _lerp(0.2, 0.9, 1.0) == pytest.approx(0.9)
        assert _lerp(0.2, 0.9, 0.5) == pytest.approx(0.55)
