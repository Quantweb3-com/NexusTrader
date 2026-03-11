Simple Buy and Sell
====================

Let's start with a simple buy and sell(cancel) strategy.

First, we need to create a strategy class. You can subscribe the ``bookl1`` data of the ``BTCUSDT.OKX`` symbol in the ``__init__`` method.

.. code-block:: python

        from nexustrader.strategy import Strategy

        class Demo(Strategy):
            def __init__(self):
                super().__init__()
                self.subscribe_bookl1(symbols=["BTCUSDT.OKX"])
                self.signal = True

Then we need to implement the ``on_bookl1`` method to handle the ``bookl1`` data.

.. code-block:: python

        class Demo(Strategy):

            # Existing code...

            def on_bookl1(self, bookl1: BookL1):
                if self.signal:
                    oid = self.create_order(
                        symbol="BTCUSDT.OKX",
                        side=OrderSide.BUY,
                        type=OrderType.LIMIT,
                        price=self.price_to_precision("BTCUSDT.OKX", bookl1.bid),
                        amount=Decimal("0.01"),
                    )

                    # You can also use the `self.create_order` method to create a `SELL` order.

                    self.cancel_order(
                        symbol="BTCUSDT.OKX",
                        oid=oid,
                    )
                    
                    self.signal = False

if you want to check the status of the order, you can use the ``on_cancel_failed_order``, ``on_canceled_order``, ``on_failed_order``, ``on_pending_order``, ``on_accepted_order``, ``on_partially_filled_order``, and ``on_filled_order`` methods. Let's implement them.

.. code-block:: python

        class Demo(Strategy):

            # Existing code...

            def on_cancel_failed_order(self, order: Order):
                print(order)
            
            def on_canceled_order(self, order: Order):
                print(order)
            
            def on_failed_order(self, order: Order):
                print(order)
            
            def on_pending_order(self, order: Order):
                print(order)
            
            def on_accepted_order(self, order: Order):
                print(order)
            
            def on_partially_filled_order(self, order: Order):
                print(order)
            
            def on_filled_order(self, order: Order):
                print(order)

Then we need to create a config file to run the strategy. You need to pass the ``strategy_id``, ``user_id``, ``strategy``, ``basic_config``, ``public_conn_config``, and ``private_conn_config`` to the ``Config`` class.

.. code-block:: python

        config = Config(
            strategy_id="okx_buy_and_sell",
            user_id="user_test",
            strategy=Demo(),
            basic_config={
                ExchangeType.OKX: BasicConfig(
                    api_key=OKX_API_KEY,
                    secret=OKX_SECRET,
                    passphrase=OKX_PASSPHRASE,
                    testnet=True,
                )
            },
            public_conn_config={
                ExchangeType.OKX: [
                    PublicConnectorConfig(
                        account_type=OkxAccountType.DEMO,
                    )
                ]
            },
            private_conn_config={
                ExchangeType.OKX: [
                    PrivateConnectorConfig(
                        account_type=OkxAccountType.DEMO,
                    )
                ]
            }
        )

Finally, you can run the strategy by passing the ``config`` to the ``Engine`` class.

.. code-block:: python

        # Existing code...

        engine = Engine(config)

    if __name__ == "__main__":
        try:
            engine.start()
        finally:
            engine.dispose()

The full code can be found in :download:`buy_and_cancel.py <../../../strategy/okx/buy_and_cancel.py>`.
