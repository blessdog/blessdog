"""Tests for MCP tool functions against a mock bridge."""

from __future__ import annotations

import json
from dataclasses import asdict
from unittest.mock import MagicMock

import pytest

from phase1_osc.types import (
    ClipInfo,
    DeviceInfo,
    MidiNote,
    ParameterInfo,
    SendInfo,
    SessionStructure,
    TrackInfo,
    TransportState,
)

# Import tool functions — they're the unwrapped originals thanks to @wraps
from phase2_agent import server
from phase2_agent.server import (
    clip_edit_notes,
    clip_fire_stop,
    clip_manage,
    device_set_parameter,
    get_session,
    scene,
    set_loop,
    set_tempo,
    special_action,
    track_create_delete,
    track_get_info,
    track_set_mixer,
    transport_get_state,
    transport_play,
    transport_stop,
    undo_redo,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SESSION = SessionStructure(
    tempo=120.0,
    time_signature_num=4,
    time_signature_den=4,
    track_count=4,
    scene_count=8,
    return_track_count=0,
    tracks=[
        TrackInfo(index=0, name="Bass"),
        TrackInfo(index=1, name="Drums"),
    ],
    scene_names=["Intro", "Verse"],
)

SAMPLE_TRANSPORT = TransportState(
    is_playing=False,
    tempo=120.0,
    song_time=0.0,
    loop_on=True,
    loop_start=0.0,
    loop_length=8.0,
    record_mode=False,
)

SAMPLE_TRACK = TrackInfo(
    index=0,
    name="Bass",
    volume=0.85,
    panning=0.0,
    mute=False,
    solo=False,
    arm=False,
    devices=[
        DeviceInfo(
            track_index=0,
            device_index=0,
            name="Simpler",
            class_name="OriginalSimpler",
            parameters=[ParameterInfo(index=0, name="Volume", value=0.8)],
        )
    ],
    sends=[SendInfo(index=0, name="Send A", value=0.0)],
)

SAMPLE_CLIP = ClipInfo(
    track_index=0,
    clip_index=0,
    name="clip",
    length=4.0,
)

SAMPLE_NOTES = [
    MidiNote(pitch=60, start_time=0.0, duration=1.0, velocity=100, mute=False),
    MidiNote(pitch=64, start_time=1.0, duration=0.5, velocity=80, mute=False),
]


@pytest.fixture(autouse=True)
def mock_bridge(monkeypatch):
    """Replace the module-level bridge with a fully-mocked version."""
    b = MagicMock()
    b.connected = True

    # Discovery
    b.discovery.get_session_structure.return_value = SAMPLE_SESSION
    b.discovery.get_track_with_devices.return_value = SAMPLE_TRACK

    # Transport
    b.transport.get_state.return_value = SAMPLE_TRANSPORT

    # Clips
    b.clips.get_info.return_value = SAMPLE_CLIP
    b.clips.get_notes.return_value = SAMPLE_NOTES

    # Scenes (count used by validation in Phase 1 — not hit in MCP tools)
    monkeypatch.setattr(server, "bridge", b)
    return b


# ---------------------------------------------------------------------------
# Tool 1 — get_session
# ---------------------------------------------------------------------------

class TestGetSession:
    def test_returns_session_json(self):
        result = json.loads(get_session())
        assert result["tempo"] == 120.0
        assert result["track_count"] == 4
        assert len(result["tracks"]) == 2


# ---------------------------------------------------------------------------
# Tools 2–7 — Transport
# ---------------------------------------------------------------------------

class TestTransport:
    def test_get_state(self):
        result = json.loads(transport_get_state())
        assert result["tempo"] == 120.0
        assert result["is_playing"] is False

    def test_play(self, mock_bridge):
        result = json.loads(transport_play())
        assert result["status"] == "playing"
        mock_bridge.transport.play.assert_called_once()

    def test_stop(self, mock_bridge):
        result = json.loads(transport_stop())
        assert result["status"] == "stopped"
        mock_bridge.transport.stop.assert_called_once()

    def test_set_tempo(self, mock_bridge):
        result = json.loads(set_tempo(140.0))
        assert result["tempo"] == 140.0
        mock_bridge.transport.set_tempo.assert_called_once_with(140.0)

    def test_set_loop(self, mock_bridge):
        result = json.loads(set_loop(True, start=4.0, length=16.0))
        assert result["loop_on"] is True
        assert result["loop_start"] == 4.0
        assert result["loop_length"] == 16.0
        mock_bridge.transport.set_loop.assert_called_once_with(True)
        mock_bridge.transport.set_loop_start.assert_called_once_with(4.0)
        mock_bridge.transport.set_loop_length.assert_called_once_with(16.0)

    def test_set_loop_minimal(self, mock_bridge):
        result = json.loads(set_loop(False))
        assert result["loop_on"] is False
        assert "loop_start" not in result
        mock_bridge.transport.set_loop.assert_called_once_with(False)
        mock_bridge.transport.set_loop_start.assert_not_called()

    def test_undo(self, mock_bridge):
        result = json.loads(undo_redo("undo"))
        assert result["action"] == "undo"
        mock_bridge.transport.undo.assert_called_once()

    def test_redo(self, mock_bridge):
        result = json.loads(undo_redo("redo"))
        assert result["action"] == "redo"
        mock_bridge.transport.redo.assert_called_once()


# ---------------------------------------------------------------------------
# Tools 8–10 — Tracks
# ---------------------------------------------------------------------------

class TestTracks:
    def test_get_info(self):
        result = json.loads(track_get_info(0))
        assert result["name"] == "Bass"
        assert result["index"] == 0
        assert len(result["devices"]) == 1

    def test_set_mixer(self, mock_bridge):
        result = json.loads(track_set_mixer(0, volume=0.5, mute=True))
        assert result["track_index"] == 0
        assert result["volume"] == 0.5
        assert result["mute"] is True
        mock_bridge.tracks.set_volume.assert_called_once_with(0, 0.5)
        mock_bridge.tracks.set_mute.assert_called_once_with(0, True)
        mock_bridge.tracks.set_panning.assert_not_called()

    def test_create_midi(self, mock_bridge):
        result = json.loads(track_create_delete("create_midi", 2))
        assert result["action"] == "create_midi"
        mock_bridge.tracks.create_midi_track.assert_called_once_with(2)

    def test_delete_track(self, mock_bridge):
        result = json.loads(track_create_delete("delete", 1))
        assert result["action"] == "delete"
        mock_bridge.tracks.delete.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# Tools 11–13 — Clips
# ---------------------------------------------------------------------------

class TestClips:
    def test_fire(self, mock_bridge):
        result = json.loads(clip_fire_stop("fire", 0, 0))
        assert result["action"] == "fire"
        mock_bridge.clips.fire.assert_called_once_with(0, 0)

    def test_stop(self, mock_bridge):
        result = json.loads(clip_fire_stop("stop", 0, 0))
        assert result["action"] == "stop"
        mock_bridge.clips.stop.assert_called_once_with(0, 0)

    def test_get_info(self):
        result = json.loads(clip_manage("get_info", 0, 0))
        assert result["name"] == "clip"
        assert result["length"] == 4.0

    def test_create(self, mock_bridge):
        result = json.loads(clip_manage("create", 0, 0, length=8.0))
        assert result["action"] == "created"
        assert result["length"] == 8.0
        mock_bridge.clips.create.assert_called_once_with(0, 0, 8.0)

    def test_delete(self, mock_bridge):
        result = json.loads(clip_manage("delete", 0, 0))
        assert result["action"] == "deleted"
        mock_bridge.clips.delete.assert_called_once_with(0, 0)

    def test_get_notes(self):
        result = json.loads(clip_edit_notes("get", 0, 0))
        assert len(result) == 2
        assert result[0]["pitch"] == 60
        assert result[1]["pitch"] == 64

    def test_add_notes(self, mock_bridge):
        notes = [
            {"pitch": 60, "start_time": 0.0, "duration": 1.0},
            {"pitch": 67, "start_time": 2.0, "duration": 0.5, "velocity": 90},
        ]
        result = json.loads(clip_edit_notes("add", 0, 0, notes=notes))
        assert result["action"] == "added"
        assert result["count"] == 2
        mock_bridge.clips.add_notes.assert_called_once()
        call_args = mock_bridge.clips.add_notes.call_args
        midi_notes = call_args[0][2]  # third positional arg
        assert midi_notes[0].pitch == 60
        assert midi_notes[1].velocity == 90

    def test_replace_notes(self, mock_bridge):
        notes = [{"pitch": 72, "start_time": 0.0, "duration": 2.0}]
        result = json.loads(clip_edit_notes("replace", 0, 0, notes=notes))
        assert result["action"] == "replaced"
        mock_bridge.clips.replace_notes.assert_called_once()

    def test_remove_notes(self, mock_bridge):
        result = json.loads(clip_edit_notes("remove", 0, 0, start=0.0, length=4.0))
        assert result["action"] == "removed"
        mock_bridge.clips.remove_notes.assert_called_once_with(0, 0, 0.0, 4.0, 0, 127)


# ---------------------------------------------------------------------------
# Tool 14 — Devices
# ---------------------------------------------------------------------------

class TestDevices:
    def test_set_parameter(self, mock_bridge):
        result = json.loads(device_set_parameter(0, 0, 1, 0.75))
        assert result["value"] == 0.75
        mock_bridge.devices.set_parameter_value.assert_called_once_with(0, 0, 1, 0.75)


# ---------------------------------------------------------------------------
# Tool 15 — Scenes
# ---------------------------------------------------------------------------

class TestScenes:
    def test_fire(self, mock_bridge):
        result = json.loads(scene("fire", 0))
        assert result["action"] == "fire"
        mock_bridge.scenes.fire.assert_called_once_with(0)

    def test_create(self, mock_bridge):
        result = json.loads(scene("create", 2))
        assert result["action"] == "create"
        mock_bridge.scenes.create.assert_called_once_with(2)

    def test_delete(self, mock_bridge):
        result = json.loads(scene("delete", 1))
        assert result["action"] == "delete"
        mock_bridge.scenes.delete.assert_called_once_with(1)

    def test_duplicate(self, mock_bridge):
        result = json.loads(scene("duplicate", 0))
        assert result["action"] == "duplicate"
        mock_bridge.scenes.duplicate.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# Tool 16 — Special actions
# ---------------------------------------------------------------------------

class TestSpecialAction:
    def test_capture_midi(self, mock_bridge):
        result = json.loads(special_action("capture_midi"))
        assert result["action"] == "capture_midi"
        mock_bridge.transport.capture_midi.assert_called_once()

    def test_trigger_record(self, mock_bridge):
        result = json.loads(special_action("trigger_record"))
        assert result["action"] == "trigger_record"
        mock_bridge.transport.trigger_record.assert_called_once()

    def test_continue_playing(self, mock_bridge):
        result = json.loads(special_action("continue_playing"))
        assert result["action"] == "continue_playing"
        mock_bridge.transport.continue_playing.assert_called_once()

    def test_set_time(self, mock_bridge):
        result = json.loads(special_action("set_time", time=16.0))
        assert result["action"] == "set_time"
        assert result["time"] == 16.0
        mock_bridge.transport.set_time.assert_called_once_with(16.0)

    def test_set_time_missing_param(self):
        result = json.loads(special_action("set_time"))
        assert result["error"] == "ValueError"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_blessdog_error_returns_json(self, mock_bridge):
        from phase1_osc.errors import TrackNotFound
        mock_bridge.discovery.get_track_with_devices.side_effect = TrackNotFound(
            "Track 99 not found"
        )
        result = json.loads(track_get_info(99))
        assert result["error"] == "TrackNotFound"
        assert "99" in result["message"]
