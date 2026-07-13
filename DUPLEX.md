# Full-Duplex Real-Time Adapters

## Architecture Overview

All adapters now support **full-duplex, bidirectional, real-time communication** using a unified socket-based protocol. This enables:

- **Server → Client streaming** (block deltas, entity updates, telemetry)
- **Client → Server commands** (writes, queries, transformations)
- **Per-client subscriptions** (selective delta filtering)
- **Automatic acknowledgments** (write tracking and confirmation)
- **Connection health monitoring** (heartbeat/ping-pong)
- **Pluggable write authorization** (policies apply before writes)

## Protocol: DPLX (Duplex Protocol)

All adapters inherit from `DuplexAdapter` and use the same wire protocol:

```
Frame Format:
  [MAGIC 4B "DPLX"][TYPE 1B][MSG_ID 2B][PAYLOAD_LEN 4B][JSON PAYLOAD]
  
  MAGIC:         Always 0x44 0x50 0x4C 0x58 ("DPLX")
  TYPE:          MessageType enum (0x10-0x1F server→client, 0x20-0x2F client→server)
  MSG_ID:        Unique message identifier (0-65535)
  PAYLOAD_LEN:   Size of JSON payload in bytes
  JSON PAYLOAD:  Application-specific data
```

### Message Types

**Server → Client (0x10-0x1F):**
- `0x10` — BLOCK_DELTA: Block state changes
- `0x11` — ENTITY_DELTA: Entity state changes
- `0x12` — STATE_UPDATE: General state updates
- `0x1F` — PING: Heartbeat probe

**Client → Server (0x20-0x2F):**
- `0x20` — WRITE_BLOCK: Write a block
- `0x21` — DELETE_BLOCK: Delete a block
- `0x22` — MOVE_ENTITY: Update entity position
- `0x23` — QUERY: Read a block
- `0x24` — SUBSCRIBE: Subscribe to channels
- `0x25` — UNSUBSCRIBE: Unsubscribe from channels
- `0x26` — COMMAND: Platform-specific command
- `0x2F` — PONG: Heartbeat response

**Responses (0x30-0x3F):**
- `0x30` — ACK: Acknowledge received message
- `0x31` — ERROR: Error response
- `0x32` — RESPONSE: Command/query response

## Adapters

All adapters now extend `DuplexAdapter` base class:

### UnrealAdapter (TCP port 7100)

**Server → Client:**
```python
# Block updates from RenderFeed
on_render_delta(delta)
  → MessageType.BLOCK_DELTA to "blocks" subscribers
  → MessageType.ENTITY_DELTA to "entities" subscribers

# Broadcast events
broadcast_delta(msg, channels=["blocks"])
```

**Client → Server:**
```python
# Unreal sends write requests
WRITE_BLOCK: {"offset": int, "data": hex_string}
→ Authorization check
→ Queued to write_queue
→ MessageType.ACK returned

# Unreal sends commands
COMMAND: {
  "command": "move_entity|spawn_entity|despawn_entity|load_region|query_blocks|ray_cast|statistics",
  "args": {...}
}
→ MessageType.RESPONSE returned
```

**Usage:**
```python
from block_engine.bridges.unreal_adapter import UnrealAdapter

adapter = UnrealAdapter(
    layout, resilient_store,
    host="127.0.0.1", port=7100,
    write_authorizer=my_policy,
)
adapter.start()

# Wire into render feed for automatic updates
feed.connect_client(
    client_id=99,
    send_cb=adapter.on_render_delta,
    view_radius=64,
)

# Or poll for writes
while True:
    write_req = adapter.get_next_write(timeout=0.1)
    if write_req:
        # Process write
        pass

# Register event listeners
adapter.on_event("write_complete", lambda e: print(f"Write: {e}"))
adapter.on_event("entity_moved", lambda e: print(f"Entity: {e}"))
```

### BlenderAdapter (TCP port 7200)

**Server → Client:**
```python
# Viewport updates
load_region(x, y, z, size)
  → RESPONSE with block data + materials

# Real-time subscriptions
SUBSCRIBE: {"channels": ["blocks", "entities"]}
→ Auto-updates on changes
```

