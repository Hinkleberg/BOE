from pathlib import Path

from block_engine.authority.flat_store import FlatStore
from block_engine.authority.resilient_store import ResilientStore
from block_engine.environment.block_layout import Block, BlockType, WorldLayout
from block_engine.replication.integrity_validator import (
    IntegrityValidator,
    CorruptionSeverity,
)
from block_engine.replication.write_authorization import (
    WriteAuthorizationLayer,
    OffsetRangePolicy,
    RateLimitPolicy,
    AuditPolicy,
    WriteAuthStatus,
)
from block_engine.replication.replication_verifier import ReplicationVerifier


def test_integrity_validator_detects_no_corruption_on_clean_store(
    tmp_path: Path,
) -> None:
    """Verify that a clean FlatStore passes integrity check."""
    layout = WorldLayout(16, 16, 16)
    image_path = tmp_path / "world.img"

    store = FlatStore(str(image_path), layout)
    data = Block(block_type=BlockType.STONE, light_level=7).to_bytes()
    offset = layout.block_offset(1, 2, 3)
    store.write_block(offset, data)

    corruptions = []

    def corruption_observer(event):
        corruptions.append(event)

    validator = IntegrityValidator(store, scan_interval_s=0.1, observer=corruption_observer)
    validator._run_scan()

    assert len(corruptions) == 0, "Clean store should have no corruptions"
    snap = validator.snapshot()
    assert snap["corruption_count"] == 0


def test_write_authorization_layer_enforces_offset_bounds(
    tmp_path: Path,
) -> None:
    """Verify that offset range policy rejects out-of-bounds writes."""
    layout = WorldLayout(16, 16, 16)
    auth = WriteAuthorizationLayer()
    auth.add_policy(OffsetRangePolicy(layout))

    data = Block(block_type=BlockType.STONE).to_bytes()

    # Valid offset
    result = auth.authorize_write(0, data)
    assert result.status == WriteAuthStatus.ALLOWED

    # Out of bounds
    result = auth.authorize_write(layout.image_size + 1, data)
    assert result.status == WriteAuthStatus.DENIED
    assert "out of bounds" in result.reason


def test_write_authorization_rate_limit_policy(tmp_path: Path) -> None:
    """Verify rate limiting policy works."""
    auth = WriteAuthorizationLayer()
    auth.add_policy(RateLimitPolicy(max_writes_per_second=3))

    data = Block(block_type=BlockType.STONE).to_bytes()

    # First 3 should pass
    for _ in range(3):
        result = auth.authorize_write(0, data)
        assert result.status == WriteAuthStatus.ALLOWED

    # 4th should be rate limited
    result = auth.authorize_write(0, data)
    assert result.status == WriteAuthStatus.RATE_LIMITED


def test_write_authorization_audit_policy(tmp_path: Path) -> None:
    """Verify audit policy logs all writes."""
    audit_events = []

    def audit_observer(event):
        audit_events.append(event)

    auth = WriteAuthorizationLayer()
    audit = AuditPolicy(observer_callback=audit_observer)
    auth.add_policy(audit)

    data = Block(block_type=BlockType.STONE).to_bytes()

    auth.authorize_write(100, data)
    auth.authorize_write(200, data)

    assert len(audit_events) == 2
    assert audit_events[0]["offset"] == 100
    assert audit_events[1]["offset"] == 200

    log = audit.audit_log()
    assert len(log) == 2


def test_write_authorization_stacked_policies(tmp_path: Path) -> None:
    """Verify multiple policies can be stacked."""
    layout = WorldLayout(16, 16, 16)
    auth = WriteAuthorizationLayer()
    auth.add_policy(OffsetRangePolicy(layout))
    auth.add_policy(RateLimitPolicy(max_writes_per_second=10))

    data = Block(block_type=BlockType.STONE).to_bytes()

    # Valid offset, within rate limit
    result = auth.authorize_write(100, data)
    assert result.status == WriteAuthStatus.ALLOWED

    # Invalid offset (fails first policy)
    result = auth.authorize_write(layout.image_size + 1, data)
    assert result.status == WriteAuthStatus.DENIED


def test_replication_verifier_tracks_verification_queue(tmp_path: Path) -> None:
    """Verify replication verifier can queue and track verifications."""

    def dummy_reader(node_id, offset):
        return Block(block_type=BlockType.STONE).to_bytes()

    # Mock replication manager
    class MockRM:
        def nodes_with_block(self, offset):
            return {"node-a", "node-b"}

    rm = MockRM()
    verifications = []

    def verification_observer(result):
        verifications.append(result)

    verifier = ReplicationVerifier(rm, dummy_reader, observer=verification_observer)
    verifier.start()

    data = Block(block_type=BlockType.STONE).to_bytes()
    verifier.enqueue_verification(offset=100, seq=1, data=data)

    import time

    time.sleep(0.3)
    verifier.stop()

    assert len(verifications) >= 1
    v = verifications[0]
    assert v.offset == 100
    assert "node-a" in v.verified_on or "node-b" in v.verified_on
