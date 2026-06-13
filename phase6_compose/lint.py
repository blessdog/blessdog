"""Deterministic music-theory linting — catch off-key / out-of-bounds notes
before (and after) they hit Ableton. Cheap because we own the scale.
"""

from __future__ import annotations

from phase1_osc.types import MidiNote

from .theory import MusicalContext


def lint(
    notes: list[MidiNote],
    ctx: MusicalContext,
    clip_length: float,
    *,
    check_key: bool = True,
) -> dict:
    """Return {ok, count, issues:[{index, pitch, start, problem}, ...]}.

    check_key=False for drums (drum pitches are not scale degrees).
    """
    issues: list[dict] = []

    for i, n in enumerate(notes):
        if check_key and not ctx.is_in_key(n.pitch):
            issues.append({"index": i, "pitch": n.pitch, "start": n.start_time,
                           "problem": "off_key"})
        if n.start_time < -1e-6 or n.start_time >= clip_length:
            issues.append({"index": i, "pitch": n.pitch, "start": n.start_time,
                           "problem": "start_out_of_bounds"})
        if n.start_time + n.duration > clip_length + 1e-3:
            issues.append({"index": i, "pitch": n.pitch, "start": n.start_time,
                           "problem": "extends_past_clip"})
        if not 1 <= n.velocity <= 127:
            issues.append({"index": i, "pitch": n.pitch, "start": n.start_time,
                           "problem": "velocity_out_of_range"})
        if n.duration <= 0:
            issues.append({"index": i, "pitch": n.pitch, "start": n.start_time,
                           "problem": "non_positive_duration"})

    return {"ok": not issues, "count": len(notes), "issues": issues}
