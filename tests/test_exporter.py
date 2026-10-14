# SPDX-License-Identifier: MIT
# Copyright 2026 Embetrix Embedded Systems Solutions <ayoub.zaki@embetrix.com>

"""Check the unmodified labgrid exporter path, without a running coordinator."""
import asyncio

from labgrid import Target, target_factory
from labgrid.remote.common import ResourceEntry
from labgrid.remote.exporter import Exporter, InvalidResourceRequestError
import pytest

from labgrid_fritz import FritzPowerPort


def test_stock_exporter_publishes_custom_resource_and_tracks_acquisition():
    async def scenario():
        exporter = object.__new__(Exporter)
        exporter.groups = {}
        exporter.hostname = "lab-host"
        exporter.isolated = True
        exporter.out_queue = asyncio.Queue()
        await exporter.add_resource("dut", "power", "FritzPowerPort", {
            "host": "lab-host", "device": "board",
            "config_file": "/etc/labgrid/fritz.json",
        })
        entry = exporter.groups["dut"]["power"]
        assert type(entry) is ResourceEntry
        assert entry.avail is True
        message = await exporter.out_queue.get()
        assert message.resource.path.group_name == "dut"
        assert "password" not in str(message)
        target = Target("dut")
        port = target_factory.make_resource(target, entry.cls, "power", entry.args)
        assert isinstance(port, FritzPowerPort)
        assert port.host == "lab-host"
        await exporter.acquire("dut", "power", "place-a")
        assert entry.acquired == "place-a"
        with pytest.raises(InvalidResourceRequestError):
            await exporter.acquire("dut", "power", "place-b")
        await exporter.release("dut", "power")
        assert entry.acquired is None
    asyncio.run(scenario())
