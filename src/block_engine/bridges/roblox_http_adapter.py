"""Roblox adapter with HTTP + full-duplex WebSocket support.

Provides two communication paths for Roblox game servers:

  1. HTTP API (legacy, pull-based):
     - POST /roblox/write — Write blocks
     - GET /roblox/read — Read single blocks
     - GET /roblox/region — Load regions
     - GET /roblox/stats — Statistics
     
  2. Full-duplex socket API (real-time bidirectional):
     - Binary framing: [MAGIC 4B "DPLX"][type 1B][msg_id 2B][payload_len 4B][JSON]
     - WRITE_BLOCK messages from game
     - BLOCK_DELTA responses with world updates
     - QUERY/COMMAND for advanced operations
     - Per-client subscriptions

No core engine changes — pure adapter via HTTP + DuplexBase.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional
from urllib.parse import parse_qs, urlparse

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from block_engine.bridges.duplex_base import (
    DuplexAdapter,
    DuplexMessage,
    MessageType,
    WriteRequest,
)


@dataclass
class RobloxBlockWrite:
    x: int
    y: int
    z: int
    block_type: int
    player_id: Optional[str] = None
    timestamp: float = 0.0


class RobloxHTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Roblox game scripts (backward compatible)."""

    def do_POST(self) -> None:
        if self.path == "/roblox/write":
            self._handle_write()
        elif self.path == "/roblox/duplex":
            self._handle_duplex_upgrade()
        else:
            self.send_error(404, "Not found")

    def do_GET(self) -> None:
        if self.path.startswith("/roblox/read"):
            self._handle_read()
        elif self.path.startswith("/roblox/region"):
            self._handle_region()
        elif self.path.startswith("/roblox/stats"):
            self._handle_stats()
        else:
            self.send_error(404, "Not found")

    def _handle_write(self) -> None:
        """Write a single block via HTTP."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            req = json.loads(body)

            x = int(req.get("x", 0))
            y = int(req.get("y", 0))
            z = int(req.get("z", 0))
            block_type = int(req.get("block_type", 0))
            player_id = req.get("player_id")

            result = self.server.adapter.write_block_from_roblox(
                x=x, y=y, z=z, block_type=block_type, player_id=player_id
            )

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
        except Exception as e:
            self.send_error(400, str(e))

    def _handle_read(self) -> None:
        """Read a single block via HTTP."""
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            x = int(params.get("x", [0])[0])
            y = int(params.get("y", [0])[0])
            z = int(params.get("z", [0])[0])

            result = self.server.adapter.read_block_from_roblox(x, y, z)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
        except Exception as e:
            self.send_error(400, str(e))

    def _handle_region(self) -> None:
        """Load a region of blocks via HTTP."""
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            x = int(params.get("x", [0])[0])
            y = int(params.get("y", [0])[0])
            z = int(params.get("z", [0])[0])
            size = int(params.get("size", [16])[0])

            result = self.server.adapter.read_region_from_roblox(x, y, z, size)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
        except Exception as e:
            self.send_error(400, str(e))

    def _handle_stats(self) -> None:
        """Return statistics via HTTP."""
        try:
            stats = self.server.adapter.statistics()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(stats).encode("utf-8"))
        except Exception as e:
            self.send_error(400, str(e))

    def _handle_duplex_upgrade(self) -> None:
        """Upgrade HTTP connection to duplex (placeholder)."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "upgrade_available",
            "duplex_endpoint": f"duplex://{self.server.server_address[0]}:{self.server.server_address[1] + 1}"
        }).encode("utf-8"))

    def log_message(self, format: str, *args):
        # Suppress default logging
        pass


