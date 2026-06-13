"""Session templates — predefined track configurations for common genres."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TrackSpec:
    name: str
    track_type: str  # "midi" or "audio"
    instrument: str | None = None
    effects: list[str] = field(default_factory=list)
    color_index: int = 0
    volume: float = 0.85


@dataclass
class SessionTemplate:
    name: str
    description: str
    genre: str
    tempo: float
    tracks: list[TrackSpec] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Built-in templates
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, SessionTemplate] = {}


def _register(template: SessionTemplate) -> None:
    TEMPLATES[template.name] = template


_register(SessionTemplate(
    name="dark_melodic_techno",
    description="Dark melodic techno session with driving bass, atmospheric pads, and crisp drums",
    genre="techno",
    tempo=128.0,
    tracks=[
        TrackSpec(name="Kick", track_type="midi", instrument="Drum Rack", color_index=13, volume=0.9),
        TrackSpec(name="Hats", track_type="midi", instrument="Drum Rack", color_index=14, volume=0.75),
        TrackSpec(name="Perc", track_type="midi", instrument="Drum Rack", color_index=15, volume=0.7),
        TrackSpec(name="Bass", track_type="midi", instrument="Wavetable", effects=["Auto Filter", "Compressor"], color_index=69, volume=0.85),
        TrackSpec(name="Lead", track_type="midi", instrument="Wavetable", effects=["Reverb", "Delay"], color_index=26, volume=0.7),
        TrackSpec(name="Pad", track_type="midi", instrument="Wavetable", effects=["Reverb"], color_index=48, volume=0.6),
        TrackSpec(name="FX", track_type="audio", effects=["Reverb", "Delay"], color_index=60, volume=0.5),
    ],
))

_register(SessionTemplate(
    name="minimal_techno",
    description="Stripped-back minimal techno with space and groove",
    genre="techno",
    tempo=124.0,
    tracks=[
        TrackSpec(name="Kick", track_type="midi", instrument="Drum Rack", color_index=13, volume=0.9),
        TrackSpec(name="Perc", track_type="midi", instrument="Drum Rack", color_index=14, volume=0.7),
        TrackSpec(name="Bass", track_type="midi", instrument="Operator", effects=["Auto Filter"], color_index=69, volume=0.85),
        TrackSpec(name="Stab", track_type="midi", instrument="Wavetable", effects=["Delay"], color_index=26, volume=0.65),
        TrackSpec(name="Atmosphere", track_type="audio", effects=["Reverb"], color_index=48, volume=0.5),
    ],
))

_register(SessionTemplate(
    name="ambient",
    description="Ambient textures with lush reverbs and evolving pads",
    genre="ambient",
    tempo=72.0,
    tracks=[
        TrackSpec(name="Pad A", track_type="midi", instrument="Wavetable", effects=["Reverb", "Delay"], color_index=48, volume=0.7),
        TrackSpec(name="Pad B", track_type="midi", instrument="Wavetable", effects=["Reverb"], color_index=49, volume=0.6),
        TrackSpec(name="Texture", track_type="audio", effects=["Reverb", "Delay"], color_index=60, volume=0.5),
        TrackSpec(name="Melody", track_type="midi", instrument="Wavetable", effects=["Reverb", "Delay"], color_index=26, volume=0.55),
        TrackSpec(name="Sub", track_type="midi", instrument="Operator", color_index=69, volume=0.75),
    ],
))

_register(SessionTemplate(
    name="hip_hop",
    description="Hip hop beat session with 808s, drums, and sample layers",
    genre="hip_hop",
    tempo=90.0,
    tracks=[
        TrackSpec(name="Kick", track_type="midi", instrument="Drum Rack", color_index=13, volume=0.9),
        TrackSpec(name="Snare", track_type="midi", instrument="Drum Rack", color_index=14, volume=0.85),
        TrackSpec(name="Hats", track_type="midi", instrument="Drum Rack", color_index=15, volume=0.7),
        TrackSpec(name="808", track_type="midi", instrument="Operator", effects=["Saturator", "Compressor"], color_index=69, volume=0.9),
        TrackSpec(name="Keys", track_type="midi", instrument="Wavetable", effects=["Reverb"], color_index=26, volume=0.65),
        TrackSpec(name="Sample", track_type="audio", effects=["Auto Filter"], color_index=60, volume=0.7),
    ],
))


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------

def find_template(query: str) -> SessionTemplate | None:
    """Find a template by name or keyword match."""
    query_lower = query.lower().replace(" ", "_")

    # Exact name match
    if query_lower in TEMPLATES:
        return TEMPLATES[query_lower]

    # Partial name or genre match
    for template in TEMPLATES.values():
        if query_lower in template.name.lower():
            return template
        if query_lower in template.genre.lower():
            return template
        if query_lower in template.description.lower():
            return template

    return None


def list_templates() -> list[dict[str, str]]:
    """Return metadata for all available templates."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "genre": t.genre,
            "tempo": str(t.tempo),
            "track_count": str(len(t.tracks)),
        }
        for t in TEMPLATES.values()
    ]
