#!/usr/bin/env python3
"""Step 2 - serve the map on this machine only (http://127.0.0.1:8765) and open it in your browser."""
import argparse
import functools
import http.server
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")  # always show the freshest events.js
        super().end_headers()

    def log_message(self, *args):
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    handler = functools.partial(Handler, directory=str(ROOT / "web"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)  # loopback only: private to this Mac
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Temporal Entanglements is running at {url}   (Ctrl-C to stop)")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
