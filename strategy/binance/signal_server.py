import zmq
import msgspec
import time
import sys


datas = [
    [
        {
            "instrumentID": "BTCUSDT.BBP",
            "position": 7,
            "wait": 60,
        }
    ],
    [
        {
            "instrumentID": "BTCUSDT.BBP",
            "position": 5,
            "wait": 5,
        }
    ],
    [
        {
            "instrumentID": "BTCUSDT.BBP",
            "position": 3,
            "wait": 5,
        }
    ],
    [
        {
            "instrumentID": "BTCUSDT.BBP",
            "position": 5,
            "wait": 5,
        }
    ],
    [
        {
            "instrumentID": "BTCUSDT.BBP",
            "position": 5,
            "wait": 5,
        }
    ],
    [
        {
            "instrumentID": "BTCUSDT.BBP",
            "position": 5,
            "wait": 5,
        }
    ],
    [
        {
            "instrumentID": "BTCUSDT.BBP",
            "position": 5,
            "wait": 5,
        }
    ],
    [
        {
            "instrumentID": "BTCUSDT.BBP",
            "position": 3,
            "wait": 5,
        }
    ],
    [
        {
            "instrumentID": "BTCUSDT.BBP",
            "position": 5,
            "wait": 5,
        }
    ],
    [
        {
            "instrumentID": "BTCUSDT.BBP",
            "position": 5,
            "wait": 5,
        }
    ],
    [
        {
            "instrumentID": "BTCUSDT.BBP",
            "position": 5,
            "wait": 5,
        }
    ],
]
context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind("ipc:///tmp/zmq_data_test")

index = 0


try:
    time.sleep(5)
    print("Server started, sending data...")

    while True:
        print(f"Sending data {datas[index]}")
        data = datas[index]
        socket.send(msgspec.json.encode(data))
        wait = datas[index][0]["wait"]
        index += 1
        if index == len(datas):
            index = 0
        time.sleep(wait)

except KeyboardInterrupt:
    print("Exiting...")
finally:
    socket.close()
    context.term()
    sys.exit(0)
