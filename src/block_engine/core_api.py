"""Stable BOE core API contract for adapters and plugins.

This module defines a narrow, versioned compatibility surface that third-party
integrations can depend on without importing internal implementation details.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

CORE_API_VERSION = "1.0"


class BlockIO(Protocol):
    """Minimal block read/write authority required by adapters and plugins."""

    @property
    def write_seq(self) -> int:
        ...

    def read_block(self, offset: int) -> bytes:
        ...

    def write_block(self, offset: int, data: bytes):
        ...

    def health_report(self) -> Dict[str, Any]:
        ...


class EntitySyncIO(Protocol):
    """Entity synchronization capability exposed to adapters/plugins."""

    def get_all_entities(self) -> List[Any]:
        ...

    def apply_entity_event(self, event: Any, **kwargs: Any) -> Any:
        ...


class InspectorIO(Protocol):
    """Optional telemetry sink used by visual inspector tooling."""

    def status(self) -> Dict[str, Any]:
        ...


@dataclass(frozen=True)
class CoreCapabilities:
    api_version: str
    has_entity_sync: bool
    has_inspector: bool
    has_health_report: bool


class BOECoreAPI:
    """Stable facade over mutable engine internals."""

    def __init__(
        self,
        *,
        layout: Any,
        block_store: BlockIO,
        entity_sync: Optional[EntitySyncIO] = None,
        inspector: Optional[InspectorIO] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._layout = layout
        self._block_store = block_store
        self._entity_sync = entity_sync
        self._inspector = inspector
        self._metadata = metadata or {}

    @property
    def layout(self) -> Any:
        return self._layout

    @property
    def block_store(self) -> BlockIO:
        return self._block_store

    @property
    def entity_sync(self) -> Optional[EntitySyncIO]:
        return self._entity_sync

    @property
    def inspector(self) -> Optional[InspectorIO]:
        return self._inspector

    @property
    def metadata(self) -> Dict[str, Any]:
        return dict(self._metadata)

    def capabilities(self) -> CoreCapabilities:
        return CoreCapabilities(
            api_version=CORE_API_VERSION,
            has_entity_sync=self._entity_sync is not None,
            has_inspector=self._inspector is not None,
            has_health_report=hasattr(self._block_store, "health_report"),
        )
