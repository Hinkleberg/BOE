# BOE Plugin SDK (v1.0)

This document defines the stable extension surface for external BOE plugins.

## Goals

- Stable API contract for third-party extensions
- Lifecycle hooks for startup/shutdown safety
- Version compatibility enforcement
- Zero core modifications required for plugin development

## SDK Modules

- `block_engine.core_api`:
  - `CORE_API_VERSION` (`"1.0"`)
  - `BOECoreAPI` (versioned facade over core services)
- `block_engine.sdk`:
  - `PluginMetadata`
  - `PluginContext`
  - `BOEPlugin` protocol
  - `PluginRegistry`

## Lifecycle

1. `PluginRegistry.register(plugin)`
2. `plugin.on_load(context)`
3. `PluginRegistry.start_all()` -> `plugin.on_start()`
4. `PluginRegistry.stop_all()` -> `plugin.on_stop()`
5. `PluginRegistry.unload_all()` -> `plugin.on_unload()`

## Compatibility Policy

- Plugins declare `metadata.api_version`.
- Compatibility is enforced by major version.
- BOE core rejects incompatible plugins at registration time.

Example:
- Core API: `1.0`
- Plugin API: `1.2` -> compatible
- Plugin API: `2.0` -> rejected

## Minimal Example

```python
from block_engine.core_api import BOECoreAPI
from block_engine.sdk import PluginContext, PluginRegistry
from block_engine.sdk.examples.sample_metrics_plugin import SampleMetricsPlugin

core = BOECoreAPI(layout=layout, block_store=resilient_store, entity_sync=entity_sync, inspector=web_bridge)
context = PluginContext(core=core, config={"env": "demo"}, logger=print)
registry = PluginRegistry(context)

registry.register(SampleMetricsPlugin())
registry.start_all()
# ... run engine ...
registry.stop_all()
registry.unload_all()
```

## Distribution Guidance

- Package plugins as normal Python distributions.
- Keep plugin dependencies isolated from BOE core dependencies.
- Depend on BOE API major version only.
- Avoid importing implementation internals outside `block_engine.core_api` and `block_engine.sdk`.
