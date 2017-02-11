# Copyright © 2016  Lars Peter Søndergaard <lps@chireiden.net>
# Copyright © 2016  FichteFoll <fichtefoll2@googlemail.com>
#
# This file is part of Shanghai, an asynchronous multi-server IRC bot.
#
# Shanghai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Shanghai is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Shanghai.  If not, see <http://www.gnu.org/licenses/>.

import asyncio
from functools import partial
import io
from pprint import pprint
import sys

import colorama

from . import Shanghai
from .config import ShanghaiConfiguration
from .event import global_dispatcher
from .logging import set_default_logger, get_logger, LogLevels


def exception_handler(loop, context):  # pylint: disable=unused-argument
    f = io.StringIO()
    print("Unhandled Exception", file=f)
    print("Message: ", context['message'], file=f)
    print("-- Context --", file=f)
    pprint(context, stream=f)

    print("-- Stack --", file=f)
    task = context.get('task', context.get('future'))
    if hasattr(task, 'print_stack'):
        task.print_stack(file=f)
    else:
        print("Cannot print stack", file=f)

    logger = get_logger("main", "exception_handler")
    logger.error(f.getvalue())


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
        thread_close_evt = asyncio.Event()

        def reader_thread():
            while True:
                try:
                    line = sys.stdin.readline()
                except KeyboardInterrupt:
                    break
                if not line:
                    break
                loop.call_soon_threadsafe(lambda: asyncio.ensure_future(input_handler(line)))

            loop.call_soon_threadsafe(lambda: thread_close_evt.set())

        threading.Thread(target=reader_thread, daemon=True).start()
        await thread_close_evt.wait()

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

    config = ShanghaiConfiguration.from_filename('shanghai.yaml')

    default_logger = get_logger('main', 'main.py', config, open_msg=True)
    set_default_logger(default_logger)
    global_dispatcher.logger = get_logger('main', 'event.py', config)

    try:
        import uvloop
    except ImportError:
        default_logger.debug('Using default event loop.')
    else:
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        default_logger.debug('Using uvloop event loop.')

    loop = asyncio.get_event_loop()
    if default_logger.isEnabledFor(LogLevels.DEBUG):
        loop.set_debug(True)

    bot = Shanghai(config, loop)
    network_tasks = list(bot.init_networks())
    loop.set_exception_handler(exception_handler)

    # For debugging purposes mainly
    async def input_handler(line):
        """Handle stdin input while running. Send lines to networks."""
        split = line.split(None, 1)
        if len(split) < 2:
            return
        nw_name, irc_line = split
        if nw_name and irc_line:
            if nw_name not in bot.networks:
                print("network '{}' not found".format(nw_name))
                return
            network = bot.networks[nw_name]['network']
            network._context.send_line(irc_line)

    print("\nnetworks:", ", ".join(bot.networks.keys()), end="\n\n")
    stdin_reader_task = asyncio.ensure_future(stdin_reader(loop, input_handler))

    try:
        loop.run_until_complete(asyncio.wait(network_tasks, loop=loop))
    except KeyboardInterrupt:
        default_logger.warn("cancelled by user")
        # schedule close event
        bot.stop_networks()
        task = asyncio.wait(network_tasks, loop=loop, timeout=5)
        done, pending = loop.run_until_complete(task)
        if pending:
            default_logger.error("The following tasks didn't terminate within the set "
                                 "timeout: %s", pending)
    else:
        default_logger.info("All network tasks terminated")

    for task in network_tasks:
        if task.done():
            try:
                task.result()  # cause exceptions to be raised
            except:
                default_logger.exception("Network task {!r} errored".format(task))

    if not stdin_reader_task.done():
        stdin_reader_task.cancel()
        try:
            loop.run_until_complete(asyncio.wait_for(stdin_reader_task, 5, loop=loop))
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            default_logger.error("stdin_reader didn't terminate within the set timeout")

    loop.close()
    default_logger.info('Closing now')
