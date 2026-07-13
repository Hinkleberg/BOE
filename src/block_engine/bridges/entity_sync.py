"""
Unified Entity Synchronization Protocol for Cross-Adapter Real-Time Updates.

When ANY adapter modifies an entity (object in Unreal), that change propagates to:
- RenderFeed (central hub)
- ALL other connected adapters in real-time

Entity IDs are globally unique and consistent across all platforms.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Callable, Optional, Any
from enum import IntEnum


class EntityEventType(IntEnum):
    """Entity lifecycle and state change events."""
    ENTITY_CREATED = 0x01       # New object/entity spawned
    ENTITY_MOVED = 0x02          # Position changed
    ENTITY_ROTATED = 0x03        # Rotation changed
    ENTITY_SCALED = 0x04         # Scale changed
    ENTITY_MODIFIED = 0x05       # Properties changed
    ENTITY_DESTROYED = 0x06      # Object deleted
    ENTITY_ATTACHED = 0x07       # Parented to another
    ENTITY_DETACHED = 0x08       # Unparented
    ENTITY_VISIBLE = 0x09        # Visibility toggled
    ENTITY_LOCKED = 0x0A         # Locked for editing
    ENTITY_UNLOCKED = 0x0B       # Unlocked for editing


class PlatformType(IntEnum):
    """Adapter platform identifiers."""
    UNREAL = 0x01
    BLENDER = 0x02
    OMNIVERSE = 0x03
    ROBLOX = 0x04
    GODOT = 0x05
    GODOT4 = 0x06
    UNITY = 0x07
    O3DE = 0x08
    MILITARY = 0x09
    SCIENTIFIC = 0x0A
    AUTONOMOUS = 0x0B
    WEB = 0x0C
    STARLINK = 0x0D


@dataclass
class Transform:
    """3D transformation data (consistent across all platforms)."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    rx: float = 0.0  # Pitch (X rotation)
    ry: float = 0.0  # Yaw (Y rotation)
    rz: float = 0.0  # Roll (Z rotation)
    sx: float = 1.0  # Scale X
    sy: float = 1.0  # Scale Y
    sz: float = 1.0  # Scale Z


@dataclass
class EntityState:
    """Unified entity representation across all platforms."""
    entity_id: int                          # Global unique ID
    platform_id: int                        # Which adapter created it (PlatformType)
    platform_entity_name: str               # Platform-specific name (UE: "Actor_0", Blender: "Cube.001")
    entity_type: str = "default"            # "mesh", "light", "camera", "voxel", etc.
    transform: Transform = None
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)  # RGB
    visible: bool = True
    locked: bool = False
    parent_entity_id: Optional[int] = None  # For hierarchies
    metadata: Dict[str, Any] = None         # Platform-specific extras
    timestamp: float = 0.0                  # Last modification time
    version: int = 0                        # Monotonic version for conflict checks
    lock_owner: str = ""                   # Client currently holding edit lock
    lock_expires_at: float = 0.0            # UNIX timestamp when lock expires


@dataclass
class EntityEvent:
    """Entity change event propagated across all adapters."""
    event_type: int                    # EntityEventType
    entity_state: EntityState          # Current entity state
    changed_fields: List[str] = None   # Which fields changed: ["x", "y", "z"] etc
    source_platform: int = 0           # Which adapter triggered this
    source_client_id: str = ""         # Which client within the adapter
    timestamp: float = 0.0


@dataclass
class ConflictResult:
    """Outcome of applying an entity event with conflict checks."""
    accepted: bool
    reason: str = ""
    entity_id: int = 0
    current_version: int = 0
    locked_by: str = ""


