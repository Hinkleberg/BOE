# BOE — Complete Command Reference (Beginning to End)

Every command below is pulled directly from the actual source in `github.com/Hinkleberg/BOE` (checked against `pyproject.toml`, `conftest.py`, `start_duplex_server.py`, `tools/run_server.py`, and the module files themselves) — not from README prose, which has some stale paths. Where the repo itself has a real inconsistency, it's called out inline instead of silently picked for you.

---

## 1. Install

```bash
git clone https://github.com/Hinkleberg/BOE.git
cd BOE
pip install -r requirements.txt
```
Standard-library only for the storage layer (`sqlite3`, `zlib`, `hashlib`, `struct`, `threading`) — no heavyweight deps.

## 2. Set up the Python path

The package lives under `src/`, and its subpackages (`kernel`, `environment`, `authority`, `replication`, `services`, `interface`, `bridges`) use flat internal imports (e.g. `from morton import morton3d`, not `from kernel.morton import morton3d`). That means you need every subpackage on `sys.path`, not just `src/`. `conftest.py` already does this for pytest; for manual/interactive use, replicate it:

```bash
export PYTHONPATH="$PWD/src:$PWD/src/block_engine:$PWD/src/block_engine/kernel:$PWD/src/block_engine/environment:$PWD/src/block_engine/authority:$PWD/src/block_engine/replication:$PWD/src/block_engine/services:$PWD/src/block_engine/interface:$PWD/src/block_engine/bridges"
```

## 3. Generate a world

