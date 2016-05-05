
import asyncio

from .core import Shanghai
from .client import Client
from .network import Network


def main():
    try:
        import uvloop
    except ImportError:
        # TODO: use a proper terminal color tool in the future (e.g. colorama)
        # ... and possibly hook it up with the logging module.
        print('\033[32;1mUsing default event loop.\033[0m')
    else:
        print('\033[32;1mUsing uvloop event loop.\033[0m')
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    loop = asyncio.get_event_loop()
    queue = asyncio.Queue(100)
    bot = Shanghai()
    bot.client = Client('localhost', 6667, queue, loop=loop)

    network = Network(queue)

    worker_task = network.worker()
    bot_task = bot.client.run()
    loop.run_until_complete(asyncio.wait([
        worker_task,
        bot_task,
    ]))
