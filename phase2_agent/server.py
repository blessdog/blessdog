"""BlessDog MCP Server — Claude controls Ableton Live + searches music library.

Exposes 16 Ableton tools (Phase 2) and 5 library tools (Phase 3),
plus a context resource and system prompt.

Run: python -m phase2_agent.server
"""

from __future__ import annotations

import json
from dataclasses import asdict
from functools import wraps
from typing import Literal

from mcp.server.fastmcp import FastMCP

from phase1_osc.errors import BlessDogError
from phase1_osc.types import MidiNote

from .bridge import AbletonBridge

from phase3_library.config import LibraryConfig
from phase3_library.db import LibraryDB
from phase3_library.search import LibrarySearch

from phase4_architect.loader import Loader
from phase4_architect.templates import find_template, list_templates
from phase4_architect.builder import SessionBuilder

from phase6_compose import MusicalContext, build_part, lint, ROLES

# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

ABLETON_CONTEXT = """\
You are controlling Ableton Live through the BlessDog MCP server.

## Session Structure
- A Live Set contains **tracks** (columns) and **scenes** (rows).
- Each track/scene intersection is a **clip slot** that may contain a clip.
- Tracks and scenes are **0-indexed**.

## Tracks
- **MIDI tracks** host instruments and play MIDI clips.
- **Audio tracks** record and play audio.
- Mixer: volume (0.0–1.0), panning (−1.0 to 1.0), mute, solo, arm.
- Each track holds a chain of **devices** (instruments + effects).

## Clips
- Clips live in slots addressed as [track_index, clip_index].
- clip_index corresponds to the scene/row number.
- Fire a clip to start playback; stop to halt it.

## MIDI Notes
- **pitch**: 0–127 (C3 = 60, C4 = 72). Sharps: C#3 = 61, etc.
- **start_time**: position in beats from clip start (0.0 = beat 1).
- **duration**: length in beats (0.25 = 16th, 0.5 = 8th, 1.0 = quarter).
- **velocity**: 1–127 (dynamics / loudness).
- **mute**: true to silence the note without deleting it.

## Scenes
- A scene is a horizontal row across all tracks.
- Firing a scene launches every clip in that row simultaneously.

## Devices
- Instruments (Simpler, Wavetable, Drum Rack …) and effects (Auto Filter,
  Reverb, Compressor …) sit on tracks.
- Each device exposes numbered **parameters** with float values.

## Composing music — use compose_part, do NOT hand-write notes
**compose_part is the primary way to create musical content.** It generates
in-key, voice-led, groovy, humanized MIDI from intent (key, mode, scale
degrees, register, feel), writes it reliably, and reads it back to confirm it
landed. Hand-emitting raw note integers via clip_edit_notes produces off-key,
stiff, flat results — only use it for surgical one-off edits.

- Pick intent, not pitches: `compose_part(role="bass", track_index=3,
  clip_index=0, key="F#", mode="minor", degrees=[1,6,4,5], bars=4)`.
- roles: chords, bass, arp, melody, drums. Tune via `options` (e.g.
  {"pattern": "root_octave", "rhythm": "8th"}) and `groove` (e.g.
  {"swing": 0.15}).
- Use `preview=True` to see notes + a lint report before writing; iterate, then
  write. Use `verify_clip` to check what's actually in a clip.

## Common Workflows
1. **Explore**: get_session → see tracks, scenes, tempo.
2. **Playback**: transport_play / transport_stop / set_tempo.
3. **Create music**: build_session (scaffold tracks) → compose_part per track
   (chords/bass/drums/…) → scene(fire) to audition. Keep the same key/mode/
   degrees across parts so they lock together.
4. **Mix**: track_set_mixer to adjust volume / pan / mute.
5. **Arrange**: scene(fire) to trigger rows of clips.
6. **Undo mistakes**: undo_redo("undo").
7. **Load devices**: view_select(track=0) → load_device(0, "Wavetable").
8. **Quick setup**: track_setup("midi", "Bass", instrument="Wavetable").
9. **Browse**: browse_browser("search", category="instruments", query="Wavetable").
10. **Scaffold**: build_session(template="dark_melodic_techno").
"""

# ---------------------------------------------------------------------------
# Server + Bridge
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "blessdog",
    instructions=ABLETON_CONTEXT,
)

