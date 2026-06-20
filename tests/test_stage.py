"""Staging logic: assign roles to MIDI tracks, create/load only what's missing.

Uses in-memory fakes (not the UDP mock) to exercise stage_roles' decision
logic — reuse instrumented MIDI tracks, skip audio tracks, create tracks when
short, load instruments onto empty ones — deterministically and fast.
"""

from __future__ import annotations

from phase4_architect.stage import stage_roles


class _FakeTracks:
    def __init__(self, tracks):
        # tracks: list of dicts {midi: bool, devices: list[str]}
        self._t = tracks

    def count(self):
        return len(self._t)

    def is_midi(self, i):
        return self._t[i]["midi"]

    def device_names(self, i):
        return list(self._t[i]["devices"])

    def create_midi_track(self, index=-1):
        self._t.append({"midi": True, "devices": []})


class _FakeBrowser:
    def load_by_name(self, category, name):
        # instruments succeed; mimic Loader's category sweep landing on a hit
        if category in ("instruments", "sounds", "drums"):
            return True, name
        return False, ""


class _FakeView:
    def set_selected_track(self, i):
        self.selected = i


class _FakeBridge:
    def __init__(self, tracks):
        self.tracks = _FakeTracks(tracks)
        self.browser = _FakeBrowser()
        self.view = _FakeView()


class _LoadingBrowser(_FakeBrowser):
    """Browser that records loads onto the bridge's track store so a second
    stage_roles call sees the instrument as present (idempotency)."""

    def __init__(self, bridge):
        self._bridge = bridge
        self._pending_track = None

    def load_by_name(self, category, name):
        ok, detail = super().load_by_name(category, name)
        if ok and self._pending_track is not None:
            self._bridge.tracks._t[self._pending_track]["devices"].append(detail)
        return ok, detail


class _RecordingView(_FakeView):
    def __init__(self, browser):
        self._browser = browser

    def set_selected_track(self, i):
        super().set_selected_track(i)
        self._browser._pending_track = i


def test_reuses_instrumented_midi_track():
    bridge = _FakeBridge([
        {"midi": True, "devices": ["Wavetable"]},   # already has instrument
        {"midi": True, "devices": []},
    ])
    staged = stage_roles(bridge, ["chords", "bass"])
    assert staged[0].track_index == 0
    assert staged[0].created_track is False
    assert staged[0].loaded_instrument is False  # reused, nothing loaded
    assert staged[1].track_index == 1
    assert staged[1].loaded_instrument is True


def test_skips_audio_tracks():
    bridge = _FakeBridge([
        {"midi": False, "devices": []},   # audio — must be skipped
        {"midi": True, "devices": []},
        {"midi": False, "devices": []},   # audio
        {"midi": True, "devices": []},
    ])
    staged = stage_roles(bridge, ["chords", "bass"])
    assert [s.track_index for s in staged] == [1, 3]


def test_creates_tracks_when_short():
    bridge = _FakeBridge([
        {"midi": True, "devices": []},   # only one MIDI track
    ])
    staged = stage_roles(bridge, ["chords", "bass", "drums"])
    assert staged[0].created_track is False
    assert staged[1].created_track is True
    assert staged[2].created_track is True
    # all distinct tracks
    assert len({s.track_index for s in staged}) == 3


def test_drums_get_drum_rack():
    bridge = _FakeBridge([{"midi": True, "devices": []}])
    staged = stage_roles(bridge, ["drums"])
    assert staged[0].instrument == "Drum Rack"


def test_idempotent_second_run_reuses():
    bridge = _FakeBridge([
        {"midi": True, "devices": []},
        {"midi": True, "devices": []},
    ])
    # wire a browser/view that actually records loads onto the track store
    browser = _LoadingBrowser(bridge)
    bridge.browser = browser
    bridge.view = _RecordingView(browser)

    first = stage_roles(bridge, ["chords", "bass"])
    assert all(s.loaded_instrument for s in first)

    second = stage_roles(bridge, ["chords", "bass"])
    assert all(s.loaded_instrument is False for s in second)  # already present
    assert [s.track_index for s in second] == [0, 1]
