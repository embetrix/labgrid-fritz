# SPDX-License-Identifier: MIT
# Copyright 2026 Embetrix Embedded Systems Solutions <ayoub.zaki@embetrix.com>

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from labgrid import Target
from labgrid.protocol import PowerProtocol
from labgrid.remote import client
from labgrid.resource.power import NetworkPowerPort
import labgrid.driver.powerdriver as power_module

from labgrid_fritz import FritzPowerDriver, FritzPowerPort
from labgrid_fritz.client import FritzClientSession, main
import labgrid_fritz.driver as driver_module


@pytest.fixture
def setup(monkeypatch):
    target = Target("test-place")
    monkeypatch.setattr(client.ClientSession, "_get_target", lambda *args: target)
    agent = Mock()
    agent.get.return_value = True
    wrapper = Mock()
    wrapper.load.return_value = agent
    constructor = Mock(return_value=wrapper)
    monkeypatch.setattr(driver_module, "AgentWrapper", constructor)
    session = object.__new__(FritzClientSession)
    session.get_acquired_place = lambda: SimpleNamespace(name="test-place")
    session.args = client.get_parser().parse_args(["-p", "test-place", "power", "get"])
    yield target, session, agent, constructor
    target.cleanup()


@pytest.mark.parametrize("action", ["get", "on", "off", "cycle"])
def test_power_without_yaml(setup, action, capsys):
    target, session, agent, constructor = setup
    FritzPowerPort(target, "socket", host="lab-host", device="outlet")
    session.args.action = action
    session.args.delay = 4.0
    session.power()
    constructor.assert_called_once_with("lab-host")
    agent.configure.assert_called_once_with("/etc/labgrid/fritz.json", "outlet", 10.0)
    if action == "get":
        assert "power for place test-place is on" in capsys.readouterr().out
        agent.set_power.assert_not_called()
    elif action == "cycle":
        agent.cycle.assert_called_once_with(4.0, 10.0, 0.25)
    else:
        agent.set_power.assert_called_once_with(action == "on", 10.0, 0.25)


def test_multiple_outlets_require_name_before_connecting(setup):
    target, session, _, constructor = setup
    for name in ("one", "two"):
        FritzPowerPort(target, name, host="lab-host", device=name)
    with pytest.raises(client.UserError, match="select one"):
        session.power()
    constructor.assert_not_called()
    session.args.name = "two"
    session.args.command = "pw"
    session.power()
    driver = target.get_driver(PowerProtocol, name="two", activate=False)
    assert driver.port.device == "two"


def test_explicit_driver_keeps_settings(setup):
    target, session, agent, _ = setup
    FritzPowerPort(target, "socket", host="lab-host", device="outlet")
    driver = FritzPowerDriver(target, "configured", request_timeout=22.0)
    session.power()
    assert target.drivers == [driver]
    agent.configure.assert_called_once_with("/etc/labgrid/fritz.json", "outlet", 22.0)


def test_unknown_name_does_not_switch_another_outlet(setup):
    target, session, _, constructor = setup
    FritzPowerPort(target, "socket", host="lab-host", device="outlet")
    session.args.name = "missing"
    with pytest.raises(client.UserError, match="no compatible resource"):
        session.power()
    constructor.assert_not_called()


def test_other_commands_do_not_bind_power(setup):
    target, session, _, constructor = setup
    FritzPowerPort(target, "socket", host="lab-host", device="outlet")
    session.args = client.get_parser().parse_args(["-p", "test-place", "console"])
    assert session._get_target(session.get_acquired_place()) is target
    assert not target.drivers
    constructor.assert_not_called()


def test_builtin_power_fallback(setup, monkeypatch, capsys):
    target, session, _, constructor = setup
    backend = Mock()
    backend.PORT = None
    backend.power_get.return_value = False
    monkeypatch.setattr(power_module, "import_module", lambda *args: backend)
    NetworkPowerPort(target, "pdu", model="test", host="pdu-host", index="1")
    session.power()
    backend.power_get.assert_called_once_with("pdu-host", None, "1")
    assert "power for place test-place is off" in capsys.readouterr().out
    constructor.assert_not_called()


@pytest.mark.parametrize("fails", [False, True])
def test_entrypoint_restores_upstream_session(monkeypatch, fails):
    original = client.ClientSession

    def upstream_main():
        assert client.ClientSession is FritzClientSession
        assert client.get_parser().parse_args(["power", "get"]).func is FritzClientSession.power
        if fails:
            raise SystemExit(2)
        return 0

    monkeypatch.setattr(client, "main", upstream_main)
    if fails:
        with pytest.raises(SystemExit):
            main()
    else:
        assert main() == 0
    assert client.ClientSession is original
