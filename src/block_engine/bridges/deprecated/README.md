# Deprecated Adapters

This folder contains legacy adapter implementations that have been superseded by newer versions.

## Contents

### O3de_adapter.py
- **Legacy Implementation:** Non-duplex HTTP-based adapter
- **Current Version:** `../o3de_adapter_duplex.py`
- **Status:** DEPRECATED
- **Reason:** Replaced by full-duplex DuplexAdapter-based implementation
- **Migration:** Switch imports from `O3de_adapter` to `o3de_adapter_duplex`

### unity_adapter.py
- **Legacy Implementation:** Non-duplex HTTP-based adapter
- **Current Version:** `../unity_adapter_duplex.py`
- **Status:** DEPRECATED
- **Reason:** Replaced by full-duplex DuplexAdapter-based implementation
- **Migration:** Switch imports from `unity_adapter` to `unity_adapter_duplex`

## Rationale for Deprecation

1. **Architecture Unification:** All modern adapters inherit from `DuplexAdapter` for:
   - Unified TCP wire protocol (DPLX)
   - Real-time bidirectional communication
   - Entity synchronization hub integration
   - Consistent threading model

2. **Entity Sync Integration:** Legacy adapters don't participate in the cross-adapter
   entity synchronization system. New adapters automatically sync entity changes
   across all connected platforms.

3. **Maintenance:** Fewer code paths to maintain, clearer architecture.

## Migration Guide

If you're currently using legacy adapters:

```python
# OLD (Deprecated)
from bridges.O3de_adapter import O3DEAdapter
from bridges.unity_adapter import UnityAdapter

# NEW (Current)
from bridges.o3de_adapter_duplex import O3DEAdapter
from bridges.unity_adapter_duplex import UnityAdapter
```

Both maintain the same public interface, so code using them should work with minimal
changes. The new versions simply add TCP duplex networking and entity sync capabilities.

## Archive Policy

These files are retained for reference. They may be safely deleted after confirming
all downstream code has migrated to the new versions.

---

**Last Updated:** 2026-07-12  
**Deprecation Effective:** Phase 5
