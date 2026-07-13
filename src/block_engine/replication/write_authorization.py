"""Write authorization layer — sits outside the engine.

Policy enforcement before writes hit ResilientStore. The engine itself
remains policy-agnostic; this layer is pluggable and replaceable.

Example policies:
  - Offset range validation (don't write outside declared bounds)
  - Block type constraints (AIR blocks can't be written to protected regions)
  - Quorum requirements (only proceed if replication quorum is reachable)
  - Rate limiting (reject writes that exceed throughput thresholds)
  - Audit trail (log all writes with caller ID and timestamp)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional


class WriteAuthStatus(Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    RATE_LIMITED = "rate_limited"


@dataclass
class WriteAuthResult:
    status: WriteAuthStatus
    reason: str
    timestamp: float


AuthorizationCallback = Callable[[int, bytes], WriteAuthResult]


class WriteAuthorizationLayer:
    """
    Validate writes before they hit ResilientStore.

    Policies can be stacked: if any policy denies, the write is rejected.
    The engine is never touched; policy is entirely external.
    """

    def __init__(self) -> None:
        self._policies: List[AuthorizationCallback] = []
        self._last_write_time = 0.0
        self._write_count = 0
        self._denied_count = 0

    def add_policy(self, policy: AuthorizationCallback) -> None:
        """Add a policy validator."""
        self._policies.append(policy)

    def authorize_write(self, offset: int, data: bytes) -> WriteAuthResult:
        """
        Check all policies. If any deny, return DENIED.
        Otherwise return ALLOWED.
        """
        for policy in self._policies:
            result = policy(offset, data)
            if result.status != WriteAuthStatus.ALLOWED:
                self._denied_count += 1
                return result

        self._write_count += 1
        self._last_write_time = time.time()
        return WriteAuthResult(
            status=WriteAuthStatus.ALLOWED,
            reason="all policies passed",
            timestamp=time.time(),
        )

    def snapshot(self) -> Dict[str, object]:
        return {
            "policy_count": len(self._policies),
            "writes_authorized": self._write_count,
            "writes_denied": self._denied_count,
            "last_write_time": self._last_write_time,
        }

    def statistics(self) -> str:
        snap = self.snapshot()
        return (
            f"WriteAuthorizationLayer: "
            f"authorized={snap['writes_authorized']} "
            f"denied={snap['writes_denied']} "
            f"policies={snap['policy_count']}"
        )


class OffsetRangePolicy:
    """Reject writes outside the declared world bounds."""

    def __init__(self, world_layout):
        self._layout = world_layout

    def __call__(self, offset: int, data: bytes) -> WriteAuthResult:
        if offset < 0 or offset >= self._layout.image_size:
            return WriteAuthResult(
                status=WriteAuthStatus.DENIED,
                reason=f"offset {offset} out of bounds [0, {self._layout.image_size})",
                timestamp=time.time(),
            )
        return WriteAuthResult(
            status=WriteAuthStatus.ALLOWED,
            reason="offset in valid range",
            timestamp=time.time(),
        )


class RateLimitPolicy:
    """Reject writes that exceed a throughput threshold."""

    def __init__(self, max_writes_per_second: int = 1000):
        self._max = max_writes_per_second
        self._window_start = time.time()
        self._window_count = 0
        self._lock = __import__("threading").Lock()

    def __call__(self, offset: int, data: bytes) -> WriteAuthResult:
        now = time.time()
        with self._lock:
            if now - self._window_start >= 1.0:
                self._window_start = now
                self._window_count = 0

            if self._window_count >= self._max:
                return WriteAuthResult(
                    status=WriteAuthStatus.RATE_LIMITED,
                    reason=f"exceeded {self._max} writes/sec",
                    timestamp=now,
                )

            self._window_count += 1
        return WriteAuthResult(
            status=WriteAuthStatus.ALLOWED,
            reason="within rate limit",
            timestamp=now,
        )


class AuditPolicy:
    """Log all writes (authorized and denied) for compliance."""

    def __init__(self, observer_callback: Optional[Callable] = None):
        self._observer = observer_callback
        self._log: List[Dict] = []
        self._lock = __import__("threading").Lock()

    def __call__(self, offset: int, data: bytes) -> WriteAuthResult:
        now = time.time()
        event = {
            "offset": offset,
            "size": len(data),
            "timestamp": now,
        }
        with self._lock:
            self._log.append(event)
        if self._observer:
            try:
                self._observer(event)
            except Exception:
                pass
        return WriteAuthResult(
            status=WriteAuthStatus.ALLOWED,
            reason="audit logged",
            timestamp=now,
        )

    def audit_log(self) -> List[Dict]:
        with self._lock:
            return list(self._log)
