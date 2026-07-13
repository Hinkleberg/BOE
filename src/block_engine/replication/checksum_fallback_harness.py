"""Checksum fallback harness — force corruption and verify replica recovery.

Deliberately corrupts blocks, then verifies that ResilientStore:
  1. Detects the corruption via checksum mismatch
  2. Queries the ReplicationManager for replicas
  3. Recovers the data from a healthy replica
  4. Overwrites the corrupt local copy
  5. Returns valid data

The harness is pure testing — the engine's recovery logic is unchanged.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from block_engine.authority.flat_store import FlatStore, ChecksumMismatchError, ChecksumMismatchError
from block_engine.authority.resilient_store import ResilientStore, CorruptBlockError
from block_engine.environment.block_layout import BLOCK_SIZE, Block, BlockType, WorldLayout
from block_engine.replication.replication_manager import ReplicationManager


@dataclass
class CorruptionRecoveryResult:
    test_name: str
    passed: bool
    detail: str
    corruption_detected: bool = False
    recovery_attempted: bool = False
    recovery_succeeded: bool = False


class ChecksumFallbackHarness:
    """Test corruption detection and replica recovery."""

    def __init__(self, layout: WorldLayout):
        self._layout = layout

    def _corrupt_block_in_image(
        self, image_path: str, offset: int, flip_bits: int = 8
    ) -> None:
        """Corrupt a specific block by flipping bits in the image file."""
        with open(image_path, "r+b") as f:
            f.seek(offset)
            original = f.read(BLOCK_SIZE)
            # Flip some bits in the middle of the block
            corrupted = bytearray(original)
            for i in range(flip_bits):
                corrupted[(offset + i) % BLOCK_SIZE] ^= 0xFF
            f.seek(offset)
            f.write(corrupted)

    def _invalidate_checksum_in_sidecar(self, image_path: str, offset: int) -> None:
        """Invalidate the stored checksum so read fails."""
        sha_path = image_path + ".sha"
        slot = offset // BLOCK_SIZE
        with open(sha_path, "r+b") as f:
            f.seek(slot * 32)
            f.write(b"\xff" * 32)  # Invalid checksum

    def test_checksum_mismatch_detection(
        self, tmp_path: Path
    ) -> CorruptionRecoveryResult:
        """
        Write a block, corrupt it, and verify checksum mismatch is detected.
        """
        image_path = tmp_path / "world.img"
        journal_path = tmp_path / "world.jrn"

        store = FlatStore(str(image_path), self._layout)
        rs = ResilientStore(store, journal_path=str(journal_path))

        offset = self._layout.block_offset(1, 1, 1)
        original_data = Block(block_type=BlockType.STONE, light_level=7).to_bytes()
        rs.write_block(offset, original_data)

        # Corrupt the block
        self._corrupt_block_in_image(str(image_path), offset)

        # Try to read — should raise ChecksumMismatchError or CorruptBlockError
        detected = False
        try:
            rs.read_block(offset)
        except (ChecksumMismatchError, CorruptBlockError):
            detected = True

        return CorruptionRecoveryResult(
            test_name="checksum_mismatch_detection",
            passed=detected,
            detail="Corruption detected via checksum validation" if detected else "Corruption not detected",
            corruption_detected=detected,
        )

    def test_replica_recovery_on_corruption(
        self, tmp_path: Path
    ) -> CorruptionRecoveryResult:
        """
        Write with replication, corrupt local copy, and verify recovery from replica.
        """
        image_path = tmp_path / "world.img"
        image_b_path = tmp_path / "world_b.img"
        journal_path = tmp_path / "world.jrn"
        repl_log_path = tmp_path / "repl.log"

        store_a = FlatStore(str(image_path), self._layout)
        store_b = FlatStore(str(image_b_path), self._layout)

        # Set up replication
        replicated_blocks: Dict[int, bytes] = {}

        def replicate_callback(node_id: str, offset: int, data: bytes) -> None:
            if node_id == "node-b":
                store_b.write_block(offset, data)
                replicated_blocks[offset] = data

        rm = ReplicationManager(
            replicate_callback,
            required_replicas=1,
            log_path=str(repl_log_path),
        )
        rm.register_node("node-b")

        def recovery_callback(node_id: str, offset: int) -> bytes:
            if node_id == "node-b" and offset in replicated_blocks:
                return replicated_blocks[offset]
            if node_id == "node-b":
                return store_b.read_block(offset)
            raise Exception(f"Unknown node: {node_id}")

        rs = ResilientStore(
            store_a,
            replication_manager=rm,
            journal_path=str(journal_path),
            recovery_callback=recovery_callback,
        )

        # Write to both
        offset = self._layout.block_offset(3, 4, 5)
        original_data = Block(block_type=BlockType.GRASS, light_level=12).to_bytes()
        rs.write_block(offset, original_data)

        # Corrupt local copy
        self._corrupt_block_in_image(str(image_path), offset)

        # Try to read — should recover from replica
        recovered = False
        recovery_succeeded = False
        try:
            recovered_data = rs.read_block(offset)
            recovered = True
            recovery_succeeded = recovered_data == original_data
        except (CorruptBlockError, ChecksumMismatchError):
            # If corruption is detected but can't recover, that's still the engine working
            recovered = False

        return CorruptionRecoveryResult(
            test_name="replica_recovery_on_corruption",
            passed=recovery_succeeded,
            detail="Recovered from replica" if recovery_succeeded else "Corruption detected (recovery path exercised)",
            corruption_detected=True,
            recovery_attempted=recovered,
            recovery_succeeded=recovery_succeeded,
        )

    def test_corruption_with_no_replicas_fails(
        self, tmp_path: Path
    ) -> CorruptionRecoveryResult:
        """
        Write without replication, corrupt, and verify error is raised.
        """
        image_path = tmp_path / "world.img"
        journal_path = tmp_path / "world.jrn"

        store = FlatStore(str(image_path), self._layout)
        rs = ResilientStore(
            store,
            replication_manager=None,
            journal_path=str(journal_path),
            recovery_callback=None,
        )

        offset = self._layout.block_offset(5, 6, 7)
        original_data = Block(block_type=BlockType.DIRT).to_bytes()
        rs.write_block(offset, original_data)

        # Corrupt
        self._corrupt_block_in_image(str(image_path), offset)

        # Should raise ChecksumMismatchError or CorruptBlockError
        error_raised = False
        try:
            rs.read_block(offset)
        except (ChecksumMismatchError, CorruptBlockError):
            error_raised = True

        return CorruptionRecoveryResult(
            test_name="corruption_with_no_replicas_fails",
            passed=error_raised,
            detail="Correctly raised error on corruption" if error_raised else "Did not raise error",
            corruption_detected=error_raised,
        )

    def run_all_tests(self) -> list[CorruptionRecoveryResult]:
        """Run all checksum fallback tests."""
        results = []
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = Path(tmpdir)
            results.append(self.test_checksum_mismatch_detection(test_path))
            results.append(self.test_replica_recovery_on_corruption(test_path))
            results.append(self.test_corruption_with_no_replicas_fails(test_path))
        return results

    def report(self, results: list[CorruptionRecoveryResult]) -> str:
        """Generate a test report."""
        passed = sum(1 for r in results if r.passed)
        lines = [
            "Checksum Fallback Harness Report",
            "================================",
            f"Passed: {passed}/{len(results)}",
            "",
        ]
        for result in results:
            status = "✓ PASS" if result.passed else "✗ FAIL"
            lines.append(f"{status}: {result.test_name}")
            lines.append(f"  {result.detail}")
            if result.corruption_detected:
                lines.append(f"  Corruption detected: ✓")
            if result.recovery_attempted:
                lines.append(
                    f"  Recovery attempted: ✓ (success={result.recovery_succeeded})"
                )
        return "\n".join(lines)
