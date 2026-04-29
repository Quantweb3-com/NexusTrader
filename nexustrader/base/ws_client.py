import asyncio
import orjson
from abc import ABC, abstractmethod
from typing import Any
from typing import Callable, Literal


from aiolimiter import AsyncLimiter
from nexustrader.core.log import SpdLog
from nexustrader.core.entity import TaskManager
from picows import (
    ws_connect,
    WSFrame,
    WSTransport,
    WSListener,
    WSMsgType,
    WSAutoPingStrategy,
    # PICOWS_DEBUG_LL,
)
from nexustrader.core.nautilius_core import LiveClock

# import logging

# file_handler = logging.FileHandler('.log/picows.log')
# file_handler.setLevel(PICOWS_DEBUG_LL)

# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# file_handler.setFormatter(formatter)

# picows_logger = logging.getLogger("picows")
# picows_logger.setLevel(PICOWS_DEBUG_LL)
# picows_logger.addHandler(file_handler)

class Listener(WSListener):
    """WebSocket listener implementation that handles connection events and message frames.
    
    Inherits from picows.WSListener to provide WebSocket event handling functionality.
    """
    
    def __init__(self, callback, logger, specific_ping_msg=None, *args, **kwargs):
        """Initialize the WebSocket listener.
        
        Args:
            logger: Logger instance for logging events
            specific_ping_msg: Optional custom ping message
        """
        super().__init__(*args, **kwargs)
        self._log = logger
        self._specific_ping_msg = specific_ping_msg
        self._callback = callback
        
    def send_user_specific_ping(self, transport: WSTransport) -> None:
        """Send a custom ping message or default ping frame.
        
        Args:
            transport (picows.WSTransport): WebSocket transport instance
        """
        if self._specific_ping_msg:
            transport.send(WSMsgType.TEXT, self._specific_ping_msg)
            self._log.debug(f"Sent user specific ping {self._specific_ping_msg}")
        else:
            transport.send_ping()
            self._log.debug("Sent default ping.")

    def on_ws_connected(self, transport: WSTransport) -> None:
        """Called when WebSocket connection is established.
        
        Args:
            transport (picows.WSTransport): WebSocket transport instance
        """
        self._log.debug("Connected to Websocket...")

    def on_ws_disconnected(self, transport: WSTransport) -> None:
        """Called when WebSocket connection is closed.
        
        Args:
            transport (picows.WSTransport): WebSocket transport instance
        """
        self._log.debug("Disconnected from Websocket.")

    def on_ws_frame(self, transport: WSTransport, frame: WSFrame) -> None:
        """Handle incoming WebSocket frames.
        
        Args:
            transport (picows.WSTransport): WebSocket transport instance
            frame (picows.WSFrame): Received WebSocket frame
        """
        try:
            match frame.msg_type:
                case WSMsgType.PING:
                    # Only send pong if auto_pong is disabled
                    self._log.debug("Received PING frame, sending PONG frame...")
                    transport.send_pong(frame.get_payload_as_bytes())
                    return
                case WSMsgType.TEXT:
                    # Queue raw bytes for handler to decode
                    self._callback(frame.get_payload_as_bytes())
                    return
                case WSMsgType.CLOSE:
                    close_code = frame.get_close_code()
                    close_msg = frame.get_close_message()
                    self._log.warn(
                        f"Received close frame. Close code: {close_code}, Close message: {close_msg}"
                    )
                    return
        except Exception as e:
            self._log.error(f"Error processing message: {str(e)}")


class WSClient(ABC):
    def __init__(
        self,
        url: str,
        limiter: AsyncLimiter,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        specific_ping_msg: bytes = None,
        reconnect_interval: int = 1,
        ping_idle_timeout: int = 2,
        ping_reply_timeout: int = 1,
        auto_ping_strategy: Literal[
            "ping_when_idle", "ping_periodically"
        ] = "ping_when_idle",
        enable_auto_ping: bool = True,
        enable_auto_pong: bool = False,
    ):
        self._clock = LiveClock()
        self._url = url
        self._specific_ping_msg = specific_ping_msg
        self._reconnect_interval = reconnect_interval
        self._ping_idle_timeout = ping_idle_timeout
        self._ping_reply_timeout = ping_reply_timeout
        self._enable_auto_pong = enable_auto_pong
        self._enable_auto_ping = enable_auto_ping
        self._listener: Listener = None
        self._transport = None
        self._subscriptions = []
        self._limiter = limiter
        self._callback = handler
        self._connected_at: int | None = None
        self._last_message_at: int | None = None
        self._last_disconnect_at: int | None = None
        self._message_count = 0
        self._reconnect_count = 0
        if auto_ping_strategy == "ping_when_idle":
            self._auto_ping_strategy = WSAutoPingStrategy.PING_WHEN_IDLE
        elif auto_ping_strategy == "ping_periodically":
            self._auto_ping_strategy = WSAutoPingStrategy.PING_PERIODICALLY
        self._task_manager = task_manager
        self._log = SpdLog.get_logger(type(self).__name__, level="DEBUG", flush=True)

    @property
    def connected(self):
        return self._transport and self._listener

    def _handle_raw_message(self, raw: bytes) -> None:
        self._last_message_at = self._clock.timestamp_ms()
        self._message_count += 1
        self._callback(raw)

    async def _connect(self):
        WSListenerFactory = lambda: Listener(self._handle_raw_message, self._log, self._specific_ping_msg)  # noqa: E731
        self._transport, self._listener = await ws_connect(
            WSListenerFactory,
            self._url,
            enable_auto_ping=self._enable_auto_ping,
            auto_ping_idle_timeout=self._ping_idle_timeout,
            auto_ping_reply_timeout=self._ping_reply_timeout,
            auto_ping_strategy=self._auto_ping_strategy,
            enable_auto_pong=self._enable_auto_pong,
        )
        self._connected_at = self._clock.timestamp_ms()

    async def connect(self):
        if not self.connected:
            await self._connect()
            self._task_manager.create_task(self._connection_handler())

    async def _connection_handler(self):
        while True:
            try:
                if not self.connected:
                    await self._connect()
                    await self._resubscribe()
                await self._transport.wait_disconnected()
            except Exception as e:
                self._reconnect_count += 1
                self._log.error(f"Connection error: {e}")
                
            if self.connected:
                self._reconnect_count += 1
                self._log.warn("Websocket reconnecting...")
                self.disconnect()
            await asyncio.sleep(self._reconnect_interval)

    async def _send(self, payload: dict):
        await self._limiter.acquire()
        self._transport.send(WSMsgType.TEXT, orjson.dumps(payload))

    def disconnect(self):
        if self.connected:
            self._log.debug("Disconnecting from websocket...")
            self._transport.disconnect()
            self._transport, self._listener = None, None
            self._last_disconnect_at = self._clock.timestamp_ms()

    def get_health(self) -> dict:
        now = self._clock.timestamp_ms()
        return {
            "enabled": True,
            "url": self._url,
            "connected": bool(self.connected),
            "subscriptions": len(self._subscriptions),
            "last_message_at": self._last_message_at,
            "last_message_age_ms": (
                now - self._last_message_at if self._last_message_at else None
            ),
            "connected_at": self._connected_at,
            "last_disconnect_at": self._last_disconnect_at,
            "message_count": self._message_count,
            "reconnect_count": self._reconnect_count,
        }

    @abstractmethod
    async def _resubscribe(self):
        pass
