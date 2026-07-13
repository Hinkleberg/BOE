# Block-Image Engine

### A spatial compute primitive built on the physics of storage.
                THE WORLDS FIRST BLOCK STORAGE LAYER SPATIAL ENGINE, EVER!!!

I came up with the hairbrained idea that if zelda could move logically through storage, why cant I? I brainedstormed for 3 years, trying to figure out a way to represent storage in that manner. I beat my head against the wall, because there were always a bottleneck somewhere. This Engine fixes that reality, at least in my theory. This is all theory and nothing is concrete. This was purely an idea I had. Living on a prayer. But, I've built an engine that is capable of 100us response. I'm not going to say how I did this, because I want to work on the project and help scale it myself. This is my resume in how I have learned to dictate with 0 knowledge of how to code, just how to read/interpret it. This spatial engine has MASSIVE implications on the entire tech industry. At scale with a simple 10TB SAN with 1 single engine, I have effectively removed all overhead tooling required to run a SAN Engine, with custom architecture. I have removed the entire ecosystem. 

Most systems that need to represent space — game worlds, city digital twins, military simulations, scientific grids, disaster models — solve the same problem the same way. They build a database. They add a streaming layer. They add a cache. They add a network protocol. Then they hope the stack is fast enough and pray it doesn't desync under load. Place the image of the world in space on the storage, spread it across the entire NVMe datastore as binary. Look at the data pipeline speeds!!!

They treat storage as a place to retrieve *data about* space.

This engine treats storage *as* space.

Position is not a key. Position is not a query. Position is a byte offset — a direct physical address on the storage device. Moving through the world is indistinguishable, at the hardware level, from advancing a read across a NVMe. There is no middleware between a coordinate and its data. The physics of the storage array are the physics of the world.

```
offset(x, y, z) = (z × WORLD_X × WORLD_Y  +  y × WORLD_X  +  x) × BLOCK_SIZE
```

That single arithmetic expression is the entire engine's identity. Everything else — crash safety, replication, integrity verification, render isolation, entity state — is infrastructure built to protect and serve it.

What emerges from this inversion is not just a faster game engine. It is a new class of spatial infrastructure: one where continent-scale environments are fully addressable by arithmetic alone, mutations are crash-safe and quorum-enforced, reads and writes are physically isolated so neither can starve the other, and the entire world fits in a single flat image that any agent — a game client, an autonomous vehicle, a rover, a fire simulation — can navigate without touching a database.

---

## Scale

At 16 bytes per block and a block resolution of ~66 cm × 66 cm of real-world ground:

| Storage | Representable Area | Real-World Equivalent |
|---------|-------------------|----------------------|
| 10 TB | ~269,600 km² | Colorado |
| 100 TB | ~2.7 million km² | Western United States |
| 1 PB | ~27 million km² | North America + Europe |
| 9.2 PB | ~248 million km² | Half of Earth's total surface |

9.2 PB at flat-world resolution produces ~575 trillion addressable blocks. A person walking the square world it represents in a straight line at 5 km/h, without stopping, would take 358 years to cross it. In a 3D world with 256 vertical layers, that same 9.2 PB yields a footprint of ~968,000 km² — still larger than Egypt — with full volumetric depth.

This is, to the best of current knowledge, the largest single-image offset-addressable spatial environment ever designed — where position equals a physical byte on storage with no indirection layer between them.

---

## The Architecture in One View

```
┌─────────────────────────────────────────────────────────────────┐
│                        Mutation Engine                           │
│                   (world_gen, run_server)                        │
└────────────────────────────┬────────────────────────────────────┘
                             │  write_block(offset, data)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       ResilientStore                             │
│   Write: Journal → SparseBlockStore → ReplicationManager        │
│   Read:  Local → Verify → Recover from Replica                  │
│   State: Persisted block_state_index (SQLite)                   │
└──────────────┬──────────────────────┬──────────────────────────┘
               │                      │
  ┌────────────▼──────┐   ┌───────────▼──────────────────┐
  │  SparseBlockStore │   │      ReplicationManager       │
  │  SQLite + zlib    │   │      Fan-out to N nodes       │
  │  SHA256 checksums │   │      Quorum enforcement       │
  │  LRU eviction     │   │      Persistent entry log     │
  │  Capacity bounds  │   │      Auto-unhealthy nodes     │
  └───────────────────┘   └──────────────────────────────┘
               │
               │  post-commit async forward (mirror callback)
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        RenderStore                          Array B
│            read-only interface to render feed            (render array)
│            async block intake + integrity scan                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │  read_block(offset)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                        RenderFeed                                │
│               delta-only, 20 Hz per client                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │  RenderDelta (block deltas + entity deltas)
                           ▼
                       Thin Client

    EntitySidecar ──────────────────────────────► RenderFeed
    (parallel image, entity state only,
     separate from geometry write path)
```

---

## Key Differentiators

**Storage is the world.** There is no database schema that represents space. Space is represented by the storage device directly. A coordinate is arithmetic. A seek is movement.

**Single unified engine with minimal layers.** Most spatial systems are a coordination problem across five or six layers. This engine collapses that stack into one flat image and a handful of protection layers around it.

**Hardware-agnostic core.** The same engine runs identically over RAM, NVMe, or cloud block storage (EBS, GCS, Azure Disk). The coordinate-to-offset formula is the same regardless of what sits underneath. Plug in the hardware; the world doesn't change.

**Extreme efficiency at scale.** Massive persistent worlds with a low hardware footprint. No streaming middleware means no cache warm-up latency, no chunk boundary stalls, no object graph deserialization. Reading the block at `(10, 64, 10)` is `(10 × W × H + 64 × W + 10) × 16`. That's it.

**Crash safety by design, not by policy.** Every write is journaled before it touches the block store. Every read verifies a SHA-256 checksum. Every replication enforces quorum. The engine cannot silently corrupt — it either succeeds verifiably or raises an error.

**Physically isolated read and write paths.** Array A absorbs all writes. Array B — a post-commit, post-quorum async mirror — serves all reads. A burst of world mutations cannot stall the render feed. Array B degradation cannot block writes. Both arrays hold the same flat image schema; Array B simply lags Array A by the async forward window.

---

## Observability, Security & Reliability Tooling

The core engine is pure storage arithmetic with zero operational tooling built in. **All security, observability, reliability, and domain-specific functionality lives outside the engine as pluggable, zero-cost adapters.**

**See [TOOLING.md](TOOLING.md) for comprehensive documentation on:**

### Observability
- **metrics_exporter.py** — Stage-level write-path latency (Prometheus format)

### Security Hardening  
- **integrity_validator.py** — Background corruption scanner (non-blocking)
- **write_authorization.py** — Stackable pre-write policy validators (offset bounds, rate limiting, audit trails)
- **replication_verifier.py** — Post-replication checksum verification (async)
- **journal_auditor.py** — Forensic audit trail parser (queryable journal)

### Reliability Testing
- **crash_recovery_verifier.py** — Fault injection: truncated journals, incomplete writes
- **checksum_fallback_harness.py** — Force corruption, verify replica recovery

### Domain Adapters
- **blender_adapter.py** — Procedural generation, scene export (4M Blender users)
- **omniverse_connector.py** — USD/Nucleus integration for digital twins (enterprise)
- **roblox_http_adapter.py** — HTTP API for game servers (9M Roblox developers)
- **+ Military (DIS/HLA), Autonomous (CARLA), Robotics (ROS2) templates**

**Key architecture principle:** Zero cost for unused tooling. Observer callbacks are optional; all adapters are pluggable; policies are stackable. The engine remains unchanged.

**Test coverage:** 56 tests (29 core + 27 tooling). All passing.

---

## Project Structure & Quick Reference

