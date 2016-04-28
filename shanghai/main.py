
import asyncio

from .core import Shanghai
from .client import Client
from .network import Network


def main():
    loop = asyncio.get_event_loop()
    queue = asyncio.Queue(100)
    bot = Shanghai()
    bot.client = Client('localhost', 6667, queue, loop=loop)

    network = Network()

    worker_task = network.worker(queue)
    bot_task = bot.client.run()
    loop.run_until_complete(asyncio.wait([
        worker_task,
        bot_task,
    ]))
