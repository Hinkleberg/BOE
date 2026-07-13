"""Crash recovery verification harness — test journal replay under fault conditions.

Injects failures (incomplete writes, truncated journal) and verifies that
ResilientStore can replay the journal and recover state correctly.

The engine doesn't know about this harness — it's pure test tooling that
exercises the crash-safety guarantees.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from block_engine.authority.flat_store import FlatStore
from block_engine.authority.resilient_store import ResilientStore
from block_engine.environment.block_layout import BLOCK_SIZE, Block, BlockType, WorldLayout
from block_engine.kernel.journal import Journal


@dataclass
class RecoveryTestResult:
    test_name: str
    passed: bool
    detail: str
    recovered_count: int = 0


class CrashRecoveryVerifier:
    """Inject faults and verify recovery works."""

    def __init__(self, layout: WorldLayout):
        self._layout = layout

    def test_journal_replay_after_truncation(
        self, tmp_path: Path
    ) -> RecoveryTestResult:
        """
        Write several blocks, truncate journal mid-write,
        then verify replay recovers correctly.
        """
        image_path = tmp_path / "world.img"
        journal_path = tmp_path / "world.jrn"

        # Phase 1: Write blocks normally
        store = FlatStore(str(image_path), self._layout)
        rs = ResilientStore(store, journal_path=str(journal_path))

        offsets = []
        for i in range(5):
            data = Block(block_type=BlockType.STONE, light_level=i).to_bytes()
            offset = self._layout.block_offset(i, i, i)
            rs.write_block(offset, data)
            offsets.append(offset)

        initial_seq = store.write_seq

        # Phase 2: Corrupt the journal by truncating it
        journal_size = os.path.getsize(str(journal_path))
        with open(str(journal_path), "r+b") as f:
            f.truncate(journal_size // 2)

        # Phase 3: Create a new store/resilient pair and replay
        store2 = FlatStore(str(image_path), self._layout)
        rs2 = ResilientStore(store2, journal_path=str(journal_path))

        # Verify we recovered what we could
        recovered_count = 0
        for offset in offsets:
            try:
                data = rs2.read_block(offset)
                if data[0] != 0:  # Not an empty block
                    recovered_count += 1
            except Exception:
                pass

        return RecoveryTestResult(
            test_name="journal_replay_after_truncation",
            passed=recovered_count >= 3,  # At least some should survive truncation
            detail=f"Recovered {recovered_count}/{len(offsets)} blocks after truncation",
            recovered_count=recovered_count,
        )

    def test_incomplete_write_recovery(self, tmp_path: Path) -> RecoveryTestResult:
        """
        Write a block, simulate incomplete write (journal exists, data incomplete),
        then verify recovery skips corrupted entries or recovers from replicas.
        """
        image_path = tmp_path / "world.img"
        journal_path = tmp_path / "world.jrn"

        store = FlatStore(str(image_path), self._layout)
        rs = ResilientStore(store, journal_path=str(journal_path))

        offset = self._layout.block_offset(2, 3, 4)
        data = Block(block_type=BlockType.GRASS, light_level=10).to_bytes()
        rs.write_block(offset, data)

        # Truncate the image file (simulate incomplete write)
        with open(str(image_path), "r+b") as f:
            current_size = f.seek(0, 2)
            f.truncate(max(0, current_size - BLOCK_SIZE * 2))

        # Replay should detect the corruption
        store2 = FlatStore(str(image_path), self._layout)
        rs2 = ResilientStore(store2, journal_path=str(journal_path))

        # Check what was in pending_replay
        pending = rs2.pending_replay
        was_detected = len(pending) > 0

        return RecoveryTestResult(
            test_name="incomplete_write_recovery",
            passed=was_detected,
            detail=f"Detected {len(pending)} incomplete writes",
            recovered_count=len(pending),
        )

    def test_journal_consistency_after_restart(
        self, tmp_path: Path
    ) -> RecoveryTestResult:
        """
        Write blocks, close cleanly, reopen, and verify all writes persisted.
        """
        image_path = tmp_path / "world.img"
        journal_path = tmp_path / "world.jrn"

        # First session
        store = FlatStore(str(image_path), self._layout)
        rs = ResilientStore(store, journal_path=str(journal_path))

        written = {}
        for i in range(3):
            offset = self._layout.block_offset(i, i, i)
            block_type = BlockType.STONE if i % 2 == 0 else BlockType.GRASS
            data = Block(block_type=block_type, light_level=i + 5).to_bytes()
            rs.write_block(offset, data)
            written[offset] = data

        seq1 = store.write_seq

        # Second session (simulating restart)
        store2 = FlatStore(str(image_path), self._layout)
        rs2 = ResilientStore(store2, journal_path=str(journal_path))
        seq2 = store2.write_seq

        # Verify seq advanced
        matches = 0
        for offset, expected_data in written.items():
            try:
                actual_data = rs2.read_block(offset)
                if actual_data == expected_data:
                    matches += 1
            except Exception:
                pass

        return RecoveryTestResult(
            test_name="journal_consistency_after_restart",
            passed=matches == len(written) and seq2 == seq1,
            detail=f"Persisted {matches}/{len(written)} blocks, seq before={seq1} after={seq2}",
            recovered_count=matches,
        )

    def run_all_tests(self, tmp_path: Optional[Path] = None) -> list[RecoveryTestResult]:
        """Run all recovery tests and return results."""
        if tmp_path is None:
            tmp_path = Path(tempfile.mkdtemp())

        results = []
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = Path(tmpdir)
            results.append(self.test_journal_replay_after_truncation(test_path))
            results.append(self.test_incomplete_write_recovery(test_path))
            results.append(self.test_journal_consistency_after_restart(test_path))

        return results

    def report(self, results: list[RecoveryTestResult]) -> str:
        """Generate a test report."""
        passed = sum(1 for r in results if r.passed)
        lines = [
            "Crash Recovery Verification Report",
            "===================================",
            f"Passed: {passed}/{len(results)}",
            "",
        ]
        for result in results:
            status = "✓ PASS" if result.passed else "✗ FAIL"
            lines.append(f"{status}: {result.test_name}")
            lines.append(f"  {result.detail}")
        return "\n".join(lines)