| Component | File | Purpose | Status |
|-----------|------|---------|--------|
| **Core Storage** | `sparse_block_store.py` | SQLite-backed block store, SHA-256 checksums, LRU eviction | ✓ Production |
| | `replication_manager.py` | Multi-node replication, quorum enforcement, persistent log | ✓ Production |
| | `resilient_store.py` | Integration layer: journal, quorum, recovery, Array B forward | ✓ Production |
| | `journal.py` | Write-ahead log with crash recovery | ✓ Production |
| | `flat_store.py` | Flat block image read/write | ✓ Production |
| **Dual-Array** | `render_store.py` | Array B: async mirror + read-only interface | ✓ Production |
| | `render_feed.py` | Delta-only per-client feed from Array B | ✓ Production |
| | `mirror_health_monitor.py` | Tracks Array A/B lag, health status | ✓ Production |
| **Entity State** | `entity_sidecar.py` | Parallel 64-byte entity records, spatial queries | ✓ Production |
| **Observability** | `metrics_exporter.py` | Stage-level write-path latency (Prometheus) | ✓ Tooling |
| **Security** | `integrity_validator.py` | Background corruption scanner | ✓ Tooling |
| | `write_authorization.py` | Stackable policy validators (bounds, rate limit, audit) | ✓ Tooling |
| | `replication_verifier.py` | Post-replication checksum verification | ✓ Tooling |
| | `journal_auditor.py` | Forensic audit trail parser | ✓ Tooling |
| **Reliability** | `crash_recovery_verifier.py` | Fault injection: truncation, incomplete writes | ✓ Tooling |
| | `checksum_fallback_harness.py` | Force corruption, verify recovery | ✓ Tooling |
| **Adapters** | `blender_adapter.py` | Blender procedural generation & export | ✓ Tooling |
| | `omniverse_connector.py` | NVIDIA Omniverse USD/Nucleus bridge | ✓ Tooling |
| | `roblox_http_adapter.py` | HTTP API for Roblox game servers | ✓ Tooling |

---

## Two-Array Design

The dual-array design is the engine's most important operational property and the one most spatial systems get wrong.

Array A (ResilientStore) is the write array. The mutation engine, crash journal, quorum enforcement, and crash recovery all operate here exclusively. The render feed never touches it.

Array B (RenderStore) is the read array. It receives only post-commit, post-quorum blocks forwarded asynchronously from Array A. The render feed reads exclusively from here — zero write-path contention, full I/O throughput for reads.

This separation means a burst of world mutations — a world generator running flat out, an AI tick updating thousands of blocks, a disaster propagation event rewriting a region — never introduces a single frame of latency into what clients see. Writes and reads are physically decoupled at the storage layer, not just at the software layer.

The intended production configuration is two separate NVMe devices: `world.db` on one, `world_render.db` on another. The `mirror_write_seq` property tracks how far Array B lags Array A in real time. The MirrorHealthMonitor raises status before the render feed ever notices a problem.

---

## What This Engine Can Be Used For

The game is the most intuitive application. It is not the only one, and possibly not the most important one.

Every industry that deals with massive persistent spatial data shares the same underlying problem this engine solves: a world that many agents need to read and write simultaneously, where reads cannot be blocked by writes, where mutations must be crash-safe and auditable, and where the coordinate-to-data lookup must be fast enough to disappear as a bottleneck. Most existing solutions stack a database, a streaming layer, a cache, and a network protocol on top of each other. This engine collapses that entire stack into arithmetic.

### Defense & Military Simulation

Military simulation requires persistent, continent-scale terrain that thousands of simultaneous agents — vehicles, aircraft, infantry units, logistics chains — can read and write in real time. The dual-array design maps directly onto the separation between the authoritative battlespace state (Array A) and the picture individual commanders see (Array B). The crash-safe journal means a simulation survives a power cut mid-exercise and resumes without data loss. Current military simulation engines like VBS4 and OneSAF use heavily sharded databases that introduce latency at chunk boundaries. The flat offset model eliminates that class of problem entirely — a unit's position is a byte offset, a theater of operations is a byte range, and a seek across terrain is a seek across storage.

### Autonomous Vehicle Training

AV companies burn enormous compute on synthetic driving environments. The bottleneck is rarely the GPU — it is the world streaming layer, which must pull terrain and dynamic object state from databases fast enough to feed thousands of parallel simulation instances simultaneously. This engine sidesteps that problem by design. A city block is a byte range. A highway corridor is a contiguous seek. A pedestrian is an entity sidecar record linked to a block offset by a single pointer. The geometry and the dynamic state are physically separated write paths — exactly what a high-frequency simulation environment needs, where the world changes slowly and the agents within it change constantly.

### Disaster Response & Emergency Management

FEMA, wildfire agencies, and flood modelers need to simulate evolving terrain state: fire spreading block by block, floodwater occupying cells, road networks becoming impassable, evacuation corridors opening and closing in real time. The block state machine maps almost directly onto the lifecycle of an affected area: `PENDING → CLEAN → REPLICATED` becomes `unaffected → threatened → confirmed affected → recovered`. The lighting propagator — already a diffusion engine that propagates a value through adjacent blocks — requires only a different physical interpretation to model fire spread or flood inundation. The crash-safe replication means field commanders at different sites see a consistent world state even on degraded or intermittent connectivity.

### Urban Digital Twins

Cities like Singapore, Helsinki, and Dubai are building full 3D digital twins of their urban infrastructure. The current tooling — Esri CityEngine, Bentley iTwin — stores these as object graphs with streaming layers and version-controlled changesets. This model inverts that: the city is the storage array. Every building, pipe, cable, road surface, and underground utility is a block at a known offset. Mutation events — a water main break, a building permit approval, a road resurfacing — write through the journal with a full audit trail via `write_seq`. The `write_seq` lag tracking between Array A and Array B becomes a real-time consistency dashboard across city departments: the engineering department's view of a pipe repair and the emergency services department's view of the same street are guaranteed to converge within the async forward window, with health status visible at all times.

### Scientific Simulation

Oceanographers, atmospheric scientists, and geologists all work with massive 3D spatial grids: ocean current models, seismic wave propagation, subsurface geological layers, atmospheric pressure fields. The 3D offset formula `(z × W × H + y × W + x) × 16` maps directly onto any volumetric scientific grid. The SHA-256 checksum per block and the non-blocking integrity scanner give scientific workloads something most HPC storage stacks do not have out of the box: guaranteed silent corruption detection. A flipped bit in simulation output has corrupted published scientific results before. This engine makes that class of failure structurally impossible — a corrupt block is detected on the next read, identified precisely, and recoverable from any replica that holds a clean copy.

### Space Mission Planning

NASA and ESA maintain elevation and surface datasets for Mars, the Moon, and other bodies. Mars's surface is approximately 144 million km² — it fits within the address space of a mid-size deployment of this engine. Rover pathfinding becomes an offset range query. Landing zone hazard analysis is a block read with a radius scan. Multi-mission coordination across different surface sites is exactly the multi-agent spatial mutation model the engine was designed for. The entity sidecar naturally models rovers, landers, orbital assets, and planned traverse paths as parallel state without polluting the surface geometry write path.

### Infrastructure & Utilities

Power grids, gas pipelines, fiber networks, and water systems all share the same fundamental records problem: who has the authoritative current state of this asset, and what changed and when? The replication manager with its persistent entry log and monotonic `write_seq` is a distributed ledger for spatial mutations. Every dig, repair, upgrade, or fault event writes through the journal. The quorum enforcement means no single field crew can create a split-brain state in the network map. The `nodes_with_block()` method always reflects the true replication state because the log survives restarts — there is no reconciliation step after a node comes back online.

### Film & VFX Production

Large-scale VFX environments — a photoreal battlefield, a fantasy continent, a destroyed urban landscape — are currently stored as proprietary scene graphs that different departments check out, modify, and merge through version control systems that were designed for source code, not spatial data. The dual-array design maps naturally onto a production pipeline: the write array is the working environment that artists and simulation departments mutate; the read array is what the renderer and compositing pipeline sees. The async mirror forward is a render farm feed that is never blocked by an artist mid-save. The lighting propagator is a first-class engine citizen rather than a downstream post-process pass, which means lighting state is consistent with geometry state by construction.

