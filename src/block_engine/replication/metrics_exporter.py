"""Lightweight write-path metrics collector for the replication bus.

The collector is intentionally side-effect free: it records timing and counts
from the write path without changing engine semantics. It can be used by a
small HTTP endpoint or by tests that need a Prometheus-style snapshot.
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Callable, Dict, List, Optional


class WritePathMetricsCollector:
    """Collect stage-level timings for the write path."""

    def __init__(self) -> None:
        self._lock = __import__("threading").Lock()
        self._writes_total = 0
        self._stage_counts: Counter[str] = Counter()
        self._stage_latency_ms: Dict[str, List[float]] = {}

    def observe(self, event: Dict[str, object]) -> None:
        stage = str(event.get("stage", "unknown"))
        duration_ms = float(event.get("duration_ms", 0.0))
        with self._lock:
            self._writes_total += 1
            self._stage_counts[stage] += 1
            self._stage_latency_ms.setdefault(stage, []).append(duration_ms)

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            summary = {
                "writes_total": self._writes_total,
                "stage_counts": dict(self._stage_counts),
                "stage_latency_ms": {
                    name: list(values)
                    for name, values in self._stage_latency_ms.items()
                },
            }
        return summary

    def prometheus_text(self) -> str:
        snapshot = self.snapshot()
        lines = [
            "# HELP block_engine_write_events_total Total write-path events observed",
            "# TYPE block_engine_write_events_total counter",
            f"block_engine_write_events_total {snapshot['writes_total']}",
            "# HELP block_engine_write_latency_ms Write-path stage latency in milliseconds",
            "# TYPE block_engine_write_latency_ms histogram",
        ]
        for stage, values in sorted(snapshot["stage_latency_ms"].items()):
            if not values:
                continue
            count = len(values)
            avg = sum(values) / count
            lines.append(
                f'block_engine_write_latency_ms{{stage="{stage}",kind="count"}} {count}'
            )
            lines.append(
                f'block_engine_write_latency_ms{{stage="{stage}",kind="avg"}} {avg:.6f}'
            )
        for stage, count in sorted(snapshot["stage_counts"].items()):
            lines.append(
                f'block_engine_write_stage_events_total{{stage="{stage}"}} {count}'
            )
        return "\n".join(lines) + "\n"
