# SPDX-License-Identifier: MIT
# Copyright 2026 Embetrix Embedded Systems Solutions <ayoub.zaki@embetrix.com>

"""Exporter-host proxy for labgrid's built-in NetworkPowerPort REST backend.

Only binds loopback. The isolated labgrid exporter supplies SSH proxy metadata.
GET /outlets/N returns 0 or 1; PUT accepts 0 or 1 and verifies the switch before
returning success. All router configuration and credentials remain on this host.
"""

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import logging
import math
import re

from .agents import fritz


class PowerServer(HTTPServer):
    # Deliberately single-threaded: the backend has one active device context.
    # Configure and operate together so requests cannot switch another outlet.
    def __init__(self, port, config_file, outlets, *, request_timeout=10.0,
                 verify_timeout=10.0, poll_interval=0.25):
        for value in (request_timeout, verify_timeout, poll_interval):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("timeouts and poll interval must be positive and finite")
        self.config_file = config_file
        self.outlets = dict(outlets)
        self.request_timeout = request_timeout
        self.verify_timeout = verify_timeout
        self.poll_interval = poll_interval
        super().__init__(("127.0.0.1", port), PowerHandler)

    def get_request(self):
        sock, address = super().get_request()
        sock.settimeout(10.0)
        return sock, address


class PowerHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Do not log request paths or arbitrary client-supplied data.
        pass

    def _reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _operate(self, write=False):
        match = re.fullmatch(r"/outlets/([1-9][0-9]*)", self.path)
        device = self.server.outlets.get(int(match[1])) if match else None
        if device is None:
            self._reply(404, b"Unknown outlet\n")
            return
        if write:
            if (self.headers.get_all("Content-Length") != ["1"] or
                    self.headers.get("Transfer-Encoding") is not None):
                self._reply(400, b"Expected a one-byte power state\n")
                return
            value = self.rfile.read(1)
            if value not in (b"0", b"1"):
                self._reply(400, b"Expected 0 or 1\n")
                return
        try:
            fritz.configure(self.server.config_file, device, self.server.request_timeout)
            if write:
                fritz.set_power(value == b"1", self.server.verify_timeout,
                                self.server.poll_interval)
                state = value == b"1"
            else:
                state = fritz.get()
            if type(state) is not bool:
                raise RuntimeError("Invalid backend state")
        except Exception as error:
            # Neither HTTP nor journal output may expose backend credentials.
            logging.error("Power operation failed (%s)", type(error).__name__)
            self._reply(502, b"Power operation failed\n")
            return
        self._reply(200, b"1" if state else b"0")

    def do_GET(self):
        self._operate()

    def do_PUT(self):
        self._operate(write=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="/etc/labgrid/fritz.json")
    parser.add_argument("--port", type=int, default=20409)
    parser.add_argument("--outlet", action="append", required=True, metavar="INDEX=DEVICE",
                        help="map a positive outlet index to a configured device; repeat for more outlets")
    parser.add_argument("--request-timeout", type=float, default=10.0)
    parser.add_argument("--verify-timeout", type=float, default=10.0)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    outlets = {}
    for mapping in args.outlet:
        match = re.fullmatch(r"([1-9][0-9]*)=([A-Za-z0-9_.-]+)", mapping)
        if not match or int(match[1]) in outlets:
            parser.error("--outlet requires a unique positive INDEX=DEVICE")
        outlets[int(match[1])] = match[2]
    try:
        server = PowerServer(args.port, args.config, outlets,
                             request_timeout=args.request_timeout,
                             verify_timeout=args.verify_timeout,
                             poll_interval=args.poll_interval)
    except ValueError as error:
        parser.error(str(error))
    with server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
