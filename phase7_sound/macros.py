"""Virtual macro layer — "3 knobs not 30".

A macro is a named 0..1 "vibe knob" that drives several role-matched parameters
at once. Unlike intent moves (relative nudges), a macro is an ABSOLUTE,
reusable knob you can sweep: at value v each target parameter is set to
lerp(low, high, v) in normalized space, then through the verified-set path.

Macros are defined over semantic ROLES (filter_cutoff, reverb_wet, …), so the
same macro auto-fits whatever a track actually has — `design_macros` returns
only the macros with at least one matching parameter. Built entirely in
BlessDog (no dependency on Ableton's Rack macros, which AbletonOSC can't create)
so it works on any track and stays testable.
"""

from __future__ import annotations

from dataclasses import dataclass

from phase1_osc.devices import Devices

from .params import ParamMatch, by_role


@dataclass
class MacroTarget:
    role: str
    low: float   # normalized param value when the macro is at 0.0
    high: float  # normalized param value when the macro is at 1.0


@dataclass
class Macro:
    name: str
    description: str
    targets: list[MacroTarget]


# Role-based macro designs. low/high are normalized (0..1) endpoints; a target
# can invert (low > high) — e.g. warmth lowers the filter as it rises.
_MACRO_DESIGNS: dict[str, tuple[str, list[tuple[str, float, float]]]] = {
    "brightness": ("opens the filter and lifts the highs", [
        ("filter_cutoff", 0.15, 0.95),
        ("high_shelf", 0.40, 0.85),
    ]),
    "space": ("adds reverb and delay for depth", [
        ("reverb_wet", 0.0, 0.70),
        ("delay_wet", 0.0, 0.50),
        ("mod_wet", 0.0, 0.45),
    ]),
    "energy": ("more drive, resonance and openness — pushes intensity", [
        ("drive", 0.10, 0.80),
        ("filter_reso", 0.20, 0.70),
        ("filter_cutoff", 0.35, 0.90),
    ]),
    "warmth": ("rolls off highs and adds gentle drive", [
        ("filter_cutoff", 0.85, 0.40),   # inverts: rises -> darker
        ("drive", 0.10, 0.55),
        ("high_shelf", 0.70, 0.30),
    ]),
}


def design_macros(matches: list[ParamMatch]) -> list[Macro]:
    """Return the macros that have at least one matching parameter on the track."""
    grouped = by_role(matches)
    out: list[Macro] = []
    for name, (desc, spec) in _MACRO_DESIGNS.items():
        targets = [MacroTarget(role, lo, hi) for role, lo, hi in spec if role in grouped]
        if targets:
            out.append(Macro(name, desc, targets))
    return out


def find_macro(name: str, matches: list[ParamMatch]) -> Macro | None:
    key = name.lower().strip()
    return next((m for m in design_macros(matches) if m.name == key), None)


def available_macros() -> list[str]:
    return sorted(_MACRO_DESIGNS)


def _lerp(low: float, high: float, t: float) -> float:
    return low + (high - low) * t


def apply_macro(
    devices: Devices, macro: Macro, matches: list[ParamMatch], value: float
) -> dict:
    """Set every parameter the macro targets to its position at `value` (0..1).

    Verified per-param, with an undo snapshot of prior raw values.
    """
    value = max(0.0, min(1.0, value))
    grouped = by_role(matches)

    changes: list[dict] = []
    undo: list[dict] = []
    for tgt in macro.targets:
        norm = _lerp(tgt.low, tgt.high, value)
        for m in grouped.get(tgt.role, []):
            raw = Devices.normalize_to_raw(m.info, norm)
            verify = devices.set_parameter_verified(
                m.track_index, m.device_index, m.param_index, raw)
            changes.append({
                "device": m.device_name,
                "param": m.info.name,
                "role": m.role,
                "to_normalized": round(norm, 3),
                "to": round(raw, 4),
                "display": verify.get("display", ""),
                "ok": verify.get("match", False),
            })
            undo.append({
                "track_index": m.track_index,
                "device_index": m.device_index,
                "param_index": m.param_index,
                "value": m.info.value,
            })

    return {
        "macro": macro.name,
        "value": value,
        "changed": len(changes),
        "changes": changes,
        "undo": undo,
    }
