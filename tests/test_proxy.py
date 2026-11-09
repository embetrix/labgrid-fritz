# SPDX-License-Identifier: MIT
# Copyright 2026 Embetrix Embedded Systems Solutions <ayoub.zaki@embetrix.com>

from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
import threading
from unittest.mock import Mock

import pytest
import requests
from labgrid.remote.config import ResourceConfig

from labgrid_fritz import proxy


@pytest.fixture
def running_server(monkeypatch):
    state = {"on": True}
    backend = Mock()
    backend.get.side_effect = lambda: state["on"]
    backend.set_power.side_effect = lambda value, *args: state.update(on=value)
    monkeypatch.setattr(proxy, "fritz", backend)
    with proxy.PowerServer(0, "/host/fritz.json", {1: "one", 2: "two"}) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        with requests.Session() as http:
            http.trust_env = False
            yield httpd, http, backend
        httpd.shutdown()
        thread.join(timeout=5)


def test_stock_client_power_without_plugin_or_yaml(running_server):
    httpd, _, backend = running_server
    # Separate client process: reject every attempt to import this package.
    # Use upstream CLI dispatch and actual REST requests against the server;
    # only coordinator target retrieval and the SSH tunnel are substituted.
    script = r'''
import sys
class NoFritz:
    def find_spec(self, fullname, *args):
        if fullname.startswith("labgrid_fritz"):
            raise AssertionError("client must not import FRITZ code")
sys.meta_path.insert(0, NoFritz())
from types import SimpleNamespace
from labgrid import Target
from labgrid.resource import NetworkPowerPort
from labgrid.remote.client import ClientSession, get_parser
from labgrid.util.ssh import sshmanager

port = int(sys.argv[1])
def forward(proxy, host, remote_port):
    assert (proxy, host, remote_port) == ("lab-host", "127.0.0.1", port)
    return port
sshmanager.request_forward = forward
for action in ("get", "off", "get", "on", "get", "cycle"):
    target = Target("dut")
    resource = NetworkPowerPort(target, "power", model="rest",
        host=f"http://127.0.0.1:{port}/outlets/{{index}}", index="1")
    # RemotePlaceManager attaches exporter proxy metadata after construction.
    resource.extra = {"proxy": "lab-host", "proxy_required": True}
    session = object.__new__(ClientSession)
    session.args = get_parser().parse_args(["-p", "dut", "power", action, "--delay", "0"])
    session.get_acquired_place = lambda: SimpleNamespace(name="dut")
    session._get_target = lambda place: target
    try:
        session.args.func(session)
    finally:
        target.cleanup()
assert not any(name.startswith("labgrid_fritz") for name in sys.modules)
'''
    env = dict(os.environ, NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
    result = subprocess.run([sys.executable, "-c", script, str(httpd.server_port)],
                            capture_output=True, text=True, timeout=20, env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "power for place dut is on", "power for place dut is off", "power for place dut is on"]
    assert [call.args[0] for call in backend.set_power.call_args_list] == [False, True, False, True]


def test_outlet_mapping_and_loopback(running_server):
    httpd, http, backend = running_server
    assert httpd.server_address[0] == "127.0.0.1"
    url = f"http://127.0.0.1:{httpd.server_port}/outlets/2"
    assert http.get(url, timeout=5).text == "1"
    backend.configure.assert_called_once_with("/host/fritz.json", "two", 10.0)
    assert http.put(url, data=b"0", timeout=5).status_code == 200
    backend.set_power.assert_called_once_with(False, 10.0, 0.25)


@pytest.mark.parametrize("path,body,status", [
    ("/outlets/99", b"1", 404), ("/outlets/1", b"on", 400),
    ("/outlets/1", b"x", 400), ("/outlets/1", b"", 400),
])
def test_invalid_commands_do_not_reach_router(running_server, path, body, status):
    httpd, http, backend = running_server
    response = http.put(f"http://127.0.0.1:{httpd.server_port}{path}", data=body, timeout=5)
    assert response.status_code == status
    backend.configure.assert_not_called()
    backend.set_power.assert_not_called()


def test_backend_failures_are_errors_and_do_not_leak_secrets(running_server, caplog):
    httpd, http, backend = running_server
    url = f"http://127.0.0.1:{httpd.server_port}/outlets/1"
    backend.get.side_effect = RuntimeError("secret-router-password")
    response = http.get(url, timeout=5)
    assert response.status_code == 502
    backend.set_power.side_effect = RuntimeError("secret-router-password")
    response2 = http.put(url, data=b"1", timeout=5)
    assert response2.status_code == 502
    assert "secret-router-password" not in response.text + response2.text + caplog.text


def test_exporter_examples_use_generic_power():
    examples = Path(__file__).parents[1] / "examples"
    for name in ("exporter.yaml", "boot-exporter.yaml"):
        with redirect_stdout(io.StringIO()):
            config = ResourceConfig(str(examples / name))
        resource = config.data["dut"]["NetworkPowerPort"]
        assert resource["model"] == "rest"
        assert "FritzPowerPort" not in config.data["dut"]


@pytest.mark.parametrize("args", [
    ["--outlet", "0=one"], ["--outlet", "1=one", "--outlet", "1=two"],
    ["--outlet", "1=one", "--port", "70000"],
    ["--outlet", "1=one", "--request-timeout", "nan"],
])
def test_invalid_server_arguments(monkeypatch, args):
    monkeypatch.setattr(sys, "argv", ["labgrid-fritz-proxy", *args])
    with pytest.raises(SystemExit) as error:
        proxy.main()
    assert error.value.code == 2
