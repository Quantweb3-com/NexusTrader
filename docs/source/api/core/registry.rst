nexustrader.core.registry
===============================

.. currentmodule:: nexustrader.core.registry

The OrderRegistry class tracks active orders by their internal OID (Order ID). It provides
methods to register, query, and unregister orders, as well as temporary order storage for
orders that are being submitted to the exchange.

Key methods:

- ``register_order(oid)`` -- mark an OID as active
- ``is_registered(oid)`` -- check whether an OID is active
- ``unregister_order(oid)`` -- remove an OID from the active set
- ``register_tmp_order(order)`` -- store an ``Order`` object temporarily before it is acknowledged
- ``get_tmp_order(oid)`` -- retrieve a temporarily stored order by OID
- ``unregister_tmp_order(oid)`` -- remove a temporarily stored order

Class Overview
-----------------

.. autoclass:: OrderRegistry
   :members: 
   :undoc-members:
   :show-inheritance:
