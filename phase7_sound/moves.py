"""Intent moves — high-level verbs ("brighter", "dreamier") become relative
nudges across a track's matched parameters.

Honest by design (research: soft-timbre words are approximate): moves are
RELATIVE nudges, every change is reported, and every apply returns an undo
snapshot of the exact prior values so Ryan can audition and revert. These are
adjustable starting points, not exact one-shots.
"""

from __future__ import annotations

from dataclasses import dataclass

from phase1_osc.devices import Devices

from .params import ParamMatch, by_role

# Normalized delta per amount level.
AMOUNT = {"subtle": 0.1, "medium": 0.2, "strong": 0.35}

# Canonical move -> [(role, signed weight)]. Weight scales the normalized nudge.
_MOVES: dict[str, list[tuple[str, float]]] = {
    "brighter": [("filter_cutoff", 1.0), ("high_shelf", 0.6)],
    "darker": [("filter_cutoff", -1.0), ("high_shelf", -0.6)],
    "warmer": [("filter_cutoff", -0.4), ("drive", 0.5), ("high_shelf", -0.4)],
    "more_drive": [("drive", 1.0), ("filter_cutoff", 0.4), ("filter_reso", 0.4)],
    "softer": [("drive", -0.6), ("filter_cutoff", -0.3), ("volume", -0.2)],
    "wider": [("reverb_wet", 0.6), ("mod_wet", 0.6)],
    "dreamier": [("reverb_wet", 0.8), ("delay_wet", 0.5), ("filter_cutoff", -0.3)],
    "drier": [("reverb_wet", -0.8), ("delay_wet", -0.6)],
    "punchier": [("drive", 0.4), ("filter_reso", 0.3), ("reverb_wet", -0.3)],
    "louder": [("volume", 0.5)],
    "quieter": [("volume", -0.5)],
}

_ALIASES: dict[str, str] = {
    "aggressive": "more_drive", "harder": "more_drive", "dirtier": "more_drive",
    "spacious": "dreamier", "wetter": "dreamier", "more_space": "dreamier",
    "cleaner": "drier", "tighter": "punchier", "warm": "warmer",
    "bright": "brighter", "dark": "darker",
}


def available_moves() -> list[str]:
    return sorted(set(_MOVES) | set(_ALIASES))


def resolve_move(intent: str) -> tuple[str, list[tuple[str, float]]]:
    key = intent.lower().strip().replace("-", "_").replace(" ", "_")
    key = _ALIASES.get(key, key)
    if key not in _MOVES:
        raise ValueError(
            f"unknown intent {intent!r}; try one of {available_moves()}"
        )
    return key, _MOVES[key]


@dataclass
class PlannedChange:
    match: ParamMatch
    old_norm: float
    new_norm: float
    new_raw: float


def plan_move(
    intent: str, matches: list[ParamMatch], amount: str = "medium"
) -> list[PlannedChange]:
    """Pure: compute the param changes a move would make (no I/O)."""
    _, spec = resolve_move(intent)
    scale = AMOUNT.get(amount, 0.2)
    grouped = by_role(matches)
    planned: list[PlannedChange] = []
    for role, weight in spec:
        for m in grouped.get(role, []):
            old_norm = Devices.raw_to_normalized(m.info, m.info.value)
            new_norm = max(0.0, min(1.0, old_norm + weight * scale))
            new_raw = Devices.normalize_to_raw(m.info, new_norm)
            planned.append(PlannedChange(m, old_norm, new_norm, new_raw))
    return planned


def apply_move(
    devices: Devices, intent: str, matches: list[ParamMatch], amount: str = "medium"
) -> dict:
    """Apply a move, verifying each set and recording an undo snapshot."""
    key, _ = resolve_move(intent)
    planned = plan_move(intent, matches, amount)

    changes: list[dict] = []
    undo: list[dict] = []
    for pc in planned:
        m = pc.match
        verify = devices.set_parameter_verified(
            m.track_index, m.device_index, m.param_index, pc.new_raw)
        changes.append({
            "device": m.device_name,
            "param": m.info.name,
            "role": m.role,
            "from": round(m.info.value, 4),
            "to": round(pc.new_raw, 4),
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
        "intent": key,
        "amount": amount,
        "changed": len(changes),
        "changes": changes,
        "undo": undo,
    }


def apply_undo(devices: Devices, snapshot: list[dict]) -> dict:
    """Restore a snapshot recorded by apply_move."""
    results = []
    for s in snapshot:
        v = devices.set_parameter_verified(
            s["track_index"], s["device_index"], s["param_index"], s["value"])
        results.append({"param_index": s["param_index"],
                        "value": s["value"], "ok": v.get("match", False)})
    return {"restored": len(results), "results": results}
