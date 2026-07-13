"""
web_bridge.py
────────────────────────
Development observer bridge for the Block Offset Engine.

This bridge does not modify the authoritative engine path. Instead, it
subscribes to committed block forwards from Array B via the same callback
pattern used by the mirror fan-out path, and exposes a WebSocket-friendly
state feed for a browser-based development viewer.

The implementation is intentionally lightweight and dependency-free so it can
run locally while the engine is still evolving.
"""

from __future__ import annotations

import base64
import hashlib
import json
import socket
import socketserver
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List

from block_engine.environment.block_layout import Block, WorldLayout


@dataclass
class WebBlockEntry:
    offset: int
    x: int
    y: int
    z: int
    block_type: int
    light_level: int
    flags: int
    metadata: int
    write_seq: int
    ts: float


class _WebSocketHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, bridge: "WebBridge", **kwargs):
        self._bridge = bridge
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/ws":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return

        accept = base64.b64encode(
            hashlib.sha1(key.encode("utf-8") + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest()
        ).decode("ascii")

        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()

        self._bridge._register_client(self.connection)

    def do_POST(self) -> None:  # noqa: N802
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)


class WebBridge:
    """A lightweight observer bridge that publishes block commits to browsers."""

    def __init__(
        self,
        layout: WorldLayout,
        *,
        host: str = "127.0.0.1",
        port: int = 7507,
    ) -> None:
        self._layout = layout
        self._host = host
        self._port = port
        self._lock = threading.Lock()
        self._blocks: Dict[int, WebBlockEntry] = {}
        self._clients: List[socket.socket] = []
        self._last_event_id = 0
        self._running = False
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._server = ThreadingHTTPServer(
            (self._host, self._port),
            lambda *args, **kwargs: _WebSocketHandler(*args, bridge=self, **kwargs),
        )
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="web-bridge",
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        self._server = None

    def _register_client(self, client: socket.socket) -> None:
        with self._lock:
            self._clients.append(client)
        client.settimeout(1.0)

    def _remove_client(self, client: socket.socket) -> None:
        with self._lock:
            try:
                self._clients.remove(client)
            except ValueError:
                pass

    def _send_frame(self, client: socket.socket, payload: bytes) -> None:
        if not payload:
            return
        length = len(payload)
        if length <= 125:
            header = bytes([0x81, length])
        elif length <= 65535:
            header = b"\x81\x7e" + length.to_bytes(2, "big")
        else:
            header = b"\x81\x7f" + length.to_bytes(8, "big")
        try:
            client.sendall(header + payload)
        except Exception:
            self._remove_client(client)

    def on_block_forward(self, offset: int, data: bytes, write_seq: int) -> bool:
        """Consume a committed block update from the mirror path."""
        try:
            block = Block.from_bytes(data)
        except Exception:
            return False

        x, y, z = self._layout.offset_to_coord(offset)
        entry = WebBlockEntry(
            offset=offset,
            x=x,
            y=y,
            z=z,
            block_type=block.block_type,
            light_level=block.light_level,
            flags=block.flags,
            metadata=block.metadata,
            write_seq=write_seq,
            ts=time.time(),
        )

        with self._lock:
            self._blocks[offset] = entry
            self._last_event_id += 1
            event_id = self._last_event_id

        self._broadcast({
            "type": "block_update",
            "event_id": event_id,
            "write_seq": write_seq,
            "offset": offset,
            "x": x,
            "y": y,
            "z": z,
            "block_type": int(block.block_type),
            "light_level": int(block.light_level),
            "flags": int(block.flags),
            "metadata": int(block.metadata),
        })
        return True

    def register_client(self, client: Any) -> None:
        with self._lock:
            self._clients.append(client)

    def _broadcast(self, payload: Dict[str, Any]) -> None:
        frame = json.dumps(payload).encode("utf-8")
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            try:
                self._send_frame(client, frame)
            except Exception:
                self._remove_client(client)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            blocks = [
                {
                    "offset": entry.offset,
                    "x": entry.x,
                    "y": entry.y,
                    "z": entry.z,
                    "block_type": int(entry.block_type),
                    "light_level": int(entry.light_level),
                    "flags": int(entry.flags),
                    "metadata": int(entry.metadata),
                    "write_seq": int(entry.write_seq),
                }
                for entry in sorted(self._blocks.values(), key=lambda item: item.offset)
            ]
            return {"type": "snapshot", "blocks": blocks}

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "client_count": len(self._clients),
                "block_count": len(self._blocks),
                "port": self._port,
            }
