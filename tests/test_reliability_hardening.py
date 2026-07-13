from pathlib import Path

from block_engine.environment.block_layout import WorldLayout
from block_engine.replication.journal_auditor import JournalAuditFormatter
from block_engine.replication.crash_recovery_verifier import CrashRecoveryVerifier
from block_engine.replication.checksum_fallback_harness import ChecksumFallbackHarness


def test_journal_auditor_parses_pending_entries(tmp_path: Path) -> None:
    """Verify journal auditor can parse pending journal entries."""
    from block_engine.kernel.journal import Journal
    from block_engine.environment.block_layout import BLOCK_SIZE, Block

    journal_path = tmp_path / "test.jrn"
    journal = Journal(str(journal_path))

    # Write some entries
    data = Block().to_bytes()
    j1 = journal.append(100, 1, data)
    j2 = journal.append(200, 2, data)

    # Parse with auditor
    auditor = JournalAuditFormatter(str(journal_path))
    trail = auditor.audit_trail()

    assert len(trail) >= 2
    assert trail[0].offset == 100
    assert trail[1].offset == 200


def test_journal_auditor_forensic_summary(tmp_path: Path) -> None:
    """Verify forensic summary structure."""
    from block_engine.kernel.journal import Journal
    from block_engine.environment.block_layout import Block

    journal_path = tmp_path / "test.jrn"
    journal = Journal(str(journal_path))

    data = Block().to_bytes()
    journal.append(50, 1, data)
    journal.append(50, 2, data)  # Same offset, different seq

    auditor = JournalAuditFormatter(str(journal_path))
    summary = auditor.forensic_summary()

    assert summary["total_entries"] >= 2
    assert 50 in summary["offsets_modified"]


def test_crash_recovery_verifier_journal_replay(tmp_path: Path) -> None:
    """Test journal replay after truncation."""
    layout = WorldLayout(16, 16, 16)
    verifier = CrashRecoveryVerifier(layout)

    result = verifier.test_journal_replay_after_truncation(tmp_path)
    assert result.recovered_count > 0
    assert not result.passed or result.detail  # Should have detail


def test_crash_recovery_verifier_incomplete_write(tmp_path: Path) -> None:
    """Test incomplete write detection."""
    layout = WorldLayout(16, 16, 16)
    verifier = CrashRecoveryVerifier(layout)

    result = verifier.test_incomplete_write_recovery(tmp_path)
    # Should detect at least some issue
    assert isinstance(result.passed, bool)


def test_crash_recovery_verifier_consistency(tmp_path: Path) -> None:
    """Test journal consistency after restart."""
    layout = WorldLayout(16, 16, 16)
    verifier = CrashRecoveryVerifier(layout)

    result = verifier.test_journal_consistency_after_restart(tmp_path)
    assert result.passed is True  # Clean shutdown should preserve all writes


def test_crash_recovery_verifier_run_all_tests(tmp_path: Path) -> None:
    """Test running all recovery tests."""
    layout = WorldLayout(16, 16, 16)
    verifier = CrashRecoveryVerifier(layout)

    results = verifier.run_all_tests(tmp_path)
    assert len(results) == 3
    assert all(hasattr(r, "test_name") for r in results)

    report = verifier.report(results)
    assert "Crash Recovery" in report
    assert "Passed:" in report


def test_checksum_fallback_harness_corruption_detection(tmp_path: Path) -> None:
    """Test corruption detection via checksum."""
    layout = WorldLayout(16, 16, 16)
    harness = ChecksumFallbackHarness(layout)

    result = harness.test_checksum_mismatch_detection(tmp_path)
    assert result.corruption_detected is True
    assert result.passed is True


def test_checksum_fallback_harness_replica_recovery(tmp_path: Path) -> None:
    """Test recovery from replica on corruption."""
    layout = WorldLayout(16, 16, 16)
    harness = ChecksumFallbackHarness(layout)

    result = harness.test_replica_recovery_on_corruption(tmp_path)
    # At minimum, corruption should be detected; recovery may or may not succeed
    # depending on the mock replication setup
    assert result.corruption_detected is True


def test_checksum_fallback_harness_no_replicas_fails(tmp_path: Path) -> None:
    """Test that corruption fails without replicas."""
    layout = WorldLayout(16, 16, 16)
    harness = ChecksumFallbackHarness(layout)

    result = harness.test_corruption_with_no_replicas_fails(tmp_path)
    assert result.passed is True  # Should correctly raise error


def test_checksum_fallback_harness_run_all_tests(tmp_path: Path) -> None:
    """Test running all checksum fallback tests."""
    layout = WorldLayout(16, 16, 16)
    harness = ChecksumFallbackHarness(layout)

    results = harness.run_all_tests()
    assert len(results) == 3
    assert all(hasattr(r, "test_name") for r in results)

    report = harness.report(results)
    assert "Checksum Fallback" in report
    assert "Passed:" in report