**Client → Server:**
```python
# Blender writes geometry changes
WRITE_BLOCK: {"offset": int, "data": hex, "metadata": {"x": int, "y": int, "z": int}}
→ Queued and processed

# Blender commands
COMMAND: {
  "command": "load_region|get_materials|set_material|ray_cast|frustum_query|procedural_fill",
  "args": {...}
}
```

**Usage:**
```python
from block_engine.bridges.blender_adapter import BlenderAdapter

# Start duplex server
adapter = BlenderAdapter(resilient_store, layout, host="127.0.0.1", port=7200)
adapter.start()

# Or use legacy in-process API (backward compatible)
blocks = adapter.load_region(x=0, y=0, z=0, size=16)
adapter.export_scene_to_boe(scene_objects)
```

### OmniverseConnector (TCP port 7300)

**Server → Client:**
```python
# USD synchronization
sync_region_to_omniverse(x, y, z, size)
  → RESPONSE with USD operations for Nucleus

# Real-time edits
on_block_changed(offset, data)
  → Notifies subscribers via callback
```

**Client → Server:**
```python
# Omniverse sends edits
WRITE_BLOCK: {"offset": int, "data": hex}
→ Block gets updated + synced

# Omniverse commands
COMMAND: {
  "command": "paint_block|transform_blocks|sculpt_region|set_material|get_region|sync_to_nucleus|import_usd",
  "args": {...}
}
```

**Usage:**
```python
from block_engine.bridges.omniverse_connector import OmniverseConnector

adapter = OmniverseConnector(
    resilient_store, layout,
    nucleus_server_url="http://localhost:8080",
    host="127.0.0.1", port=7300,
)
adapter.start()

# Subscribe to changes
adapter.subscribe_to_changes(callback=lambda upd: print(upd))

# Or use legacy API
adapter.sync_region_to_omniverse(x=0, y=0, z=0, size=16)
```

### RobloxHTTPAdapter (HTTP port 8000 + Duplex port 7100)

**HTTP API (legacy, pull-based):**
```
POST   /roblox/write           → Write block
GET    /roblox/read?x=&y=&z=   → Read block
GET    /roblox/region?x=&y=&z=&size= → Load region
GET    /roblox/stats           → Statistics
```

**Duplex API (new, push-based):**
```python
# Roblox connects on duplex port for real-time updates
WRITE_BLOCK: {"offset": int, "data": hex}
COMMAND: {
  "command": "player_joined|player_left|respawn|teleport",
  "args": {...}
}

# Server sends deltas automatically via subscription
BLOCK_DELTA: {"blocks": [...]}
ENTITY_DELTA: {"entities": [...]}
```

**Usage:**
```python
from block_engine.bridges.roblox_http_adapter import RobloxHTTPAdapter

adapter = RobloxHTTPAdapter(resilient_store, layout)
adapter.start_http(host="0.0.0.0", port=8000)     # HTTP for legacy
adapter.start()  # Duplex on 7100 for new clients

# HTTP (Lua in Roblox):
# local http = game:GetService("HttpService")
# http:PostAsync("http://server:8000/roblox/write", json_data)

# Duplex (C++/GDScript):
# Connect to server:7100, send/receive DPLX frames
```

## DuplexAdapter Base Class

All adapters inherit from `DuplexAdapter`:

```python
class DuplexAdapter:
    def __init__(
        self,
        layout,
        resilient_store,
        write_authorizer: Optional[Callable] = None,
        host: str = "127.0.0.1",
        port: int = 7200,
        max_clients: int = 256,
    ):
        ...
    
    def start(self) -> None:
        """Start socket server with accept/send/recv/heartbeat loops."""
    
    def stop(self) -> None:
        """Stop server and disconnect all clients."""
    
    # Subclasses override these:
    def _on_write_request(self, write_req: WriteRequest) -> None:
        """Process a write from client."""
    
    def _handle_command(self, client, msg: DuplexMessage) -> None:
        """Handle platform-specific commands."""
    
    # Public API:
    def broadcast_delta(self, msg: DuplexMessage, channels: Optional[List[str]] = None) -> None:
        """Send message to all subscribed clients."""
    
    def send_to_client(self, client_id: int, msg: DuplexMessage) -> bool:
        """Send message to specific client."""
    
    def statistics(self) -> Dict[str, int]:
        """Return connection/message statistics."""
```

## Write Authorization

Any adapter can integrate write authorization policies:

