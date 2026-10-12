# SPDX-License-Identifier: MIT
# Copyright 2026 Embetrix Embedded Systems Solutions <ayoub.zaki@embetrix.com>

"""Client-side labgrid driver; all FRITZ! traffic originates on the SSH host."""

import math
from pathlib import Path

import attr
from labgrid.driver.common import Driver
from labgrid.driver.exception import ExecutionError
from labgrid.driver.powerdriver import PowerResetMixin
from labgrid.factory import target_factory
from labgrid.protocol import PowerProtocol
from labgrid.step import step
from labgrid.util.agentwrapper import AgentWrapper


def _positive(instance, attribute, value):
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{attribute.name} must be finite and greater than zero")


def _nonnegative(instance, attribute, value):
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{attribute.name} must be finite and nonnegative")


@target_factory.reg_driver
@attr.s(eq=False)
class FritzPowerDriver(Driver, PowerResetMixin, PowerProtocol):
    """Switch and verify a FRITZ! socket using labgrid's SSH Python agent."""

    bindings = {"port": "FritzPowerPort"}
    delay = attr.ib(default=3.0, converter=float, validator=_nonnegative)
    request_timeout = attr.ib(default=10.0, converter=float, validator=_positive)
    verify_timeout = attr.ib(default=10.0, converter=float, validator=_positive)
    poll_interval = attr.ib(default=0.25, converter=float, validator=_positive)
    _wrapper = attr.ib(default=None, init=False, repr=False)
    _agent = attr.ib(default=None, init=False, repr=False)

    def on_activate(self):
        try:
            self._wrapper = AgentWrapper(self.port.host)
            self._agent = self._wrapper.load(
                "fritz", str(Path(__file__).parent / "agents")
            )
            self._agent.configure(
                self.port.config_file, self.port.device, self.request_timeout
            )
            # Static exporter availability is not a live hardware health check.
            self._agent.get()
        except Exception:
            self.on_deactivate()
            raise

    def on_deactivate(self):
        wrapper, self._wrapper = self._wrapper, None
        self._agent = None
        if wrapper is not None:
            try:
                wrapper.close()
            except (BrokenPipeError, EOFError, OSError):
                pass

    @Driver.check_active
    @step(result=True)
    def get(self):
        value = self._agent.get()
        if type(value) is not bool:
            raise ExecutionError("FRITZ! agent returned an invalid power state")
        return value

    @Driver.check_active
    @step()
    def on(self):
        self._agent.set_power(True, self.verify_timeout, self.poll_interval)

    @Driver.check_active
    @step()
    def off(self):
        self._agent.set_power(False, self.verify_timeout, self.poll_interval)

    @Driver.check_active
    @step()
    def cycle(self):
        self._agent.cycle(self.delay, self.verify_timeout, self.poll_interval)
