"""Formal plugin SDK for Block-Offset Engine.

External developers should target this module instead of importing internal
engine modules directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol

from block_engine.core_api import BOECoreAPI, CORE_API_VERSION


@dataclass(frozen=True)
class PluginMetadata:
    name: str
    version: str
    api_version: str
    author: str = ""
    homepage: str = ""
    description: str = ""


@dataclass
class PluginContext:
    core: BOECoreAPI
    config: Dict[str, Any] = field(default_factory=dict)
    logger: Callable[[str], None] = print


class BOEPlugin(Protocol):
    metadata: PluginMetadata

    def on_load(self, context: PluginContext) -> None:
        ...

    def on_start(self) -> None:
        ...

    def on_stop(self) -> None:
        ...

    def on_unload(self) -> None:
        ...


class PluginRegistry:
    """Lifecycle manager for BOE plugins."""

    def __init__(self, context: PluginContext):
        self._context = context
        self._plugins: Dict[str, BOEPlugin] = {}

    @staticmethod
    def _is_api_compatible(plugin_api_version: str) -> bool:
        plugin_major = plugin_api_version.split(".", 1)[0]
        core_major = CORE_API_VERSION.split(".", 1)[0]
        return plugin_major == core_major

    def register(self, plugin: BOEPlugin) -> None:
        meta = plugin.metadata
        if not self._is_api_compatible(meta.api_version):
            raise ValueError(
                f"Plugin '{meta.name}' targets incompatible API version {meta.api_version}; "
                f"core is {CORE_API_VERSION}"
            )
        if meta.name in self._plugins:
            raise ValueError(f"Plugin '{meta.name}' already registered")
        plugin.on_load(self._context)
        self._plugins[meta.name] = plugin

    def start_all(self) -> None:
        for plugin in self._plugins.values():
            plugin.on_start()

    def stop_all(self) -> None:
        for plugin in reversed(list(self._plugins.values())):
            plugin.on_stop()

    def unload_all(self) -> None:
        for plugin in reversed(list(self._plugins.values())):
            plugin.on_unload()
        self._plugins.clear()

    def names(self) -> List[str]:
        return sorted(self._plugins.keys())

    def get(self, name: str) -> Optional[BOEPlugin]:
        return self._plugins.get(name)

    def __iter__(self) -> Iterable[BOEPlugin]:
        return iter(self._plugins.values())
