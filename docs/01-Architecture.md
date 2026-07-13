# Block-Offset Engine: Architecture Overview

**Document Date:** 2026-07-12  
**Status:** Current (aligned with PORT_ALLOCATION.md)  
**Version:** Phase 5 Complete

---

## Core Architecture

The Block-Offset Engine is a distributed, full-duplex adapter ecosystem with:
- **Central Storage:** SQLite-backed ResilientStore with zlib compression
- **Real-time Sync:** EntitySyncHub for cross-adapter object synchronization
- **Network Protocol:** DPLX (binary wire protocol with 18+ message types)
- **Multi-Platform:** 8 game engine adapters + 4 domain-specific adapters
- **Browser Integration:** WebSocket 3D viewer (Three.js)

### Block Addressing Formula

```
offset(x,y,z) = (z×W×H + y×W + x) × 16 bytes
```
- Each block = 16 bytes (metadata + 8-byte payload)
- 32-bit x,y,z coordinates
- Storage: world.img.seq binary file with SHA-256 checksums

---

## Port Allocation (Current - 2026-07-12)

### ⚠️ CORRECTION NOTICE
**Previous memory (stale):**
- UE5 = 7100, Unity = 7200, Godot = 7300, O3DE = 7400

**ACTUAL current allocation** (from PORT_ALLOCATION.md):
- **Unreal = 7100**
- **Blender = 7200** ← (not Unity)
- **Omniverse = 7300** ← (not Godot)
- **Roblox = 7400** ← (not O3DE)
- **Godot = 7500** ← (moved up)
- **O3DE = 7502** ← (moved to 7502)
- **Unity = 7503** ← (moved to 7503)
- **WebBridge = 7507** ← (WebSocket 3D viewer)

### Full-Duplex TCP Adapters (DPLX Protocol)

| Port | Adapter | Purpose | Commands | Status |
|------|---------|---------|----------|--------|
| 7100 | UnrealAdapter | Unreal Engine 5.x | 26 | ✅ Active |
| 7200 | BlenderAdapter | Procedural generation | 24 | ✅ Active |
| 7300 | OmniverseConnector | NVIDIA Omniverse USD | 28 | ✅ Active |
| 7400 | RobloxHTTPAdapter | Roblox Studio | 24 | ✅ Active |
| 7500 | GodotAdapter | Godot 3.x/4.x | 18 | ✅ Active |
| 7502 | O3DEAdapter | Amazon O3DE | 12 | ✅ Active |
| 7503 | UnityAdapter | Unity Engine | 15 | ✅ Active |
| 7507 | WebBridge | WebSocket viewer | N/A | ✅ Active |

**Total Commands:** 147 across 8 adapters  
**Port Conflicts:** 0  
**Reserved Ports:** 7501, 7504-7506, 7508-7509

### HTTP & Legacy Ports

| Port | Adapter | Protocol | Status |
|------|---------|----------|--------|
| 8000 | RobloxHTTPAdapter (Legacy) | HTTP REST | ✅ Active |
| 3000 | MilitarySimAdapter | DIS | Optional |
| 9200 | StarlinkAdapter | gRPC | Optional |

---

## Full-Duplex Architecture

### Network Protocol: DPLX

Binary frame format:
```
[MAGIC 4B "DPLX"][TYPE 1B][MSG_ID 2B][PAYLOAD_LEN 4B][JSON PAYLOAD]
```

**Message Types (18+):**
- 0x01: WRITE_BLOCK (single block write)
- 0x02: WRITE_BATCH (batch blocks)
- 0x03: QUERY (data query)
- 0x04: SUBSCRIBE (event subscription)
- 0x05: BLOCK_DELTA (incremental update)
- 0x06: STATE_UPDATE (state change)
- 0x07: COMMAND (adapter command)
- 0x08: ACK (acknowledgment)
- 0x09: ERROR (error report)
- 0x0A: PING / 0x0B: PONG (keepalive)
- 0x13: ENTITY_SYNC_EVENT (cross-adapter entity update)
- 0x27: ENTITY_COMMAND (new entity creation)
- 0x32: RESPONSE (command response)

### Threading Model

Per-adapter threading (5 daemon threads):
1. `accept_loop` - Accept new client connections
2. `send_loop` - Send queued messages to clients
3. `recv_loop` - Receive and parse messages from clients
4. `heartbeat_loop` - Keepalive pings
5. `write_processor` - Block write authorization + storage

**Thread Safety:** Per-client message queues, hub listener locks, atomic operations

---

## Entity Synchronization Hub

**Purpose:** Cross-adapter real-time object synchronization

### Architecture

Hub-and-spoke pattern:
```
UnrealAdapter ──┐
BlenderAdapter ─┤
OmniverseConn ──┤
RobloxAdapter ──┼─→ EntitySyncHub ←─┐
GodotAdapter ───┤                    ├─→ Message Bus
O3DEAdapter ────┤                    │
UnityAdapter ───┤                   All adapters
WebBridge ──────┘                 subscribed for
                                    updates
```

### Entity Lifecycle

1. **Creation:** Object spawned in any platform → `ENTITY_COMMAND` (0x27)
2. **Registration:** Hub receives → assigns global 32-bit entity_id
3. **Broadcast:** Hub forwards to all subscribed adapters → `ENTITY_SYNC_EVENT` (0x13)
4. **Local Creation:** Each adapter spawns object locally with matching ID
5. **Modification:** Any adapter changes object → sends ENTITY_SYNC_EVENT → all others update
6. **Destruction:** ENTITY_DESTROYED event → cleaned up everywhere

### Event Types

