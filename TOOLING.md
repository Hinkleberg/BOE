# Observability, Security & Reliability Tooling

The core Block Offset Engine is entirely storage-agnostic and policy-free. All operational tooling — observability, security enforcement, reliability testing, and domain integration — sits **completely outside the engine** as pluggable adapters and observers. The engine remains unchanged; tooling plugs in via callbacks.

## Test Coverage

**Current:** 56 tests, all passing  
**Core impact:** 0 changes to engine logic  
**Tooling code:** ~3,000 lines (all external)

---

## Observability & Performance

### metrics_exporter.py

Stage-level latency collector for the write path. Emits Prometheus-format metrics without touching engine semantics.

**Stages instrumented:**
- `journal_append` — pre-commit latency
- `flat_store_write` — checksum + storage I/O
- `replicate` — quorum enforcement (ReplicationManager)
- `journal_commit` — durability confirmation
- `mirror_forward` — async Array B fan-out

**Usage:**

```python
from replication.metrics_exporter import WritePathMetricsCollector

collector = WritePathMetricsCollector()
rs = ResilientStore(store, event_observer=collector.observe)

# After writes
snapshot = collector.snapshot()
print(collector.prometheus_text())  # Prometheus format for Grafana
```

**What it tells you:**
- Write throughput bottlenecks (which stage is slow?)
- Replication lag impact on write latency
- Mirror forward time distribution

---

## Security Hardening

### integrity_validator.py

Background daemon scanner that detects silent block corruption without modifying state.

**Features:**
- Scans FlatStore periodically in a daemon thread
- Uses existing `verify_integrity()` (read-only)
- Corruption reported to observer callback (metrics/logs/alerts)
- Zero cost if observer is None

**Usage:**

```python
from replication.integrity_validator import IntegrityValidator, CorruptionSeverity

corruptions = []
def on_corruption(event):
    if event.severity == CorruptionSeverity.CRITICAL:
        alert(f"Block {event.offset} corrupted")
    corruptions.append(event)

validator = IntegrityValidator(flat_store, observer=on_corruption)
validator.start()
```

### write_authorization.py

Stackable policy validators that run **before** writes hit ResilientStore — never inside it.

**Built-in policies:**

- **OffsetRangePolicy** — reject writes outside declared bounds
- **RateLimitPolicy** — enforce throughput thresholds (e.g., 1000 writes/sec)
- **AuditPolicy** — forensic logging of all write attempts

**Usage:**

```python
from replication.write_authorization import (
    WriteAuthorizationLayer,
    OffsetRangePolicy,
    RateLimitPolicy,
    AuditPolicy,
)

auth = WriteAuthorizationLayer()
auth.add_policy(OffsetRangePolicy(world_layout))
auth.add_policy(RateLimitPolicy(max_writes_per_second=10000))
auth.add_policy(AuditPolicy(observer=log_write))

# Before any write
result = auth.authorize_write(offset, data)
if result.status == WriteAuthStatus.ALLOWED:
    resilient_store.write_block(offset, data)
```

### replication_verifier.py

Post-replication verification that spot-checks mirrors have matching checksums. Runs asynchronously, never blocks write path.

**Usage:**

```python
from replication.replication_verifier import ReplicationVerifier

def read_from_mirror(node_id, offset):
    return remote_mirrors[node_id].read_block(offset)

verifier = ReplicationVerifier(
    replication_manager,
    reader_callback=read_from_mirror,
    observer=on_verification_result,
)
verifier.start()

# After ResilientStore.write_block()
verifier.enqueue_verification(offset, seq, data)
```

### journal_auditor.py

Forensic parser for the binary journal. Makes the write-ahead log queryable without modifying it.

**Usage:**

```python
from replication.journal_auditor import JournalAuditFormatter

auditor = JournalAuditFormatter("world.jrn")

# Forensic queries
trail = auditor.audit_trail()  # All pending entries
offsets_written = auditor.offsets_written()  # Group by offset
summary = auditor.forensic_summary()  # Structured data
print(auditor.report())  # Human-readable audit trail
```

---

## Reliability Testing

### crash_recovery_verifier.py

Injects faults (truncated journal, incomplete writes) and verifies recovery works.

**Tests included:**

- **Journal replay after truncation** — Verify blocks survive journal corruption
- **Incomplete write detection** — Verify pending_replay flags are set correctly
- **Journal consistency after restart** — Verify clean shutdown persists all writes

**Usage:**

```python
from replication.crash_recovery_verifier import CrashRecoveryVerifier

verifier = CrashRecoveryVerifier(world_layout)
results = verifier.run_all_tests()
print(verifier.report(results))
```

### checksum_fallback_harness.py

Forces corruption and verifies the recovery path works end-to-end.

**Tests included:**

- **Checksum mismatch detection** — Corrupt a block, verify error is raised
- **Replica recovery on corruption** — Corrupt local, recover from mirror
- **Failure mode without replicas** — Verify CorruptBlockError is raised appropriately

**Usage:**

```python
from replication.checksum_fallback_harness import ChecksumFallbackHarness

harness = ChecksumFallbackHarness(world_layout)
results = harness.run_all_tests()
print(harness.report(results))
```

---

## Domain Adapters

Thin protocol translators that connect BOE to external platforms. Each adapter follows the same non-invasive pattern: read-only queries + write authorization.

### blender_adapter.py

Python-native Blender integration for procedural generation and scene export.

