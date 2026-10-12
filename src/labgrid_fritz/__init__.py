# SPDX-License-Identifier: MIT
# Copyright 2026 Embetrix Embedded Systems Solutions <ayoub.zaki@embetrix.com>

"""Import this module through labgrid's YAML ``imports`` to register the plugin."""

from .resource import FritzPowerPort
from .driver import FritzPowerDriver

__all__ = ["FritzPowerPort", "FritzPowerDriver"]
