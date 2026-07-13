import tempfile

from block_layout import WorldLayout
from entity_sidecar import EntityRecord, EntitySidecar, EntityType
from movement_transaction import MoveIntent, MovementTransaction
from spatial_index import SpatialIndex


def test_entities_near_uses_grid_shortlist() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sidecar_path = f"{tmpdir}/entities.ent"

        index = SpatialIndex(chunk_dim=16)
        sidecar = EntitySidecar(sidecar_path, max_entities=2048, spatial_index=index)

        # Two nearby entities and one far away in a different chunk region.
        sidecar.write_entity(EntityRecord(entity_id=1, entity_type=EntityType.PLAYER, x=20.0, y=20.0, z=20.0))
        sidecar.write_entity(EntityRecord(entity_id=2, entity_type=EntityType.MOB, x=23.0, y=20.0, z=21.0))
        sidecar.write_entity(EntityRecord(entity_id=3, entity_type=EntityType.ITEM, x=180.0, y=180.0, z=180.0))

        nearby = sidecar.entities_near(20.0, 20.0, 20.0, radius=8.0)
        nearby_ids = {rec.entity_id for rec in nearby}

        assert 1 in nearby_ids
        assert 2 in nearby_ids
        assert 3 not in nearby_ids


def test_type_and_owner_indices() -> None:
    index = SpatialIndex(chunk_dim=16)

    index.upsert_entity(11, 0.0, 0.0, 0.0, entity_type=1, owner_id=7)
    index.upsert_entity(12, 1.0, 0.0, 0.0, entity_type=1, owner_id=8)
    index.upsert_entity(13, 2.0, 0.0, 0.0, entity_type=2, owner_id=7)

    assert index.entities_by_type(1) == frozenset({11, 12})
    assert index.entities_by_owner(7) == frozenset({11, 13})


def test_movement_transaction_updates_spatial_membership() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sidecar_path = f"{tmpdir}/entities.ent"

        layout = WorldLayout(64, 64, 64)
        index = SpatialIndex(chunk_dim=16)
        sidecar = EntitySidecar(sidecar_path, max_entities=512, spatial_index=index)

        sidecar.write_entity(
            EntityRecord(
                entity_id=42,
                entity_type=EntityType.PLAYER,
                owner_id=99,
                x=2.0,
                y=2.0,
                z=2.0,
            )
        )

        tx = MovementTransaction(layout, sidecar, index)
        target = tx.commit(MoveIntent(entity_id=42, x=33.0, y=2.0, z=2.0, tick=5))

        # Entity should now be shortlisted in the new area, and retain companion index membership.
        candidates = index.query_radius_candidates(33.0, 2.0, 2.0, radius=1.0)
        assert 42 in candidates
        assert 42 in index.entities_by_type(EntityType.PLAYER)
        assert 42 in index.entities_by_owner(99)

        # Ensure transaction still returns an addressable offset.
        assert isinstance(target, int)
        assert target >= 0