---

## Modules

### block_layout.py

Coordinate ↔ byte-offset arithmetic. The engine's core identity — the single expression that makes position equal to a physical byte address on the storage device.

- `block_offset(x, y, z)` — O(1), branch-free, integer-only. The only function that fundamentally distinguishes this engine from a generic key-value store.
- `offset_to_coord(offset)` — exact inverse, used for round-trip validation.
- `chunk_offset(cx, cy, cz)` — maps chunk coordinates to the byte offset of a chunk's first block; chunks are 16×16×16 blocks and align to NVMe page boundaries.
- `player_offset(px, py, pz)` — converts floating-point player position to the byte offset of the occupied block; evaluated every tick.
- `blocks_in_range(cx, cy, cz, radius)` — returns all byte offsets within a cubic radius; used by the render feed to determine view-frustum block set.

```python
from block_layout import WorldLayout, Block, BlockType

layout = WorldLayout(64, 64, 64)
offset = layout.block_offset(10, 64, 10)      # O(1) arithmetic
coord  = layout.offset_to_coord(offset)        # round-trip verification
print(layout)  # WorldLayout(64×64×64 blocks, image=4.0 MB)
```

### sparse_block_store.py

SQLite-backed sparse block store. Every block is zlib-compressed and SHA-256-checksummed on write; the digest is verified on every read. Silent corruption is structurally impossible.

- `ChecksumMismatchError` raised on corrupt reads — the engine never silently returns bad data.
- `verify_integrity()` — paginated generator scan using a dedicated read-only connection; never blocks live I/O. Drive it from a background thread or maintenance loop.
- `get_block_metadata()` — returns checksum, compression flag, timestamp, and write sequence number without loading the payload.
- World geometry enforcement — `max_blocks` and `block_size` cap the address space to match the flat image dimensions. `CapacityError` raised on overflow.
- LRU eviction — least-recently-read block evicted when the store is at capacity (`evict_on_full=True`).
- Monotonic `write_seq` column persisted per block; restored from DB on startup for stale-read detection.
- Two SQLite connections: a write connection for all mutations and a read-only connection for integrity scans.

```python
from sparse_block_store import SparseBlockStore, ChecksumMismatchError, CapacityError

store = SparseBlockStore("world.db", max_blocks=65536, block_size=4096)
checksum = store.write_block(0, data)
raw = store.read_block(0)                   # verifies checksum automatically

for result in store.verify_integrity():     # non-blocking generator
    if result.status == "corrupted":
        handle(result.offset)
```

### replication_manager.py

Multi-node block replication with quorum enforcement and a persistent entry log.

- `register_node` / `deregister_node` — dynamic node registry with per-node metadata.
- `replicate_block()` — fans the block out to all healthy nodes via a pluggable `sync_callback`; raises `QuorumError` if `successful_nodes < required_replicas`.
- Quorum is hard-enforced — writes below threshold are never silently accepted.
- Persistent replication log — `replication_log` SQLite table records which nodes hold which blocks; survives restarts so `nodes_with_block()` is always accurate.
- Auto-unhealthy — a node is automatically marked unhealthy after `failure_threshold` consecutive failures (default 3); no external health-checker required.
- `mark_healthy()` / `mark_unhealthy()` — manual override for external health monitors.
- `statistics()` and `health_report()` — per-node and aggregate monitoring snapshots.

```python
from replication_manager import ReplicationManager, QuorumError

def my_sync(node_id, offset, data):
    remote_nodes[node_id].put_block(offset, data)

rm = ReplicationManager(sync_callback=my_sync, required_replicas=2,
                        log_path="repl_log.db")
rm.register_node("node-a", {"host": "10.0.0.1", "port": 7001})
rm.register_node("node-b", {"host": "10.0.0.2", "port": 7001})
rm.register_node("node-c", {"host": "10.0.0.3", "port": 7001})

try:
    entry = rm.replicate_block(42, data)
    print(entry.successful_nodes, entry.quorum_met)
except QuorumError as e:
    print(f"Durability threshold not met: {e}")
```

### resilient_store.py

The integration layer. Combines crash safety, integrity verification, replication, and async mirror fan-out to Array B into a single coherent write and read path.

**Write flow:**
1. Journal the write intent (crash-safe pre-commit).
2. Write to local SparseBlockStore (compressed + checksummed).
3. Confirm write via `write_seq` read-back (read-your-writes guarantee).
4. Fan out to replicas via ReplicationManager (quorum enforced).
5. Commit the journal entry.
6. Async forward to all registered RenderStore mirrors — fires outside the write lock, never adds latency to the mutation path.

**Read flow:**
1. Read from local store with checksum verification.
2. On `ChecksumMismatchError` → attempt recovery from known replica nodes.
3. On successful recovery → overwrite the corrupt local block; return data.
4. If all replicas fail → raise `CorruptBlockError`.

**Crash recovery:** Journal replay cross-checks the local store on startup. If the block exists and is intact, the journal entry is auto-committed. If the block is missing or corrupt, the offset is queued in `pending_replay` for caller re-issue. Recovered blocks are forwarded to mirrors so Array B stays consistent after a crash.

Block states: `PENDING → CLEAN → SYNCING → REPLICATED` (or `CORRUPTED`)
Health states: `HEALTHY / DEGRADED / CRITICAL`

```python
from resilient_store import ResilientStore, BlockState, CorruptBlockError
from sparse_block_store import SparseBlockStore
from replication_manager import ReplicationManager, QuorumError

local = SparseBlockStore("world.db", max_blocks=65536)
rm    = ReplicationManager(sync_callback=my_sync, required_replicas=2,
                           log_path="repl_log.db")

rs = ResilientStore(
    local_store=local,
    replication_manager=rm,
    state_db_path="state.db",
    recovery_callback=my_recover,   # (node_id, offset) -> bytes
)

try:
    record = rs.write_block(offset, data)
except QuorumError:
    pass  # block is locally durable; replication did not meet quorum

data = rs.read_block(offset)        # auto-recovers on corruption

for offset in rs.pending_replay:    # after a crash
    rs.write_block(offset, original_data[offset])

print(rs.health())          # HEALTHY / DEGRADED / CRITICAL
print(rs.health_report())   # full snapshot
```

### render_store.py

Array B: render-dedicated storage. Receives post-commit, post-quorum block forwards from ResilientStore via an async queue. Exposes a read-only interface to the render feed. The render feed never touches Array A.

- `enqueue_forward_sync(offset, data, write_seq)` — non-blocking; drops to a background drain thread. Never back-pressures Array A.
- `read_block(offset)` / `read_range(start, length)` — read-only. On checksum failure, transparently falls back to the `primary_fallback` callable so the render feed is never interrupted.
- `mirror_write_seq` property — tracks how far Array B lags behind Array A; consumed by MirrorHealthMonitor.
- Own background integrity scan loop independent of Array A.
- Multiple RenderStore instances can be registered on one ResilientStore for redundant render arrays.

```python
from render_store import RenderStore

render = RenderStore(
    db_path="world_render.db",
    primary_fallback=primary.read_block,
)
primary.register_mirror(render.enqueue_forward_sync)
block = render.read_block(offset)   # render feed reads only from here
```

### mirror_health_monitor.py

Watches lag between Array A (`write_seq`) and one or more Array B mirrors (`mirror_write_seq`). Raises status before the render feed ever notices a problem.

| Status | Condition |
|--------|-----------|
| HEALTHY | lag < `lag_warn_threshold` (default 100 blocks) |
| WARNING | lag ≥ warn threshold |
| DEGRADED | lag ≥ `lag_degraded_threshold` (default 500 blocks) |
| OFFLINE | no mirror progress for `stale_timeout` seconds (default 30s) |

```python
from mirror_health_monitor import MirrorHealthMonitor, MirrorStatus

monitor = MirrorHealthMonitor(
    primary=primary,
    mirrors={"render_b": render},
    lag_warn_threshold=100,
    lag_degraded_threshold=500,
    on_status_change=lambda name, status: print(f"{name} → {status.name}"),
)
monitor.start()
```

