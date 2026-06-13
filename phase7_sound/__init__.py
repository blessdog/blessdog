"""phase7_sound — shape sound by intent, reliably.

The reliable foundation for the "stop twiddling knobs" half of BlessDog:
- params.py: map device parameters to semantic roles (filter_cutoff, reverb_wet…)
- moves.py: high-level intent verbs ("brighter", "dreamier") as relative,
  reversible nudges across matched params.

Built on the range-aware, verified parameter control in phase1_osc.devices.
Honest scope: intent moves are adjustable starting points (soft-timbre words are
approximate per 2026 research), always reported and always undoable — not exact
one-shots.
"""

from __future__ import annotations

from .moves import (
    apply_move,
    apply_undo,
    available_moves,
    plan_move,
    resolve_move,
)
from .params import ParamMatch, by_role, device_kind, match_parameters, role_for

__all__ = [
    "match_parameters",
    "by_role",
    "device_kind",
    "role_for",
    "ParamMatch",
    "plan_move",
    "apply_move",
    "apply_undo",
    "available_moves",
    "resolve_move",
]
