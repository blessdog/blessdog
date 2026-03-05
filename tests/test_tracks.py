"""Tests for track management."""

import pytest

from phase1_osc.errors import TrackNotFound
from phase1_osc.tracks import Tracks
from phase1_osc.types import TrackInfo


def test_count(conn):
    tracks = Tracks(conn)
    assert tracks.count() == 4


def test_get_names(conn):
    tracks = Tracks(conn)
    names = tracks.get_names()
    assert names == ["Bass", "Drums", "Keys", "Vox"]


def test_get_info(conn):
    tracks = Tracks(conn)
    info = tracks.get_info(0)
    assert isinstance(info, TrackInfo)
    assert info.name == "Bass"
    assert info.volume == pytest.approx(0.85)
    assert info.panning == 0.0
    assert info.mute is False
    assert info.arm is False


def test_get_info_keys(conn):
    tracks = Tracks(conn)
    info = tracks.get_info(2)
    assert info.name == "Keys"
    assert info.arm is True
    assert info.panning == pytest.approx(-0.2)


def test_get_all(conn):
    tracks = Tracks(conn)
    all_tracks = tracks.get_all()
    assert len(all_tracks) == 4
    assert all_tracks[1].name == "Drums"


def test_track_not_found(conn):
    tracks = Tracks(conn)
    with pytest.raises(TrackNotFound):
        tracks.get_info(99)


def test_set_volume_does_not_raise(conn):
    tracks = Tracks(conn)
    tracks.set_volume(0, 0.5)


def test_set_mute_does_not_raise(conn):
    tracks = Tracks(conn)
    tracks.set_mute(0, True)


def test_get_sends(conn):
    tracks = Tracks(conn)
    sends = tracks.get_sends(0)
    assert len(sends) == 2
    assert sends[0].value == 0.0
    assert sends[1].value == 0.5
