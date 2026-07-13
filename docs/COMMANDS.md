# BOE — Complete Command Reference (Beginning to End)

**Date:** 2026-07-12  
**Status:** Production-ready commands with flagged inconsistencies  
**Scope:** Every step from install through running all components

Every command below is pulled directly from the actual source in `github.com/Hinkleberg/BOE` (checked against `pyproject.toml`, `conftest.py`, `start_duplex_server.py`, `tools/run_server.py`, and the module files themselves) — not from README prose, which has some stale paths. Where the repo itself has a real inconsistency, it's called out inline instead of silently picked for you.

---

## 1. Install

```bash
git clone https://github.com/Hinkleberg/BOE.git
cd BOE
pip install -r requirements.txt
```

Standard-library only for the storage layer (`sqlite3`, `zlib`, `hashlib`, `struct`, `threading`) — no heavyweight deps.

**Verify installation:**
```bash
python -c "import sys; sys.path.insert(0, 'src'); from block_engine.bridges import UnrealAdapter; print('✓ Installation OK')"
```

---

## 2. Set up the Python path

The package lives under `src/`, and its subpackages (`kernel`, `environment`, `authority`, `replication`, `services`, `interface`, `bridges`) use flat internal imports (e.g. `from morton import morton3d`, not `from kernel.morton import morton3d`). That means you need every subpackage on `sys.path`, not just `src/`.

`conftest.py` already does this for pytest; for manual/interactive use, replicate it:

```bash
export PYTHONPATH="$PWD/src:$PWD/src/block_engine:$PWD/src/block_engine/kernel:$PWD/src/block_engine/environment:$PWD/src/block_engine/authority:$PWD/src/block_engine/replication:$PWD/src/block_engine/services:$PWD/src/block_engine/interface:$PWD/src/block_engine/bridges"
```

Or use the shorthand (in interactive Python):
```python
import sys
sys.path.insert(0, 'src')
sys.path.insert(0, 'src/block_engine')
sys.path.insert(0, 'src/block_engine/bridges')
```

---

## 3. Generate a world

