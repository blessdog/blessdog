"""Dataclasses for structured AbletonOSC responses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TransportState:
    is_playing: bool = False
    tempo: float = 120.0
    time_signature_num: int = 4
    time_signature_den: int = 4
    song_time: float = 0.0
    loop_start: float = 0.0
    loop_length: float = 4.0
    loop_on: bool = False
    record_mode: bool = False


@dataclass
class MidiNote:
    pitch: int
    start_time: float  # beats
    duration: float  # beats
    velocity: int = 100
    mute: bool = False


@dataclass
class ParameterInfo:
    index: int
    name: str
    value: float
    min_value: float = 0.0
    max_value: float = 1.0
    display: str = ""


@dataclass
class DeviceInfo:
    track_index: int
    device_index: int
    name: str
    class_name: str = ""
    parameters: list[ParameterInfo] = field(default_factory=list)


@dataclass
class ClipInfo:
    track_index: int
    clip_index: int
    name: str = ""
    length: float = 0.0
    is_playing: bool = False
    is_triggered: bool = False
    is_recording: bool = False
    color: int = 0


@dataclass
class SendInfo:
    index: int
    name: str
    value: float


@dataclass
class TrackInfo:
    index: int
    name: str
    volume: float = 0.85
    panning: float = 0.0
    mute: bool = False
    solo: bool = False
    arm: bool = False
    has_midi_input: bool = False
    has_audio_input: bool = False
    clips: list[ClipInfo] = field(default_factory=list)
    devices: list[DeviceInfo] = field(default_factory=list)
    sends: list[SendInfo] = field(default_factory=list)


@dataclass
class SessionStructure:
    tempo: float
    time_signature_num: int
    time_signature_den: int
    track_count: int
    scene_count: int
    return_track_count: int
    tracks: list[TrackInfo] = field(default_factory=list)
    scene_names: list[str] = field(default_factory=list)
