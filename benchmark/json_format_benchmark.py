import time
import json
import ujson
import orjson
import random
import string
from yapic import json as yjson


def random_string(length=10):
    """Generate a random string of fixed length"""
    letters = string.ascii_lowercase
    return "".join(random.choice(letters) for i in range(length))


def generate_test_data():
    return {
        "name": random_string(10),
        "array": list(range(10000)),
        "nested": {"subarray": list(range(100)), "value": random_string(100)},
    }


def benchmark(func, data, rounds=200):
    times = []
    for _ in range(rounds):
        start_time = time.time()
        func(data)
        times.append(time.time() - start_time)
    return sum(times) / len(times)


# Test data
data = generate_test_data()

# Ensure all JSON libraries can serialize and deserialize the same data
assert data == json.loads(json.dumps(data))
assert data == ujson.loads(ujson.dumps(data))
assert data == orjson.loads(orjson.dumps(data))
assert data == yjson.loads(yjson.dumps(data))

# Benchmark
json_dump_time = benchmark(json.dumps, data)
json_load_time = benchmark(lambda x: json.loads(json.dumps(x)), data)

ujson_dump_time = benchmark(ujson.dumps, data)
ujson_load_time = benchmark(lambda x: ujson.loads(ujson.dumps(x)), data)

orjson_dump_time = benchmark(orjson.dumps, data)
orjson_load_time = benchmark(lambda x: orjson.loads(orjson.dumps(x)), data)

yjson_dump_time = benchmark(yjson.dumps, data)
yjson_load_time = benchmark(lambda x: yjson.loads(yjson.dumps(x)), data)

# Print results
print(f"json dump: {json_dump_time:.5f}s, load: {json_load_time:.5f}s")
print(f"ujson dump: {ujson_dump_time:.5f}s, load: {ujson_load_time:.5f}s")
print(f"orjson dump: {orjson_dump_time:.5f}s, load: {orjson_load_time:.5f}s")
print(f"yjson dump: {yjson_dump_time:.5f}s, load: {yjson_load_time:.5f}s")
