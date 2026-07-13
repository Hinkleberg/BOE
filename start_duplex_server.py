#!/usr/bin/env python3
"""
Start COMPLETE full-duplex adapter ecosystem.
ALL adapters with unified bidirectional communication.

Port Assignments (TCP Duplex 7100-7509, No Conflicts):
  7100 - UnrealAdapter (Unreal Engine)
  7200 - BlenderAdapter (Blender 4.x)
  7300 - OmniverseConnector (NVIDIA Omniverse)
  7400 - RobloxHTTPAdapter (TCP Duplex) + 8000 (HTTP)
  7500 - GodotAdapter (Godot 3.x)
  7502 - O3DEAdapter (Amazon O3DE)
  7503 - UnityAdapter (Unity Engine)
  7507 - WebBridge (Web 3D / WebSocket)

Reserved/Non-Duplex:
  3000 - MilitarySimAdapter (DIS Protocol)
  9200 - StarlinkAdapter (gRPC)
  7501 - Godot4Bridge (reserved for future duplex)
  7504 - Reserved for future adapters
  7505 - Reserved for future adapters
  7506 - Reserved for future adapters
  7508 - Reserved for future adapters
  7509 - Reserved for future adapters
"""
import sys
import os
import threading
import time
import argparse

# Setup paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'block_engine'))

from authority.flat_store import FlatStore
from authority.resilient_store import ResilientStore
from environment.block_layout import WorldLayout
from environment.world_gen import generate
from bridges.duplex_base import DuplexAdapter
from bridges.unreal_adapter import UnrealAdapter
from bridges.blender_adapter import BlenderAdapter
from bridges.omniverse_connector import OmniverseConnector
from bridges.roblox_http_adapter import RobloxHTTPAdapter
from bridges.godot_adapter import GodotAdapter
from bridges.unity_adapter_duplex import UnityAdapter
from bridges.o3de_adapter_duplex import O3DEAdapter
from bridges.web_bridge import WebBridge


def create_test_world():
    """Create a simple test world."""
    world_path = "world.img.seq"
    layout = WorldLayout(world_x=256, world_y=256, world_z=256)
    
    if os.path.exists(world_path):
        print(f"✓ Using existing world at {world_path}")
    else:
        print(f"Generating new world at {world_path}...")
        store = FlatStore(world_path)
        generate(store, layout, seed=42)
        store.close()
        print(f"✓ World generated")
    
    return layout


