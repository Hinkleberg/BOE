from block_engine.bridges.entity_sync import (
    EntityEvent,
    EntityEventType,
    EntityState,
    PlatformType,
    Transform,
    get_entity_sync_hub,
)


def test_entity_sync_version_conflict() -> None:
    hub = get_entity_sync_hub()
    hub._entities.clear()  # test isolation

    base_state = EntityState(
        entity_id=0,
        platform_id=PlatformType.UNREAL,
        platform_entity_name="Actor_001",
        transform=Transform(x=1, y=2, z=3),
    )
    entity_id = hub.register_entity(base_state)

    move_event = EntityEvent(
        event_type=EntityEventType.ENTITY_MOVED,
        entity_state=EntityState(
            entity_id=entity_id,
            platform_id=PlatformType.UNREAL,
            platform_entity_name="Actor_001",
            transform=Transform(x=2, y=2, z=3),
        ),
        source_platform=PlatformType.UNREAL,
        source_client_id="client-a",
    )

    first = hub.apply_entity_event(move_event, expected_version=1)
    assert first.accepted is True
    assert first.current_version == 2

    stale_event = EntityEvent(
        event_type=EntityEventType.ENTITY_MOVED,
        entity_state=EntityState(
            entity_id=entity_id,
            platform_id=PlatformType.UNITY,
            platform_entity_name="Cube_001",
            transform=Transform(x=5, y=2, z=3),
        ),
        source_platform=PlatformType.UNITY,
        source_client_id="client-b",
    )

    stale = hub.apply_entity_event(stale_event, expected_version=1)
    assert stale.accepted is False
    assert stale.reason == "version_conflict"


def test_entity_sync_lock_conflict() -> None:
    hub = get_entity_sync_hub()
    hub._entities.clear()  # test isolation

    state = EntityState(
        entity_id=0,
        platform_id=PlatformType.GODOT,
        platform_entity_name="Node3D",
        transform=Transform(),
    )
    entity_id = hub.register_entity(state)

    lock_event = EntityEvent(
        event_type=EntityEventType.ENTITY_LOCKED,
        entity_state=EntityState(
            entity_id=entity_id,
            platform_id=PlatformType.GODOT,
            platform_entity_name="Node3D",
            transform=Transform(),
        ),
        source_platform=PlatformType.GODOT,
        source_client_id="godot-user",
    )

    lock_result = hub.apply_entity_event(lock_event)
    assert lock_result.accepted is True
    assert lock_result.locked_by == "godot-user"

    conflicting_move = EntityEvent(
        event_type=EntityEventType.ENTITY_MOVED,
        entity_state=EntityState(
            entity_id=entity_id,
            platform_id=PlatformType.UNREAL,
            platform_entity_name="Actor_007",
            transform=Transform(x=9, y=0, z=0),
        ),
        source_platform=PlatformType.UNREAL,
        source_client_id="unreal-user",
    )

    conflict = hub.apply_entity_event(conflicting_move)
    assert conflict.accepted is False
    assert conflict.reason == "entity_locked"
