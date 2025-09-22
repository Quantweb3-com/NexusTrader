"""Background web server runner for strategy FastAPI apps."""

from __future__ import annotations

import asyncio
import threading

import uvicorn
from fastapi import FastAPI
import platform


class StrategyWebServer:
    """Run a FastAPI application in a dedicated background thread."""

    def __init__(
        self,
        app: FastAPI,
        *,
        host: str = "0.0.0.0",
        port: int = 8000,
        log_level: str = "info",
    ) -> None:
        self._app = app
        self._host = host
        self._port = port
        self._log_level = log_level

        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()

    @property
    def app(self) -> FastAPI:
        return self._app

    def start(self) -> None:
        if self._server is not None:
            return

        try:
            import uvloop  # type: ignore  # noqa: F401

            _uvloop_available = True
        except Exception:
            _uvloop_available = False

        loop_type = (
            "uvloop"
            if platform.system() in {"Linux", "Darwin"} and _uvloop_available
            else "asyncio"
        )

        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level=self._log_level,
            loop=loop_type,
            lifespan="on",
        )
        self._server = uvicorn.Server(config)

        def _run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._started.set()
            try:
                loop.run_until_complete(self._server.serve())
            finally:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()

        self._thread = threading.Thread(
            target=_run, name="StrategyWebServer", daemon=True
        )
        self._thread.start()
        self._started.wait()

    def stop(self) -> None:
        if not self._server:
            return

        self._server.should_exit = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._server = None
        self._thread = None
        self._started.clear()
