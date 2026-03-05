"""Tests for device enumeration and parameter control."""

import pytest

from phase1_osc.devices import Devices
from phase1_osc.types import DeviceInfo


def test_count(conn):
    devices = Devices(conn)
    assert devices.count(0) == 2
    assert devices.count(1) == 1
    assert devices.count(3) == 0


def test_get_names(conn):
    devices = Devices(conn)
    names = devices.get_names(0)
    assert names == ["Simpler", "Auto Filter"]


def test_get_info(conn):
    devices = Devices(conn)
    info = devices.get_info(0, 0)
    assert isinstance(info, DeviceInfo)
    assert info.name == "Simpler"
    assert info.class_name == "OriginalSimpler"


def test_get_parameters(conn):
    devices = Devices(conn)
    params = devices.get_parameters(0, 0)
    assert len(params) == 4
    assert params[0].name == "Device On"
    assert params[1].name == "Volume"
    assert params[1].value == pytest.approx(0.8)


def test_get_parameter_value(conn):
    devices = Devices(conn)
    val = devices.get_parameter_value(0, 0, 2)
    assert val == pytest.approx(0.01)  # Attack


def test_get_parameter_display(conn):
    devices = Devices(conn)
    display = devices.get_parameter_display(0, 0, 2)
    assert display == "0.01"


def test_set_parameter_does_not_raise(conn):
    devices = Devices(conn)
    devices.set_parameter_value(0, 0, 1, 0.5)
