"""SessionBuilder — execute a SessionTemplate to scaffold a full Ableton session."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from phase1_osc.tracks import Tracks
from phase1_osc.transport import Transport

from .loader import Loader, LoadResult
from .templates import SessionTemplate, TrackSpec


@dataclass
class TrackBuildResult:
    track_index: int
    name: str
    success: bool
    instrument_loaded: bool = False
    effects_loaded: list[str] = field(default_factory=list)
    effects_failed: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class SessionBuildResult:
    template_name: str
    success: bool
    tempo: float
    tracks_created: int
    tracks_failed: int
    track_results: list[TrackBuildResult] = field(default_factory=list)


class SessionBuilder:
    """Builds a full session from a SessionTemplate."""

    def __init__(self, tracks: Tracks, transport: Transport, loader: Loader):
        self._tracks = tracks
        self._transport = transport
        self._loader = loader

    def build(self, template: SessionTemplate) -> SessionBuildResult:
        """Execute a template to create a full session.

        Creates tracks, names them, colors them, loads instruments and effects.
        Handles partial failures gracefully — a track is still created even if
        device loading fails.
        """
        # Set tempo
        self._transport.set_tempo(template.tempo)

        track_results: list[TrackBuildResult] = []
        tracks_failed = 0

        for spec in template.tracks:
            result = self._build_track(spec)
            if not result.success:
                tracks_failed += 1
            track_results.append(result)

        return SessionBuildResult(
            template_name=template.name,
            success=tracks_failed == 0,
            tempo=template.tempo,
            tracks_created=len(track_results),
            tracks_failed=tracks_failed,
            track_results=track_results,
        )

    def _build_track(self, spec: TrackSpec) -> TrackBuildResult:
        """Create and configure a single track from a TrackSpec."""
        try:
            # Create the track (append at end)
            if spec.track_type == "midi":
                self._tracks.create_midi_track(-1)
            else:
                self._tracks.create_audio_track(-1)
            time.sleep(0.05)

            # The new track is at the end (before return tracks)
            track_count = self._tracks.count()
            track_index = track_count - 1

            # Name and color
            self._tracks.set_name(track_index, spec.name)
            self._tracks.set_color_index(track_index, spec.color_index)

            # Set volume
            if spec.volume != 0.85:
                self._tracks.set_volume(track_index, spec.volume)

            result = TrackBuildResult(
                track_index=track_index,
                name=spec.name,
                success=True,
            )

            # Load instrument
            if spec.instrument:
                load_result = self._loader.load_device(
                    track_index, spec.instrument,
                )
                result.instrument_loaded = load_result.success
                if not load_result.success:
                    result.error = load_result.error

            # Load effects
            for effect_name in spec.effects:
                load_result = self._loader.load_device(
                    track_index, effect_name, category="audio_effects",
                )
                if load_result.success:
                    result.effects_loaded.append(effect_name)
                else:
                    result.effects_failed.append(effect_name)

            return result

        except Exception as e:
            return TrackBuildResult(
                track_index=-1,
                name=spec.name,
                success=False,
                error=str(e),
            )