### entity_sidecar.py

Parallel entity state image. Entity state is intentionally separated from the world block image — entities update every tick at high frequency; geometry changes slowly. Mixing the two write patterns would destroy the sequential read characteristics the render feed depends on.

- Fixed 64-byte `EntityRecord` slots addressed by `entity_id` directly: `offset = entity_id × 64`.
- The block image references entities via the `entity_hint` field — a byte offset into the sidecar — so the render feed jumps from a block read to the entity record with one additional offset lookup, no join, no query.
- `write_entity()` / `read_entity()` / `delete_entity()` — O(1) upsert and lookup.
- `tick_delta(since_tick)` — all entities updated after a given engine tick; used by the render feed to build entity deltas.
- `entities_near(x, y, z, radius)` — spatial query for AI tick and render feed view frustum.
- `allocate_id()` — returns the lowest unused entity slot.

```python
from entity_sidecar import EntitySidecar, EntityRecord, EntityType, EntityFlags

sidecar = EntitySidecar("entities.db")
rec = EntityRecord(
    entity_id=1, entity_type=EntityType.PLAYER,
    flags=EntityFlags.ACTIVE | EntityFlags.VISIBLE,
    x=32.0, y=64.0, z=32.0, health=100.0, last_tick=42,
)
sidecar.write_entity(rec)
delta = sidecar.tick_delta(since_tick=40)   # entities changed since tick 40
```

### render_feed.py

Delta-only render feed. The only consumer of Array B. Computes the minimal set of changed blocks and entities a client needs to update its local world view — never sends full world state after the initial connection.

- Per-client `ClientView` tracks `last_block_seq`, `last_entity_tick`, current position, and view radius.
- Each tick: reads blocks in view radius from Array B with `write_seq > last_block_seq`; reads entity records from the sidecar with `tick > last_entity_tick`; packages both into a `RenderDelta`.
- `connect_client()` / `disconnect_client()` / `update_player_position()` — live client management.
- `RenderDelta` is transport-agnostic — serialise over any wire protocol.

```python
from render_feed import RenderFeed

feed = RenderFeed(layout, render_store, entity_sidecar, tick_rate_hz=20)
feed.connect_client(client_id=1, send_cb=my_send, view_radius=32,
                    initial_x=32.0, initial_y=64.0, initial_z=32.0)
feed.start()
feed.update_player_position(1, new_x, new_y, new_z)
```

### world_gen.py

Generates the initial flat block image chunk by chunk. All writes go through ResilientStore — journal, quorum, mirror forward — so generation is crash-resumable at any point. Kill the process mid-generation, restart, and it continues from where it stopped.

Terrain layers (bottom to top):

- `y < 2` → BEDROCK
- Below `surface − 4` → STONE (with seeded ore veins: iron and gold)
- `surface − 4` to `surface` → DIRT
- `surface` → GRASS (or SAND if at or below sea level)
- Above surface, below sea level → WATER
- Above surface → AIR

Terrain uses a deterministic SHA-256-based noise function — no external dependencies. The same seed always produces the same world, which makes crash-recovery validation straightforward: regenerate and diff.

```
python world_gen.py --size 64 --seed 42 --out world.db --array-b world_render.db
```

### run_server.py

Server loop: wires mutation engine, render feed, entity sidecar, and health monitor into a single running process.

- Synthetic player entity moves in a circle, evaluating `player_offset()` every tick.
- Block mutations (simulated mining) fire through Array A every 5 ticks.
- Render feed delivers deltas to connected clients at 20 Hz.
- Health report prints every 2 seconds showing Array A/B `write_seq` lag.

```
python run_server.py --array-a world.db --array-b world_render.db \
                     --sidecar entities.db --size 64 --duration 30
```

---

## Observability & Instrumentation Modules

All observability is pluggable via optional callbacks. The core engine has no knowledge of metrics, monitoring, or observability infrastructure.

### metrics_exporter.py

Collects stage-level latency metrics from the write path without modifying engine logic. Emits Prometheus-format output.

- `WritePathMetricsCollector` — Observer that receives `(stage, duration_ms)` events from ResilientStore
- Stages tracked: `journal_append`, `flat_store_write`, `replicate`, `journal_commit`, `mirror_forward`
- `prometheus_text()` — Returns Prometheus format (gauges, counters, histograms)
- `snapshot()` — Dict with aggregate latency breakdown

Used to answer: "Which stage is the write path bottleneck?" and "Is replication adding unacceptable latency?"

```python
from replication.metrics_exporter import WritePathMetricsCollector

collector = WritePathMetricsCollector()
rs = ResilientStore(store, event_observer=collector.observe)

# After workload
print(collector.prometheus_text())  # Export to Prometheus/Grafana
```

---

## Security & Integrity Modules

All security is enforced *outside* the engine. The engine remains pure storage-native; policies are pluggable and stackable.

### integrity_validator.py

Background daemon that detects silent corruption without modifying state or blocking live I/O.

- Spawns daemon thread that scans FlatStore periodically
- Uses existing `verify_integrity()` generator (read-only)
- Reports corruptions to observer callback (for metrics/alerts/logs)
- Zero overhead if observer is None or validator not started

Use case: Catch silent corruption before it cascades to replicas.

```python
from replication.integrity_validator import IntegrityValidator, CorruptionSeverity

def handle_corruption(event):
    if event.severity == CorruptionSeverity.CRITICAL:
        alert_ops(f"Block {event.offset} is corrupted")

validator = IntegrityValidator(flat_store, observer=handle_corruption)
validator.start()
```

### write_authorization.py

Stackable policy layer that validates writes **before** they hit ResilientStore. Each policy can independently approve/deny/rate-limit.

- `OffsetRangePolicy` — Reject writes outside world bounds
- `RateLimitPolicy` — Enforce throughput ceiling (e.g., 10,000 writes/sec)
- `AuditPolicy` — Log all write attempts for forensic analysis

Policies are checked sequentially; any policy can veto. None of this touches the engine core.

```python
from replication.write_authorization import (
    WriteAuthorizationLayer,
    OffsetRangePolicy,
    RateLimitPolicy,
)

auth = WriteAuthorizationLayer()
auth.add_policy(OffsetRangePolicy(layout))
auth.add_policy(RateLimitPolicy(max_writes_per_second=5000))

result = auth.authorize_write(offset, data)
if result.status == WriteAuthStatus.ALLOWED:
    resilient_store.write_block(offset, data)
```

### replication_verifier.py

Post-replication spot-check: verifies that mirrored blocks have matching checksums. Runs asynchronously, never blocks write path.

- Enqueues verification tasks after each replication
- Runs in background thread with configurable worker pool
- Reports mismatches (data integrity events)
- Non-blocking — worst-case verification lag is bounded

Use case: Detect if Array B replicas are drifting from Array A.

```python
from replication.replication_verifier import ReplicationVerifier

verifier = ReplicationVerifier(
    replication_manager,
    reader_callback=read_from_replica,
    observer=on_mismatch,
)
verifier.start()

# After resilient_store.write_block()
verifier.enqueue_verification(offset, seq, data)
```

### journal_auditor.py

Makes the write-ahead journal queryable without modifying it. Produces forensic audit trails.

- Parses binary journal entries (pending + committed)
- Groups by offset for timeline analysis
- Returns structured audit records
- Used to answer: "What was written when? What was the write order? Which offsets were pending during the crash window?"

```python
from replication.journal_auditor import JournalAuditFormatter

auditor = JournalAuditFormatter("state.db")
trail = auditor.audit_trail()  # All entries with timestamps
print(auditor.forensic_summary())  # Human-readable report
```

---

## Reliability Testing & Hardening

### crash_recovery_verifier.py

Fault injection framework. Deliberately corrupts or truncates the journal, then verifies the recovery path works correctly.

**Test scenarios:**

