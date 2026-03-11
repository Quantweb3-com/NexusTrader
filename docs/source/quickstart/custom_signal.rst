Custom Signal
==============

To use ZeroMQ-based custom signals, install the optional dependency:

.. code-block:: bash

   pip install nexustrader[signal]

Define a signal sender
-----------------------------

You need to send your trading signal to a zmq server. Here we are using the ``ipc`` protocol to send the signal. The signal may have different formats, e.g., ``"BTCUSDT.BBP"``, so we need to format the signal into our trading bot's instrument ID format on the receiver side.

.. code-block:: python

    import zmq
    import json
    import time
    import sys

    # data is a list of mock trading signal
    datas = [
        [{
            "instrumentID": "BTCUSDT.BBP",
            "position": 200,
        }],
        # more trading signal
    ]
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.bind("ipc:///tmp/zmq_data_test")

    index = 0

    def main():
        try:
            time.sleep(5)
            print("Server started, sending data...")
            
            while True:
                print(f"Sending data {datas[index]}")
                data = datas[index]
                socket.send(json.dumps(data).encode())
                index += 1
                if index == len(datas):
                    index = 0
                time.sleep(60)
                
        except KeyboardInterrupt:
            print("Exiting...")
        finally:
            socket.close()
            context.term()
            sys.exit(0)

    if __name__ == "__main__":
        main()

The full code can be found in the :download:`signal_server.py <../../../strategy/bybit/signal_server.py>`.

Build a Receiver
-----------------------------

First, we need to build a receiver to receive the signal. Then pass the ``socket`` to the ``ZeroMQSignalConfig`` in the ``config``.

.. code-block:: python

    import zmq

    context = Context()
    socket = context.socket(zmq.SUB)
    socket.connect("ipc:///tmp/zmq_data_test")
    socket.setsockopt(zmq.SUBSCRIBE, b"")

    config = Config(
        zero_mq_signal_config=ZeroMQSignalConfig(
            socket=socket,
        )
    )


Then, we need to define ``on_custom_signal`` method in the strategy.

.. code-block:: python

    class Demo(Strategy):
        def __init__(self):
            super().__init__()
            # subscribe the symbol here
            ...

        def on_custom_signal(self, signal):
            # implement the trading logic Here
            ...

The full code can be found in the :download:`custom_signal.py <../../../strategy/bybit/custom_signal.py>`.
