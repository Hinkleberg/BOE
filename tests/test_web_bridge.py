from block_engine.bridges.web_bridge import WebBridge
from block_engine.environment.block_layout import Block, BlockType, WorldLayout


def test_web_bridge_tracks_blocks_and_emits_snapshot() -> None:
    layout = WorldLayout(16, 16, 16)
    bridge = WebBridge(layout, host="127.0.0.1", port=0)
    offset = layout.block_offset(1, 2, 3)
    data = Block(block_type=BlockType.STONE, light_level=7, flags=1, metadata=99).to_bytes()

    bridge.on_block_forward(offset, data, write_seq=4)

    snapshot = bridge.snapshot()
    assert snapshot["blocks"]
    entry = snapshot["blocks"][0]
    assert entry["x"] == 1
    assert entry["y"] == 2
    assert entry["z"] == 3
    assert entry["block_type"] == BlockType.STONE
    assert entry["write_seq"] == 4
