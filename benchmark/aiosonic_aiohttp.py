import asyncio
import time
from decimal import Decimal

import aiohttp
import aiosonic

# 测试参数
NUM_REQUESTS = 10000
TIMEOUT = 2
TEST_URL = "http://127.0.0.1:8080"


async def aio_request(session: aiohttp.ClientSession, index: int):
    try:
        async with session.post(
            TEST_URL, json={"key": "value"}, timeout=TIMEOUT
        ) as response:
            print(f"Aiohttp: Request {index} completed, status: {response.status}")
            return response.status
    except asyncio.TimeoutError:
        print(f"Aiohttp: Request {index} timed out")
        return None
    except Exception as e:
        print(f"Aiohttp: Request {index} failed: {str(e)}")
        return None


async def aiohttp_test():
    async with aiohttp.ClientSession() as session:
        tasks = []
        for i in range(NUM_REQUESTS):
            tasks.append(aio_request(session, i))

        start_time = time.time()
        results = await asyncio.gather(*tasks)
        end_time = time.time()

    successful_requests = sum(1 for result in results if result is not None)
    print(
        f"Aiohttp: {successful_requests}/{NUM_REQUESTS} requests completed successfully"
    )
    return end_time - start_time


async def aiosonic_request(client: aiosonic.HTTPClient, index: int):
    try:
        response = await asyncio.wait_for(
            client.post(TEST_URL, json={"key": "value"}), timeout=TIMEOUT
        )
        print(f"Aiosonic: Request {index} completed, status: {response.status_code}")
        return response.status_code
    except asyncio.TimeoutError:
        print(f"Aiosonic: Request {index} timed out")
        return None
    except Exception as e:
        print(f"Aiosonic: Request {index} failed: {str(e)}")
        return None


async def aiosonic_test():
    client = aiosonic.HTTPClient()
    tasks = []
    for i in range(NUM_REQUESTS):
        tasks.append(aiosonic_request(client, i))

    start_time = time.time()
    results = await asyncio.gather(*tasks)
    end_time = time.time()

    successful_requests = sum(1 for result in results if result is not None)
    print(
        f"Aiosonic: {successful_requests}/{NUM_REQUESTS} requests completed successfully"
    )
    return end_time - start_time


async def run_benchmark():
    print(f"Running benchmark with {NUM_REQUESTS} requests")

    aiosonic_time = await aiosonic_test()
    print(f"aiosonic completed in {aiosonic_time:.2f} seconds")
    print(f"aiosonic requests per second: {NUM_REQUESTS / aiosonic_time:.2f}")

    aiohttp_time = await aiohttp_test()
    print(f"aiohttp completed in {aiohttp_time:.2f} seconds")
    print(f"aiohttp requests per second: {NUM_REQUESTS / aiohttp_time:.2f}")

    speedup = Decimal(aiohttp_time) / Decimal(aiosonic_time)
    print(f"aiosonic is {speedup:.2f}x faster than aiohttp")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
