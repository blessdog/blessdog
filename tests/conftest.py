"""Shared test fixtures."""

from __future__ import annotations

import time

import pytest

from phase1_osc.connection import AbletonOSCConnection
from tests.mock_osc_server import MockAbletonOSC

# Use high ports to avoid conflicts with real Ableton
MOCK_LISTEN_PORT = 17000  # mock listens here (replaces Ableton's 11000)
MOCK_RESPONSE_PORT = 17001  # mock responds here (replaces our 11001)


@pytest.fixture(scope="session")
def mock_server():
    """Start the mock AbletonOSC server once for the entire test session."""
    server = MockAbletonOSC(
        listen_port=MOCK_LISTEN_PORT,
        response_port=MOCK_RESPONSE_PORT,
    )
    server.start()
    time.sleep(0.1)  # let server bind
    yield server
    server.stop()


@pytest.fixture
def conn(mock_server):
    """Provide a connected AbletonOSCConnection against the mock server."""
    c = AbletonOSCConnection(
        send_port=MOCK_LISTEN_PORT,
        recv_port=MOCK_RESPONSE_PORT,
        timeout=2.0,
    )
    c.connect()
    yield c
    c.disconnect()
