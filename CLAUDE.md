# BlessDog — AI Music Production System

## Architecture

Two MCP servers control Ableton Live:

- **ableton-mcp** (`uisato/ableton-mcp-extended`): Primary Ableton control — clips, MIDI, tracks, devices, browser, automation, scenes, transport. ~40 tools via TCP socket + custom Remote Script.
- **blessdog** (custom): Higher-level helpers — session scaffolding, library search, reference track analysis, tempo/loop shortcuts.

Use `ableton-mcp` tools for direct Ableton operations. Use `blessdog` tools for batch workflows (build_session, track_setup, library search, analyze_reference).

## Production Workflow

**Session view first, Arrangement view second.** This is how Ableton is designed:

1. **Sketch in Session view** — create clips, loops, variations. Prototype rapidly. Use scenes to group ideas.
2. **Jam with scenes** — fire scenes, use follow actions, test arrangements live.
3. **Record into Arrangement** — when the structure is solid, record a performance from Session into Arrangement for the final linear track.

Do NOT write directly to Arrangement view for initial composition. Session view is for creative exploration; Arrangement is for finalizing.

## MIDI Notes Reference

- pitch: 0-127 (C3=60, C-1=0, C4=72)
- start_time: beats from clip start (0.0 = beat 1), always LOCAL to the clip
- duration: beats (0.25=16th, 0.5=8th, 1.0=quarter)
- velocity: 1-127
- Common roots: C=60, D=62, E=64, F=65, G=67, A=69, B=71

## Tool Selection by Task

**Clips & MIDI patterns:** create_clip, add_notes, transpose, quantize — use for drums, bass, arps, melodies
**Tracks & sound design:** create_track, load_instrument/effect from browser, set device parameters
**Playback & sequencing:** fire scenes, launch clips, follow actions — test arrangements in Session
**Transport:** play, stop, set tempo, get session info
**Mixing & automation:** set volume/pan/mute/solo, automation points, EQ, compression
**Browser:** search instruments, effects, samples by name or URI

## Key Conventions

- Tempo, key, and time signature: always check current session state before writing patterns
- Chord progressions: write root notes for bass, full voicings for pads/keys, arpeggiated for plucks
- Velocity variation: never use flat velocity — always add groove (accent downbeats, ghost notes lighter)
- Clip lengths: typically 4, 8, or 16 bars. Match to musical phrase lengths.
- Scene organization: name scenes by section (Intro, Verse, Build, Drop, Break, Outro)

## Project Structure

```
blessdog/
  phase1_osc/     — OSC bridge layer
  phase2_agent/   — MCP server (blessdog tools)
  phase3_library/ — Sample/preset library indexer
  phase4_architect/ — Session template builder
  phase5_analyzer/ — Reference track analyzer (Demucs + librosa)
  music/          — Downloaded reference tracks and stems
  tests/          — Test suite
```
