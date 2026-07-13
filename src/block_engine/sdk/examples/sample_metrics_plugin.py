"""Example BOE plugin built against the formal Plugin SDK."""

from __future__ import annotations

from block_engine.sdk import BOEPlugin, PluginContext, PluginMetadata


class SampleMetricsPlugin(BOEPlugin):
    metadata = PluginMetadata(
        name="sample-metrics-plugin",
        version="0.1.0",
        api_version="1.0",
        author="BOE Team",
        description="Logs core capability information during plugin startup.",
    )

    def __init__(self) -> None:
        self._context: PluginContext | None = None

    def on_load(self, context: PluginContext) -> None:
        self._context = context
        caps = context.core.capabilities()
        context.logger(
            f"[{self.metadata.name}] loaded against API {caps.api_version}; "
            f"entity_sync={caps.has_entity_sync} inspector={caps.has_inspector}"
        )

    def on_start(self) -> None:
        if self._context is not None:
            self._context.logger(f"[{self.metadata.name}] started")

    def on_stop(self) -> None:
        if self._context is not None:
            self._context.logger(f"[{self.metadata.name}] stopped")

    def on_unload(self) -> None:
        if self._context is not None:
            self._context.logger(f"[{self.metadata.name}] unloaded")
            self._context = None