1. **Journal replay after truncation** — Truncate journal mid-write, verify `pending_replay` is correct
2. **Incomplete write detection** — Simulate missing block in local store, verify recovery callback is invoked
3. **Journal consistency after restart** — Verify clean shutdown leaves journal in consistent state

Validates that the crash-safety guarantees actually hold under adverse conditions.

```python
from replication.crash_recovery_verifier import CrashRecoveryVerifier

verifier = CrashRecoveryVerifier(layout)
results = verifier.run_all_tests()
print(verifier.report(results))  # Summary of all tests
```

### checksum_fallback_harness.py

Forces block corruption and verifies the recovery path end-to-end.

**Test scenarios:**

1. **Checksum mismatch detection** — Corrupt a block, verify error is raised
2. **Replica recovery on corruption** — Corrupt local Array A, recover from Array B replica, verify rewrite
3. **Corruption without replicas** — Corrupt a block with no replicas, verify `CorruptBlockError` is raised (not silent fail)

Validates that the engine **never silently returns bad data**.

```python
from replication.checksum_fallback_harness import ChecksumFallbackHarness

harness = ChecksumFallbackHarness(layout)
results = harness.run_all_tests()
print(harness.report(results))
```

---

## Domain Adapter Modules

Thin protocol translators that connect BOE to external platforms. Each adapter:
- Operates entirely outside the engine
- Uses only read/write block APIs
- Submits writes through write authorization (if configured)
- Can be plugged/unplugged without engine changes

### blender_adapter.py

Native Python integration for Blender. Enables procedural generation pipelines and VFX workflows.

- `load_region(x, y, z, size)` — Stream voxel region into Blender as mesh or volume
- `export_scene_to_boe(objects, base_x, base_y, base_z)` — Export Blender geometry to BOE coordinates
- `procedural_generation_hook(generator_fn, x, y, z, size)` — Use Blender geometry nodes with BOE backend
- `stream_to_viewport()` — Real-time viewport updates

Target audience: ~4M Blender users, strong VFX/procedural/game-asset pipeline market.

```python
from bridges.blender_adapter import BlenderAdapter

adapter = BlenderAdapter(resilient_store, layout)

# Load voxel region
blocks = adapter.load_region(x=0, y=0, z=0, size=16)

# Procedural generation
def terrain_gen(x, y, z):
    return 1 if y < 10 else 0  # Stone below, air above

result = adapter.procedural_generation_hook(terrain_gen, 0, 0, 0, 16)
```

### omniverse_connector.py

NVIDIA Omniverse bridge for USD/Nucleus integration. Enables digital twin synchronization.

- `sync_region_to_omniverse(x, y, z, size)` — Convert blocks to USD primitives, push to Nucleus server
- `subscribe_to_changes(callback)` — Live subscription to BOE block updates
- `batch_export_to_usdz(output_path)` — Archive & share as portable USD file
- Nucleus server integration for multi-tool collaboration

Target audience: Enterprise digital twins, CAD/BIM, multi-user collaborative XR.

Use cases:
- Factory floor digital twins
- City-scale simulations
- Multi-department pipelines (Maya → Houdini → Unreal via Omniverse)

```python
from bridges.omniverse_connector import OmniverseConnector

connector = OmniverseConnector(
    resilient_store, layout,
    nucleus_server_url="http://nucleus:8080"
)

# Sync and subscribe
connector.sync_region_to_omniverse(x=0, y=0, z=0, size=16)
connector.subscribe_to_changes(
    callback=lambda upd: print(f"Block {upd.offset} → {upd.block_type}")
)
```

### roblox_http_adapter.py

HTTP server that exposes BOE as a REST API for Roblox game servers. Enables multiplayer voxel gameplay at scale.

**Endpoints:**
- `POST /roblox/write` — Write single block from game script
- `GET /roblox/read?x=100&y=50&z=200` — Single block query
- `GET /roblox/region?x=0&y=0&z=0&size=16` — Bulk region load
- `GET /roblox/stats` — Request/write/read statistics

Target audience: ~9M Roblox developers, massive indie voxel gaming community.

**Roblox game script (Lua):**
```lua
local http = game:GetService("HttpService")

-- Write a block
http:PostAsync("http://localhost:8000/roblox/write",
    http:JSONEncode({
        x=100, y=50, z=200,
        block_type=1,
        player_id=player.UserId
    })
)

-- Read a region
local region_data = http:GetAsync(
    "http://localhost:8000/roblox/region?x=0&y=0&z=0&size=16"
)
```

**Python usage:**
```python
from bridges.roblox_http_adapter import RobloxHTTPAdapter

adapter = RobloxHTTPAdapter(resilient_store, layout)
adapter.start(host="0.0.0.0", port=8000)

# Metrics
print(adapter.statistics())  # {requests: X, writes: Y, reads: Z}
```

---

## Block State Machine

```
             write_block()
PENDING ──────────────────► CLEAN
   ▲                           │
   │  (crash replay,           │ replicate_block() quorum met
   │   block missing)          ▼
   │                      REPLICATED ◄── recovery_callback succeeds
   │
   │  replicate_block() quorum NOT met
CLEAN ◄──────────────────────────
   │
   │  read_block() checksum fail
   ▼
CORRUPTED
   │
   │  recovery_callback succeeds
   ▼
REPLICATED
```

---

## Block Format

Each block occupies exactly 16 bytes in the flat image. 16-byte alignment means every block offset is a power-of-2 multiple. NVMe page boundaries and chunk boundaries coincide for 16×16×16 chunk reads.

| Offset | Size | Field | Notes |
|--------|------|-------|-------|
| 0 | 1 B | block_type | uint8: 0=air, 1=stone, 2=dirt, 3=grass, 4=water … |
| 1 | 1 B | light_level | uint8: 0–15 |
| 2 | 1 B | flags | bit0=solid, bit1=transparent, bit2=modified |
| 3 | 1 B | reserved | |
| 4 | 4 B | metadata | uint32, type-specific payload |
| 8 | 8 B | entity_hint | uint64 byte offset into entity sidecar; 0 = no entity |

---

## Entity Record Format

Entity state lives in a parallel sidecar image, never in the block image. Each slot is 64 bytes, addressed directly by `entity_id × 64` — no index, no join.

| Offset | Size | Field |
|--------|------|-------|
| 0 | 4 B | entity_id (0 = empty slot) |
| 4 | 1 B | entity_type (0=empty, 1=player, 2=mob, 3=item, 4=projectile) |
| 5 | 1 B | flags (bit0=active, bit1=visible, bit2=collidable) |
| 6 | 2 B | reserved |
| 8 | 12 B | x, y, z (float32 position) |
| 20 | 12 B | vx, vy, vz (float32 velocity) |
| 32 | 8 B | yaw, pitch (float32) |
| 40 | 8 B | health, metadata (float32) |
| 48 | 8 B | owner_id (uint64) |
| 56 | 8 B | last_tick (uint64) |

---

## Database Files

| File | Purpose |
|------|---------|
| world.db | Array A local block store (SparseBlockStore) |
| world_render.db | Array B render block store (RenderStore) |
| repl_log.db | Persistent replication entry log (ReplicationManager) |
| state.db | Block state index + write-ahead journal (ResilientStore) |
| entities.db | Entity sidecar (EntitySidecar) |

All use SQLite in WAL mode. Files may be co-located or placed on separate physical volumes. The intended production configuration is `world.db` and `world_render.db` on separate NVMe devices to fully realize the dual-array I/O isolation.

---

## Getting Started

**1. Install dependencies:**

```
pip install -r requirements.txt
```

Standard library only for the storage layer — `sqlite3`, `zlib`, `hashlib`, `struct`, `threading`. No third-party packages required.

**2. Generate a world:**

```
python world_gen.py --size 64 --seed 42 --out world.db --array-b world_render.db
```

Writes a 64×64×64 block world through the full mutation engine stack. Both Array A and Array B are populated. Size is snapped to the nearest 16-block chunk boundary.

**3. Run the server:**