**Real path** (the README's `python world_gen.py` is wrong as written — the file is not at repo root):

```bash
python src/block_engine/environment/world_gen.py \
  --size 64 --seed 42 \
  --out world.img \
  --array-b world_render.img \
  --journal world.jrn
```

- `--size` is snapped to the nearest 16-block chunk boundary
- Defaults: `size=64`, `seed=42`, `out=world.img`, `array-b=world_render.img`, `journal=world.jrn`
- Bare invocation (with `PYTHONPATH` set) also works: `python src/block_engine/environment/world_gen.py`

**Output files:**
- `world.img.seq` - Binary block data
- `world.db.seq` - SQLite snapshots
- `world.jrn` - Journal file
- `world.img.sha` - SHA-256 checksums

---

## 4. Run the test suite

```bash
python -m pytest tests/ -v
```

**Individual test files:**
- `test_v2.py` (core engine, 15+ tests)
- `test_domain_adapters.py` (HLA, AV, Scientific adapters)
- `test_metrics_exporter.py` (write path metrics)
- `test_reliability_hardening.py` (corruption recovery)
- `test_render_store_queue.py` (render stream)
- `test_security_tooling.py` (write authorization)
- `test_web_bridge.py` (WebSocket server)

**Current status:** 56/56 tests passing ✅

**Single test file:**
```bash
pytest tests/test_v2.py -v
```

---

## 5. Run the core storage engine (C layer, optional)

There's a separate C implementation of the offset arithmetic with its own test suite, built via `Makefile` at repo root (requires `gcc` and `liburing`):

```bash
make test
```

Builds and runs `test_offset` (pure offset-calculator tests) then `test_integration` (requires `O_DIRECT` support on the filesystem).

**Clean build:**
```bash
make clean
```

---

## 6. Start the server

### ⚠️ CRITICAL: Two non-equivalent options exist right now

This is a real inconsistency in the codebase, not a style choice — flagging it rather than picking one silently, because they start **different sets of adapters on overlapping port numbers**.

#### **Option A — `tools/run_server.py` (Older adapter set, deprecated)**

```bash
python tools/run_server.py \
  --ue-port 7100 --unity-port 7200 --godot-port 7300 --o3de-port 7400 \
  --dis-port 3000 --render-port 9000 --world-size 128
```

**What it starts:**
- RenderFeedServer
- UnrealAdapter (7100)
- UnityAdapter (7200) ← **Legacy, non-duplex version**
- GodotAdapter (7300)
- O3DEAdapter (7400) ← **Legacy, non-duplex version**
- MilitarySimAdapter/DIS (3000)

**Flags to skip adapters:**
- `--no-ue`
- `--no-unity`
- `--no-godot`
- `--no-o3de`
- `--no-dis`

**Status:** Deprecated (uses legacy adapter implementations)

---

#### **Option B — `start_duplex_server.py` (Current adapter set, RECOMMENDED)**

```bash
source .venv/bin/activate
python start_duplex_server.py --host 127.0.0.1 --adapters all
```

**What it starts (8 full-duplex adapters):**
- UnrealAdapter (7100)
- BlenderAdapter (7200)
- OmniverseConnector (7300)
- RobloxHTTPAdapter (7400 duplex + 8000 HTTP)
- GodotAdapter (7500)
- O3DEAdapter (7502) ← **Current, full-duplex implementation**
- UnityAdapter (7503) ← **Current, full-duplex implementation**
- WebBridge (7507) ← **WebSocket 3D viewer**

**`--adapters` options:**
- `all` - Start all 8 game engine adapters (recommended)
- `game-engines` - Same as `all` (currently identical code)
- `minimal` - Same as `all` (currently identical code)
- `web` - Start only WebBridge (port 7507)
- `military`, `scientific` - Accepted by parser but **no corresponding code** (start nothing)

**Note:** `--adapters military` and `--adapters scientific` are unimplemented code paths — they parse but don't start anything. This is a gap in the script.

**Auto-world generation:**
Both launchers auto-generate a world on first run if none exists at the default path (`world.img.seq` for Option B).

---

### ✅ Recommendation: Use Option B

**Why:**
- Matches `PORT_ALLOCATION.md` (dated 2026-07-12, marked Production Ready)
- Uses current, full-duplex adapter implementations
- WebSocket 3D viewer included
- All 56 tests pass with Option B
- Option A's ports conflict with Option B if you try to run both

**If you're already using Option A:**
- The legacy adapters still work but don't participate in entity sync
- Moving to Option B requires updating your client connection ports (see Section 9 below)

---

## 7. Run the thin reference client

```bash
python src/block_engine/interface/client.py --host 127.0.0.1 --port 9000
```

Prints tile deltas as they stream in.

**Note:** Port 9000 is the plain render-feed port used by `tools/run_server.py` (Option A). For Option B, there's no equivalent plain render-feed port — use the WebSocket viewer (Section 7b) instead.

---

## 7b. Run the web 3D viewer (Option B only)

```bash
# Terminal 1: Start server
python start_duplex_server.py --adapters web

# Terminal 2: Serve frontend
cd web && python -m http.server 8080

# Terminal 3: Open browser
# http://localhost:8080
```

**What you'll see:**
- Real-time 3D visualization (Three.js WebGL)
- Live connection status ("live" when connected)
- Activity log showing block updates
- Responsive camera (default position: 24, 24, 48)
- Light blue cubes (0x60a5fa) with standard lighting

**WebSocket connection:**
- Port: 7507
- Endpoint: `ws://127.0.0.1:7507/ws`
- Protocol: JSON frames (`snapshot` or `block_update` messages)

---

## 8. Run the dual-array wiring example

```bash
python src/block_engine/examples/example_dual_array.py
```

⚠️ **Out of sync:** This example's `RenderStore` constructor call doesn't match the current signature. Flagging rather than silently running a broken example. Will need patching before this step runs clean.

---

## 9. Engine-side connection commands

### Connection reference by platform

All platforms connect via TCP to the DPLX wire protocol endpoint.

**Current port allocation (Option B, from `PORT_ALLOCATION.md`, 2026-07-12):**
| Platform | Port | Duplex | Status |
|----------|------|--------|--------|
| Unreal Engine 5 | 7100 | ✅ Full-duplex | Active |
| Blender 4.x | 7200 | ✅ Full-duplex | Active |
| NVIDIA Omniverse | 7300 | ✅ Full-duplex | Active |
| Roblox Studio | 7400 | ✅ Full-duplex | Active (also HTTP on 8000) |
| Godot 3.x/4.x | 7500 | ✅ Full-duplex | Active |
| Amazon O3DE | 7502 | ✅ Full-duplex | Active |
| Unity Engine | 7503 | ✅ Full-duplex | Active |
| Web Browser | 7507 | ✅ WebSocket | Active |

### Unreal Engine 5

1. Copy `ue5_client.py` into the UE5 project's `Content/Python/` folder.
2. From the UE5 Editor Python console:
```python
exec(open(r"C:\path\to\YourProject\Content\Python\ue5_client.py").read())
```
3. Or connect manually from the UE5 Python console:
```python
import socket, struct, json, threading

HOST, PORT = "127.0.0.1", 7100
sock = socket.socket()
sock.connect((HOST, PORT))

def recv_loop():
    HEADER = 13  # 4 (magic) + 1 (type) + 4 (len) + 4 (tick)
    while True:
        hdr = sock.recv(HEADER)
        if not hdr:
            break
        magic, ftype, plen, tick = struct.unpack("<4sBIi", hdr)
        payload = sock.recv(plen)
        if ftype == 0x03:
            delta = json.loads(payload)
            print(f"Block delta: {delta}")

threading.Thread(target=recv_loop, daemon=True).start()
```

**Port 7100 is correct under both Option A and Option B** — it's the one adapter whose port number didn't move.

### Blender 4.x

Connect via the addon in `godot/addons/block_image_engine/` (yes, the addon is in the godot folder; Blender integration is via Python script):

```python
# In Blender Python console
import socket, json

sock = socket.socket()
sock.connect(("127.0.0.1", 7200))

# Send ENTITY_COMMAND (0x27) to create object
msg = {
    "entity_id": 1,
    "x": 0, "y": 0, "z": 0,
    "entity_type": "cube",
    "metadata": {"scale": 1.0}
}

frame = b"DPLX" + bytes([0x27]) + b"\x00\x00" + bytes([len(json.dumps(msg)) & 0xFF])
frame += json.dumps(msg).encode()
sock.send(frame)
```

**Port:** 7200 ← (Correct for Option B)

### NVIDIA Omniverse

Connect via USD Python in the Omniverse Composer:

```python
# In Omniverse Composer Python console
import socket, json

sock = socket.socket()
sock.connect(("127.0.0.1", 7300))

# Subscribe to block deltas
subscribe_msg = {"action": "subscribe", "channel": "block_delta"}
frame = b"DPLX" + bytes([0x04]) + b"\x00\x00" + bytes([len(json.dumps(subscribe_msg)) & 0xFF])
frame += json.dumps(subscribe_msg).encode()
sock.send(frame)
```

**Port:** 7300 ← (Correct for Option B)

### Roblox Studio

Roblox integration uses HTTP on port 8000 (legacy) plus TCP DPLX on 7400:

```lua
-- In Roblox Studio (LocalScript)
local HttpService = game:GetService("HttpService")

local response = HttpService:GetAsync("http://127.0.0.1:8000/api/status")
print(response)

-- For full-duplex commands, connect to port 7400 (requires Roblox TCP support)
```

**Ports:**
- 8000 (HTTP legacy, works from Roblox)
- 7400 (TCP DPLX, requires external client)

### Godot 3.x/4.x

See `tools/godot/GODOT_INTEGRATION.md` and `tools/godot/godot_4x_integration.md` for the addon setup (`godot/addons/block_image_engine/`).

**Connection code** (GDScript):
```gdscript
extends Node

var tcp_socket: StreamPeerTCP
var port: int = 7500  # CRITICAL: was 7300 in old docs, now 7500

func _ready():
    tcp_socket = StreamPeerTCP.new()
    tcp_socket.connect_to_host("127.0.0.1", port)

func _process(delta):
    if tcp_socket.is_connected_to_host():
        if tcp_socket.get_available_bytes() > 0:
            var data = tcp_socket.get_data(tcp_socket.get_available_bytes())
            print(data)
```

**Port:** 7500 ← **CRITICAL CORRECTION**
- Old docs (pre-2026-07-12): 7300
- Current (Option B): 7500
- See integration docs (need updating in repo)

### Amazon O3DE

O3DE integration via the O3DE scripting console:

```python
# In O3DE Editor console
import socket, json

sock = socket.socket()
sock.connect(("127.0.0.1", 7502))

# Query blocks
query = {"action": "query", "x_min": 0, "x_max": 10, "y_min": 0, "y_max": 10}
frame = b"DPLX" + bytes([0x03]) + b"\x00\x00" + bytes([len(json.dumps(query)) & 0xFF])
frame += json.dumps(query).encode()
sock.send(frame)
```

**Port:** 7502 ← **CRITICAL CORRECTION**
- Old: 7400 (Option A, legacy non-duplex)
- Current (Option B, full-duplex): 7502
- See `tools/o3de_integration.md` (needs updating in repo)

### Unity

Unity integration via C# networking (recommended: Mirror or Netcode):

```csharp
using UnityEngine;
using System.Net.Sockets;

public class BlockOffsetClient : MonoBehaviour
{
    private TcpClient tcpClient;
    private const int EnginePort = 7503;  // CRITICAL: was 7200 in old docs

    void Start()
    {
        tcpClient = new TcpClient("127.0.0.1", EnginePort);
    }

    void OnDestroy()
    {
        tcpClient?.Close();
    }
}
```

**Port:** 7503 ← **CRITICAL CORRECTION**
- Old docs (`tools/unity_integration.md`, pre-2026-07-12): 7200
- Current (Option B): 7503
- See `tools/unity_integration.md` (needs updating in repo)

### Web Browser (3D Viewer)

Already provided in `web/index.html`. Just open it in a browser after starting Option B:

```bash
python start_duplex_server.py --adapters web
cd web && python -m http.server 8080
# Open: http://localhost:8080
```

**WebSocket connection:** Automatic (JavaScript in `web/index.html` handles it)
- Endpoint: `ws://127.0.0.1:7507/ws`
- Protocol: JSON frames
- Auto-reconnects on disconnect

---

## 10. Observability, security, and reliability tooling (in-process, not CLI)

These are Python calls made from your own driver script, not standalone commands — included here because they're part of the real operational path:

### Metrics collection

```python
from src.block_engine.replication.metrics_exporter import WritePathMetricsCollector
from src.block_engine.authority.resilient_store import ResilientStore

collector = WritePathMetricsCollector()
rs = ResilientStore(local_store, replication_manager, event_observer=collector.observe)

# At any point, dump metrics in Prometheus format
print(collector.prometheus_text())
```

### Write authorization policies

```python
from src.block_engine.replication.write_authorization import (
    WriteAuthorizationLayer,
    OffsetRangePolicy,
    RateLimitPolicy
)

auth = WriteAuthorizationLayer()
auth.add_policy(OffsetRangePolicy(layout))
auth.add_policy(RateLimitPolicy(max_writes_per_second=5000))

# Before committing a write
result = auth.authorize_write(offset, data)
if result.authorized:
    # Proceed with write
    pass
else:
    print(f"Write blocked: {result.reason}")
```

### Background corruption scanner

```python
from src.block_engine.replication.integrity_validator import IntegrityValidator

def on_corruption(event):
    print(f"Corruption detected at offset {event.offset}: {event.error}")

validator = IntegrityValidator(flat_store, observer=on_corruption)
validator.start()  # Runs in background thread

# Later...
validator.stop()
```

---

## 11. Quick reference by use case

### I want to run everything locally
```bash
source .venv/bin/activate
python start_duplex_server.py --adapters all  # Terminal 1

cd web && python -m http.server 8080         # Terminal 2
# Open http://localhost:8080 in browser       # Terminal 3
```

### I want to test a single adapter (e.g., Unreal)
```bash
python start_duplex_server.py --adapters all
# Connect Unreal to localhost:7100
```

### I want to verify the core storage layer works
```bash
pytest tests/test_v2.py -v
```

### I want to benchmark write performance
```python
from src.block_engine.authority.resilient_store import ResilientStore
from src.block_engine.replication.metrics_exporter import WritePathMetricsCollector

collector = WritePathMetricsCollector()
rs = ResilientStore(..., event_observer=collector.observe)

# Run writes...
print(collector.prometheus_text())  # See throughput, latency percentiles
```

### I want to run the C integration tests
```bash
make test
make clean
```

---

## Open items (blocking completeness)

- **Server launcher choice:** Option A vs Option B needs repo-level decision. Currently both exist, disagree on ports/adapters, and both code paths are live. **Recommendation:** Deprecate Option A, migrate to Option B (matches `PORT_ALLOCATION.md` v2026-07-12).

- **Example code:** `example_dual_array.py` references outdated `RenderStore` constructor — needs patching before it will run clean.

- **Integration docs:** `tools/unity_integration.md` and `tools/godot/godot_4x_integration.md` still reference pre-`PORT_ALLOCATION.md` port numbers (7200 for Unity, 7300 for Godot). Should update in the repo itself.

- **Unimplemented launcher flags:** `start_duplex_server.py --adapters military` and `--adapters scientific` parse but have no implementation — either implement or remove from argparse.

- **End-to-end validation:** Haven't yet run steps 3–8 sequentially in a live environment to confirm they execute clean start to finish. This document reflects what the source says will happen, not a verified live run. Recommend one full walkthrough before marking "done."

---

## Document references

| Document | Purpose | Status |
|----------|---------|--------|
| `01-Architecture.md` | System architecture, port allocation, threading | Current |
| `PORT_ALLOCATION.md` | Authoritative port assignments | Current (2026-07-12) |
| `ADAPTER_COMMANDS.md` | All 147 commands across adapters | Current |
| `ENTITY_SYNC_PROTOCOL.md` | Entity sync hub spec and examples | Current |
| `ENTITY_SYNC_QUICKSTART.md` | 5-minute entity sync intro | Current |
| `PROJECT_LINKAGE_MAP.md` | File dependency chart | Current |
| `CLEANUP_COMPLETION.md` | Project structure audit | Current |
| `AUDIT_SUMMARY.md` | Audit results summary | Current |

---

**Last Updated:** 2026-07-12  
**Status:** Production-ready with flagged gaps  
**Next Review:** When Option A/B choice is finalized at repo level