**Features:**
- `load_region()` — Stream voxel data into Blender scenes
- `export_scene_to_boe()` — Export Blender geometry to BOE coordinates
- `procedural_generation_hook()` — Use Blender nodes with BOE backend
- `stream_to_viewport()` — Real-time viewport updates

**Audience:** ~4M Blender users, strong VFX/procedural community

**Usage:**

```python
from bridges.blender_adapter import BlenderAdapter

adapter = BlenderAdapter(resilient_store, world_layout)
blocks = adapter.load_region(x=0, y=0, z=0, size=16)

# Or generate procedurally
def my_generator(x, y, z):
    return 1 if y < 5 else 2  # stone below y=5, grass above

result = adapter.procedural_generation_hook(
    my_generator, x=0, y=0, z=0, size=16
)
```

### omniverse_connector.py

Bridge to NVIDIA Omniverse for digital twins and multi-tool collaboration.

**Features:**
- `sync_region_to_omniverse()` — Convert blocks to USD primitives
- `_build_usd_operations()` — Generate stage operations for Nucleus
- `subscribe_to_changes()` — Live sync when BOE updates
- `batch_export_to_usdz()` — Archive & share

**Audience:** Enterprise digital twins, CAD/BIM, collaborative XR

**Use cases:**
- Factory digital twins
- City-scale simulations
- Multi-tool pipelines (Maya→Houdini→Unreal via Omniverse)
- Nucleus server integration

**Usage:**

```python
from bridges.omniverse_connector import OmniverseConnector

connector = OmniverseConnector(
    resilient_store,
    world_layout,
    nucleus_server_url="http://localhost:8080",
)

# Sync region to Omniverse
result = connector.sync_region_to_omniverse(x=0, y=0, z=0, size=16)

# Subscribe to changes
connector.subscribe_to_changes(
    callback=lambda update: print(f"Block {update.offset} changed")
)
```

### roblox_http_adapter.py

Native HTTP API for Roblox game servers via HttpService.

**Features:**
- `POST /roblox/write` — Write blocks from game scripts
- `GET /roblox/read?x=100&y=50&z=200` — Single block queries
- `GET /roblox/region?x=0&y=0&z=0&size=16` — Region bulk reads
- Statistics tracking (requests/writes/reads)

**Audience:** ~9M Roblox developers, massive indie voxel game market

**Roblox usage (Lua):**

```lua
local http = game:GetService("HttpService")

-- Write a block
local response = http:PostAsync(
    "http://localhost:8000/roblox/write",
    http:JSONEncode({x=100, y=50, z=200, block_type=1, player_id=player.UserId})
)

-- Read a region
local data = http:GetAsync("http://localhost:8000/roblox/region?x=0&y=0&z=0&size=16")
```

**Python usage:**

```python
from bridges.roblox_http_adapter import RobloxHTTPAdapter

adapter = RobloxHTTPAdapter(resilient_store, world_layout)
adapter.start(host="0.0.0.0", port=8000)

# In Roblox game scripts, call via HttpService
# Metrics available via adapter.statistics()
```

---

## Architecture Principle: Core Agnostic, Tooling Modular

**The pattern:**

```
ResilientStore (unchanged, pure)
    ↓
Pluggable callbacks:
  - event_observer(stage, latency)  ← metrics_exporter
  - read_block(offset)               ← integrity_validator (non-blocking)
  - authorize_write(offset, data)    ← write_authorization (pre-write gate)
    ↓
Domain adapters (transport/protocol agnostic):
  - blender_adapter (Python API)
  - omniverse_connector (USD/Nucleus)
  - roblox_http_adapter (HTTP for game scripts)
  - + Military (DIS/HLA), Autonomous (CARLA), Robotics (ROS2) templates
```

**Key property:** The core engine has no knowledge of:
- What metrics are collected
- What security policies are enforced
- What domains are served
- What transport protocols are used

All of that lives outside. The engine remains pure storage-native arithmetic.

---

## Running the Test Suite

All 56 tests (core + tooling + domain adapters):

```bash
python -m pytest tests/ -v
```

Breakdown:

- **test_v2.py** (29 tests) — Core engine, spatial math, cache, simulation
- **test_web_bridge.py** (1 test) — Observer pattern
- **test_render_store_queue.py** (1 test) — Async queue
- **test_metrics_exporter.py** (1 test) — Observability
- **test_security_tooling.py** (6 tests) — Integrity, authorization, verification
- **test_reliability_hardening.py** (10 tests) — Crash recovery, checksum fallback, audit
- **test_domain_adapters.py** (11 tests) — Blender, Omniverse, Roblox

---

## Future Adapters (Templates Ready)

The adapter template is proven. Next builds are straightforward:

- **Minecraft mods** (Fabric/Forge) — 1-2M active modders
- **CARLA/AirSim** — Autonomous vehicle research
- **Gazebo/ROS2** — Robotics + SLAM point clouds
- **VBS4 / Bohemia Interactive Simulations** — Military training (DIS/HLA extension)
- **NVIDIA Omniverse** — Enterprise digital twins
- **CryEngine** — Large open-world support
- **Unreal + NaniteWorld** — Extreme scale voxel terrain

---

## Zero-Cost Abstraction

**All tooling is optional:**
- No metrics collection? No performance impact.
- No security policies? Core engine unchanged.
- No domain adapters loaded? Zero overhead.
- Observer is None? Function returns immediately.

The engine pays zero cost for tooling it doesn't use. Plug in what you need; ignore the rest.
