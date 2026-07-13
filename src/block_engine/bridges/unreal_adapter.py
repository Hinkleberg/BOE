"""
unreal_adapter.py
─────────────────
Full-duplex Unreal Engine 5.x integration adapter.

Provides bidirectional, real-time communication between Block-Image Engine
and Unreal Engine 5.x:

  Server → Client (Unreal):
    - Block deltas (compressed binary or JSON)
    - Entity state updates (positions, velocities, health)
    - Simulation events (spawns, despawns, collisions)
    - Telemetry (FPS, entity counts, memory stats)

  Client (Unreal) → Server:
    - Write block requests (from gameplay, destruction, building)
    - Entity movement/state updates
    - Query requests (read blocks, ray casts)
    - Commands (pause, reset, teleport, load region)

Wire protocol:
  - Binary framing: [MAGIC 4B "DPLX"][type 1B][msg_id 2B][payload_len 4B][JSON payload]
  - Message types: BLOCK_DELTA, ENTITY_DELTA, WRITE_BLOCK, QUERY, COMMAND, ACK, ERROR
  - Per-client subscription filtering
  - Automatic ACKs for write requests
  - Heartbeat/ping-pong for connection health

This adapter DOES NOT modify the core engine.
Core remains pure storage-native arithmetic; this is a translation layer only.

Usage:
    from block_engine.bridges.unreal_adapter import UnrealAdapter

    adapter = UnrealAdapter(
        layout, resilient_store,
        host="127.0.0.1", port=7100,
        write_authorizer=my_auth_policy,
    )
    adapter.start()

    # Optionally, wire into render feed for automatic deltas:
    feed.connect_client(
        client_id=99,
        send_cb=adapter.on_render_delta,
        view_radius=64,
    )
    
    # Or poll for new writes:
    while True:
        write_req = adapter.get_next_write()
        if write_req:
            resilient_store.write_block(write_req.offset, write_req.data)
"""

from __future__ import annotations

import json
import queue
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from block_engine.bridges.duplex_base import (
    DuplexAdapter,
    DuplexMessage,
    MessageType,
    WriteRequest,
)


@dataclass
class UnrealEntityUpdate:
    """Entity state from Unreal game code."""
    entity_id: int
    x: float
    y: float
    z: float
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    yaw: float = 0.0
    pitch: float = 0.0
    health: float = 100.0
    flags: int = 0


