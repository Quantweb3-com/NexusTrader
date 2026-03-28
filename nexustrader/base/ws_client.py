import asyncio
import msgspec
from abc import ABC, abstractmethod
from types import MethodType
from typing import Any
from typing import Callable, Literal


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
from nexustrader.core.nautilius_core import LiveClock, Logger

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

    def __init__(
        self,
        callback,
        logger,
        specific_ping_msg=None,
        user_pong_callback: Callable[["Listener", WSFrame], bool] | None = None,
        *args,
        **kwargs,
    ):
        """Initialize the WebSocket listener.

        Args:
            logger: Logger instance for logging events
            specific_ping_msg: Optional custom ping message
        """
        super().__init__(*args, **kwargs)
        self._log = logger
        self._specific_ping_msg: bytes = specific_ping_msg
        self._callback = callback

        if user_pong_callback:
            self.is_user_specific_pong = MethodType(user_pong_callback, self)

    def send_user_specific_ping(self, transport: WSTransport) -> None:
        """Send a custom ping message or default ping frame.

        Args:
            transport (picows.WSTransport): WebSocket transport instance
        """
        if self._specific_ping_msg:
            transport.send(WSMsgType.TEXT, self._specific_ping_msg)
            self._log.debug(
                f"Sent user specific ping: `{self._specific_ping_msg.decode()}`."
            )
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

    def _decode_frame(self, frame: WSFrame) -> str:
        """Decode the payload of a WebSocket frame safely.

        Args:
            frame (picows.WSFrame): Received WebSocket frame

        Returns:
            str: Decoded payload as UTF-8 text or a placeholder for binary data
        """
        try:
            return frame.get_payload_as_utf8_text()
        except Exception:
            return f"<binary data: {len(frame.get_payload_as_bytes())} bytes>"

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
                    self._log.warning(
                        f"Received close frame. Close code: {str(close_code)}"
                    )
                    return
        except Exception as e:
            import traceback

            self._log.error(
                f"Error processing message: {str(e)}\nTraceback: {traceback.format_exc()}\nws_frame: {self._decode_frame(frame)}"
            )


class WSClient(ABC):
    def __init__(
        self,
        url: str,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        specific_ping_msg: bytes = None,
        reconnect_interval: int = 1,
        ping_idle_timeout: int = 2,
        ping_reply_timeout: int = 1,
        auto_ping_strategy: Literal[
            "ping_when_idle", "ping_periodically"
        ] = "ping_when_idle",
        enable_auto_ping: bool = True,
        enable_auto_pong: bool = False,
        user_pong_callback: Callable[["Listener", WSFrame], bool] | None = None,
    ):
        self._clock = clock
        self._url = url
        self._specific_ping_msg = specific_ping_msg
        self._reconnect_interval = reconnect_interval
        self._ping_idle_timeout = ping_idle_timeout
        self._ping_reply_timeout = ping_reply_timeout
        self._enable_auto_pong = enable_auto_pong
        self._enable_auto_ping = enable_auto_ping
        self._user_pong_callback = user_pong_callback
        self._listener: Listener = None
        self._transport = None
        self._subscriptions = []
        self._callback = handler
        if auto_ping_strategy == "ping_when_idle":
            self._auto_ping_strategy = WSAutoPingStrategy.PING_WHEN_IDLE
        elif auto_ping_strategy == "ping_periodically":
            self._auto_ping_strategy = WSAutoPingStrategy.PING_PERIODICALLY
        self._task_manager = task_manager
        self._log = Logger(name=type(self).__name__)
        self._on_connected: Callable[[], Any] | None = None
        self._on_disconnected: Callable[[], Any] | None = None
        self._on_reconnected: Callable[[], Any] | None = None

    @property
    def connected(self):
        return self._transport and self._listener

    def set_lifecycle_hooks(
        self,
        on_connected: Callable[[], Any] | None = None,
        on_disconnected: Callable[[], Any] | None = None,
        on_reconnected: Callable[[], Any] | None = None,
    ):
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._on_reconnected = on_reconnected

    def _emit_hook(self, hook: Callable[[], Any] | None):
        if hook is None:
            return
        try:
            result = hook()
            if asyncio.iscoroutine(result):
                self._task_manager.create_task(result)
        except Exception as e:
            self._log.error(f"Websocket lifecycle hook error: {e}")

    async def _connect(self):
        self._log.debug(f"Connecting to Websocket at {self._url}...")
        WSListenerFactory = lambda: Listener(  # noqa: E731
            self._callback, self._log, self._specific_ping_msg, self._user_pong_callback
        )
        try:
            self._transport, self._listener = await ws_connect(
                WSListenerFactory,
                self._url,
                enable_auto_ping=self._enable_auto_ping,
                auto_ping_idle_timeout=self._ping_idle_timeout,
                auto_ping_reply_timeout=self._ping_reply_timeout,
                auto_ping_strategy=self._auto_ping_strategy,
                enable_auto_pong=self._enable_auto_pong,
            )
            self._emit_hook(self._on_connected)
        except Exception as e:
            self._log.error(f"Error connecting to websocket: {e}")
            raise e

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
                    self._emit_hook(self._on_reconnected)
                await self._transport.wait_disconnected()
            except Exception as e:
                self._log.error(f"Connection error: {e}")

            if self.connected:
                self._log.warning("Websocket reconnecting...")
                await self.disconnect()
            await asyncio.sleep(self._reconnect_interval)

    def _send(self, payload: dict):
        if not self.connected:
            self._log.warning(f"Websocket not connected. drop msg: {str(payload)}")
            return False
        self._transport.send(WSMsgType.TEXT, msgspec.json.encode(payload))
        return True

    def _send_or_raise(self, payload: dict):
        if not self._send(payload):
            from nexustrader.error import WsRequestNotSentError
            raise WsRequestNotSentError()

    async def disconnect(self):
        if not self.connected:
            return
        self._log.debug("Disconnecting from websocket...")
        transport = self._transport
        self._transport, self._listener = None, None
        transport.disconnect()
        try:
            await asyncio.wait_for(transport.wait_disconnected(), timeout=3.0)
        except asyncio.TimeoutError:
            self._log.warning("WebSocket disconnect timed out after 3s")
        self._emit_hook(self._on_disconnected)

    @abstractmethod
    async def _resubscribe(self):
        pass
