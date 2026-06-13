#!/usr/bin/env python3
"""Live demo of the composition engine — lays down a melodic-house loop.

Prereqs: Ableton Live running with the AbletonOSC control surface enabled, and
a Live Set with at least 3 MIDI tracks that have instruments (run the MCP
build_session("dark_melodic_techno") first, or load a Wavetable/Operator/Drum
Rack yourself). Then:

    .venv/bin/python -m scripts.demo_compose --key F# --mode minor --bars 4

It writes chords/bass/drums into scene 0, verifies each write landed in-key,
prints a report, and (unless --no-fire) fires the scene so you hear it.
"""

from __future__ import annotations

import argparse
import json

from phase2_agent.bridge import AbletonBridge
from phase6_compose import MusicalContext, build_part, lint


# (role, track_index, options) — tweak track indices to match your Set.
PLAN = [
    ("chords", 1, {"octave": 4, "size": 4, "rhythm": "whole"}),
    ("bass", 0, {"octave": 2, "pattern": "root_octave", "rhythm": "8th"}),
    ("drums", 2, {}),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--key", default="F#")
    ap.add_argument("--mode", default="minor")
    ap.add_argument("--bars", type=int, default=4)
    ap.add_argument("--degrees", default="1,6,4,5",
                    help="scale degrees, comma-separated (e.g. 1,6,4,5)")
    ap.add_argument("--scene", type=int, default=0)
    ap.add_argument("--tempo", type=float, default=122.0)
    ap.add_argument("--no-fire", action="store_true", help="write but don't play")
    args = ap.parse_args()

    degrees = [int(d) for d in args.degrees.split(",")]
    ctx = MusicalContext(key=args.key, mode=args.mode, tempo=args.tempo)
    clip_length = args.bars * ctx.beats_per_bar

    bridge = AbletonBridge()
    bridge.ensure_connected()
    print(f"Connected. Tempo -> {args.tempo}, key {args.key} {args.mode}, "
          f"{args.bars} bars, degrees {degrees}\n")
    bridge.transport.set_tempo(args.tempo)

    for role, track, options in PLAN:
        notes = build_part(role, ctx, degrees=degrees, bars=args.bars, **options)
        report = lint(notes, ctx, clip_length, check_key=(role != "drums"))

        bridge.clips.create(track, args.scene, clip_length)
        bridge.clips.remove_notes(track, args.scene, 0.0, clip_length, 0, 127)
        verify = bridge.clips.add_notes_verified(track, args.scene, notes)

        status = "OK" if (report["ok"] and verify["match"]) else "CHECK"
        print(f"[{status}] {role:7} track {track}: {len(notes)} notes  "
              f"lint_ok={report['ok']}  landed={verify['found']}/{verify['written']}")
        if not report["ok"]:
            print("   lint issues:", json.dumps(report["issues"][:3]))
        if not verify["match"]:
            print("   verify miss:", json.dumps({k: verify[k] for k in ("missing", "extra")}))

    if not args.no_fire:
        print(f"\nFiring scene {args.scene} — listen!")
        bridge.scenes.fire(args.scene)

    bridge.disconnect()


if __name__ == "__main__":
    main()
