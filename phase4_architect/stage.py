"""Stage a Live Set so composed parts are actually audible.

The composition engine writes correct MIDI, but notes only make sound if they
land on a MIDI track that has an instrument. A generic Set may have too few
MIDI tracks (or audio tracks where you expected MIDI), and empty tracks make no
sound. `stage_roles` closes that gap: given the musical roles you're about to
write, it guarantees each one a MIDI track with an instrument — creating tracks
and loading instruments only where missing — and returns the role→track map.

Idempotent: re-running reuses existing instrumented MIDI tracks instead of
piling on duplicates.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from phase4_architect.loader import Loader

# Which instrument to load for a role when a track has none. Wavetable plays any
# pitch and makes sound on its default preset, so it's the reliable choice for
# melodic roles; drums want a Drum Rack.
INSTRUMENT_FOR_ROLE: dict[str, str] = {
    "chords": "Wavetable",
    "pad": "Wavetable",
    "bass": "Wavetable",
    "sub": "Wavetable",
    "arp": "Wavetable",
    "melody": "Wavetable",
    "lead": "Wavetable",
    "drums": "Drum Rack",
}


@dataclass
class StagedTrack:
    role: str
    track_index: int
    instrument: str
    created_track: bool       # we made a new MIDI track for this role
    loaded_instrument: bool   # we loaded the instrument (vs. one already there)


def _midi_track_indices(bridge) -> list[int]:
    n = bridge.tracks.count()
    return [i for i in range(n) if bridge.tracks.is_midi(i)]


def stage_roles(
    bridge,
    roles: list[str],
    *,
    instrument_for_role: dict[str, str] | None = None,
) -> list[StagedTrack]:
    """Ensure each role in `roles` has a MIDI track with an instrument.

    Existing instrumented MIDI tracks are reused in order; missing MIDI tracks
    are created; empty MIDI tracks get their role's instrument loaded. Returns
    one StagedTrack per role, in the same order.
    """
    inst_map = {**INSTRUMENT_FOR_ROLE, **(instrument_for_role or {})}
    loader = Loader(bridge.view, bridge.browser)

    midi_tracks = _midi_track_indices(bridge)
    staged: list[StagedTrack] = []

    for slot, role in enumerate(roles):
        created = False
        if slot < len(midi_tracks):
            track = midi_tracks[slot]
        else:
            # No spare MIDI track — append one. create_midi_track(-1) adds at the
            # end; re-scan to learn its index (and let Live register it).
            bridge.tracks.create_midi_track(-1)
            time.sleep(0.15)
            midi_tracks = _midi_track_indices(bridge)
            track = midi_tracks[slot]
            created = True

        instrument = inst_map.get(role, "Wavetable")
        loaded = False
        if not bridge.tracks.device_names(track):
            result = loader.load_device(track, instrument)
            loaded = result.success
            if result.success:
                instrument = result.device_name

        staged.append(StagedTrack(
            role=role,
            track_index=track,
            instrument=instrument,
            created_track=created,
            loaded_instrument=loaded,
        ))

    return staged
