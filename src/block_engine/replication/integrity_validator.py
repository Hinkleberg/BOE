"""Background integrity scanner for the FlatStore.

Runs in a daemon thread and periodically scans blocks for corruption without
touching the hot write path. Corruption is reported to an observer callback,
which can forward to metrics, logs, or an alert system.

This validator is completely outside the engine — it only reads from FlatStore
and never modifies state. The engine remains unchanged.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional


class CorruptionSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class IntegrityEvent:
    offset: int
    status: str  # "ok" | "corrupted" | "error"
    severity: CorruptionSeverity
    detail: str
    timestamp: float


ObserverCallback = Callable[[IntegrityEvent], None]


class IntegrityValidator:
    """
    Scans FlatStore for corruption in the background.

    Does not modify any state. Only reads via FlatStore.verify_integrity().
    Corruption events are emitted to an observer callback, which can:
      - Update metrics
      - Write to audit log
      - Trigger alerts
      - Do nothing (observer=None means no-op)
    """

    def __init__(
        self,
        flat_store,
        *,
        scan_interval_s: float = 60.0,
        observer: Optional[ObserverCallback] = None,
    ):
        self._store = flat_store
        self._interval = scan_interval_s
        self._observer = observer
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._scan_count = 0
        self._corruption_count = 0
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the background integrity scanner."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._scan_loop,
            daemon=True,
            name="integrity-validator",
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the background scanner."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=self._interval * 2)

    def _scan_loop(self) -> None:
        while self._running:
            self._run_scan()
            time.sleep(self._interval)

    def _run_scan(self) -> None:
        """Scan all blocks via FlatStore.verify_integrity()."""
        with self._lock:
            self._scan_count += 1
        
        ok_count = 0
        for result in self._store.verify_integrity():
            if result.status == "ok":
                ok_count += 1
            elif result.status == "corrupted":
                with self._lock:
                    self._corruption_count += 1
                self._emit_event(
                    IntegrityEvent(
                        offset=result.offset,
                        status="corrupted",
                        severity=CorruptionSeverity.CRITICAL,
                        detail=result.detail,
                        timestamp=time.time(),
                    )
                )
            else:
                self._emit_event(
                    IntegrityEvent(
                        offset=result.offset,
                        status="error",
                        severity=CorruptionSeverity.WARNING,
                        detail=result.detail,
                        timestamp=time.time(),
                    )
                )

    def _emit_event(self, event: IntegrityEvent) -> None:
        if self._observer is None:
            return
        try:
            self._observer(event)
        except Exception:
            pass

    def snapshot(self) -> Dict[str, object]:
        """Return scanner health snapshot."""
        with self._lock:
            return {
                "running": self._running,
                "scan_count": self._scan_count,
                "corruption_count": self._corruption_count,
                "interval_s": self._interval,
            }

    def status(self) -> str:
        snap = self.snapshot()
        return (
            f"IntegrityValidator: "
            f"scans={snap['scan_count']} "
            f"corruptions={snap['corruption_count']} "
            f"running={snap['running']}"
        )
