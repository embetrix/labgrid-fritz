# SPDX-License-Identifier: MIT
# Copyright 2026 Embetrix Embedded Systems Solutions <ayoub.zaki@embetrix.com>

"""Public resource metadata. Router credentials never belong here."""

import re

import attr
from labgrid.factory import target_factory
from labgrid.resource.common import NetworkResource


@target_factory.reg_resource
@attr.s(eq=False)
class FritzPowerPort(NetworkResource):
    """A named socket controlled by an agent on ``host`` (an SSH host/alias).

    ``config_file`` is read on that host. ``device`` selects a table in it.
    The host is the SSH execution host, not the FRITZ!Box.
    """

    device = attr.ib(validator=attr.validators.instance_of(str))
    config_file = attr.ib(
        default="/etc/labgrid/fritz.json",
        validator=attr.validators.instance_of(str),
    )

    def __attrs_post_init__(self):
        if not self.host or self.host.startswith("-") or any(c.isspace() for c in self.host):
            raise ValueError("host must be a nonempty SSH host or alias")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", self.device):
            raise ValueError("device must be a nonempty name using letters, digits, _, . or -")
        if not self.config_file.startswith("/") or "\x00" in self.config_file:
            raise ValueError("config_file must be an absolute path on the SSH host")
        super().__attrs_post_init__()
