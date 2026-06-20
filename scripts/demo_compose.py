#!/usr/bin/env python3
"""Live demo of the composition engine — lays down an audible melodic-house loop.

Self-provisioning: it finds MIDI tracks (creating them if needed), loads an
instrument onto any that's empty, writes in-key/groovy parts, verifies each
write landed, and fires the scene so you HEAR it. No manual track setup needed —
just have Ableton running with AbletonOSC enabled. Then:

    .venv/bin/python -m scripts.demo_compose --key F# --mode minor --bars 4

Roles are assigned to MIDI tracks dynamically (no hardcoded indices), so it
works on whatever Set you have open.
"""

from __future__ import annotations

import argparse
import json

from phase2_agent.bridge import AbletonBridge
from phase4_architect.stage import stage_roles
from phase6_compose import MusicalContext, build_part, lint

# role -> generator options. Order here = order parts are assigned to MIDI tracks.
PLAN: list[tuple[str, dict]] = [
    ("chords", {"octave": 4, "size": 4, "rhythm": "whole"}),
    ("bass", {"octave": 2, "pattern": "root_octave", "rhythm": "8th"}),
    ("drums", {}),
]

# Drum voice maps. The default ("house") uses a clap on the backbeat — great on
# an electronic Drum Rack but usually silent on an acoustic kit (no clap pad).
# "acoustic" uses a snare (GM 38), which every acoustic kit has.
KITS: dict[str, dict | None] = {
    "house": None,  # generator's DEFAULT_KIT
    "acoustic": {
        "kick": ("euclid", 4, 16),
        "snare": ("steps", [4, 12]),
        "closed_hat": ("euclid", 11, 16),
        "open_hat": ("steps", [2, 6, 10, 14]),
    },
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--key", default="F#")
    ap.add_argument("--mode", default="minor")
    ap.add_argument("--bars", type=int, default=4)
    ap.add_argument("--degrees", default="1,6,4,5",
                    help="scale degrees, comma-separated (e.g. 1,6,4,5)")
    ap.add_argument("--scene", type=int, default=0)
    ap.add_argument("--tempo", type=float, default=122.0)
    ap.add_argument("--no-drums", action="store_true",
                    help="skip drums (an empty Drum Rack makes no sound)")
    ap.add_argument("--kit", choices=sorted(KITS), default="acoustic",
                    help="drum voice map: 'acoustic' (snare) or 'house' (clap)")
    ap.add_argument("--no-fire", action="store_true", help="write but don't play")
    args = ap.parse_args()

    degrees = [int(d) for d in args.degrees.split(",")]
    ctx = MusicalContext(key=args.key, mode=args.mode, tempo=args.tempo)
    clip_length = args.bars * ctx.beats_per_bar

    plan = [p for p in PLAN if not (args.no_drums and p[0] == "drums")]
    roles = [role for role, _ in plan]

    bridge = AbletonBridge()
    bridge.ensure_connected()
    print(f"Connected. Tempo -> {args.tempo}, key {args.key} {args.mode}, "
          f"{args.bars} bars, degrees {degrees}\n")
    bridge.transport.set_tempo(args.tempo)

    # 1) Make sure every part has a MIDI track with an instrument.
    print("Staging tracks...")
    staged = stage_roles(bridge, roles)
    for s in staged:
        note = []
        if s.created_track:
            note.append("created track")
        if s.loaded_instrument:
            note.append(f"loaded {s.instrument}")
        suffix = f"  ({', '.join(note)})" if note else f"  (reused, {s.instrument})"
        print(f"  {s.role:7} -> track {s.track_index}{suffix}")
    print()

    # 2) Compose, write (verified), per role.
    options = {role: dict(opts) for role, opts in plan}
    if "drums" in options and KITS[args.kit] is not None:
        options["drums"]["voices"] = KITS[args.kit]
    for s in staged:
        notes = build_part(s.role, ctx, degrees=degrees, bars=args.bars,
                           **options[s.role])
        report = lint(notes, ctx, clip_length, check_key=(s.role != "drums"))

        bridge.clips.create(s.track_index, args.scene, clip_length)
        bridge.clips.remove_notes(s.track_index, args.scene, 0.0, clip_length, 0, 127)
        verify = bridge.clips.add_notes_verified(s.track_index, args.scene, notes)

        status = "OK" if (report["ok"] and verify["match"]) else "CHECK"
        print(f"[{status}] {s.role:7} track {s.track_index}: {len(notes)} notes  "
              f"lint_ok={report['ok']}  landed={verify['found']}/{verify['written']}")
        if not report["ok"]:
            print("   lint issues:", json.dumps(report["issues"][:3]))
        if not verify["match"]:
            print("   verify miss:", json.dumps({k: verify[k] for k in ("missing", "extra")}))

    # 3) Play it.
    if not args.no_fire:
        print(f"\nFiring scene {args.scene} — listen!")
        bridge.scenes.fire(args.scene)

    bridge.disconnect()


if __name__ == "__main__":
    main()
