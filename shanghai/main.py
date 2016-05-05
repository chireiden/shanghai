
import asyncio

from .core import Shanghai
from .config import Configuration


def exception_handler(task, context):
    print(task)
    print(context)
    raise context['exception']


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

    config = Configuration('shanghai.ini')
    bot = Shanghai(config)
    tasks = list(bot.init_networks())
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(exception_handler)
    loop.run_until_complete(asyncio.wait(tasks))
