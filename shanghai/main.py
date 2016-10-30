
import asyncio
from pprint import pprint
import sys

import colorama

from .core import Shanghai
from .config import Configuration
from .logging import current_logger, LogContext, set_logging_config


def exception_handler(loop, context):
    import io
    f = io.StringIO()
    print("exception_handler context:", file=f)
    pprint(context, stream=f)
    if 'task' in context:
        context['task'].print_stack(file=f)
    elif 'future' in context:
        context['future'].print_stack(file=f)
    current_logger.error(f.getvalue())


async def stdin_reader(loop, input_handler):
    try:
        if sys.platform == 'win32':
            # Windows can't use SelectorEventLoop.connect_read_pipe
            # and ProactorEventLoop.connect_read_pipe apparently
            # doesn't work with sys.* streams or files.
            # Instead, run polling in an executor (thread).
            # http://stackoverflow.com/questions/31510190/aysncio-cannot-read-stdin-on-windows
            while True:
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    break
                loop.create_task(input_handler(line))
        else:
            reader = asyncio.StreamReader()
            reader_protocol = asyncio.StreamReaderProtocol(reader)
            await loop.connect_read_pipe(lambda: reader_protocol, sys.stdin)

            while True:
                line_bytes = await reader.readline()
                line = line_bytes.decode(sys.stdin.encoding)
                if not line:
                    break
                loop.create_task(input_handler(line))

        print("stdin stream closed")
    except:
        import traceback
        traceback.print_exc()


def main():
    colorama.init()

    config = Configuration.from_filename('shanghai.yaml')
    set_logging_config({key: value for key, value in config.items() if
                        key in ('logging', 'timezone')})

    with LogContext('shanghai', 'main.py'):
        try:
            import uvloop
        except ImportError:
            current_logger.debug('Using default event loop.')
        else:
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            current_logger.debug('Using uvloop event loop.')

        bot = Shanghai(config)
        network_tasks = list(bot.init_networks())
        print("\nnetworks:", ", ".join(bot.networks.keys()), end="\n\n")

        async def input_handler(line):
            """Handle stdin input while running. Send lines to networks."""
            if ' ' not in line:
                return
            nw_name, irc_line = line.split(None, 1)
            if nw_name and irc_line:
                if nw_name not in bot.networks:
                    print("network '{}' not found".format(nw_name))
                    return
                network = bot.networks[nw_name]['network']
                network.sendline(irc_line)

        loop = asyncio.get_event_loop()
        loop.set_debug(True)
        loop.set_exception_handler(exception_handler)
        loop.create_task(stdin_reader(loop, input_handler))

        try:
            loop.run_until_complete(asyncio.wait(network_tasks, loop=loop))
        except KeyboardInterrupt:
            current_logger.warn("[!] cancelled by user")
            # schedule close event
            task = asyncio.wait([n['network'].stop_running("KeyboardInterrupt")
                                 for n in bot.networks.values()],
                                loop=loop)
            loop.run_until_complete(task)
            # wait again until networks have disconnected
            loop.run_until_complete(asyncio.wait(network_tasks, loop=loop))

        current_logger.info('Closing now.')
