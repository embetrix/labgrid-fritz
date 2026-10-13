#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Embetrix Embedded Systems Solutions <ayoub.zaki@embetrix.com>

"""Power off, select SD mux DUT mode, attach serial, power on and watch output.

Run on the PC after acquiring the place. Ctrl-C closes the reader. The place
remains acquired until explicitly released, and the final power state is retained.
"""

import argparse
import math
import sys
import time

from labgrid import Environment
from pexpect import TIMEOUT


def boot(target, off_delay=3.0, output=None):
    output = sys.stdout.buffer if output is None else output
    # Bind all required hardware before taking any power-changing action.
    power = target.get_driver("FritzPowerDriver", activate=False)
    mux = target.get_driver("USBSDMuxDriver", activate=False)
    serial = target.get_driver("SerialDriver", activate=False)
    target.activate(power)
    target.activate(mux)
    power.off()  # Includes verification; any error aborts the sequence.
    time.sleep(off_delay)
    mux.set_mode("dut")
    if mux.get_mode().lower() not in ("dut", "client"):
        raise RuntimeError("SD mux did not enter DUT mode; leaving power off")
    target.activate(serial)  # Open before power-on to capture the first bytes.
    power.on()
    while True:
        try:
            data = serial.read(timeout=1.0)
        except TIMEOUT:
            continue
        output.write(data)
        output.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="labgrid environment YAML")
    parser.add_argument("--role", default="main")
    parser.add_argument("--off-delay", type=float, default=3.0)
    args = parser.parse_args()
    if not math.isfinite(args.off_delay) or args.off_delay < 0:
        parser.error("--off-delay must be finite and nonnegative")
    env = Environment(args.config)
    try:
        target = env.get_target(args.role)
        if target is None:
            raise RuntimeError("Configured target role does not exist")
        boot(target, off_delay=args.off_delay)
    except KeyboardInterrupt:
        print("\nConsole closed; power unchanged. Release the labgrid place when finished.")
    finally:
        env.cleanup()


if __name__ == "__main__":
    main()
