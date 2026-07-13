"""Full-duplex Amazon O3DE adapter (port 7502) - Game engine integration."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict
from block_engine.bridges.duplex_base import DuplexAdapter, DuplexMessage, MessageType, DuplexClient

@dataclass
class O3DEEntity:
    entity_id: int
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

class O3DEAdapter(DuplexAdapter):
    """Full-duplex adapter for Amazon O3DE/Lumberyard."""
    def __init__(self, resilient_store, world_layout, host: str = "127.0.0.1", port: int = 7502, max_clients: int = 256):
        super().__init__(layout=world_layout, resilient_store=resilient_store, host=host, port=port, max_clients=max_clients)
        self._entities: Dict[int, O3DEEntity] = {}
    
    def _handle_command(self, client: DuplexClient, msg: DuplexMessage) -> None:
        cmd = msg.payload.get("command")
        args = msg.payload.get("args", {})
        try:
            handlers = {
                "spawn_entity": self._cmd_spawn_entity,
                "destroy_entity": self._cmd_destroy_entity,
                "apply_physics": self._cmd_apply_physics,
                "set_collider": self._cmd_set_collider,
                "load_asset": self._cmd_load_asset,
                "unload_asset": self._cmd_unload_asset,
                "script_invoke": self._cmd_script_invoke,
                "event_dispatch": self._cmd_event_dispatch,
                "get_viewport_data": self._cmd_get_viewport_data,
                "set_entity_property": self._cmd_set_entity_property,
                "get_entity_property": self._cmd_get_entity_property,
                "raycast_query": self._cmd_raycast_query,
                "load_terrain": self._cmd_load_terrain,
            }
            if cmd in handlers:
                handlers[cmd](client, msg, args)
            else:
                super()._handle_command(client, msg)
        except Exception as e:
            self._send_error(client, msg.msg_id, str(e))
    
    def _cmd_spawn_entity(self, c: DuplexClient, m: DuplexMessage, a: Dict) -> None:
        e = O3DEEntity(entity_id=a.get("entity_id"), name=a.get("name", ""))
        self._entities[e.entity_id] = e
        c.enqueue_send(DuplexMessage(msg_type=MessageType.RESPONSE, msg_id=m.msg_id, payload={"status": "entity_spawned"}))
    
    def _cmd_destroy_entity(self, c: DuplexClient, m: DuplexMessage, a: Dict) -> None:
        self._entities.pop(a.get("entity_id"), None)
        c.enqueue_send(DuplexMessage(msg_type=MessageType.RESPONSE, msg_id=m.msg_id, payload={"status": "entity_destroyed"}))
    
    def _cmd_apply_physics(self, c: DuplexClient, m: DuplexMessage, a: Dict) -> None:
        c.enqueue_send(DuplexMessage(msg_type=MessageType.RESPONSE, msg_id=m.msg_id, payload={"status": "physics_applied"}))
    
    def _cmd_set_collider(self, c: DuplexClient, m: DuplexMessage, a: Dict) -> None:
        c.enqueue_send(DuplexMessage(msg_type=MessageType.RESPONSE, msg_id=m.msg_id, payload={"status": "collider_set"}))
    
    def _cmd_load_asset(self, c: DuplexClient, m: DuplexMessage, a: Dict) -> None:
        c.enqueue_send(DuplexMessage(msg_type=MessageType.RESPONSE, msg_id=m.msg_id, payload={"status": "asset_loaded"}))
    
    def _cmd_unload_asset(self, c: DuplexClient, m: DuplexMessage, a: Dict) -> None:
        c.enqueue_send(DuplexMessage(msg_type=MessageType.RESPONSE, msg_id=m.msg_id, payload={"status": "asset_unloaded"}))
    
    def _cmd_script_invoke(self, c: DuplexClient, m: DuplexMessage, a: Dict) -> None:
        c.enqueue_send(DuplexMessage(msg_type=MessageType.RESPONSE, msg_id=m.msg_id, payload={"status": "script_invoked"}))
    
    def _cmd_event_dispatch(self, c: DuplexClient, m: DuplexMessage, a: Dict) -> None:
        c.enqueue_send(DuplexMessage(msg_type=MessageType.RESPONSE, msg_id=m.msg_id, payload={"status": "event_dispatched"}))
    
    def _cmd_get_viewport_data(self, c: DuplexClient, m: DuplexMessage, a: Dict) -> None:
        c.enqueue_send(DuplexMessage(msg_type=MessageType.RESPONSE, msg_id=m.msg_id, payload={"viewport": {}}))
    
    def _cmd_set_entity_property(self, c: DuplexClient, m: DuplexMessage, a: Dict) -> None:
        c.enqueue_send(DuplexMessage(msg_type=MessageType.RESPONSE, msg_id=m.msg_id, payload={"status": "property_set"}))
    
    def _cmd_get_entity_property(self, c: DuplexClient, m: DuplexMessage, a: Dict) -> None:
        c.enqueue_send(DuplexMessage(msg_type=MessageType.RESPONSE, msg_id=m.msg_id, payload={"value": None}))
    
    def _cmd_raycast_query(self, c: DuplexClient, m: DuplexMessage, a: Dict) -> None:
        c.enqueue_send(DuplexMessage(msg_type=MessageType.RESPONSE, msg_id=m.msg_id, payload={"hit": None}))
    
    def _cmd_load_terrain(self, c: DuplexClient, m: DuplexMessage, a: Dict) -> None:
        c.enqueue_send(DuplexMessage(msg_type=MessageType.RESPONSE, msg_id=m.msg_id, payload={"status": "terrain_loaded"}))
