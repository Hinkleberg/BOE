from pathlib import Path

from block_engine.authority.flat_store import FlatStore
from block_engine.authority.resilient_store import ResilientStore
from block_engine.environment.block_layout import Block, BlockType, WorldLayout
from block_engine.replication.metrics_exporter import WritePathMetricsCollector


def test_metrics_collector_exposes_prometheus_output(tmp_path: Path) -> None:
    layout = WorldLayout(16, 16, 16)
    image_path = tmp_path / "world.img"
    journal_path = tmp_path / "world.jrn"

    store = FlatStore(str(image_path), layout)
    collector = WritePathMetricsCollector()
    resilient_store = ResilientStore(
        store,
        journal_path=str(journal_path),
        event_observer=collector.observe,
    )

    data = Block(block_type=BlockType.STONE, light_level=7).to_bytes()
    offset = layout.block_offset(1, 2, 3)
    resilient_store.write_block(offset, data)

    snapshot = collector.snapshot()
    assert snapshot["writes_total"] >= 1
    assert snapshot["stage_counts"]["journal_append"] >= 1
    assert snapshot["stage_counts"]["flat_store_write"] >= 1
    assert snapshot["stage_counts"]["journal_commit"] >= 1

    text = collector.prometheus_text()
    assert "block_engine_write_events_total" in text
    assert 'stage="journal_append"' in text
    assert "block_engine_write_latency_ms" in text
