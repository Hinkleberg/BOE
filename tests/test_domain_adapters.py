from pathlib import Path

from block_engine.authority.flat_store import FlatStore
from block_engine.authority.resilient_store import ResilientStore
from block_engine.environment.block_layout import Block, BlockType, WorldLayout
from block_engine.bridges.blender_adapter import BlenderAdapter
from block_engine.bridges.omniverse_connector import OmniverseConnector
from block_engine.bridges.roblox_http_adapter import RobloxHTTPAdapter, RobloxBlockWrite


def test_blender_adapter_load_region(tmp_path: Path) -> None:
    """Test Blender adapter can load a region from BOE."""
    layout = WorldLayout(16, 16, 16)
    image_path = tmp_path / "world.img"
    journal_path = tmp_path / "world.jrn"

    store = FlatStore(str(image_path), layout)
    rs = ResilientStore(store, journal_path=str(journal_path))

    # Write some test blocks
    for i in range(5):
        offset = layout.block_offset(i, i, i)
        data = Block(block_type=BlockType.STONE, light_level=i + 5).to_bytes()
        rs.write_block(offset, data)

    adapter = BlenderAdapter(rs, layout)
    blocks = adapter.load_region(x=0, y=0, z=0, size=8)

    assert len(blocks) > 0
    assert all(hasattr(b, "block_type") for b in blocks)


def test_blender_adapter_export_scene(tmp_path: Path) -> None:
    """Test Blender adapter can export scene objects to BOE."""
    layout = WorldLayout(16, 16, 16)
    image_path = tmp_path / "world.img"
    journal_path = tmp_path / "world.jrn"

    store = FlatStore(str(image_path), layout)
    rs = ResilientStore(store, journal_path=str(journal_path))
    adapter = BlenderAdapter(rs, layout)

    scene_objects = [
        {"position": (1, 1, 1), "type": 1, "light": 10},
        {"position": (2, 2, 2), "type": 2, "light": 8},
        {"position": (3, 3, 3), "type": 3, "light": 6},
    ]

    result = adapter.export_scene_to_boe(scene_objects)
    assert result["written"] == 3


def test_blender_adapter_procedural_generation(tmp_path: Path) -> None:
    """Test Blender adapter with procedural generation callback."""
    layout = WorldLayout(16, 16, 16)
    image_path = tmp_path / "world.img"
    journal_path = tmp_path / "world.jrn"

    store = FlatStore(str(image_path), layout)
    rs = ResilientStore(store, journal_path=str(journal_path))
    adapter = BlenderAdapter(rs, layout)

    def simple_generator(x, y, z):
        # Simple rule: stone at y < 5, grass above
        return 1 if y < 5 else 2

    result = adapter.procedural_generation_hook(
        simple_generator, x=0, y=0, z=0, size=8
    )
    assert result["generated"] > 0


def test_blender_adapter_viewport_stream(tmp_path: Path) -> None:
    """Test Blender adapter can format blocks for viewport streaming."""
    layout = WorldLayout(16, 16, 16)
    image_path = tmp_path / "world.img"
    journal_path = tmp_path / "world.jrn"

    store = FlatStore(str(image_path), layout)
    rs = ResilientStore(store, journal_path=str(journal_path))
    adapter = BlenderAdapter(rs, layout)

    # Load and stream
    blocks = adapter.load_region(x=0, y=0, z=0, size=4)
    viewport_data = adapter.stream_to_viewport(blocks)

    assert "meshes" in viewport_data
    assert "count" in viewport_data


def test_omniverse_connector_sync_region(tmp_path: Path) -> None:
    """Test Omniverse connector can sync a region."""
    layout = WorldLayout(16, 16, 16)
    image_path = tmp_path / "world.img"
    journal_path = tmp_path / "world.jrn"

    store = FlatStore(str(image_path), layout)
    rs = ResilientStore(store, journal_path=str(journal_path))

    # Write blocks
    for i in range(3):
        offset = layout.block_offset(i, i, i)
        data = Block(block_type=BlockType.GRASS).to_bytes()
        rs.write_block(offset, data)

    connector = OmniverseConnector(rs, layout)
    result = connector.sync_region_to_omniverse(x=0, y=0, z=0, size=8)

    assert result["synced"] > 0
    assert "usd_operations" in result


