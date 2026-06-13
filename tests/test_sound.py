"""Tests for phase7_sound: semantic parameter matching and intent moves."""

from __future__ import annotations

import pytest

from phase1_osc.devices import Devices
from phase1_osc.types import DeviceInfo, ParameterInfo
from phase7_sound import (
    apply_move,
    apply_undo,
    match_parameters,
    plan_move,
    resolve_move,
)
from phase7_sound.params import device_kind, role_for


def _dev(name, klass, params):
    """params: list of (name, value, min, max, quant)."""
    return DeviceInfo(
        track_index=0, device_index=0, name=name, class_name=klass,
        parameters=[
            ParameterInfo(index=i, name=pn, value=v, min_value=lo, max_value=hi,
                          is_quantized=bool(q))
            for i, (pn, v, lo, hi, q) in enumerate(params)
        ],
    )


# ---------------------------------------------------------------------------
# Semantic matcher
# ---------------------------------------------------------------------------

class TestMatcher:
    def test_device_kind_detection(self):
        assert device_kind(_dev("Reverb", "Reverb", [])) == "reverb"
        assert device_kind(_dev("Echo", "Delay", [])) == "delay"
        assert device_kind(_dev("Auto Filter", "AutoFilter", [])) == "filter"
        assert device_kind(_dev("Wavetable", "InstrumentVector", [])) == "instrument"

    def test_drywet_role_depends_on_device(self):
        assert role_for("reverb", "Dry/Wet") == "reverb_wet"
        assert role_for("delay", "Dry/Wet") == "delay_wet"

    def test_filter_and_reso(self):
        assert role_for("filter", "Frequency") == "filter_cutoff"
        assert role_for("instrument", "Filter Freq") == "filter_cutoff"
        assert role_for("filter", "Resonance") == "filter_reso"

    def test_device_on_ignored(self):
        assert role_for("instrument", "Device On") is None

    def test_match_parameters_over_devices(self):
        devs = [
            _dev("Auto Filter", "AutoFilter", [
                ("Device On", 1, 0, 1, 1),
                ("Frequency", 800, 20, 20000, 0),
                ("Resonance", 0.5, 0, 1.25, 0),
            ]),
            _dev("Reverb", "Reverb", [
                ("Dry/Wet", 0.3, 0, 1, 0),
            ]),
        ]
        matches = match_parameters(0, devs)
        roles = {m.role for m in matches}
        assert roles == {"filter_cutoff", "filter_reso", "reverb_wet"}


# ---------------------------------------------------------------------------
# Move planning (pure)
# ---------------------------------------------------------------------------

class TestPlanMove:
    @pytest.fixture
    def matches(self):
        devs = [
            _dev("Auto Filter", "AutoFilter", [
                ("Frequency", 2000.0, 20.0, 20000.0, 0),  # norm ~0.099
            ]),
            _dev("Reverb", "Reverb", [
                ("Dry/Wet", 0.2, 0.0, 1.0, 0),
            ]),
        ]
        return match_parameters(0, devs)

    def test_brighter_raises_cutoff(self, matches):
        planned = plan_move("brighter", matches, amount="medium")
        cutoff = next(p for p in planned if p.match.role == "filter_cutoff")
        assert cutoff.new_norm > cutoff.old_norm
        assert cutoff.new_raw > 2000.0

    def test_darker_lowers_cutoff(self, matches):
        planned = plan_move("darker", matches, amount="medium")
        cutoff = next(p for p in planned if p.match.role == "filter_cutoff")
        assert cutoff.new_norm < cutoff.old_norm

    def test_dreamier_raises_reverb(self, matches):
        planned = plan_move("dreamier", matches, amount="strong")
        wet = next(p for p in planned if p.match.role == "reverb_wet")
        assert wet.new_raw > 0.2

    def test_aliases_resolve(self):
        assert resolve_move("aggressive")[0] == "more_drive"
        assert resolve_move("bright")[0] == "brighter"

    def test_unknown_intent_rejected(self, matches):
        with pytest.raises(ValueError):
            plan_move("spicy", matches)

    def test_amount_scales_delta(self, matches):
        subtle = plan_move("brighter", matches, "subtle")[0]
        strong = plan_move("brighter", matches, "strong")[0]
        assert (strong.new_norm - strong.old_norm) > (subtle.new_norm - subtle.old_norm)


# ---------------------------------------------------------------------------
# Move apply + undo (round-trip through the mock OSC server)
# ---------------------------------------------------------------------------

class TestApplyUndo:
    @pytest.fixture
    def devices(self, conn, mock_server):
        mock_server._param_overrides.clear()
        return Devices(conn)

    def test_apply_then_undo_restores(self, devices):
        # Auto Filter on track 0, device 1: Frequency at 800 (index 1)
        devs = [devices.get_info(0, 1)]
        devs[0].parameters = devices.get_parameters(0, 1)
        matches = match_parameters(0, devs)

        before = devices.get_parameter_value(0, 1, 1)
        result = apply_move(devices, "brighter", matches, amount="strong")
        assert result["changed"] >= 1
        assert all(c["ok"] for c in result["changes"])
        after = devices.get_parameter_value(0, 1, 1)
        assert after > before  # cutoff rose

        undo = apply_undo(devices, result["undo"])
        assert undo["restored"] == result["changed"]
        assert devices.get_parameter_value(0, 1, 1) == pytest.approx(before)
