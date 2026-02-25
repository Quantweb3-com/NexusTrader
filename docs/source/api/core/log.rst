nexustrader.core.nautilius_core
================================

.. currentmodule:: nexustrader.core.nautilius_core

This module exposes Rust-powered core components (via ``nautilus_pyo3``) including the
high-performance logger, message bus, and clock used throughout NexusTrader.

These classes are implemented in Rust and wrapped via PyO3; full member introspection is
not available at documentation build time.

Logger
------

``Logger`` is the structured logger used throughout NexusTrader. Access it from a strategy via
``self.log``:

.. code-block:: python

    self.log.info("Order placed")
    self.log.warning("Unusual spread detected")
    self.log.error("Connection lost")

MessageBus
----------

``MessageBus`` is a high-performance, Rust-backed publish/subscribe bus. It routes internal
events (order updates, market data) between components without going through Python overhead.

LiveClock
---------

``LiveClock`` provides a monotonic, high-resolution wall clock used by the engine for
timestamping events.