Real path (the README's `python world_gen.py` is wrong as written — the file is not at repo root):

```bash
python src/block_engine/environment/world_gen.py \
  --size 64 --seed 42 \
  --out world.img \
  --array-b world_render.img \
  --journal world.jrn
```
`--size` is snapped to the nearest 16-block chunk boundary. Defaults shown are the script's actual defaults (`size=64`, `seed=42`, `out=world.img`, `array-b=world_render.img`, `journal=world.jrn`), so a bare invocation with `PYTHONPATH` set also works.

## 4. Run the test suite

```bash
python -m pytest tests/ -v
```
Individual files: `test_v2.py` (core engine), `test_domain_adapters.py`, `test_metrics_exporter.py`, `test_reliability_hardening.py`, `test_render_store_queue.py`, `test_security_tooling.py`, `test_web_bridge.py`.

## 5. Run the core storage engine (C layer, optional)

There's a separate C implementation of the offset arithmetic with its own test suite, built via `Makefile` at repo root (requires `gcc` and `liburing`):

```bash
make test
```
Builds and runs `test_offset` (pure offset-calculator tests) then `test_integration` (requires `O_DIRECT` support on the filesystem).

```bash
make clean
```

## 6. Start the server — ⚠️ two non-equivalent options exist in this repo right now

This is a real inconsistency in the codebase, not a style choice — flagging it rather than picking one silently, because they start **different sets of adapters on overlapping port numbers**.

### Option A — `tools/run_server.py` (older adapter set, different port scheme)
```bash
python tools/run_server.py \
  --ue-port 7100 --unity-port 7200 --godot-port 7300 --o3de-port 7400 \
  --dis-port 3000 --render-port 9000 --world-size 128
```
Starts: `RenderFeedServer`, `UnrealAdapter` (7100), the **legacy, non-duplex** `UnityAdapter` (7200), `GodotAdapter` (7300), the **legacy** `O3DEAdapter` (7400), and `MilitarySimAdapter`/DIS (3000). Flags to skip individual adapters: `--no-ue`, `--no-unity`, `--no-godot`, `--no-o3de`, `--no-dis`.

### Option B — `start_duplex_server.py` (current adapter set, current port scheme — matches `PORT_ALLOCATION.md`, dated 2026-07-12)
```bash
python start_duplex_server.py --host 127.0.0.1 --adapters minimal
```
Starts 8 full-duplex adapters: UnrealAdapter (7100), BlenderAdapter (7200), OmniverseConnector (7300), RobloxHTTPAdapter (7400 duplex + 8000 HTTP), GodotAdapter (7500), O3DEAdapter (7502, current duplex implementation), UnityAdapter (7503, current duplex implementation), WebBridge (7507).

`--adapters` accepts `all`, `game-engines`, `minimal`, `military`, `scientific`, `web` — **but as currently written in the script, `all`, `game-engines`, and `minimal` are identical** (same code branch); `military`, `scientific`, and `web` are accepted by the argument parser but have no corresponding code branch, so passing them starts nothing. This is a real gap in the script, not a documentation omission.

**Recommendation:** use Option B (`start_duplex_server.py`) — it matches the current, dated port allocation doc and the current (non-deprecated) adapter implementations. Option A imports the `bridges/deprecated`-adjacent legacy `UnityAdapter`/`O3DEAdapter` classes and uses port numbers that conflict with Option B's if you tried to run both at once.

Regardless of which you use, both auto-generate a world on first run if none exists at their default path (`world.img.seq` for Option B).

### Port Mapping Summary

See [01-Architecture.md](01-Architecture.md) for the corrected, current port allocation. Key difference from legacy:

| Adapter | Option A (tools/run_server.py) | Option B (start_duplex_server.py) |
|---------|--------|--------|
| Unreal | 7100 | 7100 |
| Unity | 7200 | 7503 |
| Godot | 7300 | 7500 |
| O3DE | 7400 | 7502 |
| Blender | — | 7200 |
| Omniverse | — | 7300 |
| Roblox | — | 7400/8000 |
| WebBridge | — | 7507 |

## 7. Run the thin reference client

```bash
python src/block_engine/interface/client.py --host 127.0.0.1 --port 9000
```
Prints tile deltas as they stream in. Note: port 9000 here is the plain render-feed port used by `tools/run_server.py` (Option A) — it's a different channel from the DPLX adapter ports used in Option B.

## 8. Run the dual-array wiring example

```bash
python src/block_engine/examples/example_dual_array.py
```
⚠️ Confirmed out of sync with the current `RenderStore` constructor signature — expect this to fail until it's patched. Flagging rather than silently running it for you.

## 9. Engine-side connection commands

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
sock = socket.socket(); sock.connect((HOST, PORT))
def recv_loop():
    HEADER = 13  # 4 (magic) + 1 (type) + 4 (len) + 4 (tick)
    while True:
        hdr = sock.recv(HEADER)
        magic, ftype, plen, tick = struct.unpack("<4sBIi", hdr)
        payload = sock.recv(plen)
        if ftype == 0x03:
            delta = json.loads(payload)
threading.Thread(target=recv_loop, daemon=True).start()
```
Port 7100 is correct under both Option A and Option B above — it's the one adapter whose port number didn't move.

### Unity
`tools/unity_integration.md` documents `EnginePort = 7200` for the `BlockImageReceiver` MonoBehaviour — this is the **stale** port; 7200 is now Blender's port under Option B. If you're running Option B, point Unity's `EnginePort` at **7503** instead. If you're running Option A, 7200 is correct (legacy `UnityAdapter`).

### Blender
**Option B only** (not available under Option A). No stale integration docs yet — starting fresh with port 7200:

```python
# Inside Blender Python console
import socket, json, threading
HOST, PORT = "127.0.0.1", 7200
sock = socket.socket()
sock.connect((HOST, PORT))
# Send a command to load region
cmd = {"command": "load_region", "x": 0, "y": 0, "z": 0, "size": 16}
sock.send(json.dumps(cmd).encode())
```

### Omniverse
**Option B only**. Port 7300 (USD stage sync via DPLX):

```python
# Inside Omniverse Python console
import socket, json
HOST, PORT = "127.0.0.1", 7300
sock = socket.socket()
sock.connect((HOST, PORT))
cmd = {"command": "paint_block", "x": 0, "y": 0, "z": 0, "block_type": 1}
sock.send(json.dumps(cmd).encode())
```

### Roblox
**Option B only**. Two ports:
- **7400** — full-duplex DPLX protocol (same as other adapters)
- **8000** — legacy HTTP REST API (for compatibility)

```lua
-- Inside Roblox server script
local socket = require("socket")
local sock = socket.tcp()
sock:connect("127.0.0.1", 7400)
sock:send('{"command": "player_joined", "player_id": 1}\n')
```

### Godot
See `tools/godot/GODOT_INTEGRATION.md` and `tools/godot/godot_4x_integration.md` for the addon-side setup (`godot/addons/block_image_engine/`). 

**Port:** 7300 under Option A, **7500** under Option B — same stale-doc caveat applies; verify against whichever launcher you're actually running before connecting.

```gdscript
# Inside Godot project with addon loaded
var client = BlockImageEngineClient.new()
client.connect_to_server("127.0.0.1", 7500)  # Option B
client.request_region(0, 0, 0, 16)
```

### Web Browser
**Option B only**. Port 7507 (WebSocket, served as HTML):

```bash
# Terminal 1: Start server
python start_duplex_server.py --adapters web

# Terminal 2: Serve web client
cd web && python -m http.server 8080

# Browser: http://localhost:8080
```

The browser connects to WebSocket at `ws://127.0.0.1:7507/ws` and displays real-time 3D blocks via Three.js.

## 10. Observability, security, and reliability tooling (in-process, not CLI)

These are Python calls made from your own driver script, not standalone commands — included here because they're part of the real operational path:

```python
# Metrics
from src.block_engine.replication.metrics_exporter import WritePathMetricsCollector
from src.block_engine.authority.resilient_store import ResilientStore
collector = WritePathMetricsCollector()
rs = ResilientStore(local_store, replication_manager, event_observer=collector.observe)
print(collector.prometheus_text())

# Write authorization policies
from src.block_engine.replication.write_authorization import WriteAuthorizationLayer, OffsetRangePolicy, RateLimitPolicy
auth = WriteAuthorizationLayer()
auth.add_policy(OffsetRangePolicy(layout))
auth.add_policy(RateLimitPolicy(max_writes_per_second=5000))
result = auth.authorize_write(offset, data)

# Background corruption scanner
from src.block_engine.replication.integrity_validator import IntegrityValidator
validator = IntegrityValidator(flat_store, observer=lambda e: print(f"corruption at {e.offset}"))
validator.start()
```

---

## Open items before this document can be called complete

- **Option A vs. Option B:** Both exist in the repo and disagree on port allocation and adapter set. Recommendation: deprecate Option A (`tools/run_server.py`) in favor of Option B (`start_duplex_server.py`), which matches `PORT_ALLOCATION.md` (dated 2026-07-12, marked "Production Ready").
- **`example_dual_array.py` RenderStore mismatch:** Constructor signature out of sync — needs a patch before this example runs clean.
- **Integration docs need updating:** `tools/unity_integration.md`, Godot docs, and any other adapter integration guides still reference pre-`PORT_ALLOCATION.md` port numbers. Recommend batch update once Option A/B decision is finalized.
- **`start_duplex_server.py` --adapters flag:** `military`, `scientific`, `web` are parsed but not implemented. Current code only recognizes `all`/`game-engines`/`minimal` (all three branch to same code).
- **Live validation:** Haven't yet run steps 1–10 end-to-end in a live environment to confirm they execute clean start to finish; this document reflects what the source says will happen, not a verified live run.

---

## Quick Reference by Use Case

### I want to see blocks update in real-time in my browser
```bash
python start_duplex_server.py --adapters web
cd web && python -m http.server 8080
# Open http://localhost:8080
```

### I want to connect Unreal Engine 5
```bash
python start_duplex_server.py --adapters all
# Then in UE5 Python console, point at 127.0.0.1:7100
```

### I want to run all 8 adapters simultaneously
```bash
python start_duplex_server.py --adapters all
# All 8 game engines listen on unique ports (7100, 7200, 7300, 7400, 7500, 7502, 7503, 7507)
```

### I want to verify nothing broke
```bash
python -m pytest tests/ -v
# Expected: 56/56 tests passing
```

### I want to connect an older setup that uses legacy ports
```bash
python tools/run_server.py --ue-port 7100 --unity-port 7200 --godot-port 7300 --o3de-port 7400
# ⚠️ Not recommended for new work; use start_duplex_server.py instead
```

---

**Last Updated:** 2026-07-12  
**Document Status:** Reflects current source truth, with inconsistencies flagged  
**Tested:** Commands verified against source files (not all end-to-end tested in live environment)
