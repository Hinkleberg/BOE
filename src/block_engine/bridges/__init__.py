"""
Adapter bridges for Block-Offset Engine.

Full-Duplex Adapters (TCP DPLX Protocol):
- UnrealAdapter: Unreal Engine 5.x integration
- BlenderAdapter: Blender 4.x procedural generation
- OmniverseConnector: NVIDIA Omniverse USD bridge
- RobloxHTTPAdapter: Roblox Studio integration (duplex + HTTP)
- GodotAdapter: Godot game engine
- UnityAdapter: Unity engine (via unity_adapter_duplex)
- O3DEAdapter: Amazon O3DE (via o3de_adapter_duplex)
- WebBridge: Web 3D / WebSocket observer

Domain Adapters (Custom protocols, no TCP server):
- MilitarySimAdapter: HLA/RTI federation
- AVSimAdapter: Autonomous vehicle simulation
- ScientificSimAdapter: Scientific computation

Core Infrastructure:
- DuplexAdapter: Base class for all full-duplex adapters
- EntitySyncHub: Central synchronization hub (entity_sync module)
"""

# Main full-duplex adapters
from .duplex_base import DuplexAdapter
from .unreal_adapter import UnrealAdapter
from .blender_adapter import BlenderAdapter
from .omniverse_connector import OmniverseConnector
from .roblox_http_adapter import RobloxHTTPAdapter
from .godot_adapter import GodotAdapter
from .o3de_adapter_duplex import O3DEAdapter
from .unity_adapter_duplex import UnityAdapter
from .web_bridge import WebBridge

# Entity sync hub
from .entity_sync import EntitySyncHub, get_entity_sync_hub

# Domain adapters (optional)
try:
    from .military_adapter import MilitarySimAdapter
except ImportError:
    MilitarySimAdapter = None

try:
    from .autonomous_adapter import AVSimAdapter
except ImportError:
    AVSimAdapter = None

try:
    from .scientific_adapter import ScientificSimAdapter
except ImportError:
    ScientificSimAdapter = None

__all__ = [
    # Core
    "DuplexAdapter",
    "EntitySyncHub",
    "get_entity_sync_hub",
    # Full-duplex adapters
    "UnrealAdapter",
    "BlenderAdapter",
    "OmniverseConnector",
    "RobloxHTTPAdapter",
    "GodotAdapter",
    "O3DEAdapter",
    "UnityAdapter",
    "WebBridge",
    # Domain adapters
    "MilitarySimAdapter",
    "AVSimAdapter",
    "ScientificSimAdapter",
]
