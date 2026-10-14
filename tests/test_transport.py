# SPDX-License-Identifier: MIT
# Copyright 2026 Embetrix Embedded Systems Solutions <ayoub.zaki@embetrix.com>

"""Exercise the real labgrid agent subprocess protocol without SSH or hardware."""
from pathlib import Path
import json

import pytest
from labgrid.util.agentwrapper import AgentException, AgentWrapper

import labgrid_fritz


def test_standalone_agent_transfer_and_operations(tmp_path):
    # Install a fake FRITZ! module inside the separate agent process, not this test.
    (tmp_path / "fake_backend.py").write_text('''
import sys
import types
class Home:
    def __init__(self, **kwargs):
        assert kwargs["address"] == "192.0.2.1"
        assert kwargs["password"] == "test-password"
        self.state = "OFF"
    def get_device_information_by_identifier(self, ain):
        assert ain == "12345 0000000"
        return {"NewPresent": "CONNECTED", "NewSwitchState": self.state}
    def set_switch(self, ain, on):
        self.state = "ON" if on else "OFF"
module = types.ModuleType("fritzconnection.lib.fritzhomeauto")
module.FritzHomeAutomation = Home
sys.modules["fritzconnection"] = types.ModuleType("fritzconnection")
sys.modules["fritzconnection.lib"] = types.ModuleType("fritzconnection.lib")
sys.modules[module.__name__] = module
methods = {}
''')
    (tmp_path / "password").write_text("test-password")
    config = tmp_path / "settings.json"
    config.write_text(json.dumps({"devices": {"board": {
        "address": "192.0.2.1", "username": "test-user",
        "ain": "12345 0000000", "password_file": str(tmp_path / "password"),
    }}}))
    agents = Path(labgrid_fritz.__file__).parent / "agents"
    with AgentWrapper() as wrapper:
        wrapper.load("fake_backend", str(tmp_path))
        agent = wrapper.load("fritz", str(agents))
        assert agent.configure(str(config), "board", 1.0) is None
        assert agent.get() is False
        agent.set_power(True, 1.0, 0.01)
        assert agent.get() is True
        agent.cycle(0.0, 1.0, 0.01)
        assert agent.get() is True
        agent.set_power(False, 1.0, 0.01)
        assert agent.get() is False
        with pytest.raises(AgentException, match="boolean"):
            agent.set_power("off")
