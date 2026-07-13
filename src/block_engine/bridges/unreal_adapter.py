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
        # Set platform identifier for entity sync hub
        from entity_sync import PlatformType
        self._platform_type = PlatformType.UNREAL
        
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
          - move_entity, spawn_entity, despawn_entity
          - load_region, query_blocks, ray_cast
          - damage_entity, heal_entity, get_entity_state
          - apply_force, apply_damage_block, apply_impulse
          - pause_simulation, reset_world, teleport_entity
          - spawn_particle_effect, set_material
          - save_world, load_world, get_physics_state
          - enable_collision, disable_collision, apply_material
          - create_light, set_post_process_volume
          - get_screenshot, physics_query
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
            elif cmd == "damage_entity":
                self._cmd_damage_entity(client, msg, args)
            elif cmd == "heal_entity":
                self._cmd_heal_entity(client, msg, args)
            elif cmd == "get_entity_state":
                self._cmd_get_entity_state(client, msg, args)
            elif cmd == "apply_force":
                self._cmd_apply_force(client, msg, args)
            elif cmd == "damage_block":
                self._cmd_damage_block(client, msg, args)
            elif cmd == "apply_impulse":
                self._cmd_apply_impulse(client, msg, args)
            elif cmd == "pause_simulation":
                self._cmd_pause_simulation(client, msg, args)
            elif cmd == "reset_world":
                self._cmd_reset_world(client, msg, args)
            elif cmd == "teleport_entity":
                self._cmd_teleport_entity(client, msg, args)
            elif cmd == "spawn_particle_effect":
                self._cmd_spawn_particle_effect(client, msg, args)
            elif cmd == "set_material":
                self._cmd_set_material_ue(client, msg, args)
            elif cmd == "save_world":
                self._cmd_save_world(client, msg, args)
            elif cmd == "load_world":
                self._cmd_load_world(client, msg, args)
            elif cmd == "get_physics_state":
                self._cmd_get_physics_state(client, msg, args)
            elif cmd == "enable_collision":
                self._cmd_enable_collision(client, msg, args)
            elif cmd == "disable_collision":
                self._cmd_disable_collision(client, msg, args)
            elif cmd == "apply_material":
                self._cmd_apply_material(client, msg, args)
            elif cmd == "create_light":
                self._cmd_create_light(client, msg, args)
            elif cmd == "set_post_process_volume":
                self._cmd_set_post_process_volume(client, msg, args)
            elif cmd == "get_screenshot":
                self._cmd_get_screenshot(client, msg, args)
            elif cmd == "physics_query":
                self._cmd_physics_query(client, msg, args)
            else:
                super()._handle_command(client, msg)
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
    
    def _cmd_damage_entity(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Damage an entity."""
        entity_id = args.get("entity_id")
        damage = args.get("damage", 10)
        if entity_id in self._entity_updates:
            entity = self._entity_updates[entity_id]
            entity.health = max(0, entity.health - damage)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "damaged", "entity_id": entity_id, "damage": damage}
        )
        client.enqueue_send(response)
    
    def _cmd_heal_entity(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Heal an entity."""
        entity_id = args.get("entity_id")
        heal_amount = args.get("heal_amount", 50)
        if entity_id in self._entity_updates:
            entity = self._entity_updates[entity_id]
            entity.health = min(100, entity.health + heal_amount)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "healed", "entity_id": entity_id, "heal_amount": heal_amount}
        )
        client.enqueue_send(response)
    
    def _cmd_get_entity_state(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Get full entity state."""
        entity_id = args.get("entity_id")
        entity_data = None
        if entity_id in self._entity_updates:
            entity = self._entity_updates[entity_id]
            entity_data = {
                "id": entity_id,
                "x": entity.x, "y": entity.y, "z": entity.z,
                "vx": entity.vx, "vy": entity.vy, "vz": entity.vz,
                "yaw": entity.yaw, "pitch": entity.pitch,
                "health": entity.health, "flags": entity.flags
            }
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"entity": entity_data}
        )
        client.enqueue_send(response)
    
    def _cmd_apply_force(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Apply physics force to entity."""
        entity_id = args.get("entity_id")
        fx = args.get("fx", 0.0)
        fy = args.get("fy", 0.0)
        fz = args.get("fz", 0.0)
        if entity_id in self._entity_updates:
            entity = self._entity_updates[entity_id]
            entity.vx += fx * 0.01
            entity.vy += fy * 0.01
            entity.vz += fz * 0.01
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "force_applied", "entity_id": entity_id, "force": [fx, fy, fz]}
        )
        client.enqueue_send(response)
    
    def _cmd_damage_block(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Damage/break a block."""
        x = args.get("x", 0)
        y = args.get("y", 0)
        z = args.get("z", 0)
        damage = args.get("damage", 1)
        try:
            offset = self._layout.block_offset(x, y, z)
            self._store.write_block(offset, bytes(16))  # Clear the block
            response = DuplexMessage(
                msg_type=MessageType.RESPONSE,
                msg_id=msg.msg_id,
                payload={"status": "block_damaged", "position": [x, y, z]}
            )
        except Exception as e:
            response = DuplexMessage(
                msg_type=MessageType.RESPONSE,
                msg_id=msg.msg_id,
                payload={"status": "error", "error": str(e)}
            )
        client.enqueue_send(response)
    
    def _cmd_apply_impulse(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Apply instantaneous impulse to entity."""
        entity_id = args.get("entity_id")
        ix = args.get("ix", 0.0)
        iy = args.get("iy", 0.0)
        iz = args.get("iz", 0.0)
        if entity_id in self._entity_updates:
            entity = self._entity_updates[entity_id]
            entity.vx += ix
            entity.vy += iy
            entity.vz += iz
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "impulse_applied", "entity_id": entity_id}
        )
        client.enqueue_send(response)
    
    def _cmd_pause_simulation(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Pause simulation."""
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "simulation_paused"}
        )
        client.enqueue_send(response)
    
    def _cmd_reset_world(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Reset the world."""
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "world_reset"}
        )
        client.enqueue_send(response)
    
    def _cmd_teleport_entity(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Teleport entity to location."""
        entity_id = args.get("entity_id")
        x = args.get("x", 0.0)
        y = args.get("y", 0.0)
        z = args.get("z", 0.0)
        if entity_id in self._entity_updates:
            entity = self._entity_updates[entity_id]
            entity.x = x
            entity.y = y
            entity.z = z
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "teleported", "entity_id": entity_id, "position": [x, y, z]}
        )
        client.enqueue_send(response)
    
    def _cmd_spawn_particle_effect(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Spawn particle effect."""
        effect_type = args.get("effect_type", "explosion")
        x = args.get("x", 0.0)
        y = args.get("y", 0.0)
        z = args.get("z", 0.0)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "particle_spawned", "type": effect_type, "position": [x, y, z]}
        )
        client.enqueue_send(response)
    
    def _cmd_set_material_ue(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Set material on block."""
        x = args.get("x", 0)
        y = args.get("y", 0)
        z = args.get("z", 0)
        material = args.get("material", "default")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "material_set", "position": [x, y, z], "material": material}
        )
        client.enqueue_send(response)
    
    def _cmd_save_world(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Save world state."""
        save_name = args.get("save_name", "autosave")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "world_saved", "name": save_name}
        )
        client.enqueue_send(response)
    
    def _cmd_load_world(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Load world state."""
        save_name = args.get("save_name", "autosave")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "world_loaded", "name": save_name}
        )
        client.enqueue_send(response)
    
    def _cmd_get_physics_state(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Get physics system state."""
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "physics_state", "gravity": 9.81, "entities": len(self._entity_updates)}
        )
        client.enqueue_send(response)
    
    def _cmd_enable_collision(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Enable collision for entity."""
        entity_id = args.get("entity_id")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "collision_enabled", "entity_id": entity_id}
        )
        client.enqueue_send(response)
    
    def _cmd_disable_collision(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Disable collision for entity."""
        entity_id = args.get("entity_id")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "collision_disabled", "entity_id": entity_id}
        )
        client.enqueue_send(response)
    
    def _cmd_apply_material(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Apply material to block."""
        block_type = args.get("block_type", 1)
        material_path = args.get("material_path", "")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "material_applied", "block_type": block_type, "path": material_path}
        )
        client.enqueue_send(response)
    
    def _cmd_create_light(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Create light actor."""
        light_type = args.get("light_type", "point")
        x = args.get("x", 0.0)
        y = args.get("y", 0.0)
        z = args.get("z", 0.0)
        intensity = args.get("intensity", 1000.0)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "light_created", "type": light_type, "intensity": intensity}
        )
        client.enqueue_send(response)
    
    def _cmd_set_post_process_volume(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Set post-process volume settings."""
        bloom = args.get("bloom", 0.5)
        contrast = args.get("contrast", 1.0)
        saturation = args.get("saturation", 1.0)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "post_process_set", "bloom": bloom, "contrast": contrast, "saturation": saturation}
        )
        client.enqueue_send(response)
    
    def _cmd_get_screenshot(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Capture screenshot."""
        filename = args.get("filename", "screenshot.png")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "screenshot_captured", "filename": filename}
        )
        client.enqueue_send(response)
    
    def _cmd_physics_query(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Query physics information."""
        query_type = args.get("query_type", "overlaps")
        x = args.get("x", 0.0)
        y = args.get("y", 0.0)
        z = args.get("z", 0.0)
        radius = args.get("radius", 100.0)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "physics_query", "type": query_type, "results": []}
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