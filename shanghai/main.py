
import traceback
import asyncio
from pprint import pprint
import sys
import io

import colorama

from .core import Shanghai
from .config import Configuration
from .logging import current_logger, LogContext, set_logging_config


def exception_handler(loop, context):  # pylint: disable=unused-argument
    f = io.StringIO()
    print("=== Unhandled Exception ===", file=f)
    print("- Context -", file=f)
    pprint(context, stream=f)
    traceback.print_exc(file=f)
    print("- Stack -", file=f)
    # print(colorama.Fore.RED, file=f, end='')
    if 'task' in context:
        context['task'].print_stack(file=f)
    elif 'future' in context:
        context['future'].print_stack(file=f)
    # print(colorama.Fore.RESET, file=f, end='')
    print("===========================", file=f)
    print(f.getvalue())


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
                try:
                    line_bytes = await reader.readline()
                except asyncio.CancelledError:
                    return
                line = line_bytes.decode(sys.stdin.encoding)
                if not line:
                    break
                loop.create_task(input_handler(line))

        print("stdin stream closed")
    except:  # pylint: disable=bare-except
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
        stdin_reader_task = asyncio.ensure_future(
            stdin_reader(loop, input_handler))

        try:
            loop.run_until_complete(asyncio.wait(network_tasks, loop=loop))
        except KeyboardInterrupt:
            current_logger.warn("cancelled by user")
            # schedule close event
            bot.stop_networks()
            task = asyncio.wait(network_tasks, loop=loop, timeout=5)
            done, pending = loop.run_until_complete(task)
            if pending:
                current_logger.error("The following tasks didn't terminate within the set "
                                     "timeout: %s", pending)

        stdin_reader_task.cancel()
        loop.run_until_complete(stdin_reader_task)

        current_logger.info('Closing now.')