```python
enum EntityEventType:
    ENTITY_CREATED = 0
    MOVED = 1
    ROTATED = 2
    SCALED = 3
    MODIFIED = 4
    DESTROYED = 5
    ATTACHED = 6
    DETACHED = 7
    VISIBLE = 8
    LOCKED = 9
    UNLOCKED = 10
```

### Platform Types

```python
enum PlatformType:
    UNREAL = 0
    BLENDER = 1
    OMNIVERSE = 2
    ROBLOX = 3
    GODOT = 4
    GODOT4 = 5
    UNITY = 6
    O3DE = 7
    MILITARY = 8
    SCIENTIFIC = 9
    AUTONOMOUS = 10
    WEB = 11
    STARLINK = 12
```

### Transform Data

```python
@dataclass
class Transform:
    x: float      # Position X
    y: float      # Position Y
    z: float      # Position Z
    rx: float     # Rotation X (radians)
    ry: float     # Rotation Y (radians)
    rz: float     # Rotation Z (radians)
    sx: float     # Scale X
    sy: float     # Scale Y
    sz: float     # Scale Z
```

---

## Storage Layer

### Hierarchy

```
ResilientStore
  ├─ FlatStore (64-block region chunks)
  ├─ Journal (transaction log)
  ├─ Block Layout (coordinate system)
  └─ Compression (zlib)

    ↓

SQLite Database (world.db)
  ├─ blocks table (offset, data, timestamp, checksum)
  ├─ metadata table (world config, version)
  └─ journal table (transaction history)

    ↓

Disk Files
  ├─ world.img.seq (binary block data)
  ├─ world.db.seq (SQLite snapshots)
  ├─ world.jrn (journal file)
  └─ world.img.sha (SHA-256 checksums)
```

### Recovery

- Resilient recovery on corruption
- SHA-256 block verification
- Journal replay on crash
- Atomic transactions

---

## Web 3D Viewer

**Port:** 7507 (WebSocket)  
**Protocol:** WebSocket frames with JSON payload  
**Frontend:** Three.js WebGL renderer  
**File:** web/index.html

### Rendering

- Instanced mesh rendering (up to 4,096 blocks)
- Grid-based 1:1 block positioning
- Light blue cubes (0x60a5fa) with standard lighting
- Real-time updates via WebSocket
- 60 FPS target

### Message Types

**Server → Browser:**
- `snapshot` - Initial block state (contains array of blocks)
- `block_update` - Individual block position/type change

**Browser → Server:**
- Standard WebSocket ping/pong

### Connection Flow

```
Block-Offset Engine
    ↓
RenderFeed (block change stream)
    ↓
WebBridge._on_block_delta()
    ↓
JSON serialization (snapshot or block_update)
    ↓
WebSocket frame transmission
    ↓
web/index.html JavaScript
    ↓
Three.js Scene Update
    ↓
Browser Canvas Rendering
    ↓
User sees live 3D
```

---

## Adapter Ecosystem

### Full-Duplex Game Engine Adapters (8 total)

Each inherits from `DuplexAdapter` base class:
- Unified TCP/DPLX networking
- Entity sync hub integration
- Command interface
- Real-time bidirectional updates

**Combined Command Count:** 147 commands

### Domain-Specific Adapters (4 total)

Non-network adapters for specialized domains:
- **MilitarySimAdapter** (HLA/RTI federation)
- **AVSimAdapter** (ROS2/CARLA/AirSim)
- **ScientificSimAdapter** (NetCDF/HDF5 simulations)
- **ProtocolUtilities** (DIS translator, Godot4Bridge)

These use the entity_sidecar for metadata but don't expose TCP listeners.

---

## Launcher & Configuration

**File:** start_duplex_server.py

**Command-line Options:**
```bash
--host 127.0.0.1      # Listen address (default)
--adapters all        # Which adapters to start:
                      #   all, game-engines, military,
                      #   scientific, web, minimal
```

**Startup Order (default "all"):**
1. Unreal (7100)
2. Blender (7200)
3. Omniverse (7300)
4. Roblox (7400/8000)
5. Godot (7500)
6. O3DE (7502)
7. Unity (7503)
8. WebBridge (7507)

---

## Getting Started

### Quick Start

```bash
# Activate environment
source .venv/bin/activate

# Start all adapters
python start_duplex_server.py --adapters all

# In another terminal, start 3D viewer
cd web && python -m http.server 8080

# Open browser: http://localhost:8080
```

### Testing

```bash
# Run all tests
pytest tests/ -v

# Expected: 56/56 tests passing
```

### Development

**Key Files:**
- Core: `src/block_engine/flat_store.py`, `resilient_store.py`
- Adapters: `src/block_engine/bridges/[adapter_name].py`
- Hub: `src/block_engine/bridges/entity_sync.py`
- Base: `src/block_engine/bridges/duplex_base.py`
- Web: `web/index.html`

---

## Documentation References

- **PORT_ALLOCATION.md** - Current port assignments and conflict resolution
- **ENTITY_SYNC_PROTOCOL.md** - Entity synchronization specification
- **ENTITY_SYNC_QUICKSTART.md** - Quick implementation guide
- **ADAPTER_COMMANDS.md** - All 147 commands across adapters
- **PROJECT_LINKAGE_MAP.md** - Complete file dependency map
- **CLEANUP_COMPLETION.md** - Project structure audit report

---

## Version History

| Version | Date | Major Changes |
|---------|------|---------------|
| 1.0.2-audit | 2026-07-12 | Project structure audit + port fix |
| 1.0.2 | 2026-07-12 | WebSocket port correction |
| 1.0.1 | 2026-07-11 | Entity sync + 8 full-duplex adapters |
| 1.0.0 | 2026-07-10 | Initial Phase 5 complete |

---

**Last Updated:** 2026-07-12  
**Maintainer:** Block-Offset Team  
**License:** See LICENSE file
