# BOE Performance Snapshot (2026-07-13)

This document captures local benchmark numbers for the current write + mirror pipeline after dual Dev/Live compare mode and spatial grid indexing updates.

## Environment

- Workspace: BOE main repository
- Python: `.venv` interpreter
- Layout: `WorldLayout(64, 64, 64)`
- Writes: `N=1000` blocks
- Paths measured:
  - Authority write only (`ResilientStore` over `FlatStore`)
  - Authority write with live mirror attached (`RenderStore`)
  - Async mirror propagation to live visibility

## Results

| Metric | p50 (ms) | p95 (ms) | avg (ms) | max (ms) |
|--------|----------|----------|----------|----------|
| AUTH_ONLY_MS | 0.0114 | 0.0122 | 0.0115 | 0.0838 |
| AUTH_PLUS_MIRROR_WRITE_MS | 0.0732 | 0.1369 | 0.0809 | 0.3132 |
| MIRROR_PROPAGATION_MS | 1.0350 | 1.0531 | 1.0293 | 1.2461 |

## Interpretation

- Authority commits are in the tens of microseconds range on this local machine.
- Adding live mirror fan-out remains sub-millisecond for p95 authority commit latency.
- Dev -> Live visibility settles around ~1ms in this local run.

## Caveats

- These are local storage-path numbers, not player-facing input-to-photon latency.
- Adapter network hops and client render cadence add additional latency in production.
- Treat this as a baseline snapshot for regression tracking.
