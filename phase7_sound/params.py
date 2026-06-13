"""Semantic parameter matcher — map Ableton device parameters to meaningful
sound roles (filter_cutoff, reverb_wet, drive, …) so intent can target them.

Pure: takes DeviceInfo objects (with .parameters populated by
Devices.get_parameters) and returns role matches. Keyword-based and device-kind
aware — a "Dry/Wet" knob is reverb on a Reverb but delay on a Delay. It degrades
gracefully: unmatched params are simply not returned (callers still see them via
inspect_device for manual control).
"""

from __future__ import annotations

from dataclasses import dataclass

from phase1_osc.types import DeviceInfo, ParameterInfo

# Device name/class keyword -> kind. First match wins.
_DEVICE_KINDS: list[tuple[str, tuple[str, ...]]] = [
    ("reverb", ("reverb", "hall", "room")),
    ("delay", ("delay", "echo", "ping pong")),
    ("chorus", ("chorus", "flanger", "phaser", "ensemble")),
    ("filter", ("auto filter", "filter")),
    ("eq", ("eq ", "eq8", "eq eight", "channel eq", "equalizer")),
    ("saturator", ("saturator", "overdrive", "distortion", "amp", "drive")),
    ("compressor", ("compressor", "glue", "limiter")),
]


def device_kind(device: DeviceInfo) -> str:
    hay = f"{device.name} {device.class_name}".lower()
    for kind, keys in _DEVICE_KINDS:
        if any(k in hay for k in keys):
            return kind
    return "instrument"


@dataclass
class ParamMatch:
    track_index: int
    device_index: int
    param_index: int
    role: str
    device_name: str
    info: ParameterInfo


def role_for(kind: str, param_name: str) -> str | None:
    """Resolve a parameter name (in the context of its device kind) to a role."""
    p = param_name.lower().strip()

    if p in ("device on", "on"):
        return None

    # Wet / mix amount — meaning depends on the effect.
    if "dry/wet" in p or p == "wet" or p == "amount":
        return {"reverb": "reverb_wet", "delay": "delay_wet",
                "chorus": "mod_wet", "saturator": "drive"}.get(kind)

    if "feedback" in p:
        return "feedback"
    if "resonance" in p or p == "q" or p.endswith(" q"):
        return "filter_reso"
    if "cutoff" in p or "filter freq" in p or "filter frequency" in p:
        return "filter_cutoff"
    if p == "frequency" and kind in ("filter", "instrument"):
        return "filter_cutoff"
    if "drive" in p or "saturation" in p or "overdrive" in p or "distortion" in p:
        return "drive"
    if "pan" in p:
        return "pan"
    if "high" in p and "gain" in p:
        return "high_shelf"
    if "low" in p and "gain" in p:
        return "low_shelf"
    if "attack" in p:
        return "attack"
    if "release" in p:
        return "release"
    if ("volume" in p or p in ("gain", "level")) and kind in (
        "instrument", "compressor", "utility"
    ):
        return "volume"
    return None


def match_parameters(track_index: int, devices: list[DeviceInfo]) -> list[ParamMatch]:
    """Return all role matches across a track's devices."""
    matches: list[ParamMatch] = []
    for dev in devices:
        kind = device_kind(dev)
        for p in dev.parameters:
            role = role_for(kind, p.name)
            if role:
                matches.append(ParamMatch(
                    track_index=track_index,
                    device_index=dev.device_index,
                    param_index=p.index,
                    role=role,
                    device_name=dev.name,
                    info=p,
                ))
    return matches


def by_role(matches: list[ParamMatch]) -> dict[str, list[ParamMatch]]:
    grouped: dict[str, list[ParamMatch]] = {}
    for m in matches:
        grouped.setdefault(m.role, []).append(m)
    return grouped