def main():
    parser = argparse.ArgumentParser(description="Start COMPLETE full-duplex adapter ecosystem")
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--adapters", default="all", 
                       choices=["all", "game-engines", "military", "scientific", "web", "minimal"],
                       help="Adapter set to start")
    args = parser.parse_args()
    
    print("=" * 80)
    print("BLOCK-OFFSET ENGINE: COMPLETE FULL-DUPLEX ADAPTER ECOSYSTEM")
    print("=" * 80)
    
    # Create world
    layout = create_test_world()
    store = ResilientStore("world.img.seq")
    print(f"✓ Store opened: {store}\n")
    
    adapters = []
    
    try:
        # GAME ENGINES (Unreal, Unity, Godot, O3DE, Blender, Roblox)
        if args.adapters in ["all", "game-engines", "minimal"]:
            print("GAME ENGINES")
            print("─" * 80)
            
            # Unreal (7100)
            print("Starting UnrealAdapter (7100)...")
            unreal = UnrealAdapter(layout=layout, resilient_store=store, host=args.host, port=7100)
            unreal.start()
            adapters.append(("UnrealAdapter", unreal, 7100))
            print("✓ UnrealAdapter running\n")
            
            # Blender (7200)
            print("Starting BlenderAdapter (7200)...")
            blender = BlenderAdapter(resilient_store=store, world_layout=layout, host=args.host, port=7200)
            blender.start()
            adapters.append(("BlenderAdapter", blender, 7200))
            print("✓ BlenderAdapter running\n")
            
            # Omniverse (7300)
            print("Starting OmniverseConnector (7300)...")
            omniverse = OmniverseConnector(resilient_store=store, world_layout=layout, host=args.host, port=7300)
            omniverse.start()
            adapters.append(("OmniverseConnector", omniverse, 7300))
            print("✓ OmniverseConnector running\n")
            
            # Roblox (8000 HTTP + 7400 Duplex)
            print("Starting RobloxHTTPAdapter (8000 HTTP / 7400 Duplex)...")
            roblox = RobloxHTTPAdapter(resilient_store=store, world_layout=layout, host=args.host, duplex_port=7400)
            roblox.start_http(host=args.host, port=8000)
            roblox.start()
            adapters.append(("RobloxHTTPAdapter", roblox, 7400))
            print("✓ RobloxHTTPAdapter running\n")
            
            # Godot (7500)
            print("Starting GodotAdapter (7500)...")
            godot = GodotAdapter(resilient_store=store, world_layout=layout, host=args.host, port=7500)
            godot.start()
            adapters.append(("GodotAdapter", godot, 7500))
            print("✓ GodotAdapter running\n")
            
            # Unity (7503)
            print("Starting UnityAdapter (7503)...")
            unity = UnityAdapter(resilient_store=store, world_layout=layout, host=args.host, port=7503)
            unity.start()
            adapters.append(("UnityAdapter", unity, 7503))
            print("✓ UnityAdapter running\n")
            
            # O3DE (7502)
            print("Starting O3DEAdapter (7502)...")
            o3de = O3DEAdapter(resilient_store=store, world_layout=layout, host=args.host, port=7502)
            o3de.start()
            adapters.append(("O3DEAdapter", o3de, 7502))
            print("✓ O3DEAdapter running\n")
            
            # WebBridge (7507 - WebSocket)
            print("Starting WebBridge (7507 WebSocket)...")
            web = WebBridge(layout=layout, host=args.host, port=7507)
            web.start()
            adapters.append(("WebBridge", web, 7507))
            print("✓ WebBridge running\n")
        
        print("\n" + "=" * 80)
        print("ADAPTERS RUNNING")
        print("=" * 80)
        for name, adapter, port in adapters:
            try:
                stats = adapter.statistics()
                print(f"  {name:30s} Port {port:5d} - {stats.get('connected_clients', 0)} clients")
            except:
                print(f"  {name:30s} Port {port:5d} - Ready")
        
        print("\n" + "=" * 80)
        print("FULL-DUPLEX WIRE PROTOCOL (DPLX)")
        print("=" * 80)
        print("Frame: [MAGIC 4B 'DPLX'][TYPE 1B][MSG_ID 2B][PAYLOAD_LEN 4B][JSON]")
        print("\nEXAMPLE COMMANDS:")
        print("  Unreal (7100):")
        print('    {"command": "move_entity", "args": {"entity_id": 1, "x": 0, "y": 0, "z": 0}}')
        print("\n  Blender (7200):")
        print('    {"command": "load_region", "args": {"x": 0, "y": 0, "z": 0, "size": 16}}')
        print("\n  Omniverse (7300):")
        print('    {"command": "paint_block", "args": {"offset": 1000, "block_type": 5}}')
        print("\n  Roblox (HTTP 8000 / Duplex 7400):")
        print('    GET http://127.0.0.1:8000/roblox/stats')
        print('    {"command": "respawn", "args": {"player_id": 1}}')
        print("\n  Godot (7500):")
        print('    {"command": "spawn_actor", "args": {"actor_id": 1, "actor_type": "StaticBody3D"}}')
        print("\n  O3DE (7502):")
        print('    {"command": "spawn_entity", "args": {"entity_id": 1, "name": "TestEntity"}}')
        print("\n  Unity (7503):")
        print('    {"command": "instantiate_prefab", "args": {"obj_id": 1, "prefab": "Cube"}}')
        print("\n  WebBridge (7507 WebSocket):")
        print('    ws://127.0.0.1:7507/ws')
        
        print("\n" + "=" * 80)
        print("PORT ALLOCATION SUMMARY (NO CONFLICTS)")
        print("=" * 80)
        print("  TCP Duplex Ports:  7100-7509 (8 adapters, reserved for future)")
        print("  HTTP Ports:        8000 (Roblox legacy API)")
        print("  DIS Protocol:      3000 (MilitarySimAdapter - optional)")
        print("  gRPC Ports:        9200 (StarlinkAdapter - optional)")
        
        print("\n" + "=" * 80)
        print("Press Ctrl+C to stop servers")
        print("=" * 80 + "\n")
        
        # Keep running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        # Cleanup
        for name, adapter, port in adapters:
            try:
                adapter.stop()
                print(f"✓ {name} stopped")
            except Exception as e:
                print(f"✗ {name} error: {e}")
        
        print("✓ Shutdown complete")


if __name__ == "__main__":
    main()
