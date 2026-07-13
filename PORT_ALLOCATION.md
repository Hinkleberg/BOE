# Port Allocation & Assignment Document

**Status:** ✅ COMPLETE - All adapters assigned unique ports with zero conflicts

---

## TCP Duplex Ports (7100-7509)

All full-duplex adapters using DPLX wire protocol.

| Port | Adapter | Status | Notes |
|------|---------|--------|-------|
| **7100** | UnrealAdapter | ✅ Active | Unreal Engine 5.x integration |
| **7200** | BlenderAdapter | ✅ Active | Blender 4.x procedural generation |
| **7300** | OmniverseConnector | ✅ Active | NVIDIA Omniverse USD bridge |
| **7400** | RobloxHTTPAdapter (Duplex) | ✅ Active | Roblox Studio duplex channel |
| **7500** | GodotAdapter | ✅ Active | Godot 3.x/4.x game engine |
| **7502** | O3DEAdapter | ✅ Active | Amazon O3DE (was 7300 - fixed) |
| **7503** | UnityAdapter | ✅ Active | Unity Engine (was 7200 - fixed) |
| **7507** | WebBridge | ✅ Active | Web 3D / WebSocket (was 7500 - fixed) |
| 7501 | *Reserved* | — | Future adapter |
| 7504 | *Reserved* | — | Future adapter |
| 7505 | *Reserved* | — | Future adapter |
| 7506 | *Reserved* | — | Future adapter |
| 7508 | *Reserved* | — | Future adapter |
| 7509 | *Reserved* | — | Future adapter |

**Total Active:** 8 adapters  
**Total Reserved:** 6 ports for future expansion  
**Conflicts:** ZERO ✅

---

## Other Protocol Ports

| Port | Adapter | Protocol | Status |
|------|---------|----------|--------|
| **8000** | RobloxHTTPAdapter (HTTP) | HTTP REST | ✅ Active |
| **3000** | MilitarySimAdapter | DIS | Optional (not in launcher) |
| **9200** | StarlinkAdapter | gRPC | Optional (external dependency) |

---

## Fixed Conflicts

| Issue | Before | After | Reason |
|-------|--------|-------|--------|
| **WebBridge** | 7500 | 7507 | Conflicted with GodotAdapter |
| **O3DEAdapter (old)** | 7300 | 7502 | Conflicted with OmniverseConnector; duplicate with duplex version |
| **UnityAdapter (old)** | 7200 | 7503 | Conflicted with BlenderAdapter; duplicate with duplex version |

---

## Adapter Type Classification

### Full-Duplex Network Adapters (Inherit from DuplexAdapter)
These accept TCP connections and use DPLX wire protocol:
- UnrealAdapter (7100)
- BlenderAdapter (7200)
- OmniverseConnector (7300)
- RobloxHTTPAdapter (7400 duplex)
- GodotAdapter (7500)
- O3DEAdapter (7502)
- UnityAdapter (7503)
- WebBridge (7507)

### Domain Adapters (No network ports)
These process data from entity_sidecar and render_feed, don't listen on ports:
- ScientificSimAdapter (no port)
- AVSimAdapter (no port)
- MilitarySimAdapter (uses external DIS protocol on 3000, not in main launcher)
- StarlinkAdapter (uses gRPC on 9000+, not in main launcher)
- Godot4Bridge (protocol handler, no port)

### Legacy Adapters (Not in current launcher)
- O3DEAdapter (non-duplex, old implementation)
- UnityAdapter (non-duplex, old implementation, http only)

---

## Launch Command Reference

**Start all duplex adapters (8 adapters, 9 ports):**
```bash
python start_duplex_server.py --adapters minimal
python start_duplex_server.py --adapters all  # Same as minimal for now
```

**Ports used:**
```
7100, 7200, 7300, 7400, 7500, 7502, 7503, 7507, 8000
```

**Verification:** All adapters shown in startup output with 0 conflicts.

---

## Socket Binding Checklist

| Port | Process | Listen Status |
|------|---------|----------------|
| 7100 | UnrealAdapter | [UnrealAdapter] Listening on 127.0.0.1:7100 ✓ |
| 7200 | BlenderAdapter | [BlenderAdapter] Listening on 127.0.0.1:7200 ✓ |
| 7300 | OmniverseConnector | [OmniverseConnector] Listening on 127.0.0.1:7300 ✓ |
| 7400 | RobloxHTTPAdapter | [RobloxHTTPAdapter] Listening on 127.0.0.1:7400 ✓ |
| 7500 | GodotAdapter | [GodotAdapter] Listening on 127.0.0.1:7500 ✓ |
| 7502 | O3DEAdapter | [O3DEAdapter] Listening on 127.0.0.1:7502 ✓ |
| 7503 | UnityAdapter | [UnityAdapter] Listening on 127.0.0.1:7503 ✓ |
| 7507 | WebBridge | ✓ (WebSocket server active) |
| 8000 | RobloxHTTPAdapter | [RobloxHTTPAdapter] HTTP listening on 127.0.0.1:8000 ✓ |

---

## Files Modified

1. **start_duplex_server.py**
   - Updated port header documentation
   - Fixed imports to include WebBridge
   - Added WebBridge startup (7507)
   - Updated example commands to reflect all adapters
   - Added port allocation summary in output

2. **src/block_engine/bridges/web_bridge.py**
   - Changed default port from 7500 → 7507

3. **src/block_engine/bridges/O3de_adapter.py** (legacy)
   - Changed default port from 7300 → 7502

4. **src/block_engine/bridges/unity_adapter.py** (legacy)
   - Changed default port from 7200 → 7503

5. **src/block_engine/bridges/unity_adapter_duplex.py**
   - Already correct at 7503 ✓

6. **src/block_engine/bridges/o3de_adapter_duplex.py**
   - Already correct at 7502 ✓

---

## Validation Results

✅ **All adapters start without errors**  
✅ **Zero port conflicts detected**  
✅ **All expected adapters listening on correct ports**  
✅ **No duplicate port assignments**  
✅ **Server startup output shows proper port allocation**

---

## Future Expansion

Reserved ports (7501, 7504-7506, 7508-7509) available for:
- Godot4Bridge (7501) if converted to duplex
- Additional platform adapters
- Cloud/distributed simulation bridges
- Custom domain-specific adapters

---

**Last Updated:** 2026-07-12  
**Status:** Production Ready  
**Next Phase:** Phase 6 - Additional adapter integration