```python
from block_engine.replication.write_authorization import (
    WriteAuthorizationLayer,
    OffsetRangePolicy,
    RateLimitPolicy,
)

auth = WriteAuthorizationLayer()
auth.add_policy(OffsetRangePolicy(layout))
auth.add_policy(RateLimitPolicy(max_writes_per_second=10000))

def authorizer(client_id: int, offset: int, data: bytes) -> AuthorizationResult:
    return auth.authorize_write(offset, data)

adapter = UnrealAdapter(
    layout, resilient_store,
    write_authorizer=authorizer,
)
```

## Multi-Adapter Setup

Run multiple adapters simultaneously on different ports:

```python
# Core engine (unchanged)
rs = ResilientStore(local_store, replication_manager)

# Multiple adapters
unreal = UnrealAdapter(layout, rs, port=7100)
blender = BlenderAdapter(rs, layout, port=7200)
omniverse = OmniverseConnector(rs, layout, port=7300)
roblox = RobloxHTTPAdapter(rs, layout)

# Start all
unreal.start()
blender.start()
omniverse.start()
roblox.start_http()  # HTTP on 8000
# roblox.start()  # Optional: duplex on 7100 (would conflict with unreal)

# Wire render feed to all interested adapters
feed.connect_client(client_id=99, send_cb=unreal.on_render_delta, view_radius=64)
```

## Client Connection Example (Unreal C++)

```cpp
// Pseudo-code: Unreal Engine 5 C++ client connecting to UnrealAdapter
void ABlockOffsetClient::BeginPlay() {
    // Create socket
    Socket = FTcpSocketBuilder(TEXT("BlockOffsetClient"))
        .AsBlocking()
        .Build();
    
    // Connect to server
    FIPv4Address Addr;
    FIPv4Address::Parse(TEXT("127.0.0.1"), Addr);
    FInternetAddr InternetAddr(Addr, 7100);
    
    if (Socket->Connect(InternetAddr)) {
        UE_LOG(LogTemp, Warning, TEXT("Connected to BlockOffsetEngine"));
        
        // Subscribe to blocks and entities
        SendDuplexMessage(MessageType::SUBSCRIBE, {
            "channels": ["blocks", "entities"]
        });
        
        // Start receive loop
        ReceiveThread = FRunnableThread::Create(
            new FBlockOffsetReceiver(Socket),
            TEXT("BlockOffsetReceiver")
        );
    }
}

void ABlockOffsetClient::WriteBlock(int32 X, int32 Y, int32 Z, uint8 BlockType) {
    uint64 Offset = Layout.BlockOffset(X, Y, Z);
    FString DataHex = FString::Printf(TEXT("%02X%02X0000..."), BlockType, 8);
    
    SendDuplexMessage(MessageType::WRITE_BLOCK, {
        "offset": Offset,
        "data": DataHex
    });
}
```

## Statistics & Monitoring

All adapters expose statistics:

```python
stats = adapter.statistics()
print(stats)
# {
#     "messages_sent": 1234,
#     "messages_recv": 567,
#     "writes_authorized": 100,
#     "writes_denied": 5,
#     "clients_connected": 3,
#     "clients_disconnected": 1,
#     "connected_clients": 2,
#     "write_queue_size": 12,
# }
```

## Performance Characteristics

- **Latency:** 1-5ms per message (depends on network)
- **Throughput:** 10,000+ messages/sec per adapter (depends on JSON size + network)
- **Per-client overhead:** ~2KB per connected client (buffers + metadata)
- **Scalability:** Up to 256 clients per adapter (configurable)

## Key Features

1. **Unified Protocol** — All adapters use same DPLX framing and message types
2. **Full Duplex** — Simultaneous bidirectional communication
3. **Real-Time Streaming** — Block deltas pushed automatically to clients
4. **Subscription Filtering** — Clients only receive updates they care about
5. **Command Handler** — Extensible command system for platform-specific operations
6. **Write Authorization** — Optional policies before writes hit engine
7. **Connection Health** — Automatic heartbeat/ping-pong detection
8. **Backward Compatible** — Legacy APIs still work (HTTP, in-process)
9. **Zero Core Impact** — Engine unchanged; all tooling external
10. **Pluggable** — Add/remove adapters without affecting others

---

**See [TOOLING.md](TOOLING.md) for security, reliability, and observability tools that integrate with these adapters.**