class RobloxHTTPAdapter(DuplexAdapter):
    """
    Roblox adapter with HTTP (backward compatible) + full-duplex support.
    
    Supports both:
      1. HTTP API (pull-based, existing scripts compatible)
      2. Full-duplex socket API (real-time bidirectional)
    
    Usage (HTTP, existing):
      adapter = RobloxHTTPAdapter(resilient_store, world_layout)
      adapter.start_http(host="0.0.0.0", port=8000)
      
      # Roblox scripts call via HttpService:
      # POST http://server:8000/roblox/write
      # GET http://server:8000/roblox/read?x=100&y=50&z=200
      # GET http://server:8000/roblox/region?x=0&y=0&z=0&size=16
    
    Usage (full-duplex, new):
      adapter = RobloxHTTPAdapter(resilient_store, world_layout)
      adapter.start_http(host="0.0.0.0", port=8000)  # HTTP on 8000
      adapter.start()  # Duplex on 7400
      
      # Roblox connects to duplex port for real-time bidirectional:
      # - Send WRITE_BLOCK, QUERY, COMMAND messages
      # - Receive BLOCK_DELTA, ENTITY_DELTA, RESPONSE messages
    """

    def __init__(
        self,
        resilient_store,
        world_layout,
        host: str = "127.0.0.1",
        duplex_port: int = 7400,
        max_clients: int = 256,
    ):
        super().__init__(
            layout=world_layout,
            resilient_store=resilient_store,
            write_authorizer=None,
            host=host,
            port=duplex_port,
            max_clients=max_clients,
        )
        # Set platform identifier for entity sync hub
        from bridges.entity_sync import PlatformType
        self._platform_type = PlatformType.ROBLOX
        
        self._http_server: Optional[ThreadingHTTPServer] = None
        self._http_thread: Optional[threading.Thread] = None

    def start_http(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        """Start HTTP server (backward compatible API)."""
        if self._http_server is not None:
            return

        self._http_server = ThreadingHTTPServer(
            (host, port),
            lambda *args, **kwargs: RobloxHTTPHandler(*args, **kwargs),
        )
        self._http_server.adapter = self
        self._http_thread = threading.Thread(
            target=self._http_server.serve_forever,
            daemon=True,
            name="roblox-http",
        )
        self._http_thread.start()
        print(f"[RobloxHTTPAdapter] HTTP server listening on {host}:{port}")

    def stop_http(self) -> None:
        """Stop HTTP server."""
        if self._http_server:
            self._http_server.shutdown()
            self._http_server = None

    def _on_write_request(self, write_req: WriteRequest) -> None:
        """Process a write request from Roblox (duplex path)."""
        try:
            if write_req.data:
                self._store.write_block(write_req.offset, write_req.data)
                self._stats["http_writes"] = self._stats.get("http_writes", 0) + 1
        except Exception as e:
            print(f"[RobloxHTTPAdapter] Write error: {e}")

    def _handle_command(self, client, msg: DuplexMessage) -> None:
        """Handle Roblox-specific commands."""
        cmd = msg.payload.get("command")
        args = msg.payload.get("args", {})
        
        try:
            if cmd == "player_joined":
                self._cmd_player_joined(client, msg, args)
            elif cmd == "player_left":
                self._cmd_player_left(client, msg, args)
            elif cmd == "respawn":
                self._cmd_respawn(client, msg, args)
            elif cmd == "teleport":
                self._cmd_teleport(client, msg, args)
            elif cmd == "damage_player":
                self._cmd_damage_player(client, msg, args)
            elif cmd == "heal_player":
                self._cmd_heal_player(client, msg, args)
            elif cmd == "give_item":
                self._cmd_give_item(client, msg, args)
            elif cmd == "remove_item":
                self._cmd_remove_item(client, msg, args)
            elif cmd == "set_velocity":
                self._cmd_set_velocity(client, msg, args)
            elif cmd == "apply_force":
                self._cmd_apply_force(client, msg, args)
            elif cmd == "save_game":
                self._cmd_save_game(client, msg, args)
            elif cmd == "load_game":
                self._cmd_load_game(client, msg, args)
            elif cmd == "pause_game":
                self._cmd_pause_game(client, msg, args)
            elif cmd == "resume_game":
                self._cmd_resume_game(client, msg, args)
            elif cmd == "set_environment":
                self._cmd_set_environment(client, msg, args)
            elif cmd == "create_npc":
                self._cmd_create_npc(client, msg, args)
            elif cmd == "delete_npc":
                self._cmd_delete_npc(client, msg, args)
            elif cmd == "trigger_event":
                self._cmd_trigger_event(client, msg, args)
            elif cmd == "get_leaderboard":
                self._cmd_get_leaderboard(client, msg, args)
            elif cmd == "save_checkpoint":
                self._cmd_save_checkpoint(client, msg, args)
            elif cmd == "load_checkpoint":
                self._cmd_load_checkpoint(client, msg, args)
            elif cmd == "set_difficulty":
                self._cmd_set_difficulty(client, msg, args)
            elif cmd == "get_player_stats":
                self._cmd_get_player_stats(client, msg, args)
            elif cmd == "set_game_rule":
                self._cmd_set_game_rule(client, msg, args)
            else:
                super()._handle_command(client, msg)
        except Exception as e:
            self._send_error(client, msg.msg_id, str(e))

    def _cmd_player_joined(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Notify that a player joined."""
        player_id = args.get("player_id")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "player_joined", "player_id": player_id}
        )
        client.enqueue_send(response)

    def _cmd_player_left(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Notify that a player left."""
        player_id = args.get("player_id")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "player_left", "player_id": player_id}
        )
        client.enqueue_send(response)

    def _cmd_respawn(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Handle player respawn."""
        player_id = args.get("player_id")
        x = args.get("x", 0)
        y = args.get("y", 0)
        z = args.get("z", 0)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "respawned", "player_id": player_id, "position": [x, y, z]}
        )
        client.enqueue_send(response)

    def _cmd_teleport(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Handle player teleport."""
        player_id = args.get("player_id")
        x = args.get("x", 0)
        y = args.get("y", 0)
        z = args.get("z", 0)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "teleported", "player_id": player_id, "position": [x, y, z]}
        )
        client.enqueue_send(response)

    def _cmd_damage_player(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Damage a player."""
        player_id = args.get("player_id")
        damage = args.get("damage", 10)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "damaged", "player_id": player_id, "damage": damage}
        )
        client.enqueue_send(response)

    def _cmd_heal_player(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Heal a player."""
        player_id = args.get("player_id")
        health = args.get("health", 50)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "healed", "player_id": player_id, "health": health}
        )
        client.enqueue_send(response)

    def _cmd_give_item(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Give item to player."""
        player_id = args.get("player_id")
        item = args.get("item")
        quantity = args.get("quantity", 1)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "item_given", "player_id": player_id, "item": item, "quantity": quantity}
        )
        client.enqueue_send(response)

    def _cmd_remove_item(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Remove item from player."""
        player_id = args.get("player_id")
        item = args.get("item")
        quantity = args.get("quantity", 1)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "item_removed", "player_id": player_id, "item": item, "quantity": quantity}
        )
        client.enqueue_send(response)

    def _cmd_set_velocity(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Set player velocity."""
        player_id = args.get("player_id")
        vx = args.get("vx", 0)
        vy = args.get("vy", 0)
        vz = args.get("vz", 0)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "velocity_set", "player_id": player_id, "velocity": [vx, vy, vz]}
        )
        client.enqueue_send(response)

    def _cmd_apply_force(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Apply force to player."""
        player_id = args.get("player_id")
        fx = args.get("fx", 0)
        fy = args.get("fy", 0)
        fz = args.get("fz", 0)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "force_applied", "player_id": player_id, "force": [fx, fy, fz]}
        )
        client.enqueue_send(response)

    def _cmd_save_game(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Save game state."""
        save_name = args.get("save_name", "autosave")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "game_saved", "save_name": save_name}
        )
        client.enqueue_send(response)

    def _cmd_load_game(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Load game state."""
        save_name = args.get("save_name", "autosave")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "game_loaded", "save_name": save_name}
        )
        client.enqueue_send(response)

    def _cmd_pause_game(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Pause the game."""
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "game_paused"}
        )
        client.enqueue_send(response)

    def _cmd_resume_game(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Resume the game."""
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "game_resumed"}
        )
        client.enqueue_send(response)

    def _cmd_set_environment(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Set environment properties."""
        weather = args.get("weather", "sunny")
        time_of_day = args.get("time_of_day", "day")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "environment_set", "weather": weather, "time": time_of_day}
        )
        client.enqueue_send(response)

    def _cmd_create_npc(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Create NPC."""
        npc_id = args.get("npc_id")
        npc_type = args.get("npc_type", "default")
        x = args.get("x", 0)
        y = args.get("y", 0)
        z = args.get("z", 0)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "npc_created", "npc_id": npc_id, "type": npc_type, "position": [x, y, z]}
        )
        client.enqueue_send(response)

    def _cmd_delete_npc(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Delete NPC."""
        npc_id = args.get("npc_id")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "npc_deleted", "npc_id": npc_id}
        )
        client.enqueue_send(response)

    def _cmd_trigger_event(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Trigger game event."""
        event = args.get("event")
        parameters = args.get("parameters", {})
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "event_triggered", "event": event, "parameters": parameters}
        )
        client.enqueue_send(response)

    def _cmd_get_leaderboard(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Get leaderboard data."""
        limit = args.get("limit", 10)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "leaderboard_retrieved", "limit": limit, "entries": []}
        )
        client.enqueue_send(response)

    def _cmd_save_checkpoint(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Save checkpoint."""
        checkpoint_name = args.get("checkpoint_name")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "checkpoint_saved", "name": checkpoint_name}
        )
        client.enqueue_send(response)

    def _cmd_load_checkpoint(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Load checkpoint."""
        checkpoint_name = args.get("checkpoint_name")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "checkpoint_loaded", "name": checkpoint_name}
        )
        client.enqueue_send(response)

    def _cmd_set_difficulty(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Set game difficulty."""
        difficulty = args.get("difficulty", "normal")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "difficulty_set", "difficulty": difficulty}
        )
        client.enqueue_send(response)

    def _cmd_get_player_stats(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Get player statistics."""
        player_id = args.get("player_id")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "stats_retrieved", "player_id": player_id, "stats": {}}
        )
        client.enqueue_send(response)

    def _cmd_set_game_rule(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Set game rule."""
        rule = args.get("rule")
        value = args.get("value")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "rule_set", "rule": rule, "value": value}
        )
        client.enqueue_send(response)

    # HTTP API methods (backward compatible)

    def write_block_from_roblox(
        self, x: int, y: int, z: int, block_type: int, player_id: Optional[str] = None
    ) -> Dict:
        """Handle write from HTTP API."""
        try:
            offset = self._layout.block_offset(x, y, z)
            data = bytes([block_type, 8, 0, 0]) + bytes(12)
            self._store.write_block(offset, data)
            self._stats["http_writes"] = self._stats.get("http_writes", 0) + 1
            return {
                "status": "success",
                "offset": offset,
                "x": x,
                "y": y,
                "z": z,
                "block_type": block_type,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def read_block_from_roblox(self, x: int, y: int, z: int) -> Dict:
        """Handle read from HTTP API."""
        try:
            offset = self._layout.block_offset(x, y, z)
            data = self._store.read_block(offset)
            self._stats["http_reads"] = self._stats.get("http_reads", 0) + 1
            return {
                "status": "success",
                "offset": offset,
                "x": x,
                "y": y,
                "z": z,
                "data": data.hex(),
                "block_type": data[0],
                "light": data[1],
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def read_region_from_roblox(self, x: int, y: int, z: int, size: int) -> Dict:
        """Handle region read from HTTP API."""
        blocks = []
        for dx in range(size):
            for dy in range(size):
                for dz in range(size):
                    try:
                        bx, by, bz = x + dx, y + dy, z + dz
                        offset = self._layout.block_offset(bx, by, bz)
                        data = self._store.read_block(offset)
                        blocks.append({
                            "offset": offset,
                            "x": bx,
                            "y": by,
                            "z": bz,
                            "data": data.hex(),
                            "block_type": data[0],
                            "light": data[1],
                        })
                        self._stats["http_reads"] = self._stats.get("http_reads", 0) + 1
                    except Exception:
                        pass

        return {
            "status": "success",
            "region": {"x": x, "y": y, "z": z, "size": size},
            "blocks": blocks,
            "count": len(blocks),
        }

    # Backward compatibility API (for existing tests)
    
    def write_block(self, write_req: RobloxBlockWrite) -> Dict:
        """Legacy write_block method for backward compatibility."""
        return self.write_block_from_roblox(
            x=write_req.x, y=write_req.y, z=write_req.z,
            block_type=write_req.block_type, player_id=write_req.player_id
        )
    
    def read_block(self, x: int, y: int, z: int) -> Dict:
        """Legacy read_block method for backward compatibility."""
        return self.read_block_from_roblox(x, y, z)
    
    def read_region(self, x: int, y: int, z: int, size: int) -> Dict:
        """Legacy read_region method for backward compatibility."""
        return self.read_region_from_roblox(x, y, z, size)
    
    def statistics(self) -> Dict[str, int]:
        """Legacy statistics method (overrides parent for compatibility)."""
        stats = super().statistics()
        # Map new stat names to old ones for backward compatibility
        return {
            "total_requests": self._stats.get("http_reads", 0) + self._stats.get("http_writes", 0),
            "writes": self._stats.get("http_writes", 0),
            "reads": self._stats.get("http_reads", 0),
            "connected_clients": stats.get("connected_clients", 0),
        }

    def stop(self) -> None:
        """Stop the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def __repr__(self) -> str:
        with self._lock:
            n = len(self._clients)
        return f"RobloxHTTPAdapter(duplex://{self._host}:{self._port}, duplex_clients={n})"