```
python run_server.py --array-a world.db --array-b world_render.db --sidecar entities.db --size 64
```

Runs at 20 Hz. Health report every 2 seconds. Ctrl-C for clean shutdown.

**4. Run the thin client:**

```
python client.py
```

**5. Run the dual-array wiring example:**

```
python example_dual_array.py
```

Demonstrates the dual-array setup in isolation — writes blocks through Array A, reads them back from Array B, prints the health report.

**6. Run full test suite (core + tooling + adapters):**

```
python -m pytest tests/ -v
```

Runs all 56 tests: 29 core engine tests, 1 render queue test, 1 web bridge test, 1 metrics test, 6 security tests, 10 reliability tests, and 11 domain adapter tests. All passing.

**7. Run with observability (metrics):**

```python
from src.block_engine.replication.metrics_exporter import WritePathMetricsCollector
from src.block_engine.authority.resilient_store import ResilientStore

collector = WritePathMetricsCollector()
rs = ResilientStore(local_store, replication_manager, event_observer=collector.observe)

# After some writes
print(collector.prometheus_text())  # Prometheus-format metrics
snapshot = collector.snapshot()  # Detailed latency breakdown
```

**8. Run with security policies:**

```python
from src.block_engine.replication.write_authorization import (
    WriteAuthorizationLayer,
    OffsetRangePolicy,
    RateLimitPolicy,
)

auth = WriteAuthorizationLayer()
auth.add_policy(OffsetRangePolicy(layout))  # Enforce world bounds
auth.add_policy(RateLimitPolicy(max_writes_per_second=5000))

# Before any write
result = auth.authorize_write(offset, data)
if result.status == WriteAuthStatus.ALLOWED:
    resilient_store.write_block(offset, data)
```

**9. Start integrity scanner (corruption detection):**

```python
from src.block_engine.replication.integrity_validator import IntegrityValidator

def on_corruption(event):
    print(f"⚠️  Corruption detected at {event.offset}")

validator = IntegrityValidator(flat_store, observer=on_corruption)
validator.start()  # Runs in daemon thread
```

**10. Run Blender adapter (procedural generation):**

```python
from src.block_engine.bridges.blender_adapter import BlenderAdapter

adapter = BlenderAdapter(resilient_store, world_layout)

# Generate terrain procedurally
def terrain_gen(x, y, z):
    if y < 5:
        return 1  # Stone
    elif y < 8:
        return 2  # Dirt
    else:
        return 0  # Air

result = adapter.procedural_generation_hook(terrain_gen, x=0, y=0, z=0, size=16)
```

**11. Start Roblox HTTP adapter (multiplayer voxel games):**

```python
from src.block_engine.bridges.roblox_http_adapter import RobloxHTTPAdapter

adapter = RobloxHTTPAdapter(resilient_store, world_layout)
adapter.start(host="0.0.0.0", port=8000)

# Roblox game scripts now call: POST http://server:8000/roblox/write
# with {x, y, z, block_type, player_id}
```

**12. Run reliability tests (fault injection):**

```python
from src.block_engine.replication.crash_recovery_verifier import CrashRecoveryVerifier

verifier = CrashRecoveryVerifier(world_layout)
results = verifier.run_all_tests()
print(verifier.report(results))  # Verify all crash scenarios work
```

---

## Design Notes

### Storage Layer (Core)
- The storage layer has no network I/O. Wire in your transport by supplying `sync_callback` and `recovery_callback` to ReplicationManager and ResilientStore.
- `verify_integrity()` is a generator — drive it from a background thread or a low-priority maintenance loop. It will not stall reads or writes under any load condition.
- `max_blocks` should match the total block count of your flat world image so the engine enforces the same address space geometry as the underlying storage array.
- The async mirror forward in ResilientStore fires outside the write lock. Array B never adds latency to mutation throughput regardless of mirror count.
- Hardware I/O (`io_uring`, `O_DIRECT`) is stubbed for future integration. The logic layer is complete and hardware-independent.
- Entity spatial queries (`entities_near`) are linear scans in this prototype. Replace with an R-tree or spatial hash for production entity counts above a few thousand.
- Terrain noise uses SHA-256 digests as a portable, dependency-free substitute for Perlin/Simplex noise. Same seed, same world — deterministic for crash-recovery validation and regression testing.

### Observability & Tooling (All External)
- All observability, security, and reliability tooling is completely outside the engine. The core remains pure storage-native arithmetic.
- Observer callbacks are optional and zero-cost when unused (all checks are `if observer is None: return`).
- Metrics exporter emits stage-level write-path latency (journal_append, flat_store_write, replicate, journal_commit, mirror_forward).
- Security policies are stackable and composable — add more policies without modifying the engine or existing policies.
- Integrity validator runs in a daemon thread and never blocks live I/O; corruption reports go to an observer callback.
- All reliability testing (crash recovery, corruption fallback) uses fault injection — these are not runtime behaviors, they are test-only.

### Architecture Pattern
- ResilientStore with optional `event_observer` callback: `write_block(offset, data, observer=None)`
- Integrity scanner: read-only background daemon, never modifies state
- Write authorization: pre-write gate, policies are stackable
- Replication verifier: post-replication async verification, never blocks write path
- Domain adapters: thin translators between application protocols (HTTP, Blender, USD) and block read/write APIs

### Zero-Cost Abstraction
- Metrics not collected? No overhead.
- Security policies not configured? No overhead.
- Domain adapters not loaded? No overhead.
- Observer callback is None? Function returns immediately on the first check.

The engine pays zero cost for any tooling it does not use. Plug in only what you need.

---

## Frequently Asked Questions

### Architecture & Design

**Q: Why is the core engine completely separate from tooling?**  
A: The engine is pure storage-native arithmetic. Mixing operational concerns (metrics, policies, validation) into the core would compromise its hardware-agnostic property and create coupling to deployment-specific requirements. All tooling is external, pluggable, and zero-cost when unused.

**Q: What happens if I don't use the security tooling?**  
A: Nothing. The engine is untouched. Policies are opt-in. If `write_authorization` is not configured, all writes succeed (subject to existing crash-safety and quorum enforcement). The engine's core guarantees remain: journaled writes, checksum verification, quorum replication.

**Q: Can I use my own observability tooling?**  
A: Yes. The `event_observer` callback in ResilientStore is a simple `(stage, duration_ms)` interface. Plug in your metrics collector, send to Prometheus, Datadog, or any custom sink. The engine doesn't know or care what consumes the events.

### Two-Array Design

**Q: Why two storage arrays instead of one?**  
A: Physically separated arrays eliminate the most common source of latency in large-scale systems: write-read contention. A burst of world mutations (tens of thousands of blocks/sec) cannot introduce frame stalls because reads are isolated on Array B. Production deployments should place Array A and B on separate physical NVMe devices.

**Q: What if Array B falls behind Array A?**  
A: The `MirrorHealthMonitor` tracks lag. If lag exceeds thresholds (default 500 blocks), status changes to DEGRADED but writes continue unblocked. Array B is strictly for render feed consumption — if it falls behind, newer clients see slightly older state but never miss updates (the render feed is delta-only and catches up the moment Array B advances).

**Q: Can I run with just Array A (no Array B)?**  
A: Yes. Array B is optional. The render feed will fail without it, but pure mutation engine operation works fine. For batch processing or non-interactive workloads, you can skip Array B entirely.

### Replication & Durability

**Q: What does quorum enforcement actually guarantee?**  
A: If `required_replicas=2` and you have 3 nodes, a write succeeds only after at least 2 nodes ACK. If 2 nodes fail, the 1 remaining node can't form a quorum and writes fail (gracefully). This prevents split-brain scenarios and ensures any surviving node has the complete data.

**Q: What happens if all replica nodes are down?**  
A: Writes block and raise `QuorumError`. The block is still journaled locally (crash-safe) but replication quota is not met. You have two options: (1) mark nodes healthy manually if you know they're recovering, or (2) lower `required_replicas` threshold (operationally riskier).

