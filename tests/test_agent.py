# SPDX-License-Identifier: MIT
# Copyright 2026 Embetrix Embedded Systems Solutions <ayoub.zaki@embetrix.com>

from types import SimpleNamespace
import json
import sys

import pytest

from labgrid_fritz.agents import fritz


@pytest.fixture
def config(tmp_path):
    secret = tmp_path / "password"
    secret.write_text("test-secret-only\n")
    path = tmp_path / "fritz.json"
    path.write_text(json.dumps({"devices": {"board": {
        "address": "192.0.2.1", "username": "test-user",
        "ain": "12345 0000000", "password_file": str(secret),
    }}}))
    return path


@pytest.fixture(autouse=True)
def reset_agent(monkeypatch):
    monkeypatch.setattr(fritz, "_home", None)
    monkeypatch.setattr(fritz, "_ain", None)


class FakeHome:
    def __init__(self):
        self.state = "OFF"
        self.commands = []

    def set_switch(self, ain, on):
        self.commands.append((ain, on))
        self.state = "ON" if on else "OFF"

    def get_device_information_by_identifier(self, ain):
        return {"NewPresent": "CONNECTED", "NewSwitchState": self.state}


@pytest.fixture
def home(monkeypatch):
    home = FakeHome()
    monkeypatch.setattr(fritz, "_home", home)
    monkeypatch.setattr(fritz, "_ain", "12345 0000000")
    return home


def install_library(monkeypatch, constructor):
    monkeypatch.setitem(sys.modules, "fritzconnection", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "fritzconnection.lib", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules, "fritzconnection.lib.fritzhomeauto",
        SimpleNamespace(FritzHomeAutomation=constructor),
    )


def test_configure_reads_password_on_agent_and_reuses_connection(config, monkeypatch):
    calls = []
    def constructor(**kwargs):
        calls.append(kwargs)
        return FakeHome()
    install_library(monkeypatch, constructor)
    assert fritz.configure(str(config), "board") is None
    assert fritz.get() is False
    fritz.set_power(True)
    assert fritz.get() is True
    assert len(calls) == 1
    assert calls[0]["password"] == "test-secret-only"
    assert calls[0]["port"] == 49000
    assert calls[0]["timeout"] == 10.0


def test_bad_config_does_not_leak_contents(config):
    config.write_text('{"password": "sensitive-value" invalid json')
    with pytest.raises(RuntimeError) as exc:
        fritz.configure(str(config), "board")
    assert "sensitive-value" not in str(exc.value)


def test_device_selection_uses_configured_router_and_socket(config, monkeypatch):
    settings = json.loads(config.read_text())
    settings["devices"]["second-outlet"] = {
        **settings["devices"]["board"],
        "address": "192.0.2.2", "port": 49001, "ain": "99999 0000001",
    }
    config.write_text(json.dumps(settings))
    calls = []
    devices = []
    def constructor(**kwargs):
        calls.append(kwargs)
        device = FakeHome()
        devices.append(device)
        return device
    install_library(monkeypatch, constructor)
    fritz.configure(str(config), "second-outlet")
    fritz.set_power(True)
    fritz.configure(str(config), "board")
    fritz.set_power(False)
    assert [(call["address"], call["port"]) for call in calls] == [
        ("192.0.2.2", 49001), ("192.0.2.1", 49000),
    ]
    assert devices[0].commands == [("99999 0000001", True)]
    assert devices[1].commands == [("12345 0000000", False)]


def test_unknown_device_is_rejected(config):
    with pytest.raises(RuntimeError, match="Invalid FRITZ"):
        fritz.configure(str(config), "missing")


def test_empty_password_is_rejected(config):
    config.with_name("password").write_text("")
    with pytest.raises(RuntimeError, match="password file"):
        fritz.configure(str(config), "board")


def test_failed_reconfigure_clears_existing_connection(home, config):
    with pytest.raises(RuntimeError):
        fritz.configure(str(config), "missing")
    with pytest.raises(RuntimeError, match="not configured"):
        fritz.get()


def test_connection_errors_are_sanitized(config, monkeypatch):
    def fail(**kwargs):
        raise ConnectionError("request contains test-secret-only")
    install_library(monkeypatch, fail)
    with pytest.raises(RuntimeError) as exc:
        fritz.configure(str(config), "board")
    assert str(exc.value) == "FRITZ! connection failed (ConnectionError)"


@pytest.mark.parametrize("response, message", [
    ({"NewPresent": "DISCONNECTED", "NewSwitchState": "OFF"}, "not present"),
    ({"NewSwitchState": "UNDEFINED"}, "no valid"),
    ({}, "no valid"),
    ({"NewSwitchState": "ON", "NewSwitchIsValid": "INVALID"}, "invalid"),
    (None, "invalid device response"),
])
def test_invalid_states_are_not_reported_as_off(home, monkeypatch, response, message):
    monkeypatch.setattr(home, "get_device_information_by_identifier", lambda ain: response)
    with pytest.raises(RuntimeError, match=message):
        fritz.get()


def test_switch_and_cycle_order(home, monkeypatch):
    events = []
    original = home.set_switch
    def switch(ain, on):
        events.append(("switch", on))
        original(ain, on)
    monkeypatch.setattr(home, "set_switch", switch)
    monkeypatch.setattr(fritz.time, "sleep", lambda delay: events.append(("sleep", delay)))
    fritz.cycle(3.0)
    assert events == [("switch", False), ("sleep", 3.0), ("switch", True)]
    assert fritz.get() is True


def test_verification_polls_delayed_state(home, monkeypatch):
    states = iter(["OFF", "OFF", "ON"])
    monkeypatch.setattr(home, "get_device_information_by_identifier",
                        lambda ain: {"NewSwitchState": next(states)})
    sleeps = []
    monkeypatch.setattr(fritz.time, "sleep", sleeps.append)
    fritz.set_power(True)
    assert len(sleeps) == 2


def test_failed_off_verification_aborts_cycle(home, monkeypatch):
    home.state = "ON"
    monkeypatch.setattr(home, "set_switch", lambda ain, on: home.commands.append(on))
    times = iter([0.0, 11.0])
    monkeypatch.setattr(fritz.time, "monotonic", lambda: next(times))
    with pytest.raises(RuntimeError, match="did not reach"):
        fritz.cycle()
    assert home.commands == [False]


@pytest.mark.parametrize("method", ["set_switch", "get_device_information_by_identifier"])
def test_operation_errors_are_sanitized(home, monkeypatch, method):
    def fail(*args, **kwargs):
        raise ValueError("secret-in-response")
    monkeypatch.setattr(home, method, fail)
    with pytest.raises(RuntimeError) as exc:
        fritz.set_power(True)
    assert "secret-in-response" not in str(exc.value)
    assert "ValueError" in str(exc.value)


@pytest.mark.parametrize("value", ["on", 1, None])
def test_non_boolean_switch_requests_never_reach_router(home, value):
    with pytest.raises(ValueError):
        fritz.set_power(value)
    assert not home.commands


@pytest.mark.parametrize("value", [-1, 0, float("nan"), float("inf")])
def test_invalid_timeout_never_switches(home, value):
    with pytest.raises(ValueError):
        fritz.set_power(True, verify_timeout=value)
    assert not home.commands
