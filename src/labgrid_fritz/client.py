# SPDX-License-Identifier: MIT
# Copyright 2026 Embetrix Embedded Systems Solutions <ayoub.zaki@embetrix.com>

"""Labgrid CLI with automatic FRITZ! power driver binding."""

from labgrid.protocol import PowerProtocol
from labgrid.remote import client

from .driver import FritzPowerDriver
from .resource import FritzPowerPort


class FritzClientSession(client.ClientSession):
    """Keep upstream command handling and add FRITZ! power discovery."""

    def _get_target(self, place):
        target = super()._get_target(place)
        if self.args.command not in ("power", "pw"):
            return target

        name = self.args.name
        # Explicit configuration takes precedence, including its timings and
        # bindings. Leave ambiguity between configured drivers to labgrid.
        if any(isinstance(driver, PowerProtocol) and
               (name is None or driver.name == name)
               for driver in target.drivers):
            return target

        ports = [resource for resource in target.resources
                 if isinstance(resource, FritzPowerPort) and
                 (name is None or resource.name == name)]
        if len(ports) > 1:
            names = ", ".join(str(port.name) for port in ports)
            raise client.UserError(
                f"multiple FRITZ! power resources ({names}); select one with power --name NAME"
            )
        if ports:
            port = ports[0]
            target.set_binding_map({"port": port.name})
            FritzPowerDriver(target, name=port.name)
        return target


def main():
    # Labgrid 26 has no session/plugin injection API. Scope this substitution
    # to our entry point: both its parser and start_session use ClientSession.
    # Importing this module does not modify the stock labgrid client.
    original = client.ClientSession
    client.ClientSession = FritzClientSession
    try:
        return client.main()
    finally:
        client.ClientSession = original


if __name__ == "__main__":
    main()
