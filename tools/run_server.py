"""
tools/run_server.py
Start everything for local testing:
- Creates WorldLayout, FlatStore, ResilientStore
- Generates world if not present
- Creates EntitySidecar, SpatialIndex, MovementTransaction, MutationEngine
- Starts RenderFeedServer
- Starts UnrealAdapter on port 7100 (UE5)
- Starts UnityAdapter on port 7200 (Unity)
- Starts ai_loop task
"""
import argparse
import asyncio
import math
import os
import socket
import sys
import time

# Ensure local source modules can be imported when running from repository root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "block_engine")))


def _find_available_port(preferred: int, max_attempts: int = 20) -> int:
    port = preferred
    for _ in range(max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1
    raise RuntimeError(f"No available TCP port found from {preferred} to {port - 1}")

from environment.block_layout import Block, BlockType, WorldLayout, BLOCK_SIZE
from authority.flat_store import FlatStore
from authority.resilient_store import ResilientStore
from environment.world_gen import generate
from kernel.entity_sidecar import EntityRecord, EntitySidecar, EntityType, EntityFlags
from kernel.spatial_index import SpatialIndex
from kernel.movement_transaction import MovementTransaction
from services.mutation_engine import MutationEngine
from interface.render_delta import BlockDelta, EntityDelta, RenderDelta
from interface.render_feed import RenderFeedServer
from bridges.unreal_adapter import UnrealAdapter
from bridges.deprecated.unity_adapter import UnityAdapter
from bridges.godot_adapter import GodotAdapter
from bridges.deprecated.O3de_adapter import O3DEAdapter
from bridges.military_adapter import CoordOrigin, MilitarySimAdapter

WORLD_PATH = "world.img"
SIDECAR_PATH = "sidecar.img"
JOURNAL_PATH = "mutation.journal"

class LocalRenderFeed:
    def __init__(self, layout: WorldLayout, sidecar: EntitySidecar, world_reader):
        self.layout = layout
        self.sidecar = sidecar
        self.world_reader = world_reader
        self.clients: list[dict] = []
        self.last_tick = 0
        self.last_entity_tick = 0
        self.last_entity_records: list[EntityRecord] = []

    def connect_client(
        self,
        client_id: int,
        send_cb,
        view_radius: int = 32,
        initial_x: float = 0.0,
        initial_y: float = 0.0,
        initial_z: float = 0.0,
    ):
        self.clients.append({
            "client_id": client_id,
            "send_cb": send_cb,
            "view_radius": view_radius,
            "x": initial_x,
            "y": initial_y,
            "z": initial_z,
        })

    def update_client_position(self, client_id: int, x: float, y: float, z: float) -> None:
        for client in self.clients:
            if client["client_id"] == client_id:
                client["x"] = x
                client["y"] = y
                client["z"] = z
                break

    def build_delta(self, changed_offsets: list[int]) -> RenderDelta:
        self.last_tick += 1
        block_deltas = []
        for offset in sorted(set(changed_offsets)):
            if offset < 0 or offset + BLOCK_SIZE > self.layout.image_size:
                continue
            block_deltas.append(BlockDelta(offset=offset, data=self.world_reader(offset)))

        entity_records = self.sidecar.tick_delta(self.last_entity_tick)
        entity_deltas = [
            EntityDelta(
                entity_id=rec.entity_id,
                x=rec.x,
                y=rec.y,
                z=rec.z,
                metadata=b"",
            )
            for rec in entity_records
        ]
        if entity_records:
            self.last_entity_tick = max(rec.last_tick for rec in entity_records)
        self.last_entity_records = entity_records

        return RenderDelta(
            tick=self.last_tick,
            block_deltas=block_deltas,
            entity_deltas=entity_deltas,
        )

    def dispatch(self, delta: RenderDelta) -> None:
        for client in self.clients:
            try:
                client["send_cb"](delta)
            except Exception:
                pass


async def main():
    print("⚠️  DEPRECATION NOTICE: tools/run_server.py is deprecated and uses legacy non-duplex adapters.")
    print("    Recommended: Use start_duplex_server.py instead (full-duplex adapters, entity sync).")
    print("    See PORT_ALLOCATION.md and docs/COMMANDS.md for current port assignments.\n")

    ap = argparse.ArgumentParser(description="[DEPRECATED] Start the local engine with optional UE5/Unity/Godot adapters")
    ap.add_argument("--ue-port", type=int, default=7100, help="Unreal adapter port")
    ap.add_argument("--unity-port", type=int, default=7600, help="Unity adapter port (legacy, use start_duplex_server.py for 7503)")
    ap.add_argument("--godot-port", type=int, default=7601, help="Godot adapter port (legacy, use start_duplex_server.py for 7500)")
    ap.add_argument("--o3de-port", type=int, default=7602, help="O3DE adapter port (legacy, use start_duplex_server.py for 7502)")
    ap.add_argument("--dis-port", type=int, default=3000, help="DIS adapter port")
    ap.add_argument("--render-port", type=int, default=9000, help="Render feed port")
    ap.add_argument("--world-size", type=int, default=128, help="World size in blocks")
    ap.add_argument("--no-ue", action="store_true", help="Skip Unreal adapter startup")
    ap.add_argument("--no-unity", action="store_true", help="Skip Unity adapter startup")
    ap.add_argument("--no-godot", action="store_true", help="Skip Godot adapter startup")
    ap.add_argument("--no-o3de", action="store_true", help="Skip O3DE adapter startup")
    ap.add_argument("--no-dis", action="store_true", help="Skip Military DIS adapter startup")
    args = ap.parse_args()

    layout = WorldLayout(args.world_size, args.world_size, args.world_size)
    flat = FlatStore(WORLD_PATH, layout)
    rs = ResilientStore(local_store=flat, journal_path=JOURNAL_PATH)

    if not os.path.exists(WORLD_PATH):
        generate(layout, rs)

    spatial_index = SpatialIndex(chunk_dim=16)
    sidecar = EntitySidecar(SIDECAR_PATH, max_entities=64, spatial_index=spatial_index)
    rebuilt = sidecar.rebuild_spatial_index()
    print(f"Spatial index rebuild complete: {rebuilt} entities indexed")
    movement_transaction = MovementTransaction(layout, sidecar, spatial_index, journal=JOURNAL_PATH)
    mut = MutationEngine(movement_transaction)

    render_port = _find_available_port(args.render_port)
    print(f"Render feed bound on 127.0.0.1:{render_port}")
    render_server = RenderFeedServer(host="127.0.0.1", port=render_port)
    await render_server.start()

    local_feed = LocalRenderFeed(layout, sidecar, flat.read_block)

    started_adapters = []
    adapter_clients = []

    if not args.no_ue:
        ue_port = _find_available_port(args.ue_port)
        print(f"Unreal adapter bound on 127.0.0.1:{ue_port}")
        ue5 = UnrealAdapter(layout, host="127.0.0.1", port=ue_port)
        ue5.start()
        local_feed.connect_client(
            client_id=99,
            send_cb=ue5.on_render_delta,
            view_radius=64,
            initial_x=layout.world_x / 2,
            initial_y=layout.world_y / 2,
            initial_z=layout.world_z / 2,
        )
        adapter_clients.append(ue5)
    else:
        print("Skipping Unreal adapter")

    if not args.no_unity:
        unity_port = _find_available_port(args.unity_port)
        print(f"Unity adapter bound on 127.0.0.1:{unity_port}")
        unity = UnityAdapter(layout, host="127.0.0.1", port=unity_port)
        unity.start()
        local_feed.connect_client(
            client_id=50,
            send_cb=unity.on_render_delta,
            view_radius=48,
            initial_x=layout.world_x / 2,
            initial_y=layout.world_y / 2,
            initial_z=layout.world_z / 2,
        )
        adapter_clients.append(unity)
    else:
        print("Skipping Unity adapter")

    if not args.no_godot:
        godot_port = _find_available_port(args.godot_port)
        print(f"Godot adapter bound on 127.0.0.1:{godot_port}")
        godot = GodotAdapter(layout, host="127.0.0.1", port=godot_port)
        godot.start()
        local_feed.connect_client(
            client_id=75,
            send_cb=godot.on_render_delta,
            view_radius=48,
            initial_x=layout.world_x / 2,
            initial_y=layout.world_y / 2,
            initial_z=layout.world_z / 2,
        )
        adapter_clients.append(godot)
    else:
        print("Skipping Godot adapter")

    if not args.no_o3de:
        o3de_port = _find_available_port(args.o3de_port)
        print(f"O3DE adapter bound on 127.0.0.1:{o3de_port}")
        o3de = O3DEAdapter(layout, host="127.0.0.1", port=o3de_port)
        o3de.start()
        local_feed.connect_client(
            client_id=30,
            send_cb=o3de.on_render_delta,
            view_radius=64,
            initial_x=layout.world_x / 2,
            initial_y=layout.world_y / 2,
            initial_z=layout.world_z / 2,
        )
        adapter_clients.append(o3de)
    else:
        print("Skipping O3DE adapter")

    if not args.no_dis:
        dis_port = _find_available_port(args.dis_port)
        print(f"Military DIS adapter configured on port {dis_port}")
        military = MilitarySimAdapter(
            resilient_store=rs,
            entity_sidecar=sidecar,
            render_feed=render_server,
            origin=CoordOrigin(lat=0.0, lon=0.0, alt=0.0),
            dis_port=dis_port,
        )
        military.start()
        adapter_clients.append(military)
    else:
        print("Skipping Military DIS adapter")

    player = EntityRecord(
        entity_id=1,
        entity_type=EntityType.PLAYER,
        flags=EntityFlags.ACTIVE | EntityFlags.VISIBLE,
        x=float(layout.world_x // 2),
        y=float(layout.world_y // 2),
        z=float(layout.world_z // 2),
        health=100.0,
        last_tick=0,
    )
    sidecar.write_entity(player)

    radius = max(1, layout.world_x // 4)
    tick = 0
    t0 = time.time()
    interval = 1.0 / 20.0

    try:
        while True:
            tick += 1
            elapsed = time.time() - t0
            angle = elapsed * 0.5
            px = layout.world_x / 2 + math.cos(angle) * radius
            pz = layout.world_z / 2 + math.sin(angle) * radius
            py = float(layout.world_y // 2)
            player.x = px
            player.y = py
            player.z = pz
            player.last_tick = tick
            sidecar.write_entity(player)

            changed_offsets = []
            if tick % 5 == 0:
                bx = int(px) % layout.world_x
                by = max(0, int(py) - 1)
                bz = int(pz) % layout.world_z
                offset = layout.block_offset(bx, by, bz)
                blk = Block(block_type=BlockType.AIR, flags=0)
                rs.write_block(offset, blk.to_bytes())
                changed_offsets.append(offset)

            delta = local_feed.build_delta(changed_offsets)
            local_feed.dispatch(delta)

            entity_payload = [
                {
                    "entity_id": rec.entity_id,
                    "entity_type": rec.entity_type,
                    "x": rec.x,
                    "y": rec.y,
                    "z": rec.z,
                    "vx": rec.vx,
                    "vy": rec.vy,
                    "vz": rec.vz,
                    "yaw": rec.yaw,
                    "pitch": rec.pitch,
                    "health": rec.health,
                    "flags": rec.flags,
                    "last_tick": rec.last_tick,
                }
                for rec in local_feed.last_entity_records
            ]
            render_server.notify_tiles_changed(changed_offsets, flat.read_block, entity_payload)

            if tick % 40 == 0:
                report = rs.health_report()
                print(
                    f"[t={elapsed:.1f}s] tick={tick} "
                    f"health={report['health']} "
                    f"mirror_count={report['mirror_count']}"
                )

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass
    finally:
        for adapter in adapter_clients:
            try:
                adapter.stop()
            except Exception:
                pass

if __name__ == "__main__":
    asyncio.run(main())
