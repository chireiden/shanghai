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
import io
import itertools
import re
import time
from typing import Any, Iterator, List, cast
from typing.re import Match

from .connection import Connection
from .config import NetworkConfiguration, Server
from .event import (NetworkEvent, GlobalEventName, NetworkEventName,
                    global_dispatcher, global_event, Priority, EventDispatcher, ReturnValue)
from .irc import Message, Options, ServerReply
from .logging import get_logger, Logger
from .util import ShadowAttributesMixin


class NetworkContext(ShadowAttributesMixin):

    def __init__(self, network: 'Network', *, logger: Logger=None) -> None:
        super().__init__()
        self.network = network
        if logger is None:
            logger = network.logger
        self.logger = logger

    def send_bytes(self, line: bytes) -> None:
        self.network.send_bytes(line)


class Network:
    """Sample Network class"""

    registered: bool
    nickname: str
    user: str
    realname: str
    vhost: str
    options: Options

    event_queue: asyncio.Queue
    _connection: Connection
    _context: NetworkContext
    _worker_task: asyncio.Task
    _connection_task: asyncio.Task

    def __init__(self, config: NetworkConfiguration, loop: asyncio.AbstractEventLoop = None) \
            -> None:
        self.name = config.name
        self.config = config
        self.loop = loop or asyncio.get_event_loop()
        self.logger = get_logger('network', self.name, config)

        self._server_iter: Iterator[Server] = itertools.cycle(self.config.servers)
        self._worker_task_failure_timestamps: List[float] = []

        self._reset()

    def _reset(self) -> None:
        self.registered = False
        self.nickname = ""
        self.user = ""
        self.realname = ""
        self.vhost = ""
        self.options = Options()

        self.stopped = False
        self.connected = False

        server = next(self._server_iter)
        self.event_queue = asyncio.Queue()
        self._connection = Connection(server, self.event_queue, self.loop, logger=self.logger)

    async def _build_context(self) -> NetworkContext:
        ctx = NetworkContext(self)
        self.logger.debug("building context")

        self._nw_evt_disp = NetworkEventDispatcher(ctx)
        ctx.add_attribute('network_event', self._nw_evt_disp.decorator)

        self.logger.debug("intializing NetworkContext")
        await global_dispatcher.dispatch(GlobalEventName.INIT_NETWORK_CTX, ctx)

        return ctx

    async def run(self) -> None:
        self._context = await self._build_context()
        self.logger.debug("context:", self._context)

        for retry in itertools.count(1):
            self._connection_task = self.loop.create_task(self._connection.run())
            self._worker_task = self.loop.create_task(self._worker())
            self._worker_task.add_done_callback(self._worker_done)

            try:
                await self._connection_task
            except Exception:
                self.logger.exception("Connection Task errored")

            # Wait until worker task emptied the queue (and terminates)
            await self._worker_task
            if self.stopped:
                return

            # We didn't stop, so try to reconnect after a timeout
            seconds = 10 * retry
            self.logger.info(f"Retry connecting in {seconds} seconds")
            await asyncio.sleep(seconds)  # TODO doesn't terminate if KeyboardInterrupt occurs here
            self._reset()

    def _worker_done(self, task: asyncio.Future) -> None:
        # Task.add_done_callback expects a Future as the argument of the callable.
        # https://github.com/python/typeshed/pull/1614
        assert task is self._worker_task
        task = cast(asyncio.Task, task)
        if task.cancelled():
            self._connection_task.cancel()
        else:
            if not task.exception():
                self.logger.debug("Worker task exited gracefully")
                return

            f = io.StringIO()
            task.print_stack(file=f)
            self.logger.error(f.getvalue())

            now = time.time()
            self._worker_task_failure_timestamps.append(time.time())
            if len(self._worker_task_failure_timestamps) == 5:
                if self._worker_task_failure_timestamps.pop(0) >= now - 10:
                    self.logger.error("Worker task exceeded exception threshold; terminating")
                    self._close("Exception threshold exceeded")
                    return

            self.logger.warning("Restarting worker task")
            self._worker_task = self.loop.create_task(self._worker())
            self._worker_task.add_done_callback(self._worker_done)

    async def _worker(self) -> None:
        """Dispatches events from the event queue."""
        while not (self._connection_task.done() and self.event_queue.empty()):
            event = await self.event_queue.get()
            self.logger.debug(event)
            await self._nw_evt_disp.dispatch_nwevent(event)

    def _close(self, quitmsg: str = None) -> None:
        self.logger.info("closing network")
        self._connection.close()
        self.stopped = True

    def send_bytes(self, line: bytes) -> None:
        self._connection.writeline(line)

    def request_close(self, quitmsg: str = None) -> None:
        event = NetworkEvent(NetworkEventName.CLOSE_REQUEST, quitmsg)
        self.event_queue.put_nowait(event)


