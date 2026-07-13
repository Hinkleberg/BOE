from block_engine.core_api import BOECoreAPI
from block_engine.sdk import PluginContext, PluginMetadata, PluginRegistry


class _DummyStore:
    def __init__(self) -> None:
        self.write_seq = 0

    def read_block(self, offset: int) -> bytes:
        return b"\x00" * 16

    def write_block(self, offset: int, data: bytes):
        self.write_seq += 1
        return {"offset": offset, "write_seq": self.write_seq}

    def health_report(self):
        return {"health": "HEALTHY", "write_seq": self.write_seq}


class _GoodPlugin:
    metadata = PluginMetadata(name="good", version="0.1.0", api_version="1.0")

    def __init__(self):
        self.loaded = False
        self.started = False

    def on_load(self, context: PluginContext) -> None:
        self.loaded = True

    def on_start(self) -> None:
        self.started = True

    def on_stop(self) -> None:
        self.started = False

    def on_unload(self) -> None:
        self.loaded = False


class _BadPlugin:
    metadata = PluginMetadata(name="bad", version="0.1.0", api_version="2.0")

    def on_load(self, context: PluginContext) -> None:
        return None

    def on_start(self) -> None:
        return None

    def on_stop(self) -> None:
        return None

    def on_unload(self) -> None:
        return None


def test_plugin_registry_accepts_compatible_plugin() -> None:
    core = BOECoreAPI(layout=object(), block_store=_DummyStore())
    registry = PluginRegistry(PluginContext(core=core))

    plugin = _GoodPlugin()
    registry.register(plugin)
    registry.start_all()

    assert plugin.loaded is True
    assert plugin.started is True
    assert registry.names() == ["good"]


def test_plugin_registry_rejects_incompatible_plugin() -> None:
    core = BOECoreAPI(layout=object(), block_store=_DummyStore())
    registry = PluginRegistry(PluginContext(core=core))

    try:
        registry.register(_BadPlugin())
        assert False, "Expected incompatible plugin registration to fail"
    except ValueError as exc:
        assert "incompatible API version" in str(exc)