class EntitySyncHub:
    """
    Central synchronization hub for entity changes.
    Receives updates from all adapters and broadcasts to all others.
    """
    
    def __init__(self):
        self._entities: Dict[int, EntityState] = {}
        self._next_entity_id = 1
        self._listeners: List[Callable[[EntityEvent], None]] = []
        self._adapter_subscriptions: Dict[str, set] = {}  # client_id → {entity_ids}
    
    def register_entity(self, state: EntityState) -> int:
        """Register new entity or update existing one. Returns entity_id."""
        if state.entity_id == 0:
            state.entity_id = self._generate_entity_id()
        if state.version <= 0:
            state.version = 1
        state.timestamp = time.time()
        self._entities[state.entity_id] = state
        return state.entity_id
    
    def _generate_entity_id(self) -> int:
        """Generate globally unique entity ID."""
        eid = self._next_entity_id
        self._next_entity_id += 1
        return eid
    
    def on_entity_event(self, event: EntityEvent) -> None:
        """
        Called when any adapter reports an entity change.
        Broadcasts to all other adapters.
        """
        self.apply_entity_event(event)

    def apply_entity_event(
        self,
        event: EntityEvent,
        *,
        expected_version: Optional[int] = None,
        lock_token: str = "",
        lock_timeout_s: float = 15.0,
    ) -> ConflictResult:
        """
        Apply entity change with optimistic concurrency + lock ownership checks.

        Rules:
        - If expected_version is set, reject stale updates.
        - If entity is locked by another client and lock has not expired, reject.
        - Successful updates increment entity version.
        """
        state = event.entity_state
        now = time.time()

        if state.entity_id == 0:
            state.entity_id = self._generate_entity_id()

        current = self._entities.get(state.entity_id)

        if current is not None:
            # Lock conflict check first; stale locks are ignored.
            if current.lock_owner and current.lock_expires_at > now:
                if lock_token and lock_token == current.lock_owner:
                    pass
                elif event.source_client_id and event.source_client_id == current.lock_owner:
                    pass
                elif event.event_type != EntityEventType.ENTITY_UNLOCKED:
                    return ConflictResult(
                        accepted=False,
                        reason="entity_locked",
                        entity_id=current.entity_id,
                        current_version=current.version,
                        locked_by=current.lock_owner,
                    )

            if expected_version is not None and expected_version != current.version:
                return ConflictResult(
                    accepted=False,
                    reason="version_conflict",
                    entity_id=current.entity_id,
                    current_version=current.version,
                    locked_by=current.lock_owner,
                )

        base_version = current.version if current is not None else 0
        state.version = max(base_version + 1, state.version or 0)
        state.timestamp = now

        # Handle lock/unlock lifecycle in the canonical state.
        if event.event_type == EntityEventType.ENTITY_LOCKED:
            owner = event.source_client_id or lock_token
            state.lock_owner = owner
            state.lock_expires_at = now + max(1.0, lock_timeout_s)
        elif event.event_type == EntityEventType.ENTITY_UNLOCKED:
            if current is not None and current.lock_owner:
                owner = event.source_client_id or lock_token
                if owner and owner != current.lock_owner and current.lock_expires_at > now:
                    return ConflictResult(
                        accepted=False,
                        reason="unlock_denied",
                        entity_id=current.entity_id,
                        current_version=current.version,
                        locked_by=current.lock_owner,
                    )
            state.lock_owner = ""
            state.lock_expires_at = 0.0
        elif current is not None:
            # Carry lock forward unless this event modifies lock lifecycle.
            if current.lock_expires_at > now:
                state.lock_owner = current.lock_owner
                state.lock_expires_at = current.lock_expires_at
            else:
                state.lock_owner = ""
                state.lock_expires_at = 0.0

        self._entities[state.entity_id] = state
        event.timestamp = now

        for listener in self._listeners:
            try:
                listener(event)
            except Exception as e:
                print(f"[EntitySyncHub] Listener error: {e}")

        return ConflictResult(
            accepted=True,
            entity_id=state.entity_id,
            current_version=state.version,
            locked_by=state.lock_owner,
        )
    
    def subscribe_to_entity(self, client_id: str, entity_id: int) -> None:
        """Register client interest in specific entity updates."""
        if client_id not in self._adapter_subscriptions:
            self._adapter_subscriptions[client_id] = set()
        self._adapter_subscriptions[client_id].add(entity_id)
    
    def unsubscribe_from_entity(self, client_id: str, entity_id: int) -> None:
        """Remove client interest in entity."""
        if client_id in self._adapter_subscriptions:
            self._adapter_subscriptions[client_id].discard(entity_id)
    
    def get_entity(self, entity_id: int) -> Optional[EntityState]:
        """Retrieve entity state by ID."""
        return self._entities.get(entity_id)
    
    def get_all_entities(self) -> List[EntityState]:
        """Get all registered entities (for new clients joining)."""
        return list(self._entities.values())
    
    def add_listener(self, callback: Callable[[EntityEvent], None]) -> None:
        """Register callback to receive all entity events."""
        self._listeners.append(callback)
    
    def remove_listener(self, callback: Callable[[EntityEvent], None]) -> None:
        """Unregister callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)
    
    def create_delta_for_subscribers(self, event: EntityEvent, subscriber_list: List[str]) -> Dict[str, Any]:
        """
        Create event payload for subscribers.
        Filter based on their subscriptions.
        """
        interested_subscribers = []
        for sub_id in subscriber_list:
            if sub_id in self._adapter_subscriptions:
                if event.entity_state.entity_id in self._adapter_subscriptions[sub_id]:
                    interested_subscribers.append(sub_id)
        
        return {
            "event_type": event.event_type,
            "entity_id": event.entity_state.entity_id,
            "entity_state": asdict(event.entity_state),
            "changed_fields": event.changed_fields or [],
            "source_platform": event.source_platform,
            "timestamp": event.timestamp,
            "subscribers": interested_subscribers,
        }
    
    def serialize_event(self, event: EntityEvent) -> str:
        """Serialize EntityEvent to JSON for network transmission."""
        return json.dumps({
            "event_type": event.event_type,
            "entity_id": event.entity_state.entity_id,
            "platform_id": event.entity_state.platform_id,
            "platform_entity_name": event.entity_state.platform_entity_name,
            "entity_type": event.entity_state.entity_type,
            "transform": asdict(event.entity_state.transform or Transform()),
            "color": event.entity_state.color,
            "visible": event.entity_state.visible,
            "locked": event.entity_state.locked,
            "version": event.entity_state.version,
            "lock_owner": event.entity_state.lock_owner,
            "lock_expires_at": event.entity_state.lock_expires_at,
            "parent_entity_id": event.entity_state.parent_entity_id,
            "metadata": event.entity_state.metadata or {},
            "changed_fields": event.changed_fields or [],
            "source_platform": event.source_platform,
            "source_client_id": event.source_client_id,
            "timestamp": event.timestamp,
        })
    
    @staticmethod
    def deserialize_event(data: str) -> EntityEvent:
        """Deserialize EntityEvent from JSON."""
        obj = json.loads(data)
        transform = Transform(**obj.get("transform", {}))
        state = EntityState(
            entity_id=obj["entity_id"],
            platform_id=obj["platform_id"],
            platform_entity_name=obj["platform_entity_name"],
            entity_type=obj.get("entity_type", "default"),
            transform=transform,
            color=tuple(obj.get("color", [1.0, 1.0, 1.0])),
            visible=obj.get("visible", True),
            locked=obj.get("locked", False),
            version=int(obj.get("version", 0)),
            lock_owner=obj.get("lock_owner", ""),
            lock_expires_at=float(obj.get("lock_expires_at", 0.0)),
            parent_entity_id=obj.get("parent_entity_id"),
            metadata=obj.get("metadata", {}),
        )
        return EntityEvent(
            event_type=obj["event_type"],
            entity_state=state,
            changed_fields=obj.get("changed_fields", []),
            source_platform=obj["source_platform"],
            source_client_id=obj["source_client_id"],
            timestamp=obj["timestamp"],
        )


# Global singleton instance
_entity_sync_hub = None

def get_entity_sync_hub() -> EntitySyncHub:
    """Get or create the global entity sync hub."""
    global _entity_sync_hub
    if _entity_sync_hub is None:
        _entity_sync_hub = EntitySyncHub()
    return _entity_sync_hub
