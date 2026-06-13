"""Tests for AbletonBridge lifecycle management."""

from __future__ import annotations

import pytest

from phase2_agent.bridge import AbletonBridge
from tests.conftest import MOCK_LISTEN_PORT, MOCK_RESPONSE_PORT


@pytest.fixture
def bridge(mock_server):
    """Provide an AbletonBridge pointed at the mock server."""
    b = AbletonBridge(
        send_port=MOCK_LISTEN_PORT,
        recv_port=MOCK_RESPONSE_PORT,
        timeout=2.0,
    )
    yield b
    b.disconnect()


class TestBridgeLifecycle:
    def test_starts_disconnected(self, bridge):
        assert not bridge.connected

    def test_ensure_connected(self, bridge):
        bridge.ensure_connected()
        assert bridge.connected

    def test_ensure_connected_idempotent(self, bridge):
        bridge.ensure_connected()
        bridge.ensure_connected()
        assert bridge.connected

    def test_disconnect(self, bridge):
        bridge.ensure_connected()
        assert bridge.connected
        bridge.disconnect()
        assert not bridge.connected

    def test_reconnect_after_disconnect(self, bridge):
        bridge.ensure_connected()
        bridge.disconnect()
        assert not bridge.connected
        bridge.ensure_connected()
        assert bridge.connected


class TestBridgeDomainAccess:
    def test_transport_accessible(self, bridge):
        bridge.ensure_connected()
        tempo = bridge.transport.get_tempo()
        assert tempo == 120.0

    def test_tracks_accessible(self, bridge):
        bridge.ensure_connected()
        count = bridge.tracks.count()
        assert count == 4

    def test_discovery_accessible(self, bridge):
        bridge.ensure_connected()
        session = bridge.discovery.get_session_structure()
        assert session.tempo == 120.0
        assert session.track_count == 4
