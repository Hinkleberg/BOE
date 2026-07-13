"""
Block-Offset Engine: Full-Duplex Adapter Ecosystem

Core package containing:
- Adapter implementations for multiple game engines and simulation platforms
- Entity synchronization hub for cross-adapter real-time updates
- Wire protocol and networking infrastructure
- Storage layer (resilient stores, caches)
- World simulation environment
"""

__version__ = "1.0.0"
__author__ = "Block-Offset Team"

from .core_api import CORE_API_VERSION, BOECoreAPI

__all__ = ["__version__", "__author__", "CORE_API_VERSION", "BOECoreAPI"]
