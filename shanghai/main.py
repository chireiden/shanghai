
import asyncio
from functools import partial
import io
from pprint import pprint
import sys

import colorama

from .core import Shanghai
from .config import Configuration
from .logging import current_logger, LogContext, set_logging_config


def exception_handler(loop, context):  # pylint: disable=unused-argument
    f = io.StringIO()
    print("=== Unhandled Exception ===", file=f)
    print("- Context -", file=f)
    pprint(context, stream=f)
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
    if sys.platform == 'win32':
        # Windows can't use SelectorEventLoop.connect_read_pipe
        # and ProactorEventLoop.connect_read_pipe apparently
        # doesn't work with sys.* streams or files.
        # http://stackoverflow.com/questions/31510190/aysncio-cannot-read-stdin-on-windows
        #
        # Running polling in an executor (thread) doesn't work properly either
        # since there is absolutely no way to stop the executor (sys.stdin.readline)
        # and make the program terminate.
        # So instead, we spawn a custom daemon thread.
        # Fuck yeah asyncio!
        import threading

        def reader_thread():
            while True:
                try:
                    line = sys.stdin.readline()
                except KeyboardInterrupt:
                    # Wake the main loop to make it realize that an exception has been thrown.
                    # This feels so dirty ...
                    loop.call_soon_threadsafe(lambda: None, loop=loop)
                    break

                if not line:
                    break
                loop.call_soon_threadsafe(lambda: asyncio.ensure_future(input_handler(line),
                                                                        loop=loop))

            print("stdin stream closed")

        threading.Thread(target=reader_thread, daemon=True).start()

    else:
        reader = asyncio.StreamReader()
        await loop.connect_read_pipe(partial(asyncio.StreamReaderProtocol, reader), sys.stdin)

        while True:
            line_bytes = await reader.readline()
            line = line_bytes.decode(sys.stdin.encoding)
            if not line:
                break
            asyncio.ensure_future(input_handler(line), loop=loop)

        print("stdin stream closed")


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
        loop = asyncio.get_event_loop()
        loop.set_debug(True)
        loop.set_exception_handler(exception_handler)

        # For debugging purposes mainly
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
                network.send_line(irc_line)

        print("\nnetworks:", ", ".join(bot.networks.keys()), end="\n\n")
        stdin_reader_task = asyncio.ensure_future(stdin_reader(loop, input_handler))

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
        else:
            current_logger.info("All network tasks terminated")

        if not stdin_reader_task.done():
            stdin_reader_task.cancel()
            try:
                loop.run_until_complete(asyncio.wait_for(stdin_reader_task, 5, loop=loop))
            except asyncio.CancelledError:
                pass
            except asyncio.TimeoutError:
                current_logger.error("stdin_reader didn't terminate within the set timeout")

        loop.close()
        current_logger.info('Closing now')
