"""Tests for transport control."""

from phase1_osc.transport import Transport
from phase1_osc.types import TransportState


def test_get_tempo(conn):
    transport = Transport(conn)
    tempo = transport.get_tempo()
    assert tempo == 120.0


def test_get_is_playing(conn):
    transport = Transport(conn)
    playing = transport.get_is_playing()
    assert playing is False


def test_get_time(conn):
    transport = Transport(conn)
    t = transport.get_time()
    assert t == 0.0


def test_get_loop_on(conn):
    transport = Transport(conn)
    assert transport.get_loop_on() is True


def test_get_loop_start(conn):
    transport = Transport(conn)
    assert transport.get_loop_start() == 0.0


def test_get_loop_length(conn):
    transport = Transport(conn)
    assert transport.get_loop_length() == 8.0


def test_get_record_mode(conn):
    transport = Transport(conn)
    assert transport.get_record_mode() is False


def test_get_state(conn):
    transport = Transport(conn)
    state = transport.get_state()
    assert isinstance(state, TransportState)
    assert state.tempo == 120.0
    assert state.is_playing is False
    assert state.loop_on is True
    assert state.loop_length == 8.0


def test_play_does_not_raise(conn):
    transport = Transport(conn)
    transport.play()  # fire-and-forget, should not raise


def test_stop_does_not_raise(conn):
    transport = Transport(conn)
    transport.stop()


def test_set_tempo_does_not_raise(conn):
    transport = Transport(conn)
    transport.set_tempo(140.0)


def test_undo_redo_do_not_raise(conn):
    transport = Transport(conn)
    transport.undo()
    transport.redo()