bridge = AbletonBridge()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def _handle_errors(func):
    """Decorator: ensure connection + catch BlessDogError → JSON error."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            bridge.ensure_connected()
            return func(*args, **kwargs)
        except BlessDogError as e:
            return json.dumps({
                "error": type(e).__name__,
                "message": str(e),
            })
    return wrapper


def _json(obj) -> str:
    """Serialize a dataclass or dict to JSON."""
    if hasattr(obj, "__dataclass_fields__"):
        return json.dumps(asdict(obj))
    return json.dumps(obj)


# ---------------------------------------------------------------------------
# Resource + Prompt
# ---------------------------------------------------------------------------

@mcp.resource("blessdog://context")
def ableton_context() -> str:
    """Ableton Live session context and conventions."""
    return ABLETON_CONTEXT


@mcp.prompt("ableton-context")
def ableton_context_prompt() -> str:
    """System prompt explaining Ableton session structure and workflows."""
    return ABLETON_CONTEXT


# ---------------------------------------------------------------------------
# Tool 1 — Session discovery
# ---------------------------------------------------------------------------

@mcp.tool()
@_handle_errors
def get_session() -> str:
    """Get the full Ableton Live session structure: tempo, tracks, scenes."""
    return _json(bridge.discovery.get_session_structure())


# ---------------------------------------------------------------------------
# Tools 2–7 — Transport
# ---------------------------------------------------------------------------

@mcp.tool()
@_handle_errors
def transport_get_state() -> str:
    """Get transport state: playing, tempo, time, loop, record."""
    return _json(bridge.transport.get_state())


@mcp.tool()
@_handle_errors
def transport_play() -> str:
    """Start playback."""
    bridge.transport.play()
    return json.dumps({"status": "playing"})


@mcp.tool()
@_handle_errors
def transport_stop() -> str:
    """Stop playback."""
    bridge.transport.stop()
    return json.dumps({"status": "stopped"})


@mcp.tool()
@_handle_errors
def set_tempo(bpm: float) -> str:
    """Set the song tempo in BPM."""
    bridge.transport.set_tempo(bpm)
    return json.dumps({"tempo": bpm})


@mcp.tool()
@_handle_errors
def set_loop(
    enabled: bool,
    start: float | None = None,
    length: float | None = None,
) -> str:
    """Enable/disable loop and optionally set loop start and length (in beats)."""
    bridge.transport.set_loop(enabled)
    if start is not None:
        bridge.transport.set_loop_start(start)
    if length is not None:
        bridge.transport.set_loop_length(length)
    result = {"loop_on": enabled}
    if start is not None:
        result["loop_start"] = start
    if length is not None:
        result["loop_length"] = length
    return json.dumps(result)


@mcp.tool()
@_handle_errors
def undo_redo(action: Literal["undo", "redo"]) -> str:
    """Undo or redo the last action in Ableton."""
    if action == "undo":
        bridge.transport.undo()
    else:
        bridge.transport.redo()
    return json.dumps({"action": action})


# ---------------------------------------------------------------------------
# Tools 8–10 — Tracks
# ---------------------------------------------------------------------------

@mcp.tool()
@_handle_errors
def track_get_info(track_index: int) -> str:
    """Get detailed info for a track including devices and sends."""
    return _json(bridge.discovery.get_track_with_devices(track_index))


@mcp.tool()
@_handle_errors
def track_set_mixer(
    track_index: int,
    volume: float | None = None,
    pan: float | None = None,
    mute: bool | None = None,
    solo: bool | None = None,
    arm: bool | None = None,
) -> str:
    """Set mixer properties for a track. Only provided values are changed."""
    changed = {}
    if volume is not None:
        bridge.tracks.set_volume(track_index, volume)
        changed["volume"] = volume
    if pan is not None:
        bridge.tracks.set_panning(track_index, pan)
        changed["pan"] = pan
    if mute is not None:
        bridge.tracks.set_mute(track_index, mute)
        changed["mute"] = mute
    if solo is not None:
        bridge.tracks.set_solo(track_index, solo)
        changed["solo"] = solo
    if arm is not None:
        bridge.tracks.set_arm(track_index, arm)
        changed["arm"] = arm
    return json.dumps({"track_index": track_index, **changed})


@mcp.tool()
@_handle_errors
def track_create_delete(
    action: Literal["create_midi", "create_audio", "delete"],
    index: int = -1,
) -> str:
    """Create or delete a track. Index -1 appends at end for create."""
    if action == "create_midi":
        bridge.tracks.create_midi_track(index)
    elif action == "create_audio":
        bridge.tracks.create_audio_track(index)
    else:
        bridge.tracks.delete(index)
    return json.dumps({"action": action, "index": index})


# ---------------------------------------------------------------------------
# Tools 11–13 — Clips
# ---------------------------------------------------------------------------

@mcp.tool()
@_handle_errors
def clip_fire_stop(
    action: Literal["fire", "stop"],
    track_index: int,
    clip_index: int,
) -> str:
    """Fire or stop a clip."""
    if action == "fire":
        bridge.clips.fire(track_index, clip_index)
    else:
        bridge.clips.stop(track_index, clip_index)
    return json.dumps({
        "action": action,
        "track_index": track_index,
        "clip_index": clip_index,
    })


@mcp.tool()
@_handle_errors
def clip_manage(
    action: Literal["get_info", "create", "delete", "rename"],
    track_index: int,
    clip_index: int,
    length: float = 4.0,
    name: str | None = None,
) -> str:
    """Get info, create, delete, or rename a clip. Length is in beats (for create)."""
    if action == "get_info":
        return _json(bridge.clips.get_info(track_index, clip_index))
    elif action == "create":
        bridge.clips.create(track_index, clip_index, length)
        return json.dumps({
            "action": "created",
            "track_index": track_index,
            "clip_index": clip_index,
            "length": length,
        })
    elif action == "rename":
        if not name:
            return json.dumps({"error": "name is required for rename"})
        bridge.clips.set_name(track_index, clip_index, name)
        return json.dumps({
            "action": "renamed",
            "track_index": track_index,
            "clip_index": clip_index,
            "name": name,
        })
    else:
        bridge.clips.delete(track_index, clip_index)
        return json.dumps({
            "action": "deleted",
            "track_index": track_index,
            "clip_index": clip_index,
        })


@mcp.tool()
@_handle_errors
def clip_edit_notes(
    action: Literal["get", "add", "replace", "remove"],
    track_index: int,
    clip_index: int,
    notes: list[dict] | None = None,
    start: float = 0.0,
    length: float = 128.0,
    pitch_low: int = 0,
    pitch_high: int = 127,
) -> str:
    """Edit MIDI notes in a clip.

    For 'add' and 'replace', provide notes as a list of dicts:
      [{"pitch": 60, "start_time": 0.0, "duration": 1.0, "velocity": 100, "mute": false}, ...]
    velocity defaults to 100, mute defaults to false.

    For 'get' and 'remove', use start/length/pitch_low/pitch_high to
    define the range.
    """
    if action == "get":
        raw = bridge.clips.get_notes(
            track_index, clip_index, start, length, pitch_low, pitch_high,
        )
        return json.dumps([asdict(n) for n in raw])

    elif action == "add":
        midi_notes = _parse_notes(notes or [])
        bridge.clips.add_notes(track_index, clip_index, midi_notes)
        return json.dumps({
            "action": "added",
            "count": len(midi_notes),
            "track_index": track_index,
            "clip_index": clip_index,
        })

    elif action == "replace":
        midi_notes = _parse_notes(notes or [])
        bridge.clips.replace_notes(
            track_index, clip_index, midi_notes,
            start, length, pitch_low, pitch_high,
        )
        return json.dumps({
            "action": "replaced",
            "count": len(midi_notes),
            "track_index": track_index,
            "clip_index": clip_index,
        })

    else:  # remove
        bridge.clips.remove_notes(
            track_index, clip_index, start, length, pitch_low, pitch_high,
        )
        return json.dumps({
            "action": "removed",
            "track_index": track_index,
            "clip_index": clip_index,
        })


def _parse_notes(raw: list[dict]) -> list[MidiNote]:
    """Convert list of dicts to MidiNote objects."""
    return [
        MidiNote(
            pitch=int(n["pitch"]),
            start_time=float(n["start_time"]),
            duration=float(n["duration"]),
            velocity=int(n.get("velocity", 100)),
            mute=bool(n.get("mute", False)),
        )
        for n in raw
    ]


# ---------------------------------------------------------------------------
# Composition (Phase 6) — intent-driven, theory-aware MIDI generation
# ---------------------------------------------------------------------------

def _notes_to_dicts(notes: list[MidiNote]) -> list[dict]:
    return [
        {"pitch": n.pitch, "start": n.start_time, "dur": n.duration, "vel": n.velocity}
        for n in notes
    ]


@mcp.tool()
@_handle_errors
def compose_part(
    role: str,
    track_index: int,
    clip_index: int,
    key: str = "C",
    mode: str = "minor",
    bars: int = 4,
    degrees: list[int] | None = None,
    tempo: float | None = None,
    preview: bool = False,
    create_clip: bool = True,
    replace: bool = True,
    options: dict | None = None,
    groove: dict | None = None,
) -> str:
    """Generate an in-key, groovy musical part and write it to a clip.

    This is the PRIMARY way to create music — do not hand-emit raw notes.
    Deterministic theory primitives produce in-key, voice-led, humanized MIDI,
    write it reliably (chunked), and read it back to confirm it landed.

    - role: one of chords | bass | arp | melody | drums
    - key/mode: e.g. key="F#", mode="minor" (modes: major, minor, dorian,
      phrygian, lydian, mixolydian, aeolian, harmonic_minor)
    - degrees: scale degrees for the progression, e.g. [1, 6, 4, 5] = i-VI-iv-v.
      (Ignored by drums.)
    - bars: clip length in bars (4/4).
    - preview: True returns the generated notes + lint WITHOUT writing, so you
      can inspect/iterate cheaply before committing.
    - options: per-role generator tuning, e.g. {"octave": 2, "pattern":
      "root_octave", "rhythm": "8th"} for bass, or {"voices": {...}} for drums.
    - groove: humanization overrides, e.g. {"swing": 0.15, "velocity": 14}.

    Returns the lint report and a read-back verification of what actually
    landed in Ableton.
    """
    if role not in ROLES:
        return json.dumps({"error": "ValueError",
                           "message": f"role must be one of {list(ROLES)}"})

    ctx = MusicalContext(key=key, mode=mode, tempo=tempo or 120.0)
    notes = build_part(
        role, ctx, degrees=degrees, bars=bars, groove=groove, **(options or {}),
    )
    clip_length = bars * ctx.beats_per_bar
    report = lint(notes, ctx, clip_length, check_key=(role != "drums"))

    if preview:
        return json.dumps({
            "role": role,
            "preview": True,
            "key": key,
            "mode": mode,
            "bars": bars,
            "clip_length": clip_length,
            "note_count": len(notes),
            "lint": report,
            "notes": _notes_to_dicts(notes),
        })

    if create_clip:
        # Harmless if the slot is already filled (server-side no-op).
        bridge.clips.create(track_index, clip_index, clip_length)
    if replace:
        bridge.clips.remove_notes(track_index, clip_index, 0.0, clip_length, 0, 127)

    verify = bridge.clips.add_notes_verified(track_index, clip_index, notes)

    return json.dumps({
        "role": role,
        "track_index": track_index,
        "clip_index": clip_index,
        "key": key,
        "mode": mode,
        "bars": bars,
        "clip_length": clip_length,
        "lint": report,
        "verify": verify,
    })


@mcp.tool()
@_handle_errors
def verify_clip(
    track_index: int,
    clip_index: int,
    key: str | None = None,
    mode: str = "minor",
    clip_length: float | None = None,
) -> str:
    """Read a clip's notes back and report on them.

    Reads the notes actually in the clip (range-correct, resilient to dense
    clips) and returns the count. If key is provided, also lints them for
    in-key / in-bounds correctness — useful to check anything written earlier.
    """
    info = bridge.clips.get_info(track_index, clip_index)
    length = clip_length or info.length or 16.0
    notes = bridge.clips.get_notes(track_index, clip_index, 0.0, length + 1.0, 0, 127)

    result: dict = {
        "track_index": track_index,
        "clip_index": clip_index,
        "clip_name": info.name,
        "clip_length": length,
        "note_count": len(notes),
    }
    if key:
        ctx = MusicalContext(key=key, mode=mode)
        result["lint"] = lint(notes, ctx, length + 1.0, check_key=True)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool 14 — Devices
# ---------------------------------------------------------------------------

@mcp.tool()
@_handle_errors
def device_set_parameter(
    track_index: int,
    device_index: int,
    parameter_index: int,
    value: float,
) -> str:
    """Set a device parameter value."""
    bridge.devices.set_parameter_value(
        track_index, device_index, parameter_index, value,
    )
    return json.dumps({
        "track_index": track_index,
        "device_index": device_index,
        "parameter_index": parameter_index,
        "value": value,
    })


# ---------------------------------------------------------------------------
# Tool 15 — Scenes
# ---------------------------------------------------------------------------

@mcp.tool()
@_handle_errors
def scene(
    action: Literal["fire", "create", "delete", "duplicate"],
    index: int = 0,
) -> str:
    """Fire, create, delete, or duplicate a scene."""
    if action == "fire":
        bridge.scenes.fire(index)
    elif action == "create":
        bridge.scenes.create(index)
    elif action == "delete":
        bridge.scenes.delete(index)
    else:
        bridge.scenes.duplicate(index)
    return json.dumps({"action": action, "index": index})


# ---------------------------------------------------------------------------
# Tool 16 — Special actions
# ---------------------------------------------------------------------------

@mcp.tool()
@_handle_errors
def special_action(
    action: Literal["capture_midi", "trigger_record", "continue_playing", "set_time"],
    time: float | None = None,
) -> str:
    """Perform a special transport action.

    - capture_midi: capture recently played MIDI as a clip
    - trigger_record: start session recording (arms + records)
    - continue_playing: resume playback from current position
    - set_time: jump to a specific beat position (requires time param)
    """
    if action == "capture_midi":
        bridge.transport.capture_midi()
    elif action == "trigger_record":
        bridge.transport.trigger_record()
    elif action == "continue_playing":
        bridge.transport.continue_playing()
    elif action == "set_time":
        if time is None:
            return json.dumps({"error": "ValueError", "message": "time is required for set_time"})
        bridge.transport.set_time(time)
    return json.dumps({"action": action, **({"time": time} if time is not None else {})})


# ---------------------------------------------------------------------------
# Tool 22 — View selection
# ---------------------------------------------------------------------------

@mcp.tool()
@_handle_errors
def view_select(
    track: int | None = None,
    scene: int | None = None,
    device: tuple[int, int] | None = None,
) -> str:
    """Select a track, scene, or device in Ableton's UI.

    - track: select track by index
    - scene: select scene by index
    - device: select device as [track_index, device_index]
    """
    result = {}
    if track is not None:
        bridge.view.set_selected_track(track)
        result["selected_track"] = track
    if scene is not None:
        bridge.view.set_selected_scene(scene)
        result["selected_scene"] = scene
    if device is not None:
        bridge.view.set_selected_device(device[0], device[1])
        result["selected_device"] = list(device)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool 23 — Load device
# ---------------------------------------------------------------------------

@mcp.tool()
@_handle_errors
def load_device(
    track_index: int,
    name: str,
    category: str | None = None,
) -> str:
    """Load an instrument, effect, or sample onto a track by name.

    Selects the track, searches the browser, and loads the first match.
    Category is auto-detected but can be overridden:
    instruments, audio_effects, drums, samples, etc.
    """
    loader = Loader(bridge.view, bridge.browser)
    result = loader.load_device(track_index, name, category=category)
    return json.dumps({
        "success": result.success,
        "track_index": result.track_index,
        "device_name": result.device_name,
        "source": result.source,
        "error": result.error,
    })


# ---------------------------------------------------------------------------
# Tool 24 — Track setup
# ---------------------------------------------------------------------------

@mcp.tool()
@_handle_errors
def track_setup(
    track_type: Literal["midi", "audio"],
    name: str,
    color: int | None = None,
    instrument: str | None = None,
) -> str:
    """Create a track, name it, color it, and optionally load an instrument.

    Combines create + name + color + load in one call.
    """
    if track_type == "midi":
        bridge.tracks.create_midi_track(-1)
    else:
        bridge.tracks.create_audio_track(-1)

    import time
    time.sleep(0.05)

    track_count = bridge.tracks.count()
    idx = track_count - 1

    bridge.tracks.set_name(idx, name)

    result = {
        "track_index": idx,
        "name": name,
        "track_type": track_type,
    }

    if color is not None:
        bridge.tracks.set_color_index(idx, color)
        result["color_index"] = color

    if instrument:
        loader = Loader(bridge.view, bridge.browser)
        load_result = loader.load_device(idx, instrument)
        result["instrument_loaded"] = load_result.success
        result["instrument_name"] = load_result.device_name
        if not load_result.success:
            result["instrument_error"] = load_result.error

    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool 25 — Browse browser
# ---------------------------------------------------------------------------

@mcp.tool()
@_handle_errors
def browse_browser(
    action: Literal["categories", "search", "list_children"],
    category: str | None = None,
    query: str | None = None,
    path: list[str] | None = None,
    max_results: int = 20,
) -> str:
    """Browse Ableton's device browser.

    Actions:
    - categories: list all browser categories
    - search: search within a category (requires category + query)
    - list_children: list children at a path (requires category, optional path)
    """
    if action == "categories":
        cats = bridge.browser.categories()
        return json.dumps({"categories": cats})

    elif action == "search":
        if not category or not query:
            return json.dumps({"error": "ValueError", "message": "search requires category and query"})
        items = bridge.browser.search(category, query, max_results)
        return json.dumps({
            "results": [
                {"name": i.name, "uri": i.uri, "is_loadable": i.is_loadable, "child_count": i.child_count}
                for i in items
            ],
            "count": len(items),
        })

    else:  # list_children
        if not category:
            return json.dumps({"error": "ValueError", "message": "list_children requires category"})
        segments = path or []
        items = bridge.browser.list_children(category, *segments)
        return json.dumps({
            "results": [
                {"name": i.name, "uri": i.uri, "is_loadable": i.is_loadable, "child_count": i.child_count}
                for i in items
            ],
            "count": len(items),
        })


# ---------------------------------------------------------------------------
# Tool 26 — Build session
# ---------------------------------------------------------------------------

@mcp.tool()
@_handle_errors
def build_session(
    template: str | None = None,
    list_available: bool = False,
) -> str:
    """Scaffold a full session from a predefined template.

    Set list_available=true to see all available templates.
    Provide template name to build (e.g. "dark_melodic_techno").
    """
    if list_available:
        return json.dumps({"templates": list_templates()})

    if not template:
        return json.dumps({"error": "ValueError", "message": "provide template name or set list_available=true"})

    tmpl = find_template(template)
    if not tmpl:
        available = [t["name"] for t in list_templates()]
        return json.dumps({
            "error": "NotFound",
            "message": f"template '{template}' not found",
            "available": available,
        })

    loader = Loader(bridge.view, bridge.browser)
    builder = SessionBuilder(bridge.tracks, bridge.transport, loader)
    result = builder.build(tmpl)

    return json.dumps({
        "template": result.template_name,
        "success": result.success,
        "tempo": result.tempo,
        "tracks_created": result.tracks_created,
        "tracks_failed": result.tracks_failed,
        "track_results": [
            {
                "track_index": tr.track_index,
                "name": tr.name,
                "success": tr.success,
                "instrument_loaded": tr.instrument_loaded,
                "effects_loaded": tr.effects_loaded,
                "effects_failed": tr.effects_failed,
                "error": tr.error,
            }
            for tr in result.track_results
        ],
    })


# ---------------------------------------------------------------------------
# Library (Phase 3) — lazy init
# ---------------------------------------------------------------------------

_library_config: LibraryConfig | None = None
_library_db: LibraryDB | None = None
_library_search: LibrarySearch | None = None


def _get_library() -> LibrarySearch:
    """Lazy-init the library search instance."""
    global _library_config, _library_db, _library_search
    if _library_search is None:
        _library_config = LibraryConfig.load()
        _library_db = LibraryDB(_library_config.db_path)
        _library_search = LibrarySearch(_library_db)
    return _library_search


def _get_library_config() -> LibraryConfig:
    """Lazy-init and return library config."""
    _get_library()
    return _library_config  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Tools 17–21 — Library search
# ---------------------------------------------------------------------------

@mcp.tool()
def search_library(
    query: str,
    file_type: str | None = None,
    category: str | None = None,
    limit: int = 20,
) -> str:
    """Search the music library by keyword.

    Searches across file names, categories, library names, device classes,
    and NI preset metadata. Filter by file_type (sample, instrument, effect,
    preset, midi) or category (drums/kicks, bass, synth/pads, etc.).
    """
    try:
        lib = _get_library()
        results = lib.search(query, file_type=file_type, category=category, limit=limit)
        return json.dumps({"results": results, "count": len(results)})
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


@mcp.tool()
def library_stats() -> str:
    """Get summary statistics of the indexed music library.

    Returns total files, size, and breakdowns by type, source, library, and category.
    """
    try:
        lib = _get_library()
        return json.dumps(lib.stats())
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


@mcp.tool()
def library_browse(
    category: str | None = None,
    library_source: str | None = None,
    limit: int = 50,
) -> str:
    """Browse the music library by category or source.

    Categories: drums/kicks, drums/snares, bass, synth/pads, keys, fx, etc.
    Sources: ni_library, ableton_factory, drum_kit, user_collection.
    """
    try:
        lib = _get_library()
        results = lib.browse(category=category, library_source=library_source, limit=limit)
        return json.dumps({"results": results, "count": len(results)})
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


@mcp.tool()
def library_reindex() -> str:
    """Trigger an incremental rescan of all configured library paths.

    Scans for new/modified files and updates the search index.
    Only re-processes files that have changed since the last scan.
    """
    try:
        lib = _get_library()
        config = _get_library_config()
        result = lib.reindex(config)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


@mcp.tool()
def library_duplicates(limit: int = 50) -> str:
    """Show duplicate files found across library locations.

    Reports files with the same name, extension, and size in multiple
    locations, along with total wasted space.
    """
    try:
        lib = _get_library()
        return json.dumps(lib.duplicates(limit=limit))
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ---------------------------------------------------------------------------
# Tool 27 — Download reference track
# ---------------------------------------------------------------------------

@mcp.tool()
def download_reference(
    url: str,
    filename: str | None = None,
    wav: bool = True,
) -> str:
    """Download audio from a YouTube URL for reference analysis.

    Extracts the best quality audio and saves to blessdog/music/.
    Set wav=True (default) for analysis-ready WAV, or False for
    compressed format.

    Returns file path, title, artist, and duration.
    """
    try:
        from phase5_analyzer.download import download
        result = download(url, wav=wav, filename=filename)
        return json.dumps(result.to_dict())
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ---------------------------------------------------------------------------
# Tools 28–29 — Reference Track Analyzer (Phase 5)
# ---------------------------------------------------------------------------

@mcp.tool()
def analyze_reference(
    audio_path: str,
    title: str | None = None,
    artist: str | None = None,
    bpm: float | None = None,
    key: str | None = None,
    model: str = "htdemucs",
) -> str:
    """Analyze a reference track using stem separation + per-stem analysis.

    Splits the audio into drums/bass/vocals/other using Demucs, then
    extracts tempo, key, chord progression, energy curves, arrangement
    sections, and rhythmic patterns from each stem.

    Provide known metadata (title, artist, bpm, key) to skip estimation.
    Returns structured analysis for LLM-driven arrangement mapping.

    This is a long-running operation (1-5 minutes depending on track length).
    """
    try:
        from phase5_analyzer.analyzer import analyze_track

        metadata: dict = {}
        if title:
            metadata["title"] = title
        if artist:
            metadata["artist"] = artist
        if bpm:
            metadata["known_bpm"] = bpm
        if key:
            metadata["known_key"] = key

        result = analyze_track(audio_path, metadata=metadata, model=model)
        return result.to_json()

    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


@mcp.tool()
def analyze_reference_summary(
    audio_path: str,
    title: str | None = None,
    artist: str | None = None,
    bpm: float | None = None,
    key: str | None = None,
    model: str = "htdemucs",
) -> str:
    """Analyze a reference track and return a concise text summary.

    Same as analyze_reference but returns a compact markdown summary
    optimized for LLM context, instead of the full JSON data.

    Use this when you need the overview without raw data arrays.
    """
    try:
        from phase5_analyzer.analyzer import analyze_track

        metadata: dict = {}
        if title:
            metadata["title"] = title
        if artist:
            metadata["artist"] = artist
        if bpm:
            metadata["known_bpm"] = bpm
        if key:
            metadata["known_key"] = key

        result = analyze_track(audio_path, metadata=metadata, model=model)
        return result.summary()

    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
