"""
duplex_base.py
──────────────
Base class for full-duplex, real-time bidirectional adapters.

Provides common infrastructure for WebSocket-based communication,
message queuing, and command handling. All external tools (Unreal, Blender,
Omniverse, Roblox, etc.) can inherit from this to guarantee symmetric
read/write capabilities and low-latency feedback loops.

Each adapter can:
  - Send delta updates to clients in real-time
  - Receive write requests, commands, and telemetry from clients
  - Execute callbacks on client-initiated events
  - Maintain per-client state and subscriptions
  - Enforce write authorization policies
"""

from __future__ import annotations

import json
import queue
import socket
import struct
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Set


class MessageType(IntEnum):
    """Enumeration of message types for duplex communication."""
    
    # Server → Client (deltas, state)
    BLOCK_DELTA = 0x10
    ENTITY_DELTA = 0x11
    STATE_UPDATE = 0x12
    PING = 0x1F
    
    # Client → Server (commands, writes, events)
    WRITE_BLOCK = 0x20
    DELETE_BLOCK = 0x21
    MOVE_ENTITY = 0x22
    QUERY = 0x23
    SUBSCRIBE = 0x24
    UNSUBSCRIBE = 0x25
    COMMAND = 0x26
    PONG = 0x2F
    
    # Errors & responses
    ACK = 0x30
    ERROR = 0x31
    RESPONSE = 0x32


@dataclass
class DuplexMessage:
    """Encapsulates a bidirectional message."""
    msg_type: MessageType
    msg_id: int = 0
    client_id: int = 0
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class DuplexClient:
    """Represents a connected full-duplex client."""
    
    def __init__(self, client_id: int, sock: socket.socket, addr: tuple):
        self.client_id = client_id
        self.sock = sock
        self.addr = addr
        self.subscriptions: Set[str] = set()  # Subscribed channels
        self.last_heartbeat = time.time()
        self.pending_acks: Dict[int, float] = {}  # msg_id → timestamp
        self.recv_buffer = b""
        self.send_queue: queue.Queue = queue.Queue(maxsize=1000)
    
    def enqueue_send(self, msg: DuplexMessage) -> bool:
        """Enqueue a message for sending. Returns False if queue full."""
        try:
            msg.client_id = self.client_id
            self.send_queue.put_nowait(msg)
            return True
        except queue.Full:
            return False
    
    def is_alive(self, timeout: float = 30.0) -> bool:
        """Check if client connection is still alive."""
        return (time.time() - self.last_heartbeat) < timeout


@dataclass
class WriteRequest:
    """Encapsulates a client write request."""
    client_id: int
    offset: int
    data: bytes
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class AuthorizationResult:
    """Result of write authorization check."""
    allowed: bool
    reason: str = ""
    rate_limited: bool = False


