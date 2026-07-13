"""Replication verification — confirms Array B mirrors got the data.

After ResilientStore replicates to Array B via the ReplicationManager,
this verifier spot-checks that mirrors actually have the blocks with
matching checksums. Runs asynchronously and never blocks the write path.

The engine doesn't know about this layer — it's pure observation.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


@dataclass
class ReplicationVerification:
    offset: int
    seq: int
    replicated_to: List[str]
    verified_on: List[str]  # Which nodes we confirmed have it
    mismatches: List[str]   # Nodes that have data but wrong checksum
    missing: List[str]      # Nodes we expected but didn't reach
    timestamp: float


VerificationCallback = Callable[[ReplicationVerification], None]


class ReplicationVerifier:
    """
    After replication, spot-check that Array B actually has the blocks.

    Calls a reader callback to fetch the block from each mirror and
    compare checksums. Never modifies state. Runs asynchronously so
    writes are never blocked.
    """

    def __init__(
        self,
        replication_manager,
        reader_callback: Callable[[str, int], bytes],
        *,
        observer: Optional[VerificationCallback] = None,
    ):
        self._rm = replication_manager
        self._reader = reader_callback
        self._observer = observer
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._queue: List[tuple[int, int, bytes]] = []
        self._lock = threading.Lock()

    def enqueue_verification(self, offset: int, seq: int, data: bytes) -> None:
        """
        Queue a block for replication verification.
        This is called after ResilientStore.write_block() succeeds.
        """
        with self._lock:
            self._queue.append((offset, seq, data))

    def start(self) -> None:
        """Start the async verification worker."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._verify_loop,
            daemon=True,
            name="replication-verifier",
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the verification worker."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    def _verify_loop(self) -> None:
        while self._running:
            with self._lock:
                if not self._queue:
                    queue = []
                else:
                    queue = self._queue[:]
                    self._queue.clear()

            for offset, seq, data in queue:
                self._verify_one(offset, seq, data)

            time.sleep(0.1)

    def _verify_one(self, offset: int, seq: int, data: bytes) -> None:
        """Verify one replicated block across mirrors."""
        replicated_to = list(self._rm.nodes_with_block(offset))
        verified_on = []
        mismatches = []
        missing = []

        import hashlib
        expected_checksum = hashlib.sha256(data).digest()

        for node_id in replicated_to:
            try:
                remote_data = self._reader(node_id, offset)
                remote_checksum = hashlib.sha256(remote_data).digest()
                if remote_checksum == expected_checksum:
                    verified_on.append(node_id)
                else:
                    mismatches.append(node_id)
            except Exception:
                missing.append(node_id)

        result = ReplicationVerification(
            offset=offset,
            seq=seq,
            replicated_to=replicated_to,
            verified_on=verified_on,
            mismatches=mismatches,
            missing=missing,
            timestamp=time.time(),
        )

        if self._observer:
            try:
                self._observer(result)
            except Exception:
                pass

    def pending_count(self) -> int:
        with self._lock:
            return len(self._queue)

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return {
                "running": self._running,
                "pending_verifications": len(self._queue),
            }
