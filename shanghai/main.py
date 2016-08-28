
import asyncio
from pprint import pprint

from .core import Shanghai
from .config import Configuration
from .logging import get_logger


core_logger = None


def exception_handler(loop, context):
    import io
    import contextlib
    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        print("exception_handler context:")
        pprint(context)
    core_logger.error(f.getvalue())
    if 'task' in context:
        context['task'].print_stack()


def main():
    global core_logger

    config = Configuration.from_filename('shanghai.yaml')
    core_logger = get_logger('shanghai', 'main.py', config)

    try:
        import uvloop
    except ImportError:
        # TODO: use a proper terminal color tool in the future (e.g. colorama)
        # ... and possibly hook it up with the logging module.
        core_logger.debug('\033[32;1mUsing default event loop.\033[0m')
    else:
        core_logger.debug('\033[32;1mUsing uvloop event loop.\033[0m')
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    bot = Shanghai(config)
    network_tasks = list(bot.init_networks())
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(exception_handler)
    try:
        loop.run_until_complete(asyncio.wait(network_tasks, loop=loop))
    except KeyboardInterrupt:
        core_logger.info("[!] cancelled by user")
        # schedule close event
        task = asyncio.wait([n['network'].stop_running("KeyboardInterrupt")
                             for n in bot.networks.values()],
                            loop=loop)
        loop.run_until_complete(task)
        # wait again until networks have disconnected
        loop.run_until_complete(asyncio.wait(network_tasks, loop=loop))
