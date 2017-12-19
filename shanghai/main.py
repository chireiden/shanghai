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
from typing import Any, Awaitable, Callable, Dict

import colorama

from . import Shanghai
from .config import ShanghaiConfiguration
from .logging import set_default_logger, get_logger, LogLevels


def exception_handler(loop: asyncio.AbstractEventLoop, context: Dict[str, Any]) -> None:
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


async def stdin_reader(loop: asyncio.AbstractEventLoop,
                       input_handler: Callable[[str], Awaitable]
                       ) -> None:
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
                loop.call_soon_threadsafe(lambda: loop.create_task(input_handler(line)))

            loop.call_soon_threadsafe(lambda: thread_close_evt.set())

        threading.Thread(target=reader_thread, daemon=True).start()
        await thread_close_evt.wait()

    else:
        reader = asyncio.StreamReader()
        make_protocol = partial(asyncio.StreamReaderProtocol, reader)
        await loop.connect_read_pipe(make_protocol, sys.stdin)

        while True:
            line_bytes = await reader.readline()
            line = line_bytes.decode(sys.stdin.encoding)
            if not line:
                break
            loop.create_task(input_handler(line))

        print("stdin stream closed")


def main() -> None:
    colorama.init()

    config = ShanghaiConfiguration.from_filename('shanghai.yaml')

    default_logger = get_logger('main', 'main.py', config, open_msg=True)
    set_default_logger(default_logger)

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
    async def input_handler(line: str) -> None:
        """Handle stdin input while running. Send lines to networks."""
        split = line.split(None, 1)
        if len(split) < 2:
            return
        nw_name, irc_line = split
        if nw_name and irc_line:
            if nw_name not in bot.networks:
                print(f"network {nw_name!r} not found")
                return
            network = bot.networks[nw_name]['network']
            network.send_bytes(irc_line.encode('utf-8'))

    print("\nnetworks:", ", ".join(bot.networks.keys()), end="\n\n")
    stdin_reader_task = asyncio.ensure_future(stdin_reader(loop, input_handler))

    try:
        loop.run_until_complete(asyncio.wait(network_tasks, loop=loop))
    except KeyboardInterrupt:
        default_logger.warn("Cancelled by user")
        # schedule close event
        bot.stop_networks()
        task = asyncio.wait(network_tasks, loop=loop, timeout=5)
        done, pending = loop.run_until_complete(task)
        if pending:
            default_logger.error("The following tasks didn't terminate"
                                 f" within the set timeout: {pending}")
    else:
        default_logger.info("All network tasks terminated")

    for task in network_tasks:
        if task.done():
            try:
                task.result()  # cause exceptions to be raised
            except Exception:
                default_logger.exception(f"Network task {task!r} errored")

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
