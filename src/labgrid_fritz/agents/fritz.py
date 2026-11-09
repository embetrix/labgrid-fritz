# SPDX-License-Identifier: MIT
# Copyright 2026 Embetrix Embedded Systems Solutions <ayoub.zaki@embetrix.com>

"""Self-contained labgrid agent: only this module is loaded on the remote host.

Do not use relative imports: AgentWrapper executes this source outside the package.
Library exception messages are deliberately not sent back: they may contain secrets.
"""

import json
import math
import os
from pathlib import Path
import re
import time


_home = None
_ain = None


def _number(value, name, *, zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(value) or value < 0 or (not zero and value == 0):
        raise ValueError(f"invalid {name}")


def configure(config_file, device, request_timeout=10.0):
    """Read one socket's configuration and credentials entirely on this host."""
    global _home, _ain
    _home, _ain = None, None
    _number(request_timeout, "request_timeout")
    try:
        path = Path(config_file)
        if not path.is_absolute():
            raise ValueError()
        with path.open(encoding="utf-8") as stream:
            config = json.load(stream)
        settings = config["devices"][device]
        for field in ("address", "username", "ain"):
            if not isinstance(settings[field], str) or not settings[field].strip():
                raise ValueError()
        if any(key in settings for key in ("password", "password_env")):
            raise ValueError()
        if ("password_file" in settings) == ("password_credential" in settings):
            raise ValueError()
        if "password_credential" in settings:
            credential = settings["password_credential"]
            if not isinstance(credential, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", credential):
                raise ValueError()
            directory = Path(os.environ["CREDENTIALS_DIRECTORY"])
            if not directory.is_absolute():
                raise ValueError()
            password_path = directory / credential
        else:
            password_path = Path(settings["password_file"])
        if not password_path.is_absolute():
            raise ValueError()
        port = settings.get("port", 49000)
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        raise RuntimeError(
            "Invalid FRITZ! configuration: check the file, device name, address, "
            "username, AIN, port and password_file or systemd password_credential on the host"
        ) from None

    try:
        # Permit the conventional trailing newline of a text file; preserve spaces.
        password = password_path.read_text().rstrip("\r\n")
        if not password:
            raise ValueError()
    except (OSError, ValueError):
        raise RuntimeError("FRITZ! password file is unreadable or empty") from None

    try:
        from fritzconnection.lib.fritzhomeauto import FritzHomeAutomation
    except ImportError:
        raise RuntimeError("Install fritzconnection on the SSH host") from None

    try:
        home = FritzHomeAutomation(
            address=settings["address"],
            port=port,
            user=settings["username"],
            password=password,
            timeout=request_timeout,
            use_tls=False,
        )
    except Exception as error:
        raise RuntimeError(f"FRITZ! connection failed ({type(error).__name__})") from None
    _home, _ain = home, settings["ain"]


def _require_configured():
    if _home is None:
        raise RuntimeError("FRITZ! agent is not configured")


def get():
    """Return a boolean; never interpret an absent or unknown state as OFF."""
    _require_configured()
    try:
        info = _home.get_device_information_by_identifier(_ain)
    except Exception as error:
        raise RuntimeError(f"FRITZ! state query failed ({type(error).__name__})") from None
    if not isinstance(info, dict):
        raise RuntimeError("FRITZ! returned an invalid device response")
    present = info.get("NewPresent")
    if present is not None and str(present).upper() not in ("1", "TRUE", "CONNECTED"):
        raise RuntimeError("FRITZ! socket is not present")
    if info.get("NewSwitchIsValid") == "INVALID":
        raise RuntimeError("FRITZ! socket state is invalid")
    state = info.get("NewSwitchState")
    if state == "ON":
        return True
    if state == "OFF":
        return False
    raise RuntimeError("FRITZ! socket has no valid ON/OFF state")


def set_power(value, verify_timeout=10.0, poll_interval=0.25):
    """Set state once, then poll until it is observed or the deadline expires."""
    _require_configured()
    if type(value) is not bool:
        raise ValueError("power state must be a boolean")
    _number(verify_timeout, "verify_timeout")
    _number(poll_interval, "poll_interval")
    try:
        _home.set_switch(_ain, on=value)
    except Exception as error:
        raise RuntimeError(f"FRITZ! switching failed ({type(error).__name__})") from None
    deadline = time.monotonic() + verify_timeout
    while True:
        if get() is value:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("FRITZ! socket did not reach the requested power state")
        time.sleep(min(poll_interval, remaining))


def cycle(delay=3.0, verify_timeout=10.0, poll_interval=0.25):
    """Only start the off delay after OFF is confirmed. Abort on any failure."""
    _number(delay, "delay", zero=True)
    set_power(False, verify_timeout, poll_interval)
    time.sleep(delay)
    set_power(True, verify_timeout, poll_interval)


methods = {"configure": configure, "get": get, "set_power": set_power, "cycle": cycle}
