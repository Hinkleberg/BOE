#!/usr/bin/env python3
"""Simple local HTTP server for the development web viewer."""

from __future__ import annotations

import argparse
import http.server
import os
import socketserver
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "web"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    with socketserver.TCPServer((args.host, args.port), Handler) as httpd:
        print(f"Serving web viewer on http://{args.host}:{args.port}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
