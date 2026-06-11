#!/usr/bin/env python3
"""Serve paper survey static pages."""

import argparse
import http.server
import logging
import os
import signal
import sys
import time
from datetime import datetime
from functools import partial
from pathlib import Path

from config import BASE_DIR, load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
)
log = logging.getLogger("paper-survey")

START_TIME = time.monotonic()
REQUEST_COUNT = 0
ERROR_COUNT = 0


class ReuseHTTPServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    allow_reuse_port = True
    daemon_threads = True


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        global REQUEST_COUNT
        REQUEST_COUNT += 1
        start = time.monotonic()
        try:
            super().do_GET()
        except Exception:
            global ERROR_COUNT
            ERROR_COUNT += 1
            raise
        finally:
            elapsed = (time.monotonic() - start) * 1000
            if elapsed > 500:
                log.warning("Slow request: %s %.0fms", self.path, elapsed)

    def log_message(self, format, *args):
        log.info("%s - %s", self.client_address[0], format % args)

    def log_error(self, format, *args):
        global ERROR_COUNT
        ERROR_COUNT += 1
        log.error("%s - %s", self.client_address[0], format % args)


def handle_signal(signum, frame):
    name = signal.Signals(signum).name
    uptime = time.monotonic() - START_TIME
    log.info("Received %s after %.0fs uptime, %d requests served, %d errors. Shutting down.",
             name, uptime, REQUEST_COUNT, ERROR_COUNT)
    sys.exit(0)


def main():
    cfg = load_config()
    server_cfg = cfg.get("server", {})

    parser = argparse.ArgumentParser(description="Paper Survey HTTP Server")
    parser.add_argument(
        "-p", "--port", type=int,
        default=int(server_cfg.get("port", 7777)),
        help="port to listen on",
    )
    parser.add_argument(
        "-b", "--bind",
        default=str(server_cfg.get("host", "0.0.0.0")),
        help="address to bind",
    )
    parser.add_argument(
        "-d", "--dir",
        default=str(BASE_DIR / server_cfg.get("static_dir", "docs")),
        help="directory to serve",
    )
    args = parser.parse_args()

    static_dir = Path(args.dir).resolve()
    static_dir.mkdir(parents=True, exist_ok=True)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    index = static_dir / "index.html"
    if index.exists():
        size_kb = index.stat().st_size / 1024
        mtime = datetime.fromtimestamp(index.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        log.info("index.html: %.1f KB, last modified %s", size_kb, mtime)
    else:
        log.warning("index.html not found in %s", static_dir)

    handler = partial(Handler, directory=str(static_dir))
    server = ReuseHTTPServer((args.bind, args.port), handler)

    log.info("Server started on http://%s:%d", args.bind, args.port)
    log.info("Static dir: %s", static_dir)
    log.info("PID: %d", os.getpid())

    try:
        server.serve_forever()
    except SystemExit:
        server.shutdown()
    except Exception as e:
        log.critical("Server crashed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