**Q: Can I recover from journal corruption?**  
A: The `crash_recovery_verifier.py` tests this explicitly. If the journal is truncated mid-write, the incomplete entry is detected at startup and queued in `pending_replay`. You re-issue those writes through ResilientStore.

### Performance & Scaling

**Q: What's the write throughput bottleneck?**  
A: Depends on your configuration. Metrics exporter will tell you which stage (journal_append, flat_store_write, replicate, mirror_forward) is slowest. Typical bottleneck is replication I/O (network or remote storage); use `replication_verifier` to verify replicas are actually receiving data correctly.

**Q: How do I scale to 9.2 PB?**  
A: Use sparse blocks and multiple SparseBlockStore instances. The engine's coordinate arithmetic is O(1) regardless of world size. Storage bottleneck is entirely the underlying media (NVMe bandwidth, network bandwidth for remote replicas). The engine itself doesn't scale differently.

**Q: Is the 100 µs latency target measured or theoretical?**  
A: Theoretical, based on a 16-byte block aligned on NVMe page boundaries and assuming direct NVMe I/O (`io_uring`, `O_DIRECT`). Hardware integration is stubbed in this release. Real performance depends on hardware, storage media, and configuration.

### Domain Adapters

**Q: Can I build my own adapter?**  
A: Yes. Follow the pattern: read `resilient_store.read_block()`, run application-specific business logic, optionally write back via `write_authorization` → `resilient_store.write_block()`. The adapters are thin translators, not thick middleware.

**Q: Can multiple adapters run simultaneously?**  
A: Yes. Blender, Omniverse, and Roblox adapters all use the same ResilientStore instance. Writes serialize through the journal and replication manager (no race conditions). Reads are concurrent from Array B.

**Q: How do I add support for a new platform (e.g., Unreal, CryEngine)?**  
A: Create a new adapter in `src/block_engine/bridges/yourengine_adapter.py`. Implement `load_region()`, `export_geometry_to_boe()`, and coordinate transformation logic specific to that engine. See `blender_adapter.py` and `roblox_http_adapter.py` as templates.

### Testing & Reliability

**Q: Why are there so many reliability tests?**  
A: Crash safety is foundational but easy to get subtly wrong. The test suite validates that the engine actually recovers correctly after truncated journals, incomplete writes, and corruption scenarios. If any of these fail, durability claims are broken.

**Q: What does "non-silent corruption" mean?**  
A: If a block is corrupted (bit flips, transmission error, storage failure), the engine raises `CorruptBlockError` or recovers from a replica. It never returns corrupt data silently. Every read verifies a SHA-256 checksum; mismatch is always detected.

**Q: Can I disable crash recovery?**  
A: No. The journal is mandatory and crash recovery is always active. Every restart replays pending journal entries and detects incomplete writes. This is not configurable because crash safety is architectural.

---

## Proof-of-Concept Validation Checklist

- [ ] `world_gen` completes without error for `--size 64`
- [ ] Array A `write_seq` equals total block count after generation
- [ ] Array B `mirror_write_seq` converges to Array A `write_seq` within 1 second of generation completing
- [ ] Server loop runs for 10s with zero mirror DEGRADED events
- [ ] Kill server mid-generation, restart — journal replay produces identical block image
- [ ] `example_dual_array.py` reads all written blocks from Array B after writing through Array A
- [ ] Coordinate round-trip: `offset_to_coord(block_offset(x, y, z)) == (x, y, z)` for all valid coordinates
- [ ] Module self-tests pass: `sparse_block_store.py`, `replication_manager.py`, `resilient_store.py`

---

*This is a research prototype. The architecture is complete and the storage layer is production-quality. The game client, terrain generator, and simulation modules are proof-of-concept scaffolding to demonstrate the primitive. See module docstrings for detailed design notes and assumptions.*

---

## Appended: Spatial Movement and Studio Mutation Extension

The mutation engine remains an **in-world studio plug-in surface**. It is not a generic database mutation layer and does not compromise the direct frame/block-storage model. It accepts typed world mutations and routes them to the engine primitives that preserve direct addressing, journal order, sidecar isolation, and replication publication.

### Added modules

- `kernel/spatial_index.py` — direct entity-to-block membership map. It is an in-memory acceleration structure, not a source of truth or query/database layer.
- `kernel/movement_transaction.py` — journaled authoritative relocation. A movement commit updates the entity sidecar and spatial membership as one engine transition.
- `environment/movement_resolver.py` — pure policy seam for physics, collision, studio rules, or domain-specific movement interpretation.
- `replication/movement_replication.py` — transport-agnostic committed movement publication for region coordinators, mirrors, or render consumers.
- `services/mutation_engine.py` — studio-facing typed mutation gateway. It routes movement but does not own storage, coordinate arithmetic, or transport.

### Movement invariant

Movement is evaluated as a direct coordinate-to-offset transition:

```text
intent → resolver → MovementTransaction → sidecar write + spatial membership → journal commit → replication publication
```

The world block image remains geometry/state at its physical offsets. High-frequency entity motion remains in the sidecar. The spatial index only accelerates membership and can be rebuilt from sidecar records after restart. Adapters may submit `MoveIntent` objects, but they do not write transforms directly.

### Studio plug-in boundary

A studio can replace or extend `MovementResolver` to implement character controllers, vehicle dynamics, autonomous agents, scientific particles, tactical units, or cinematic constraints. The resulting intent is still committed through the same authoritative transaction path.


---

# Frame-Pure Deployment Model

## Core premise

The Block Storage Spatial Engine is the frame-level spatial primitive. It is not a database, filesystem, cache, network service, SAN product, or game engine stack. Its core operation is direct spatial addressing:

```text
coordinate → block address → frame operation
```

External tooling may exist around the frame—studio authoring tools, renderers, replication appliances, asset systems, transport adapters, analytics, and industry-specific integrations—but those are not layers inside the engine. They are replaceable consumers or producers of frame operations.

No hardware, SAN frame, filesystem, SQL store, cache, network fabric, or production backend is attached to this repository at present. The repository defines the engine model and integration boundaries; it is not a measurement of a deployed system.

## Direct-frame latency target

The intended direct-frame response target is **100 µs** for a frame operation. This is a design target for a directly attached deployment, not a measured result from this repository. It must be reported as a target until a named frame, controller, media configuration, command size, queue depth, read/write mix, and percentile-latency test demonstrate it.

At 100 µs per serialized operation, the theoretical ceiling is:

| Operation model | Theoretical rate |
|---|---:|
| One serialized operation | 10,000 ops/s |
| 16 independent queues | 160,000 ops/s |
| 64 independent queues | 640,000 ops/s |

These are latency-derived ceilings only. They are not device IOPS claims. Actual throughput is constrained by frame parallelism, command batching, block size, media bandwidth, consistency requirements, and workload locality.

## 3 PB spatial-frame capacity

Using the engine's 16-byte logical block and 0.66 m × 0.66 m horizontal resolution:

| Measure | 3 PB decimal |
|---|---:|
| Raw logical bytes | 3,000,000,000,000,000 B |
| Addressable 16-byte blocks | 187,500,000,000,000 |
| One-layer surface coverage | ~81.7 million km² |
| Equivalent square side length | ~9,040 km |
| Footprint with 256 vertical layers | ~319,000 km² |

This is the capacity of a compact spatial state field, not a claim that it stores all equivalent AAA art, audio, source assets, builds, or production history. Its efficiency is strongest where the required information per cell is compact and spatially regular: occupancy, terrain class, heat, hazard state, flood depth, navigation cost, visibility, and simulation fields.

## Comparison to a hypothetical 3 PB AAA environment

A conventional AAA studio's 3 PB is typically heterogeneous production storage: source assets, textures, meshes, audio, animation, build products, versions, backups, and caches. The frame uses the same raw byte budget for a uniform, directly addressable spatial state field.

