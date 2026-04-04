nexustrader.core.nautilius_core
================================

.. currentmodule:: nexustrader.core.nautilius_core

This module provides the core infrastructure components used throughout NexusTrader:
the logger, message bus, and clock. Since version 0.3.7 these are pure-Python
implementations and no longer depend on ``nautilus-trader``. Since version 0.3.21
the logging backend is `picologging <https://github.com/microsoft/picologging>`_,
a C-extension logger that is 4–10× faster than the standard ``logging`` module.

Logger
------

``Logger`` is the structured logger used throughout NexusTrader. Access it from a
strategy via ``self.log``:

.. code-block:: python

    self.log.info("Order placed")
    self.log.warning("Unusual spread detected")
    self.log.error("Connection lost")

    # Optional color hint (ignored if the terminal does not support ANSI):
    from nexustrader.constants import LogColor
    self.log.info("Golden Cross signal!", color=LogColor.GREEN)

Log levels (lowest → highest): ``TRACE``, ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``.

.. note::

   Since 0.3.21, ``TRACE`` calls are emitted at ``DEBUG`` severity because
   ``picologging`` does not support custom log levels.  The ``trace()`` method
   still exists on the ``Logger`` shim for source compatibility.

Configure the minimum level via :class:`~nexustrader.config.LogConfig`:

.. code-block:: python

    from nexustrader.config import Config, LogConfig

    config = Config(
        ...,
        log_config=LogConfig(level_stdout="DEBUG"),
    )

MessageBus
----------

``MessageBus`` is the in-process pub/sub and point-to-point routing bus. It connects
internal components (connectors, EMS, OMS, strategies) without polling overhead.

Two communication patterns:

- **Topic (fan-out)** — ``subscribe(topic, handler)`` / ``publish(topic, msg)``:
  one publisher, many subscribers.
- **Endpoint (point-to-point)** — ``register(endpoint, handler)`` / ``send(endpoint, msg)``:
  exactly one registered handler per endpoint.

LiveClock
---------

``LiveClock`` exposes the current wall-clock time and drives repeating timers.

**Time accessors**

.. code-block:: python

    clock.timestamp()     # float  — seconds since epoch
    clock.timestamp_ms()  # int    — milliseconds since epoch
    clock.timestamp_ns()  # int    — nanoseconds since epoch
    clock.utc_now()       # datetime (UTC)

**Timers**

.. code-block:: python

    from datetime import datetime, timedelta, timezone
    from nexustrader.core.nautilius_core import TimeEvent

    def on_tick(event: TimeEvent) -> None:
        print(event.ts_event, event.ts_init)  # nanoseconds

    clock.set_timer(
        name="my_timer",
        interval=timedelta(seconds=1),
        start_time=datetime.now(tz=timezone.utc) + timedelta(seconds=1),
        stop_time=None,       # runs indefinitely
        callback=on_tick,
    )

    clock.cancel_timer("my_timer")

TimeEvent
---------

Emitted by ``LiveClock`` when a timer fires.

.. code-block:: python

    @dataclass
    class TimeEvent:
        name: str     # timer name
        ts_event: int # scheduled fire time (nanoseconds, UTC epoch)
        ts_init: int  # actual call time   (nanoseconds, UTC epoch)
