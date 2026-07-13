from pathlib import Path

from interface.render_store import ForwardEntry, RenderStore


def test_enqueue_forward_sync_initializes_thread_queue_before_drain_loop(monkeypatch, tmp_path: Path) -> None:
    def no_op_drain_loop(self) -> None:
        return None

    monkeypatch.setattr(RenderStore, "_drain_loop", no_op_drain_loop)

    store = RenderStore(tmp_path / "render_store.sqlite")
    try:
        assert store._thread_enqueue(ForwardEntry(write_seq=1, offset=1, data=b"x"))
    finally:
        store.close()
