# SPDX-License-Identifier: MIT
# Copyright 2026 Embetrix Embedded Systems Solutions <ayoub.zaki@embetrix.com>

import importlib.util
import io
from pathlib import Path
from unittest.mock import Mock

import pytest


spec = importlib.util.spec_from_file_location(
    "boot_example", Path(__file__).parents[1] / "examples" / "boot.py"
)
boot_example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot_example)


def make_target(events):
    power, mux, serial = Mock(), Mock(), Mock()
    devices = {"FritzPowerDriver": power, "USBSDMuxDriver": mux, "SerialDriver": serial}
    target = Mock()
    target.get_driver.side_effect = lambda name, activate: devices[name]
    target.activate.side_effect = lambda driver: events.append(
        "serial-open" if driver is serial else "activate"
    )
    power.off.side_effect = lambda: events.append("off-confirmed")
    power.on.side_effect = lambda: events.append("on")
    mux.set_mode.side_effect = lambda mode: events.append("mux-" + mode)
    mux.get_mode.return_value = "dut"
    serial.read.side_effect = [b"U-Boot SPL\n", KeyboardInterrupt()]
    return target, power, mux, serial


def test_boot_opens_serial_before_power_on(monkeypatch):
    events = []
    target, _, _, _ = make_target(events)
    monkeypatch.setattr(boot_example.time, "sleep", lambda delay: events.append("off-delay"))
    output = io.BytesIO()
    with pytest.raises(KeyboardInterrupt):
        boot_example.boot(target, output=output)
    assert events == ["activate", "activate", "off-confirmed", "off-delay", "mux-dut", "serial-open", "on"]
    assert output.getvalue() == b"U-Boot SPL\n"


def test_wrong_mux_mode_leaves_power_off(monkeypatch):
    events = []
    target, power, mux, _ = make_target(events)
    mux.get_mode.return_value = "host"
    monkeypatch.setattr(boot_example.time, "sleep", lambda delay: None)
    with pytest.raises(RuntimeError, match="leaving power off"):
        boot_example.boot(target)
    power.on.assert_not_called()
    assert "serial-open" not in events