class DuplexAdapter:
    """
    Base class for full-duplex real-time adapters.
    
    Provides:
      - WebSocket-like TCP server for bidirectional communication
      - Message framing and encoding/decoding
      - Per-client state management
      - Write request queuing and authorization
      - Heartbeat/ping-pong for connection health
      - Subscription management for selective updates
    
    Subclasses must implement:
      - _on_write_request(write_req) → bool
      - _on_query(query_msg) → response_msg
      - _on_command(cmd_msg) → response_msg
      - platform-specific message formatting
    """
    
    MAGIC = b"DPLX"  # Frame magic bytes
    HEADER_STRUCT = struct.Struct("<4sBHI")  # magic(4) + type(1) + msg_id(2) + payload_len(4)
    
    def __init__(
        self,
        layout,
        resilient_store,
        write_authorizer: Optional[Callable] = None,
        host: str = "127.0.0.1",
        port: int = 7200,
        max_clients: int = 256,
        heartbeat_interval: float = 5.0,
        client_timeout: float = 30.0,
    ):
        self._layout = layout
        self._store = resilient_store
        self._write_authorizer = write_authorizer
        self._host = host
        self._port = port
        self._max_clients = max_clients
        self._heartbeat_interval = heartbeat_interval
        self._client_timeout = client_timeout
        
        self._clients: Dict[int, DuplexClient] = {}
        self._client_counter = 0
        self._lock = threading.Lock()
        self._running = False
        self._server: Optional[socket.socket] = None
        
        self._write_queue: queue.Queue = queue.Queue(maxsize=10000)
        self._write_callbacks: List[Callable[[WriteRequest], None]] = []
        
        self._stats = {
            "messages_sent": 0,
            "messages_recv": 0,
            "writes_authorized": 0,
            "writes_denied": 0,
            "clients_connected": 0,
            "clients_disconnected": 0,
        }
    
    def start(self) -> None:
        """Start the duplex server."""
        self._running = True
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self._host, self._port))
        self._server.listen(self._max_clients)
        self._server.settimeout(1.0)
        
        # Accept loop
        t_accept = threading.Thread(
            target=self._accept_loop, daemon=True, name=f"{self.__class__.__name__}-accept"
        )
        t_accept.start()
        
        # Send loop
        t_send = threading.Thread(
            target=self._send_loop, daemon=True, name=f"{self.__class__.__name__}-send"
        )
        t_send.start()
        
        # Receive loop
        t_recv = threading.Thread(
            target=self._recv_loop, daemon=True, name=f"{self.__class__.__name__}-recv"
        )
        t_recv.start()
        
        # Heartbeat loop
        t_hb = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name=f"{self.__class__.__name__}-heartbeat"
        )
        t_hb.start()
        
        # Write processor
        t_write = threading.Thread(
            target=self._write_processor, daemon=True, name=f"{self.__class__.__name__}-write"
        )
        t_write.start()
        
        print(f"[{self.__class__.__name__}] Listening on {self._host}:{self._port}")
    
    def stop(self) -> None:
        """Stop the duplex server and close all client connections."""
        self._running = False
        with self._lock:
            for client in self._clients.values():
                try:
                    client.sock.close()
                except Exception:
                    pass
            self._clients.clear()
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
    
    def _accept_loop(self) -> None:
        """Accept incoming client connections."""
        while self._running:
            try:
                if self._server is None:
                    continue
                conn, addr = self._server.accept()
                with self._lock:
                    if len(self._clients) >= self._max_clients:
                        conn.close()
                        continue
                    client_id = self._client_counter
                    self._client_counter += 1
                    client = DuplexClient(client_id, conn, addr)
                    self._clients[client_id] = client
                
                print(f"[{self.__class__.__name__}] Client {client_id} connected from {addr}")
                self._stats["clients_connected"] += 1
                
                # Spawn read/write handlers for this client
                threading.Thread(
                    target=self._handle_client_recv,
                    args=(client_id,),
                    daemon=True,
                    name=f"client-{client_id}-recv"
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    print(f"[{self.__class__.__name__}] Accept error: {e}")
    
    def _send_loop(self) -> None:
        """Main send loop: dispatch queued messages to all clients."""
        while self._running:
            try:
                with self._lock:
                    dead_clients = []
                    for client_id, client in list(self._clients.items()):
                        while not client.send_queue.empty():
                            try:
                                msg = client.send_queue.get_nowait()
                                frame = self._encode_message(msg)
                                client.sock.sendall(frame)
                                self._stats["messages_sent"] += 1
                            except queue.Empty:
                                break
                            except Exception:
                                dead_clients.append(client_id)
                                break
                    
                    for cid in dead_clients:
                        self._disconnect_client(cid)
                
                time.sleep(0.001)  # 1ms granularity
            except Exception as e:
                print(f"[{self.__class__.__name__}] Send loop error: {e}")
    
    def _recv_loop(self) -> None:
        """Monitor for incoming data from all clients."""
        while self._running:
            try:
                with self._lock:
                    dead_clients = []
                    for client_id, client in list(self._clients.items()):
                        try:
                            data = client.sock.recv(4096)
                            if not data:
                                dead_clients.append(client_id)
                            else:
                                client.recv_buffer += data
                                self._process_recv_buffer(client)
                        except socket.timeout:
                            pass
                        except Exception:
                            dead_clients.append(client_id)
                    
                    for cid in dead_clients:
                        self._disconnect_client(cid)
                
                time.sleep(0.001)
            except Exception as e:
                print(f"[{self.__class__.__name__}] Recv loop error: {e}")
    
    def _process_recv_buffer(self, client: DuplexClient) -> None:
        """Decode and process complete messages from client buffer."""
        while len(client.recv_buffer) >= len(self.HEADER_STRUCT):
            # Try to decode header
            header_bytes = client.recv_buffer[:len(self.HEADER_STRUCT)]
            try:
                magic, msg_type, msg_id, payload_len = self.HEADER_STRUCT.unpack(header_bytes)
            except struct.error:
                client.recv_buffer = b""
                return
            
            if magic != self.MAGIC or payload_len > 1_000_000:
                client.recv_buffer = b""
                return
            
            # Check if full message received
            full_len = len(self.HEADER_STRUCT) + payload_len
            if len(client.recv_buffer) < full_len:
                break
            
            # Extract and decode payload
            payload_bytes = client.recv_buffer[len(self.HEADER_STRUCT):full_len]
            client.recv_buffer = client.recv_buffer[full_len:]
            
            try:
                payload = json.loads(payload_bytes.decode("utf-8"))
            except Exception:
                payload = {}
            
            msg = DuplexMessage(
                msg_type=MessageType(msg_type),
                msg_id=msg_id,
                client_id=client.client_id,
                payload=payload,
            )
            
            self._stats["messages_recv"] += 1
            self._dispatch_message(client, msg)
    
    def _dispatch_message(self, client: DuplexClient, msg: DuplexMessage) -> None:
        """Dispatch incoming message to handler."""
        try:
            if msg.msg_type == MessageType.PONG:
                client.last_heartbeat = time.time()
            elif msg.msg_type == MessageType.WRITE_BLOCK:
                self._handle_write_block(client, msg)
            elif msg.msg_type == MessageType.DELETE_BLOCK:
                self._handle_delete_block(client, msg)
            elif msg.msg_type == MessageType.QUERY:
                self._handle_query(client, msg)
            elif msg.msg_type == MessageType.SUBSCRIBE:
                self._handle_subscribe(client, msg)
            elif msg.msg_type == MessageType.UNSUBSCRIBE:
                self._handle_unsubscribe(client, msg)
            elif msg.msg_type == MessageType.COMMAND:
                self._handle_command(client, msg)
        except Exception as e:
            self._send_error(client, msg.msg_id, str(e))
    
    def _handle_write_block(self, client: DuplexClient, msg: DuplexMessage) -> None:
        """Handle client write block request."""
        payload = msg.payload
        offset = payload.get("offset")
        data = bytes.fromhex(payload.get("data", ""))
        
        if offset is None or not data:
            self._send_error(client, msg.msg_id, "Invalid write request")
            return
        
        # Check authorization
        auth_result = self._authorize_write(client.client_id, offset, data)
        if not auth_result.allowed:
            self._stats["writes_denied"] += 1
            self._send_error(client, msg.msg_id, f"Write denied: {auth_result.reason}")
            return
        
        # Queue for processing
        write_req = WriteRequest(
            client_id=client.client_id,
            offset=offset,
            data=data,
            metadata=payload.get("metadata", {})
        )
        
        try:
            self._write_queue.put_nowait(write_req)
            self._stats["writes_authorized"] += 1
            
            # Send ACK immediately
            ack = DuplexMessage(
                msg_type=MessageType.ACK,
                msg_id=msg.msg_id,
                payload={"offset": offset, "status": "queued"}
            )
            client.enqueue_send(ack)
        except queue.Full:
            self._send_error(client, msg.msg_id, "Write queue full")
    
    def _handle_delete_block(self, client: DuplexClient, msg: DuplexMessage) -> None:
        """Handle block deletion request."""
        offset = msg.payload.get("offset")
        if offset is None:
            self._send_error(client, msg.msg_id, "Invalid delete request")
            return
        
        auth_result = self._authorize_write(client.client_id, offset, b"\x00" * 16)
        if not auth_result.allowed:
            self._send_error(client, msg.msg_id, f"Delete denied: {auth_result.reason}")
            return
        
        write_req = WriteRequest(
            client_id=client.client_id,
            offset=offset,
            data=b"",
            metadata={"deleted": True}
        )
        try:
            self._write_queue.put_nowait(write_req)
            ack = DuplexMessage(
                msg_type=MessageType.ACK,
                msg_id=msg.msg_id,
                payload={"offset": offset, "status": "delete_queued"}
            )
            client.enqueue_send(ack)
        except queue.Full:
            self._send_error(client, msg.msg_id, "Write queue full")
    
    def _handle_query(self, client: DuplexClient, msg: DuplexMessage) -> None:
        """Handle client query (read request)."""
        offset = msg.payload.get("offset")
        if offset is None:
            self._send_error(client, msg.msg_id, "Invalid query")
            return
        
        try:
            data = self._store.read_block(offset)
            response = DuplexMessage(
                msg_type=MessageType.RESPONSE,
                msg_id=msg.msg_id,
                payload={
                    "offset": offset,
                    "data": data.hex(),
                    "status": "ok"
                }
            )
            client.enqueue_send(response)
        except Exception as e:
            self._send_error(client, msg.msg_id, str(e))
    
    def _handle_subscribe(self, client: DuplexClient, msg: DuplexMessage) -> None:
        """Handle subscription request."""
        channels = msg.payload.get("channels", [])
        for ch in channels:
            client.subscriptions.add(ch)
        
        ack = DuplexMessage(
            msg_type=MessageType.ACK,
            msg_id=msg.msg_id,
            payload={"subscribed": channels}
        )
        client.enqueue_send(ack)
    
    def _handle_unsubscribe(self, client: DuplexClient, msg: DuplexMessage) -> None:
        """Handle unsubscription request."""
        channels = msg.payload.get("channels", [])
        for ch in channels:
            client.subscriptions.discard(ch)
        
        ack = DuplexMessage(
            msg_type=MessageType.ACK,
            msg_id=msg.msg_id,
            payload={"unsubscribed": channels}
        )
        client.enqueue_send(ack)
    
    def _handle_command(self, client: DuplexClient, msg: DuplexMessage) -> None:
        """Handle platform-specific command. Subclasses should override."""
        response = DuplexMessage(
            msg_type=MessageType.RESPONSE,
            msg_id=msg.msg_id,
            payload={"status": "ok", "command": msg.payload.get("command")}
        )
        client.enqueue_send(response)
    
    def _heartbeat_loop(self) -> None:
        """Send periodic ping to all clients."""
        while self._running:
            try:
                time.sleep(self._heartbeat_interval)
                with self._lock:
                    for client in self._clients.values():
                        ping = DuplexMessage(
                            msg_type=MessageType.PING,
                            msg_id=0,
                        )
                        client.enqueue_send(ping)
            except Exception:
                pass
    
    def _write_processor(self) -> None:
        """Process queued write requests and forward to engine."""
        while self._running:
            try:
                write_req = self._write_queue.get(timeout=0.1)
                self._on_write_request(write_req)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[{self.__class__.__name__}] Write processor error: {e}")
    
    def _authorize_write(self, client_id: int, offset: int, data: bytes) -> AuthorizationResult:
        """Check if write is authorized. Override in subclass for custom logic."""
        if self._write_authorizer:
            try:
                return self._write_authorizer(client_id, offset, data)
            except Exception:
                return AuthorizationResult(allowed=False, reason="Authorization check failed")
        return AuthorizationResult(allowed=True)
    
    def _encode_message(self, msg: DuplexMessage) -> bytes:
        """Encode message to binary frame."""
        payload = json.dumps(msg.payload).encode("utf-8")
        header = self.HEADER_STRUCT.pack(
            self.MAGIC,
            msg.msg_type,
            msg.msg_id & 0xFFFF,
            len(payload)
        )
        return header + payload
    
    def _send_error(self, client: DuplexClient, msg_id: int, reason: str) -> None:
        """Send error response to client."""
        error = DuplexMessage(
            msg_type=MessageType.ERROR,
            msg_id=msg_id,
            payload={"error": reason}
        )
        client.enqueue_send(error)
    
    def _disconnect_client(self, client_id: int) -> None:
        """Disconnect a client."""
        if client_id in self._clients:
            client = self._clients[client_id]
            try:
                client.sock.close()
            except Exception:
                pass
            del self._clients[client_id]
            self._stats["clients_disconnected"] += 1
            print(f"[{self.__class__.__name__}] Client {client_id} disconnected")
    
    def _handle_client_recv(self, client_id: int) -> None:
        """Per-client receive handler (called in separate thread)."""
        # Handled by main recv_loop; this is a placeholder for subclass overrides
        pass
    
    def broadcast_delta(self, msg: DuplexMessage, channels: Optional[List[str]] = None) -> None:
        """Broadcast a delta to all subscribed clients."""
        with self._lock:
            for client in self._clients.values():
                if channels is None or any(ch in client.subscriptions for ch in channels):
                    client.enqueue_send(msg)
    
    def send_to_client(self, client_id: int, msg: DuplexMessage) -> bool:
        """Send message to specific client."""
        with self._lock:
            if client_id in self._clients:
                return self._clients[client_id].enqueue_send(msg)
        return False
    
    def statistics(self) -> Dict[str, int]:
        """Return communication statistics."""
        with self._lock:
            return {
                **self._stats,
                "connected_clients": len(self._clients),
                "write_queue_size": self._write_queue.qsize(),
            }
    
    # Subclass hooks
    def _on_write_request(self, write_req: WriteRequest) -> None:
        """Override in subclass to handle write requests."""
        raise NotImplementedError()
    
    def __repr__(self) -> str:
        with self._lock:
            n = len(self._clients)
        return f"{self.__class__.__name__}({self._host}:{self._port}, clients={n})"