class UnrealAdapter(DuplexAdapter):
    """
    Full-duplex adapter for Unreal Engine 5.x.
    
    Extends DuplexAdapter with:
      - RenderDelta integration for automatic server→client streaming
      - Unreal-specific command handling
      - Entity lifecycle management
      - Event system for client-side gameplay triggers
    """
    
    def __init__(
        self,
        layout,
        resilient_store,
        write_authorizer: Optional[Callable] = None,
        host: str = "127.0.0.1",
        port: int = 7100,
        max_clients: int = 256,
    ):
        super().__init__(
            layout=layout,
            resilient_store=resilient_store,
            write_authorizer=write_authorizer,
            host=host,
            port=port,
            max_clients=max_clients,
            heartbeat_interval=5.0,
            client_timeout=30.0,
        )
        self._write_queue: queue.Queue = queue.Queue(maxsize=10000)
        self._entity_updates: Dict[int, UnrealEntityUpdate] = {}
        self._event_callbacks: Dict[str, list] = {}  # event_type → [callback, ...]
    
    def on_render_delta(self, delta) -> None:
        """
        Wire this as RenderFeed send_cb for automatic streaming.
        Converts RenderDelta to DuplexMessages and broadcasts.
        
        Usage:
            feed.connect_client(
                client_id=99,
                send_cb=adapter.on_render_delta,
                view_radius=64,
            )
        """
        # Broadcast block deltas to clients subscribed to "blocks" channel
        if delta.block_deltas:
            msg = DuplexMessage(
                msg_type=MessageType.BLOCK_DELTA,
                msg_id=0,
                payload={
                    "tick": delta.tick,
                    "blocks": [
                        {
                            "offset": bd.offset,
                            "data": bd.data.hex(),
                        }
                        for bd in delta.block_deltas
                    ]
                }
            )
            self.broadcast_delta(msg, channels=["blocks"])
        
        # Broadcast entity deltas to clients subscribed to "entities" channel
        if delta.entity_deltas:
            msg = DuplexMessage(
                msg_type=MessageType.ENTITY_DELTA,
                msg_id=0,
                payload={
                    "tick": delta.tick,
                    "entities": [
                        {
                            "entity_id": ed.entity_id,
                            "x": ed.x,
                            "y": ed.y,
                            "z": ed.z,
                            "health": ed.health,
                            "last_tick": ed.last_tick,
                        }
                        for ed in delta.entity_deltas
                    ]
                }
            )
            self.broadcast_delta(msg, channels=["entities"])
    
    def _on_write_request(self, write_req: WriteRequest) -> None:
        """
        Process a write request from Unreal.
        
        This runs in a background thread (write processor).
        Calls write to resilient_store after authorization.
        """
        try:
            data = write_req.data
            if data:
                self._store.write_block(write_req.offset, data)
            
            # Fire event for listeners
            self._fire_event("write_complete", {
                "client_id": write_req.client_id,
                "offset": write_req.offset,
                "timestamp": write_req.timestamp,
            })
        except Exception as e:
            self._fire_event("write_error", {
                "client_id": write_req.client_id,
                "offset": write_req.offset,
                "error": str(e),
            })
    
    def _handle_command(self, client, msg: DuplexMessage) -> None:
        """
        Handle Unreal-specific commands:
          - move_entity: Update entity position + velocity
          - spawn_entity: Create new entity
          - despawn_entity: Remove entity
          - load_region: Pre-load a region
          - query_blocks: Read multiple blocks
          - ray_cast: Trace a ray and find intersecting blocks
        """
        cmd = msg.payload.get("command")
        args = msg.payload.get("args", {})
        
        try:
            if cmd == "move_entity":
                self._cmd_move_entity(client, msg, args)
            elif cmd == "spawn_entity":
                self._cmd_spawn_entity(client, msg, args)
            elif cmd == "despawn_entity":
                self._cmd_despawn_entity(client, msg, args)
            elif cmd == "load_region":
                self._cmd_load_region(client, msg, args)
            elif cmd == "query_blocks":
                self._cmd_query_blocks(client, msg, args)
            elif cmd == "ray_cast":
                self._cmd_ray_cast(client, msg, args)
            elif cmd == "statistics":
                self._cmd_statistics(client, msg, args)
            else:
                self._send_error(client, msg.msg_id, f"Unknown command: {cmd}")
        except Exception as e:
            self._send_error(client, msg.msg_id, str(e))
    
    def _cmd_move_entity(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Process entity movement command from Unreal."""
        entity_id = args.get("entity_id")
        update = UnrealEntityUpdate(
            entity_id=entity_id,
            x=args.get("x", 0.0),
            y=args.get("y", 0.0),
            z=args.get("z", 0.0),
            vx=args.get("vx", 0.0),
            vy=args.get("vy", 0.0),
            vz=args.get("vz", 0.0),
            yaw=args.get("yaw", 0.0),
            pitch=args.get("pitch", 0.0),
            health=args.get("health", 100.0),
            flags=args.get("flags", 0),
        )
        self._entity_updates[entity_id] = update
        self._fire_event("entity_moved", {"entity_id": entity_id, "update": update})
        
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "ok", "entity_id": entity_id}
        )
        client.enqueue_send(response)
    
    def _cmd_spawn_entity(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Spawn an entity in the world."""
        entity_id = args.get("entity_id")
        self._fire_event("entity_spawned", {"entity_id": entity_id, "args": args})
        
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "ok", "entity_id": entity_id}
        )
        client.enqueue_send(response)
    
    def _cmd_despawn_entity(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Despawn an entity from the world."""
        entity_id = args.get("entity_id")
        self._entity_updates.pop(entity_id, None)
        self._fire_event("entity_despawned", {"entity_id": entity_id})
        
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "ok", "entity_id": entity_id}
        )
        client.enqueue_send(response)
    
    def _cmd_load_region(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Pre-load a region of blocks."""
        x = args.get("x", 0)
        y = args.get("y", 0)
        z = args.get("z", 0)
        size = args.get("size", 16)
        
        blocks = []
        for dx in range(size):
            for dy in range(size):
                for dz in range(size):
                    try:
                        offset = self._layout.block_offset(x + dx, y + dy, z + dz)
                        data = self._store.read_block(offset)
                        blocks.append({
                            "offset": offset,
                            "x": x + dx,
                            "y": y + dy,
                            "z": z + dz,
                            "data": data.hex(),
                        })
                    except Exception:
                        pass
        
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={
                "status": "ok",
                "region": {"x": x, "y": y, "z": z, "size": size},
                "block_count": len(blocks),
                "blocks": blocks,
            }
        )
        client.enqueue_send(response)
    
    def _cmd_query_blocks(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Query multiple blocks (e.g., for LOD streaming)."""
        offsets = args.get("offsets", [])
        blocks = []
        
        for offset in offsets:
            try:
                data = self._store.read_block(offset)
                blocks.append({"offset": offset, "data": data.hex(), "status": "ok"})
            except Exception as e:
                blocks.append({"offset": offset, "status": "error", "error": str(e)})
        
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"blocks": blocks}
        )
        client.enqueue_send(response)
    
    def _cmd_ray_cast(self, client, msg: DuplexMessage, args: Dict) -> None:
        """
        Simple ray casting query.
        Return first solid block hit along ray.
        """
        origin_x = args.get("origin_x", 0.0)
        origin_y = args.get("origin_y", 0.0)
        origin_z = args.get("origin_z", 0.0)
        direction_x = args.get("direction_x", 1.0)
        direction_y = args.get("direction_y", 0.0)
        direction_z = args.get("direction_z", 0.0)
        max_distance = args.get("max_distance", 1000.0)
        
        # Simple linear march (placeholder; subclass can implement proper raycasting)
        step = 1.0
        steps = int(max_distance / step)
        hit = None
        
        for i in range(steps):
            x = int(origin_x + direction_x * i * step)
            y = int(origin_y + direction_y * i * step)
            z = int(origin_z + direction_z * i * step)
            
            try:
                offset = self._layout.block_offset(x, y, z)
                data = self._store.read_block(offset)
                # Assume block type 0 = air (empty)
                if data[0] != 0:
                    hit = {
                        "offset": offset,
                        "x": x, "y": y, "z": z,
                        "distance": i * step,
                        "data": data.hex(),
                    }
                    break
            except Exception:
                pass
        
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"hit": hit if hit else None}
        )
        client.enqueue_send(response)
    
    def _cmd_statistics(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Return adapter statistics."""
        stats = self.statistics()
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload=stats
        )
        client.enqueue_send(response)
    
    def _fire_event(self, event_type: str, data: Dict) -> None:
        """Fire a local event to Python callbacks."""
        if event_type in self._event_callbacks:
            for callback in self._event_callbacks[event_type]:
                try:
                    callback(data)
                except Exception as e:
                    print(f"[UnrealAdapter] Event callback error ({event_type}): {e}")
    
    def on_event(self, event_type: str, callback: Callable) -> None:
        """Register a callback for events."""
        if event_type not in self._event_callbacks:
            self._event_callbacks[event_type] = []
        self._event_callbacks[event_type].append(callback)
    
    def get_next_write(self, timeout: float = 0.1) -> Optional[WriteRequest]:
        """Poll for the next write request from a client."""
        try:
            return self._write_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def entity_updates(self) -> Dict[int, UnrealEntityUpdate]:
        """Get current entity state from Unreal."""
        return dict(self._entity_updates)
    
    def __repr__(self) -> str:
        return f"UnrealAdapter(duplex://{self._host}:{self._port})"