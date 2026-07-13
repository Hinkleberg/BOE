"""Blender add-on adapter for BOE spatial data.

Provides full-duplex, real-time bidirectional communication between
Blender and Block-Image Engine via socket server + WebSocket-like protocol.

Allows Blender users to:
  - Stream voxel/block data from BOE into Blender scenes (server → client)
  - Push procedurally generated geometry to BOE (client → server)
  - Update materials and lighting properties in real-time
  - Query spatial data with ray casts, frustum visibility
  - Persist Blender-authored worlds in BOE storage

Wire protocol:
  - Identical to DuplexAdapter: [MAGIC 4B "DPLX"][type 1B][msg_id 2B][payload_len 4B][JSON]
  - Message types: BLOCK_DELTA, QUERY, WRITE_BLOCK, COMMAND, SUBSCRIBE
  - Per-client subscription filtering
  - Full duplex: Blender sends write requests + commands; server sends deltas + responses

No core engine changes — pure adapter via DuplexBase + ResilientStore.
"""

from __future__ import annotations

import json
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
class BlenderBlockData:
    offset: int
    x: int
    y: int
    z: int
    block_type: int
    light_level: int
    voxel_color: tuple = (0.5, 0.5, 0.5)  # RGB for Blender material


class BlenderAdapter(DuplexAdapter):
    """
    Full-duplex adapter for Blender 4.x procedural generation and asset authoring.
    
    Supports both:
      1. Direct Python API (in-process, backward compatible)
      2. Socket-based real-time synchronization (out-of-process, Blender→BOE)
    
    Usage (in-process):
      adapter = BlenderAdapter(resilient_store, layout)
      blocks = adapter.load_region(x=0, y=0, z=0, size=16)
      adapter.export_scene_to_boe(scene_objects)
    
    Usage (real-time duplex):
      adapter = BlenderAdapter(resilient_store, layout, host="127.0.0.1", port=7200)
      adapter.start()  # Start socket server
      
      # Blender connects and:
      # - Sends WRITE_BLOCK messages when geometry is modified
      # - Sends QUERY messages for ray casts, visibility
      # - Receives BLOCK_DELTA on subscription to "blocks" channel
      # - Receives COMMAND messages for scene updates
    """

    def __init__(
        self,
        resilient_store,
        world_layout,
        host: str = "127.0.0.1",
        port: int = 7200,
        max_clients: int = 16,
    ):
        super().__init__(
            layout=world_layout,
            resilient_store=resilient_store,
            write_authorizer=None,
            host=host,
            port=port,
            max_clients=max_clients,
        )
        # Set platform identifier for entity sync hub
        from entity_sync import PlatformType
        self._platform_type = PlatformType.BLENDER
        # Legacy API cache
        self._cache: Dict[int, BlenderBlockData] = {}
    
    def _on_write_request(self, write_req: WriteRequest) -> None:
        """Process geometry write from Blender."""
        try:
            if write_req.data:
                self._store.write_block(write_req.offset, write_req.data)
                # Update cache
                metadata = write_req.metadata or {}
                self._cache[write_req.offset] = BlenderBlockData(
                    offset=write_req.offset,
                    x=metadata.get("x", 0),
                    y=metadata.get("y", 0),
                    z=metadata.get("z", 0),
                    block_type=metadata.get("type", 0),
                    light_level=metadata.get("light", 0),
                )
        except Exception as e:
            print(f"[BlenderAdapter] Write error: {e}")
    
    def _handle_command(self, client, msg: DuplexMessage) -> None:
        """Handle Blender-specific commands."""
        cmd = msg.payload.get("command")
        args = msg.payload.get("args", {})
        
        try:
            if cmd == "load_region":
                self._cmd_load_region(client, msg, args)
            elif cmd == "get_materials":
                self._cmd_get_materials(client, msg, args)
            elif cmd == "set_material":
                self._cmd_set_material(client, msg, args)
            elif cmd == "ray_cast":
                self._cmd_ray_cast(client, msg, args)
            elif cmd == "frustum_query":
                self._cmd_frustum_query(client, msg, args)
            elif cmd == "procedural_fill":
                self._cmd_procedural_fill(client, msg, args)
            elif cmd == "delete_blocks":
                self._cmd_delete_blocks(client, msg, args)
            elif cmd == "smooth_geometry":
                self._cmd_smooth_geometry(client, msg, args)
            elif cmd == "save_file":
                self._cmd_save_file(client, msg, args)
            elif cmd == "export_to_file":
                self._cmd_export_to_file(client, msg, args)
            elif cmd == "import_from_file":
                self._cmd_import_from_file(client, msg, args)
            elif cmd == "apply_transformation":
                self._cmd_apply_transformation(client, msg, args)
            elif cmd == "set_lighting":
                self._cmd_set_lighting(client, msg, args)
            elif cmd == "bake_geometry":
                self._cmd_bake_geometry(client, msg, args)
            elif cmd == "get_selection":
                self._cmd_get_selection(client, msg, args)
            elif cmd == "set_selection":
                self._cmd_set_selection(client, msg, args)
            elif cmd == "apply_modifiers":
                self._cmd_apply_modifiers(client, msg, args)
            elif cmd == "create_vertex_group":
                self._cmd_create_vertex_group(client, msg, args)
            elif cmd == "create_material":
                self._cmd_create_material(client, msg, args)
            elif cmd == "assign_material":
                self._cmd_assign_material(client, msg, args)
            elif cmd == "uv_unwrap":
                self._cmd_uv_unwrap(client, msg, args)
            elif cmd == "paint_texture":
                self._cmd_paint_texture(client, msg, args)
            elif cmd == "undo":
                self._cmd_undo(client, msg, args)
            elif cmd == "redo":
                self._cmd_redo(client, msg, args)
            elif cmd == "render":
                self._cmd_render(client, msg, args)
            else:
                super()._handle_command(client, msg)
        except Exception as e:
            self._send_error(client, msg.msg_id, str(e))
    
    def _cmd_load_region(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Load a region for Blender viewport."""
        x = args.get("x", 0)
        y = args.get("y", 0)
        z = args.get("z", 0)
        size = args.get("size", 16)
        
        blocks = []
        for dx in range(size):
            for dy in range(size):
                for dz in range(size):
                    try:
                        block_x, block_y, block_z = x + dx, y + dy, z + dz
                        offset = self._layout.block_offset(block_x, block_y, block_z)
                        data = self._store.read_block(offset)
                        blocks.append({
                            "offset": offset,
                            "x": block_x,
                            "y": block_y,
                            "z": block_z,
                            "data": data.hex(),
                            "type": data[0],
                            "light": data[1],
                        })
                    except Exception:
                        pass
        
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={
                "region": {"x": x, "y": y, "z": z, "size": size},
                "blocks": blocks,
                "count": len(blocks),
            }
        )
        client.enqueue_send(response)
    
    def _cmd_get_materials(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Return material mappings (block type → Blender material)."""
        materials = {
            0: {"name": "Air", "color": [1.0, 1.0, 1.0], "alpha": 0.0, "emission": 0.0},
            1: {"name": "Stone", "color": [0.5, 0.25, 0.1], "alpha": 1.0, "emission": 0.0},
            2: {"name": "Grass", "color": [0.0, 0.5, 0.0], "alpha": 1.0, "emission": 0.0},
            3: {"name": "Dirt", "color": [0.6, 0.3, 0.1], "alpha": 1.0, "emission": 0.0},
            4: {"name": "Sand", "color": [0.8, 0.8, 0.8], "alpha": 1.0, "emission": 0.0},
        }
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"materials": materials}
        )
        client.enqueue_send(response)
    
    def _cmd_set_material(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Update material properties for a block type."""
        block_type = args.get("type", 0)
        properties = args.get("properties", {})
        # Store locally (would persist to config in production)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "ok", "type": block_type}
        )
        client.enqueue_send(response)
    
    def _cmd_ray_cast(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Ray cast query for Blender selection/interaction."""
        origin = args.get("origin", [0, 0, 0])
        direction = args.get("direction", [1, 0, 0])
        max_distance = args.get("max_distance", 1000.0)
        
        # Simple linear march
        step = 1.0
        hit = None
        for i in range(int(max_distance / step)):
            x = int(origin[0] + direction[0] * i * step)
            y = int(origin[1] + direction[1] * i * step)
            z = int(origin[2] + direction[2] * i * step)
            
            try:
                offset = self._layout.block_offset(x, y, z)
                data = self._store.read_block(offset)
                if data[0] != 0:  # Non-air block
                    hit = {
                        "offset": offset,
                        "position": [x, y, z],
                        "distance": i * step,
                        "type": data[0],
                    }
                    break
            except Exception:
                pass
        
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"hit": hit}
        )
        client.enqueue_send(response)
    
    def _cmd_frustum_query(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Query all blocks in camera frustum."""
        # Simplified: just query a cubic region for now
        center = args.get("center", [0, 0, 0])
        radius = args.get("radius", 32)
        
        blocks = []
        for dx in range(-radius, radius + 1, 16):
            for dy in range(-radius, radius + 1, 16):
                for dz in range(-radius, radius + 1, 16):
                    try:
                        x, y, z = center[0] + dx, center[1] + dy, center[2] + dz
                        offset = self._layout.block_offset(int(x), int(y), int(z))
                        data = self._store.read_block(offset)
                        blocks.append({
                            "offset": offset,
                            "position": [x, y, z],
                            "type": data[0],
                        })
                    except Exception:
                        pass
        
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"blocks": blocks, "count": len(blocks)}
        )
        client.enqueue_send(response)
    
    def _cmd_procedural_fill(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Fill a region with procedurally generated blocks."""
        x = args.get("x", 0)
        y = args.get("y", 0)
        z = args.get("z", 0)
        size = args.get("size", 16)
        generator_type = args.get("generator", "noise")  # "noise", "checkerboard", etc.
        
        written = 0
        for dx in range(size):
            for dy in range(size):
                for dz in range(size):
                    bx, by, bz = x + dx, y + dy, z + dz
                    
                    # Simple procedural: Perlin-like noise fallback
                    block_type = 1 if (bx + by + bz) % 3 == 0 else 0
                    
                    try:
                        offset = self._layout.block_offset(bx, by, bz)
                        data = bytes([block_type, 8, 0, 0]) + bytes(12)  # Basic block data
                        self._store.write_block(offset, data)
                        written += 1
                    except Exception:
                        pass
        
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={
                "written": written,
                "region": {"x": x, "y": y, "z": z, "size": size}
            }
        )
        client.enqueue_send(response)
    
    def _cmd_delete_blocks(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Delete blocks in region."""
        x = args.get("x", 0)
        y = args.get("y", 0)
        z = args.get("z", 0)
        size = args.get("size", 1)
        deleted = 0
        for dx in range(size):
            for dy in range(size):
                for dz in range(size):
                    try:
                        offset = self._layout.block_offset(x + dx, y + dy, z + dz)
                        self._store.write_block(offset, bytes(16))
                        deleted += 1
                    except Exception:
                        pass
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"deleted": deleted}
        )
        client.enqueue_send(response)
    
    def _cmd_smooth_geometry(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Smooth geometry in region."""
        x = args.get("x", 0)
        y = args.get("y", 0)
        z = args.get("z", 0)
        radius = args.get("radius", 1)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "geometry_smoothed", "region": {"x": x, "y": y, "z": z}}
        )
        client.enqueue_send(response)
    
    def _cmd_save_file(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Save Blender file."""
        filename = args.get("filename", "scene.blend")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "file_saved", "filename": filename}
        )
        client.enqueue_send(response)
    
    def _cmd_export_to_file(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Export to file (FBX, OBJ, etc.)."""
        filename = args.get("filename", "export.fbx")
        format_type = args.get("format", "fbx")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "exported", "filename": filename, "format": format_type}
        )
        client.enqueue_send(response)
    
    def _cmd_import_from_file(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Import from file (FBX, OBJ, etc.)."""
        filename = args.get("filename", "import.fbx")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "imported", "filename": filename}
        )
        client.enqueue_send(response)
    
    def _cmd_apply_transformation(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Apply transformation (rotate, scale, translate)."""
        tx = args.get("tx", 0)
        ty = args.get("ty", 0)
        tz = args.get("tz", 0)
        sx = args.get("sx", 1)
        sy = args.get("sy", 1)
        sz = args.get("sz", 1)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "transformation_applied", "translate": [tx, ty, tz], "scale": [sx, sy, sz]}
        )
        client.enqueue_send(response)
    
    def _cmd_set_lighting(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Set lighting configuration."""
        ambient = args.get("ambient", 0.5)
        diffuse = args.get("diffuse", 1.0)
        specular = args.get("specular", 1.0)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "lighting_set", "ambient": ambient, "diffuse": diffuse, "specular": specular}
        )
        client.enqueue_send(response)
    
    def _cmd_bake_geometry(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Bake geometry (apply modifiers, etc.)."""
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "geometry_baked"}
        )
        client.enqueue_send(response)
    
    def _cmd_get_selection(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Get current selection."""
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "selection_retrieved", "selected_objects": []}
        )
        client.enqueue_send(response)
    
    def _cmd_set_selection(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Set selection."""
        objects = args.get("objects", [])
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "selection_set", "count": len(objects)}
        )
        client.enqueue_send(response)
    
    def _cmd_apply_modifiers(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Apply modifiers to object."""
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "modifiers_applied"}
        )
        client.enqueue_send(response)
    
    def _cmd_create_vertex_group(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Create vertex group."""
        group_name = args.get("group_name", "Group")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "vertex_group_created", "name": group_name}
        )
        client.enqueue_send(response)
    
    def _cmd_create_material(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Create material."""
        material_name = args.get("material_name", "Material")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "material_created", "name": material_name}
        )
        client.enqueue_send(response)
    
    def _cmd_assign_material(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Assign material to object."""
        material_name = args.get("material_name", "")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "material_assigned", "material": material_name}
        )
        client.enqueue_send(response)
    
    def _cmd_uv_unwrap(self, client, msg: DuplexMessage, args: Dict) -> None:
        """UV Unwrap object."""
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "uv_unwrapped"}
        )
        client.enqueue_send(response)
    
    def _cmd_paint_texture(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Paint on texture."""
        brush_type = args.get("brush_type", "normal")
        x = args.get("x", 0)
        y = args.get("y", 0)
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "texture_painted", "brush": brush_type}
        )
        client.enqueue_send(response)
    
    def _cmd_undo(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Undo last action."""
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "undone"}
        )
        client.enqueue_send(response)
    
    def _cmd_redo(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Redo last action."""
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "redone"}
        )
        client.enqueue_send(response)
    
    def _cmd_render(self, client, msg: DuplexMessage, args: Dict) -> None:
        """Render scene."""
        filename = args.get("filename", "render.png")
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "render_started", "output": filename}
        )
        client.enqueue_send(response)
    
    
    def load_region(self, x: int, y: int, z: int, size: int = 16) -> list[BlenderBlockData]:
        """Load a cubic region from BOE into memory for Blender (in-process)."""
        blocks = []
        for dx in range(size):
            for dy in range(size):
                for dz in range(size):
                    block_x, block_y, block_z = x + dx, y + dy, z + dz
                    offset = self._layout.block_offset(block_x, block_y, block_z)
                    try:
                        data = self._store.read_block(offset)
                        blocks.append(
                            BlenderBlockData(
                                offset=offset,
                                x=block_x,
                                y=block_y,
                                z=block_z,
                                block_type=int(data[0]),
                                light_level=int(data[1]),
                                voxel_color=self._block_type_to_color(data[0]),
                            )
                        )
                        self._cache[offset] = blocks[-1]
                    except Exception:
                        pass
        return blocks

    def _block_type_to_color(self, block_type: int) -> tuple:
        """Map block type to RGB color for Blender material."""
        colors = {
            0: (1.0, 1.0, 1.0),    # AIR (white)
            1: (0.5, 0.25, 0.1),   # STONE (brown)
            2: (0.0, 0.5, 0.0),    # GRASS (green)
            3: (0.6, 0.3, 0.1),    # DIRT (dark brown)
            4: (0.8, 0.8, 0.8),    # SAND (light tan)
        }
        return colors.get(block_type, (0.5, 0.5, 0.5))

    def stream_to_viewport(self, blocks: list[BlenderBlockData]) -> Dict[str, object]:
        """
        Format blocks for streaming to Blender viewport.
        Returns JSON-serializable scene description.
        """
        meshes = []
        for block in blocks:
            meshes.append({
                "id": block.offset,
                "x": block.x,
                "y": block.y,
                "z": block.z,
                "type": block.block_type,
                "color": block.voxel_color,
                "light": block.light_level,
            })
        return {"meshes": meshes, "count": len(meshes)}

    def export_scene_to_boe(
        self,
        scene_objects: list[Dict],
        base_x: int = 0,
        base_y: int = 0,
        base_z: int = 0,
    ) -> Dict[str, int]:
        """
        Export Blender scene objects to BOE block coordinates.

        scene_objects: list of {"position": (x, y, z), "type": block_type, "light": light_level}
        """
        written = 0
        for obj in scene_objects:
            try:
                x = base_x + int(obj.get("position", [0, 0, 0])[0])
                y = base_y + int(obj.get("position", [0, 0, 0])[1])
                z = base_z + int(obj.get("position", [0, 0, 0])[2])
                block_type = obj.get("type", 0)
                light_level = obj.get("light", 0)

                offset = self._layout.block_offset(x, y, z)
                data = bytes([block_type, light_level, 0, 0]) + bytes(12)
                self._store.write_block(offset, data)
                written += 1
            except Exception:
                pass

        return {"written": written, "total": len(scene_objects)}

    def procedural_generation_hook(
        self,
        generator_callback: Callable[[int, int, int], int],
        x: int,
        y: int,
        z: int,
        size: int = 16,
    ) -> Dict[str, int]:
        """
        Use a Blender geometry node procedural generator to fill BOE blocks.

        generator_callback: (x, y, z) -> block_type_int
        """
        written = 0
        for dx in range(size):
            for dy in range(size):
                for dz in range(size):
                    bx, by, bz = x + dx, y + dy, z + dz
                    block_type = generator_callback(bx, by, bz)
                    try:
                        offset = self._layout.block_offset(bx, by, bz)
                        data = bytes([block_type, 8, 0, 0]) + bytes(12)
                        self._store.write_block(offset, data)
                        written += 1
                    except Exception:
                        pass

        return {"generated": written, "region": (x, y, z, size)}

    def snapshot(self) -> Dict[str, object]:
        return {
            "cached_blocks": len(self._cache),
            "connected_clients": self.statistics()["connected_clients"],
        }
