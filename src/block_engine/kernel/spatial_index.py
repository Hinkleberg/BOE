"""Chunk-aligned spatial membership index for high-frequency entity queries."""

from __future__ import annotations

import math
import threading
from collections import defaultdict
from typing import Dict, FrozenSet, Iterable, Optional, Set, Tuple


ChunkKey = Tuple[int, int, int]


class SpatialIndex:
    """
    In-memory, derived spatial index.

    This index is intentionally not authoritative state; the sidecar remains the
    source of truth and this structure can be rebuilt at startup.
    """

    def __init__(self, *, chunk_dim: int = 16):
        self._chunk_dim = max(1, int(chunk_dim))
        self._lock = threading.Lock()

        # Legacy direct-address block membership (kept for compatibility).
        self._by_block: Dict[int, Set[int]] = defaultdict(set)
        self._entity_block: Dict[int, int] = {}

        # Chunk-grid membership for fast radius shortlist queries.
        self._by_chunk: Dict[ChunkKey, Set[int]] = defaultdict(set)
        self._entity_chunk: Dict[int, ChunkKey] = {}

        # Companion indices for immediate category/ownership lookups.
        self._by_type: Dict[int, Set[int]] = defaultdict(set)
        self._by_owner: Dict[int, Set[int]] = defaultdict(set)
        self._entity_type: Dict[int, int] = {}
        self._entity_owner: Dict[int, int] = {}

    # ------------------------------------------------------------------ chunk

    def _chunk_of_world(self, x: float, y: float, z: float) -> ChunkKey:
        return (
            math.floor(float(x) / self._chunk_dim),
            math.floor(float(y) / self._chunk_dim),
            math.floor(float(z) / self._chunk_dim),
        )

    def _chunk_of_block_offset(self, block_offset: int) -> ChunkKey:
        blocks_per_chunk = self._chunk_dim ** 3
        chunk_linear = max(0, int(block_offset) // blocks_per_chunk)
        return (chunk_linear, 0, 0)

    # ---------------------------------------------------------------- legacy

    def locate(self, entity_id: int) -> Optional[int]:
        with self._lock:
            return self._entity_block.get(entity_id)

    def move(self, entity_id: int, block_offset: int):
        """Compatibility path for legacy block-offset callers."""
        with self._lock:
            old = self._entity_block.get(entity_id)
            if old is not None:
                bucket = self._by_block.get(old)
                if bucket is not None:
                    bucket.discard(entity_id)
                    if not bucket:
                        del self._by_block[old]

            self._entity_block[entity_id] = block_offset
            self._by_block[block_offset].add(entity_id)

            # Keep chunk membership coherent for callers still using move().
            old_chunk = self._entity_chunk.get(entity_id)
            new_chunk = self._chunk_of_block_offset(block_offset)
            if old_chunk != new_chunk:
                if old_chunk is not None:
                    cb = self._by_chunk.get(old_chunk)
                    if cb is not None:
                        cb.discard(entity_id)
                        if not cb:
                            del self._by_chunk[old_chunk]
                self._by_chunk[new_chunk].add(entity_id)
                self._entity_chunk[entity_id] = new_chunk

            return old, block_offset

    def entities_at(self, block_offset: int) -> FrozenSet[int]:
        with self._lock:
            return frozenset(self._by_block.get(block_offset, ()))

    # --------------------------------------------------------------- upsert

    def upsert_entity(
        self,
        entity_id: int,
        x: float,
        y: float,
        z: float,
        *,
        entity_type: Optional[int] = None,
        owner_id: Optional[int] = None,
    ) -> None:
        """Insert/update entity spatial membership and optional companion indices."""
        new_chunk = self._chunk_of_world(x, y, z)
        with self._lock:
            old_chunk = self._entity_chunk.get(entity_id)
            if old_chunk != new_chunk:
                if old_chunk is not None:
                    ob = self._by_chunk.get(old_chunk)
                    if ob is not None:
                        ob.discard(entity_id)
                        if not ob:
                            del self._by_chunk[old_chunk]
                self._by_chunk[new_chunk].add(entity_id)
                self._entity_chunk[entity_id] = new_chunk

            if entity_type is not None:
                old_type = self._entity_type.get(entity_id)
                if old_type != entity_type:
                    if old_type is not None:
                        tb = self._by_type.get(old_type)
                        if tb is not None:
                            tb.discard(entity_id)
                            if not tb:
                                del self._by_type[old_type]
                    self._by_type[entity_type].add(entity_id)
                    self._entity_type[entity_id] = entity_type

            if owner_id is not None:
                old_owner = self._entity_owner.get(entity_id)
                if old_owner != owner_id:
                    if old_owner is not None:
                        ob = self._by_owner.get(old_owner)
                        if ob is not None:
                            ob.discard(entity_id)
                            if not ob:
                                del self._by_owner[old_owner]
                    self._by_owner[owner_id].add(entity_id)
                    self._entity_owner[entity_id] = owner_id

    def remove_entity(self, entity_id: int) -> None:
        with self._lock:
            old_block = self._entity_block.pop(entity_id, None)
            if old_block is not None:
                bb = self._by_block.get(old_block)
                if bb is not None:
                    bb.discard(entity_id)
                    if not bb:
                        del self._by_block[old_block]

            old_chunk = self._entity_chunk.pop(entity_id, None)
            if old_chunk is not None:
                cb = self._by_chunk.get(old_chunk)
                if cb is not None:
                    cb.discard(entity_id)
                    if not cb:
                        del self._by_chunk[old_chunk]

            old_type = self._entity_type.pop(entity_id, None)
            if old_type is not None:
                tb = self._by_type.get(old_type)
                if tb is not None:
                    tb.discard(entity_id)
                    if not tb:
                        del self._by_type[old_type]

            old_owner = self._entity_owner.pop(entity_id, None)
            if old_owner is not None:
                ob = self._by_owner.get(old_owner)
                if ob is not None:
                    ob.discard(entity_id)
                    if not ob:
                        del self._by_owner[old_owner]

    # ---------------------------------------------------------------- query

    def query_radius_candidates(
        self,
        x: float,
        y: float,
        z: float,
        radius: float,
        *,
        entity_type: Optional[int] = None,
        owner_id: Optional[int] = None,
    ) -> Set[int]:
        """Return entity-id shortlist from intersecting chunk buckets."""
        center = self._chunk_of_world(x, y, z)
        span = int(math.ceil(max(0.0, float(radius)) / self._chunk_dim))

        with self._lock:
            candidates: Set[int] = set()
            cx, cy, cz = center
            for dx in range(-span, span + 1):
                for dy in range(-span, span + 1):
                    for dz in range(-span, span + 1):
                        candidates.update(self._by_chunk.get((cx + dx, cy + dy, cz + dz), ()))

            if entity_type is not None:
                candidates.intersection_update(self._by_type.get(entity_type, ()))
            if owner_id is not None:
                candidates.intersection_update(self._by_owner.get(owner_id, ()))

            return set(candidates)

    def entities_by_type(self, entity_type: int) -> FrozenSet[int]:
        with self._lock:
            return frozenset(self._by_type.get(entity_type, ()))

    def entities_by_owner(self, owner_id: int) -> FrozenSet[int]:
        with self._lock:
            return frozenset(self._by_owner.get(owner_id, ()))

    # --------------------------------------------------------------- admin

    def clear(self) -> None:
        with self._lock:
            self._by_block.clear()
            self._entity_block.clear()
            self._by_chunk.clear()
            self._entity_chunk.clear()
            self._by_type.clear()
            self._entity_type.clear()
            self._by_owner.clear()
            self._entity_owner.clear()
