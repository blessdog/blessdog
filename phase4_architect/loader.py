"""Loader — select track, search browser, load device/sample."""

from __future__ import annotations

import time
from dataclasses import dataclass

from phase1_osc.browser import Browser
from phase1_osc.errors import LoadError
from phase1_osc.view import View

# Map file types / keywords to browser categories for auto-resolution
_CATEGORY_MAP = {
    # By device purpose
    "instrument": "instruments",
    "synth": "instruments",
    "sampler": "instruments",
    "drum_rack": "drums",
    "drum": "drums",
    "audio_effect": "audio_effects",
    "effect": "audio_effects",
    "midi_effect": "midi_effects",
    # By file extension
    ".adg": "instruments",
    ".adv": "instruments",
    ".aupreset": "plugins",
    ".nksf": "instruments",
    ".wav": "samples",
    ".aif": "samples",
    ".aiff": "samples",
    ".mp3": "samples",
    ".flac": "samples",
}

# Common Ableton instruments → category shortcuts
_KNOWN_INSTRUMENTS = {
    "wavetable": "instruments",
    "operator": "instruments",
    "simpler": "instruments",
    "sampler": "instruments",
    "drift": "instruments",
    "drum rack": "drums",
    "collision": "instruments",
    "tension": "instruments",
    "electric": "instruments",
    "analog": "instruments",
}

_KNOWN_EFFECTS = {
    "auto filter": "audio_effects",
    "reverb": "audio_effects",
    "delay": "audio_effects",
    "compressor": "audio_effects",
    "eq eight": "audio_effects",
    "eq three": "audio_effects",
    "glue compressor": "audio_effects",
    "saturator": "audio_effects",
    "erosion": "audio_effects",
    "chorus-ensemble": "audio_effects",
    "phaser-flanger": "audio_effects",
    "echo": "audio_effects",
    "hybrid reverb": "audio_effects",
    "pedal": "audio_effects",
    "utility": "audio_effects",
    "limiter": "audio_effects",
    "gate": "audio_effects",
    "corpus": "audio_effects",
    "overdrive": "audio_effects",
    "redux": "audio_effects",
    "vinyl distortion": "audio_effects",
    "spectrum": "audio_effects",
    "tuner": "audio_effects",
}


@dataclass
class LoadResult:
    success: bool
    track_index: int
    device_name: str
    source: str = ""
    error: str = ""


class Loader:
    """Loads devices and samples onto Ableton tracks via the browser."""

    def __init__(self, view: View, browser: Browser):
        self._view = view
        self._browser = browser

    def _resolve_category(self, name: str, category: str | None = None, file_type: str | None = None) -> str:
        """Determine the browser category to search."""
        if category:
            return category

        name_lower = name.lower()

        # Check known instruments
        if name_lower in _KNOWN_INSTRUMENTS:
            return _KNOWN_INSTRUMENTS[name_lower]

        # Check known effects
        if name_lower in _KNOWN_EFFECTS:
            return _KNOWN_EFFECTS[name_lower]

        # Check file type mapping
        if file_type and file_type in _CATEGORY_MAP:
            return _CATEGORY_MAP[file_type]

        # Default to instruments
        return "instruments"

    def load_device(
        self,
        track_index: int,
        name: str,
        category: str | None = None,
        file_type: str | None = None,
    ) -> LoadResult:
        """Select a track and load a device by name from the browser."""
        resolved_category = self._resolve_category(name, category, file_type)

        # Select the target track first — browser.load_item loads onto selected track
        self._view.set_selected_track(track_index)
        time.sleep(0.05)

        # Search categories in priority order.
        # "sounds" has complete presets (instrument+effects chains) — best for
        # generic names like "pad", "bass", "lead". Try it first unless the
        # caller specified a category or we matched a known device name.
        categories_to_try = [resolved_category]
        if resolved_category not in ("audio_effects", "samples"):
            # Sounds presets are the best match for generic instrument names
            if "sounds" not in categories_to_try:
                categories_to_try.insert(0, "sounds")
        if resolved_category != "audio_effects":
            categories_to_try.append("audio_effects")
        if resolved_category != "instruments":
            categories_to_try.append("instruments")
        if resolved_category != "drums":
            categories_to_try.append("drums")

        for cat in categories_to_try:
            try:
                success, detail = self._browser.load_by_name(cat, name)
                if success:
                    return LoadResult(
                        success=True,
                        track_index=track_index,
                        device_name=detail,
                        source=f"browser:{cat}",
                    )
            except LoadError:
                continue

        return LoadResult(
            success=False,
            track_index=track_index,
            device_name=name,
            error=f"'{name}' not found in browser",
        )

    def load_from_library(
        self,
        track_index: int,
        query: str,
        category: str | None = None,
        file_type: str | None = None,
    ) -> LoadResult:
        """Search library DB first, then fall back to browser search."""
        # This delegates to load_device — library DB results can inform
        # the category/name but actual loading always goes through the browser
        return self.load_device(track_index, query, category, file_type)