def test_omniverse_connector_usd_operations(tmp_path: Path) -> None:
    """Test Omniverse connector generates correct USD operations."""
    layout = WorldLayout(16, 16, 16)
    image_path = tmp_path / "world.img"
    journal_path = tmp_path / "world.jrn"

    store = FlatStore(str(image_path), layout)
    rs = ResilientStore(store, journal_path=str(journal_path))
    connector = OmniverseConnector(rs, layout)

    result = connector.sync_region_to_omniverse(x=0, y=0, z=0, size=4)
    ops = result["usd_operations"]

    assert "stage" in ops
    assert "prims" in ops
    assert isinstance(ops["prims"], list)


def test_omniverse_connector_change_subscription(tmp_path: Path) -> None:
    """Test Omniverse connector can subscribe to block changes."""
    layout = WorldLayout(16, 16, 16)
    image_path = tmp_path / "world.img"
    journal_path = tmp_path / "world.jrn"

    store = FlatStore(str(image_path), layout)
    rs = ResilientStore(store, journal_path=str(journal_path))
    connector = OmniverseConnector(rs, layout)

    received_updates = []

    def on_change(update):
        received_updates.append(update)

    connector.subscribe_to_changes(on_change)

    # Trigger a change
    offset = layout.block_offset(5, 5, 5)
    data = Block(block_type=BlockType.DIRT).to_bytes()
    connector.on_block_changed(offset, data)

    assert len(received_updates) > 0


def test_roblox_http_adapter_write_block() -> None:
    """Test Roblox HTTP adapter can write blocks."""
    layout = WorldLayout(16, 16, 16)
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        image_path = f"{tmpdir}/world.img"
        journal_path = f"{tmpdir}/world.jrn"

        store = FlatStore(image_path, layout)
        rs = ResilientStore(store, journal_path=journal_path)
        adapter = RobloxHTTPAdapter(rs, layout)

        write = RobloxBlockWrite(x=5, y=5, z=5, block_type=1, player_id="player1")
        result = adapter.write_block(write)

        assert result["status"] == "success"
        assert result["offset"] == layout.block_offset(5, 5, 5)


def test_roblox_http_adapter_read_block() -> None:
    """Test Roblox HTTP adapter can read blocks."""
    layout = WorldLayout(16, 16, 16)
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        image_path = f"{tmpdir}/world.img"
        journal_path = f"{tmpdir}/world.jrn"

        store = FlatStore(image_path, layout)
        rs = ResilientStore(store, journal_path=journal_path)

        # Write a block
        offset = layout.block_offset(3, 4, 5)
        data = Block(block_type=BlockType.STONE, light_level=10).to_bytes()
        rs.write_block(offset, data)

        adapter = RobloxHTTPAdapter(rs, layout)
        result = adapter.read_block(3, 4, 5)

        assert result["status"] == "success"
        assert result["x"] == 3
        assert result["y"] == 4
        assert result["z"] == 5
        assert result["block_type"] == int(BlockType.STONE)


def test_roblox_http_adapter_read_region() -> None:
    """Test Roblox HTTP adapter can read a region."""
    layout = WorldLayout(16, 16, 16)
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        image_path = f"{tmpdir}/world.img"
        journal_path = f"{tmpdir}/world.jrn"

        store = FlatStore(image_path, layout)
        rs = ResilientStore(store, journal_path=journal_path)

        # Write a few blocks
        for i in range(3):
            offset = layout.block_offset(i, i, i)
            data = Block(block_type=BlockType.GRASS).to_bytes()
            rs.write_block(offset, data)

        adapter = RobloxHTTPAdapter(rs, layout)
        result = adapter.read_region(x=0, y=0, z=0, size=8)

        assert result["status"] == "success"
        assert result["count"] > 0
        assert isinstance(result["blocks"], list)


def test_roblox_http_adapter_statistics() -> None:
    """Test Roblox HTTP adapter statistics tracking."""
    layout = WorldLayout(16, 16, 16)
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        image_path = f"{tmpdir}/world.img"
        journal_path = f"{tmpdir}/world.jrn"

        store = FlatStore(image_path, layout)
        rs = ResilientStore(store, journal_path=journal_path)
        adapter = RobloxHTTPAdapter(rs, layout)

        # Perform operations
        write = RobloxBlockWrite(x=1, y=1, z=1, block_type=1)
        adapter.write_block(write)
        adapter.read_block(1, 1, 1)
        adapter.read_region(x=0, y=0, z=0, size=4)

        stats = adapter.statistics()
        assert stats["total_requests"] >= 3
        assert stats["writes"] >= 1
        assert stats["reads"] >= 2
