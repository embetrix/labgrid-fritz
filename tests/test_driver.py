# SPDX-License-Identifier: MIT
# Copyright 2026 Embetrix Embedded Systems Solutions <ayoub.zaki@embetrix.com>

from pathlib import Path
from unittest.mock import Mock

import pytest
from labgrid import Environment, Target
from labgrid.protocol import PowerProtocol

from labgrid_fritz import FritzPowerDriver, FritzPowerPort
import labgrid_fritz.driver as driver_module


@pytest.fixture
def setup(monkeypatch):
    agent = Mock()
    agent.get.return_value = False
    wrapper = Mock()
    wrapper.load.return_value = agent
    constructor = Mock(return_value=wrapper)
    monkeypatch.setattr(driver_module, "AgentWrapper", constructor)
    target = Target("board")
    port = FritzPowerPort(target, None, host="lab-host", device="board")
    driver = FritzPowerDriver(target, None)
    yield target, port, driver, agent, wrapper, constructor
    target.cleanup()


def test_power_protocol_and_remote_lifecycle(setup):
    target, port, driver, agent, wrapper, constructor = setup
    assert target.get_driver(PowerProtocol, activate=False) is driver
    target.activate(driver)
    constructor.assert_called_once_with("lab-host")
    agent.configure.assert_called_once_with("/etc/labgrid/fritz.json", "board", 10.0)
    agent.get.assert_called_once_with()
    agent_file = Path(wrapper.load.call_args.args[1]) / "fritz.py"
    assert agent_file.is_file()
    assert driver.get() is False
    driver.on()
    driver.off()
    driver.cycle()
    assert agent.set_power.call_args_list[0].args == (True, 10.0, 0.25)
    assert agent.set_power.call_args_list[1].args == (False, 10.0, 0.25)
    agent.cycle.assert_called_once_with(3.0, 10.0, 0.25)
    target.deactivate(driver)
    wrapper.close.assert_called_once_with()


def test_no_commands_before_activation(setup):
    _, _, driver, agent, _, _ = setup
    with pytest.raises(Exception):
        driver.on()
    agent.set_power.assert_not_called()


def test_failed_activation_closes_agent(setup):
    target, _, driver, agent, wrapper, _ = setup
    agent.configure.side_effect = RuntimeError("unreachable")
    with pytest.raises(RuntimeError, match="unreachable"):
        target.activate(driver)
    wrapper.close.assert_called_once_with()
    assert driver._agent is None


def test_environment_imports_and_binds_driver(tmp_path, monkeypatch):
    config = tmp_path / "environment.yaml"
    config.write_text('''imports:
  - labgrid_fritz
targets:
  main:
    resources:
      FritzPowerPort:
        host: lab-host
        device: board
    drivers:
      FritzPowerDriver:
        delay: 4
''')
    env = Environment(str(config))
    try:
        driver = env.get_target().get_driver(PowerProtocol, activate=False)
        assert isinstance(driver, FritzPowerDriver)
        assert driver.delay == 4.0
        assert driver.port.host == "lab-host"
    finally:
        env.cleanup()


@pytest.mark.parametrize("kwargs", [
    {"host": ""}, {"host": "-oProxyCommand=bad"}, {"host": "host\nother"},
    {"device": ""}, {"config_file": "relative.json"},
])
def test_resource_validation(kwargs):
    args = {"host": "lab-host", "device": "board"}
    args.update(kwargs)
    with pytest.raises(ValueError):
        FritzPowerPort(None, None, **args)


@pytest.mark.parametrize("kwargs", [
    {"delay": -1}, {"request_timeout": 0}, {"verify_timeout": float("nan")},
    {"poll_interval": float("inf")},
])
def test_driver_timing_validation(kwargs):
    target = Target("board")
    FritzPowerPort(target, None, host="lab-host", device="board")
    with pytest.raises(ValueError):
        FritzPowerDriver(target, None, **kwargs)
