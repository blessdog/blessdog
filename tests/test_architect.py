"""Tests for Phase 4 — Session Architect: loader, templates, builder."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, call

import pytest

from phase4_architect.loader import Loader, LoadResult
from phase4_architect.templates import (
    TEMPLATES,
    SessionTemplate,
    TrackSpec,
    find_template,
    list_templates,
)
from phase4_architect.builder import SessionBuilder, SessionBuildResult

from phase2_agent import server
from phase2_agent.server import (
    build_session,
    browse_browser,
    load_device,
    track_setup,
    view_select,
)


# ---------------------------------------------------------------------------
# Template tests
# ---------------------------------------------------------------------------

class TestTemplates:
    def test_builtin_templates_exist(self):
        assert len(TEMPLATES) >= 4
        assert "dark_melodic_techno" in TEMPLATES
        assert "minimal_techno" in TEMPLATES
        assert "ambient" in TEMPLATES
        assert "hip_hop" in TEMPLATES

    def test_template_has_tracks(self):
        t = TEMPLATES["dark_melodic_techno"]
        assert len(t.tracks) > 0
        assert t.tempo == 128.0
        assert t.genre == "techno"

    def test_find_by_exact_name(self):
        t = find_template("dark_melodic_techno")
        assert t is not None
        assert t.name == "dark_melodic_techno"

    def test_find_by_keyword(self):
        t = find_template("techno")
        assert t is not None
        assert "techno" in t.genre

    def test_find_by_partial_name(self):
        t = find_template("ambient")
        assert t is not None
        assert t.name == "ambient"

    def test_find_not_found(self):
        t = find_template("nonexistent_genre_xyz")
        assert t is None

    def test_list_templates(self):
        result = list_templates()
        assert len(result) >= 4
        names = [t["name"] for t in result]
        assert "dark_melodic_techno" in names
        assert "hip_hop" in names
        # Each entry has required fields
        for entry in result:
            assert "name" in entry
            assert "description" in entry
            assert "genre" in entry
            assert "tempo" in entry
            assert "track_count" in entry

    def test_track_spec_defaults(self):
        ts = TrackSpec(name="Test", track_type="midi")
        assert ts.instrument is None
        assert ts.effects == []
        assert ts.color_index == 0
        assert ts.volume == 0.85


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------

class TestLoader:
    def setup_method(self):
        self.mock_view = MagicMock()
        self.mock_browser = MagicMock()
        self.loader = Loader(self.mock_view, self.mock_browser)

    def test_selects_track_before_loading(self):
        self.mock_browser.load_by_name.return_value = (True, "Wavetable")
        result = self.loader.load_device(2, "Wavetable")
        self.mock_view.set_selected_track.assert_called_once_with(2)
        assert result.success is True
        assert result.device_name == "Wavetable"

    def test_returns_success_result(self):
        self.mock_browser.load_by_name.return_value = (True, "Operator")
        result = self.loader.load_device(0, "Operator")
        assert result.success is True
        assert result.track_index == 0
        assert result.device_name == "Operator"
        assert "browser" in result.source

    def test_handles_not_found(self):
        self.mock_browser.load_by_name.return_value = (False, "FakeDevice")
        result = self.loader.load_device(0, "FakeDevice")
        assert result.success is False
        assert "not found" in result.error

    def test_resolves_known_instrument(self):
        self.mock_browser.load_by_name.return_value = (True, "Wavetable")
        self.loader.load_device(0, "Wavetable")
        # Should try instruments first for known instruments
        first_call = self.mock_browser.load_by_name.call_args_list[0]
        assert first_call[0][0] == "instruments"

    def test_resolves_known_effect(self):
        self.mock_browser.load_by_name.return_value = (True, "Auto Filter")
        self.loader.load_device(0, "Auto Filter")
        first_call = self.mock_browser.load_by_name.call_args_list[0]
        assert first_call[0][0] == "audio_effects"

    def test_explicit_category_override(self):
        self.mock_browser.load_by_name.return_value = (True, "Custom")
        self.loader.load_device(0, "Custom", category="samples")
        first_call = self.mock_browser.load_by_name.call_args_list[0]
        assert first_call[0][0] == "samples"


# ---------------------------------------------------------------------------
# Builder tests
# ---------------------------------------------------------------------------

class TestBuilder:
    def setup_method(self):
        self.mock_tracks = MagicMock()
        self.mock_transport = MagicMock()
        self.mock_view = MagicMock()
        self.mock_browser = MagicMock()
        self.loader = Loader(self.mock_view, self.mock_browser)
        self.builder = SessionBuilder(
            self.mock_tracks, self.mock_transport, self.loader,
        )

    def test_sets_tempo(self):
        template = SessionTemplate(
            name="test", description="test", genre="test", tempo=140.0,
            tracks=[TrackSpec(name="T", track_type="midi")],
        )
        self.mock_tracks.count.return_value = 1
        self.mock_browser.load_by_name.return_value = (False, "")
        result = self.builder.build(template)
        self.mock_transport.set_tempo.assert_called_once_with(140.0)
        assert result.tempo == 140.0

    def test_creates_tracks(self):
        template = SessionTemplate(
            name="test", description="test", genre="test", tempo=120.0,
            tracks=[
                TrackSpec(name="Kick", track_type="midi"),
                TrackSpec(name="Sample", track_type="audio"),
            ],
        )
        self.mock_tracks.count.return_value = 1
        self.mock_browser.load_by_name.return_value = (False, "")
        result = self.builder.build(template)
        assert result.tracks_created == 2
        self.mock_tracks.create_midi_track.assert_called_once_with(-1)
        self.mock_tracks.create_audio_track.assert_called_once_with(-1)

    def test_names_and_colors_tracks(self):
        template = SessionTemplate(
            name="test", description="test", genre="test", tempo=120.0,
            tracks=[TrackSpec(name="Bass", track_type="midi", color_index=69)],
        )
        self.mock_tracks.count.return_value = 1
        self.mock_browser.load_by_name.return_value = (False, "")
        self.builder.build(template)
        self.mock_tracks.set_name.assert_called_once_with(0, "Bass")
        self.mock_tracks.set_color_index.assert_called_once_with(0, 69)

    def test_handles_partial_failures(self):
        template = SessionTemplate(
            name="test", description="test", genre="test", tempo=120.0,
            tracks=[
                TrackSpec(name="Good", track_type="midi", instrument="Wavetable"),
                TrackSpec(name="Bad", track_type="midi", instrument="NonExistent"),
            ],
        )
        self.mock_tracks.count.return_value = 1
        # First call succeeds, second fails
        self.mock_browser.load_by_name.return_value = (False, "NonExistent")

        result = self.builder.build(template)
        assert result.tracks_created == 2
        # Both tracks created, but neither instrument loaded
        assert all(not tr.instrument_loaded for tr in result.track_results)

    def test_loads_effects(self):
        template = SessionTemplate(
            name="test", description="test", genre="test", tempo=120.0,
            tracks=[TrackSpec(
                name="Lead", track_type="midi",
                effects=["Reverb", "Delay"],
            )],
        )
        self.mock_tracks.count.return_value = 1
        self.mock_browser.load_by_name.return_value = (True, "Reverb")
        result = self.builder.build(template)
        assert "Reverb" in result.track_results[0].effects_loaded


# ---------------------------------------------------------------------------
# MCP tool tests (tools 22-26)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_bridge(monkeypatch):
    """Replace the module-level bridge with a fully-mocked version."""
    b = MagicMock()
    b.connected = True
    b.tracks.count.return_value = 5
    b.browser.categories.return_value = {"instruments": 10, "audio_effects": 8}
    b.browser.search.return_value = []
    b.browser.list_children.return_value = []
    b.browser.load_by_name.return_value = (True, "Wavetable")
    monkeypatch.setattr(server, "bridge", b)
    return b


class TestViewSelect:
    def test_select_track(self, mock_bridge):
        result = json.loads(view_select(track=2))
        assert result["selected_track"] == 2
        mock_bridge.view.set_selected_track.assert_called_once_with(2)

    def test_select_scene(self, mock_bridge):
        result = json.loads(view_select(scene=3))
        assert result["selected_scene"] == 3
        mock_bridge.view.set_selected_scene.assert_called_once_with(3)

    def test_select_nothing(self):
        result = json.loads(view_select())
        assert result == {}


class TestLoadDevice:
    def test_load_success(self, mock_bridge):
        mock_bridge.browser.load_by_name.return_value = (True, "Wavetable")
        result = json.loads(load_device(0, "Wavetable"))
        assert result["success"] is True
        assert result["device_name"] == "Wavetable"

    def test_load_not_found(self, mock_bridge):
        mock_bridge.browser.load_by_name.return_value = (False, "FakeSynth")
        result = json.loads(load_device(0, "FakeSynth"))
        assert result["success"] is False

    def test_with_category(self, mock_bridge):
        mock_bridge.browser.load_by_name.return_value = (True, "Reverb")
        result = json.loads(load_device(0, "Reverb", category="audio_effects"))
        assert result["success"] is True


class TestTrackSetup:
    def test_create_midi_with_instrument(self, mock_bridge):
        mock_bridge.browser.load_by_name.return_value = (True, "Wavetable")
        result = json.loads(track_setup("midi", "Lead", color=26, instrument="Wavetable"))
        assert result["track_type"] == "midi"
        assert result["name"] == "Lead"
        assert result["color_index"] == 26
        assert result["instrument_loaded"] is True
        mock_bridge.tracks.create_midi_track.assert_called_once_with(-1)
        mock_bridge.tracks.set_name.assert_called_once()

    def test_create_audio_no_instrument(self, mock_bridge):
        result = json.loads(track_setup("audio", "FX"))
        assert result["track_type"] == "audio"
        assert "instrument_loaded" not in result
        mock_bridge.tracks.create_audio_track.assert_called_once_with(-1)


class TestBrowseBrowser:
    def test_categories(self, mock_bridge):
        result = json.loads(browse_browser("categories"))
        assert "categories" in result
        mock_bridge.browser.categories.assert_called_once()

    def test_search(self, mock_bridge):
        from phase1_osc.browser import BrowserItem
        mock_bridge.browser.search.return_value = [
            BrowserItem(name="Wavetable", uri="uri:1", is_loadable=True, child_count=0),
        ]
        result = json.loads(browse_browser("search", category="instruments", query="wave"))
        assert result["count"] == 1
        assert result["results"][0]["name"] == "Wavetable"

    def test_search_missing_params(self):
        result = json.loads(browse_browser("search"))
        assert "error" in result

    def test_list_children(self, mock_bridge):
        result = json.loads(browse_browser("list_children", category="instruments"))
        assert "results" in result


class TestBuildSession:
    def test_list_available(self):
        result = json.loads(build_session(list_available=True))
        assert "templates" in result
        assert len(result["templates"]) >= 4

    def test_build_template(self, mock_bridge):
        mock_bridge.browser.load_by_name.return_value = (True, "Loaded")
        result = json.loads(build_session(template="dark_melodic_techno"))
        assert result["template"] == "dark_melodic_techno"
        assert result["tempo"] == 128.0
        assert result["tracks_created"] > 0

    def test_template_not_found(self):
        result = json.loads(build_session(template="nonexistent"))
        assert result["error"] == "NotFound"
        assert "available" in result

    def test_no_args(self):
        result = json.loads(build_session())
        assert "error" in result