| Question | Conventional heterogeneous estate | Frame-pure spatial engine |
|---|---|---|
| Primary unit | files/assets/records | fixed spatial block |
| Spatial lookup | application/index/asset path dependent | deterministic coordinate-to-block address |
| Best use | content production and heterogeneous data | dense spatial state |
| What 3 PB means | many kinds of production data | 187.5 trillion compact spatial cells |
| Equivalent content claim | not applicable | not applicable |

The advantage is not that 3 PB of spatial cells replaces 3 PB of studio production assets. The advantage is that a workload needing a huge regular spatial state field can represent that field without embedding it in a general-purpose content estate.

## I/O demographics to validate on a frame

The following are deployment measurements to publish once a frame exists:

| Metric | Required reporting |
|---|---|
| Latency | p50, p95, p99, p99.9 by operation type |
| IOPS | read, write, mixed; command size and queue count |
| Throughput | bytes/s for contiguous ranges and spatial neighborhoods |
| Locality | same-block, adjacent-block, radius scan, long traversal |
| Concurrency | independent queues and contention behavior |
| Durability | acknowledgement point and failure behavior |
| Capacity | raw, usable, mirrored, parity, snapshot, and reserve space |
| Energy/rack | measured watts, cooling, ports, and physical footprint |

Until those measurements exist, the only numerical statements in this README are logical-capacity calculations and the 100 µs design target—not measured performance or datacenter reduction.

Block Offset Engine (BOE)
A Lightweight Storage-Native Spatial Engine for Persistent Worlds, AI Memory, and Real-Time Simulation

Vision

Block Offset Engine is a next-generation spatial runtime designed around one fundamental idea:

What if the world did not load from storage, but instead existed as persistent storage?

Traditional engines treat storage as a place where assets and data are retrieved.

Block Offset Engine explores a different model:

Storage becomes the foundation of the environment.

Objects, entities, simulations, AI states, resources, and world events can exist as persistent addressable data structures capable of being streamed, replicated, modified, and evolved.

Overview

Block Offset Engine (BOE) is a lightweight, embeddable spatial engine designed for:

persistent world simulation
AI-driven environments
real-time state replication
large-scale spatial data management
interactive gaming environments
digital twins
distributed simulations

With an extremely small footprint (~28 MB), BOE is designed to operate independently from the environment it is deployed into.

It is not tied to:

a specific game engine
a rendering technology
a cloud provider
a hardware platform
a specific application

It is an engine layer.

The Core Concept
Traditional Engine Architecture

Most modern engines follow a model similar to:

Storage

   ↓

Asset Loading

   ↓

Memory

   ↓

Simulation

   ↓

Rendering

Data is temporary.

The application owns the world.

Block Offset Engine Architecture

BOE reverses this relationship.

Persistent Storage

        ↓

Spatial Objects

        ↓

Simulation State

        ↓

Applications

        ↓

Rendering / AI / Interaction

The world exists independently.

Applications connect to it.

Why Block Offset Engine?

Modern applications are approaching new limitations:

Increasing world sizes
Persistent multiplayer environments
AI agents requiring long-term memory
Real-time simulations
Massive data generation
Distributed computing requirements

Traditional architectures rely heavily on:

memory caching
temporary object states
periodic saving
database synchronization

BOE explores a persistent-first approach.

Engine Characteristics
Lightweight Core Runtime

Current engine footprint:

Approximately 28 MB

Designed for:

portability
embedded deployment
edge environments
cloud workloads
local applications

The engine can be placed into different environments without requiring a massive supporting framework.

Spatial Object Architecture

Everything in BOE can be represented as a persistent spatial object.

Example:

Object

 |
 +-- Unique Identifier
 |
 +-- Spatial Coordinates
 |
 +-- State Data
 |
 +-- Historical Data
 |
 +-- Relationships
 |
 +-- Ownership
 |
 +-- Replication Information
 |
 +-- AI Metadata

Objects are not temporary game entities.

They are persistent world elements.

The Living World Model

Imagine a world where objects maintain continuity:

A building remembers:

Construction Date

Owners

Repairs

Events

Economic History

An AI agent remembers:

Experiences

Relationships

Knowledge

Goals

Previous Decisions

A resource remembers:

Discovery Location

Extraction History

Ownership

Market Activity

The world becomes a persistent system rather than a collection of loaded assets.

Predictive Spatial Streaming

One of the core design goals of BOE is reducing latency through prediction.

Instead of:

Request Data

      ↓

Retrieve Data

      ↓

Wait

BOE enables:

Current Position

      ↓

Predict Future Requirements

      ↓

Prefetch Data

      ↓

Prepare Environment

Potential applications:

open-world games
AR environments
simulations
autonomous systems
Snapshot and Replication System

Persistent environments require reliable state management.

BOE is designed around high-frequency state snapshots.

Snapshots enable:

replication
rollback
recovery
simulation branching
historical analysis

Architecture:

World State A

      ↓

Snapshot

      ↓

Delta Changes

      ↓

Replica

      ↓

World State B

Instead of rebuilding worlds, BOE maintains transitions between states.

AI Memory Infrastructure

Current AI systems are limited by context windows.

A persistent intelligent environment requires:

memory
experience
history
consequences
environmental awareness

BOE provides a foundation for persistent AI environments.

Example:

AI Agent

       |
       |
 Persistent Memory Object

       |
       |
 Experiences
 Relationships
 Knowledge
 Goals
 Location History

The AI does not simply answer.

It exists.

Gaming Applications

While BOE is designed as a general-purpose engine, gaming represents one of the most exciting applications.

Persistent Planet-Scale Worlds

Imagine combining:

Google Earth-style visualization
Pokémon GO-style interaction
MMO persistence
strategy mechanics
collectible card systems
AI-driven environments

The result:

A world where locations, objects, resources, and events exist persistently.

Spatial Trading Card System Concept

BOE enables a new class of digital assets.

Cards are not merely images.

They can represent persistent objects.

Example:

Legendary Artifact Card

        ↓

Unique Object

        ↓

Location

        ↓

History

        ↓

Ownership

        ↓

Evolution

A card becomes an interface into the world.

AI-Driven Game Worlds

Potential future:

Player

 ↓

Persistent World

 ↓

AI Agents

 ↓

Learning

 ↓

World Evolution

NPCs are no longer scripted objects.

They become persistent participants.

Digital Twin Applications

BOE can support environments such as:

cities
infrastructure
logistics networks
industrial systems
environmental models

Because the engine separates:

World Data

from

Visualization

the same environment can be viewed through multiple applications.

Hardware Compatibility

Designed to operate with modern storage architectures:

NVMe SSD
enterprise storage systems
SAN environments
distributed storage architectures

The engine is designed around the principle that storage performance can become a foundation for real-time persistent systems.

System Architecture
                 Applications

       Games | AI | Simulation | Tools


                      |

              Block Offset Engine


    Spatial Objects | Snapshots | Replication


                      |

              Storage Infrastructure


        NVMe | SSD | SAN | Distributed Systems
Design Philosophy

Block Offset Engine follows several principles:

Persistence First

Data should exist beyond execution sessions.

Environment Independence

The engine should not depend on a single application.

Spatial Awareness

Location and relationships are fundamental.

Scalable State Management

Large environments require intelligent data handling.

AI Compatibility

Future intelligent systems require persistent worlds.

Current Development Goals

Future milestones:

Core Engine
Object indexing
Spatial addressing
Snapshot management
Replication framework
Agent memory
Environment interaction
Persistent learning systems
Simulation Layer
Physics integration
Economic systems
Procedural environments
Multiplayer Layer
Distributed worlds
State synchronization
Large-scale persistence
The Long-Term Vision

Block Offset Engine explores a future where:

Games are not just played.

They exist.

AI does not just respond.

It remembers.

Worlds are not loaded.

They persist.

Project Status

Block Offset Engine is an experimental storage-native spatial engine exploring the intersection of:

storage systems
gaming technology
artificial intelligence
distributed computing
persistent simulation
About

Created by:

Michael Hinkle

Exploring the future of persistent digital environments.