class NetworkEventDispatcher(EventDispatcher):

    def __init__(self, context: NetworkContext, logger: Logger = None) -> None:
        super().__init__(logger)
        self.context = context
        self.decorator.allowed_names = set(NetworkEventName.__members__.values())

    async def dispatch_nwevent(self, event: NetworkEvent) -> ReturnValue:
        return await self.dispatch(event.name, self.context, event.value)


# Core event handlers #############################################################################

@global_event(GlobalEventName.INIT_NETWORK_CTX, priority=Priority.CORE)
async def init_context(ctx: NetworkContext) -> None:
    ctx.logger.debug("running init_context in network.py")

    @ctx.network_event.core(NetworkEventName.CONNECTED)
    async def on_connected(ctx: NetworkContext, _: Any) -> None:
        ctx.network.connected = True
        ctx.logger.info("connected!")

    @ctx.network_event.core(NetworkEventName.DISCONNECTED)
    async def on_disconnected(ctx: NetworkContext, _: Any) -> None:
        ctx.logger.info('connection closed by peer!')

    @ctx.network_event(NetworkEventName.CLOSE_REQUEST, priority=Priority.POST_CORE)
    # Lower than core to allow core plugins to eat the event
    async def on_close_request(ctx: NetworkContext, _: Any) -> None:
        if ctx.network.connected:
            ctx.logger.info('closing connection')
            ctx.network._close()
        else:
            ctx.logger.info('closing connection prematurely')
            # Because we got "close_now" before "connected",
            # a connection has likely not been established yet.
            # So we cancel the task instead of closing the connection.
            if not ctx.network._connection_task.done():
                ctx.network._connection_task.cancel()
            ctx.network.stopped = True

    @ctx.message_event.core(ServerReply.RPL_WELCOME)
    async def on_msg_welcome(ctx: NetworkContext, message: Message) -> None:
        ctx.network.nickname = message.params[0]
        ctx.send_cmd('MODE', ctx.network.nickname, '+B')

        # join channels
        for channel, chanconf in ctx.network.config.get('channels', {}).items():
            key = chanconf.get('key', None)
            if key is not None:
                ctx.send_cmd('JOIN', channel, key)
            else:
                ctx.send_cmd('JOIN', channel)

    @ctx.network_event.core(NetworkEventName.CONNECTED)
    async def register_connection(ctx: NetworkContext, _: Any) -> None:
        # testing
        network = ctx.network
        network.nickname = network.config['nick']
        network.user = network.config['user']
        network.realname = network.config['realname']
        ctx.send_cmd('NICK', network.nickname)
        ctx.send_cmd('USER', network.user, '*', '*', network.realname)

        @ctx.message_event.core(ServerReply.ERR_NICKNAMEINUSE)
        async def nick_in_use(ctx: NetworkContext, _: Any) -> None:
            def inc_suffix(m: Match[str]) -> str:
                num = m.group(1) or 0
                return str(int(num) + 1)
            ctx.network.nickname = re.sub(r"(\d*)$", inc_suffix, ctx.network.nickname)
            ctx.send_cmd('NICK', ctx.network.nickname)

        # Clear the above hooks since we only want to negotiate a nick until we found a free one
        @ctx.message_event.core(ServerReply.RPL_WELCOME)
        async def register_done(ctx: NetworkContext, _: Any) -> None:
            nick_in_use.unregister()
            register_done.unregister()
