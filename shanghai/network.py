# Shanghai - Multiserver Asyncio IRC Bot
# Copyright © 2016  Lars Peter Søndergaard <lps@chireiden.net>
# Copyright © 2016  FichteFoll <fichtefoll2@googlemail.com>
#
# This file is part of Shanghai.
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

from .connection import Connection
from .event import (NetworkEvent, GlobalEventName, NetworkEventName,
                    global_dispatcher, global_event, Priority,
                    NetworkEventDispatcher)
from .irc import Options, ServerReply
from .logging import get_logger, Logger
from .util import ShadowAttributesMixin


class Network:
    """Sample Network class"""

    def __init__(self, config, loop=None):
        self.name = config.name
        self.config = config
        self.loop = loop
        self.logger = get_logger('network', self.name, config)

        self.event_queue = None

        self._server_iter = itertools.cycle(self.config.servers)
        self._connection = None
        self._context = None
        self._worker_task_failure_timestamps = []

        self._reset()

    def _reset(self):
        self.registered = False
        self.nickname = None
        self.user = None
        self.realname = None
        self.vhost = None
        self.options = Options()

        self._connection_task = None
        self._worker_task = None
        self.stopped = False
        self.connected = False

        server = next(self._server_iter)
        self.event_queue = asyncio.Queue()
        self._connection = Connection(server, self.event_queue, self.loop, logger=self.logger)

    async def _build_context(self):
        ctx = NetworkContext(self)
        self.logger.debug("building context")

        self._nw_evt_disp = NetworkEventDispatcher(ctx)
        ctx.add_attribute('network_event', self._nw_evt_disp.decorator)

        self.logger.debug("intializing NetworkContext")
        await global_dispatcher.dispatch(GlobalEventName.INIT_NETWORK_CTX, ctx)

        return ctx

    async def run(self):
        self._context = await self._build_context()
        self.logger.debug("context:", self._context)

        for retry in itertools.count(1):
            self._connection_task = asyncio.ensure_future(self._connection.run())
            self._worker_task = asyncio.ensure_future(self._worker())
            self._worker_task.add_done_callback(self._worker_done)

            try:
                await self._connection_task
            except:
                self.logger.exception("Connection Task errored")

            # Wait until worker task emptied the queue (and terminates)
            await self._worker_task
            if self.stopped:
                return

            # We didn't stop, so try to reconnect after a timeout
            seconds = 10 * retry
            self.logger.info('Retry connecting in {} seconds'.format(seconds))
            await asyncio.sleep(seconds)  # TODO doesn't terminate if KeyboardInterrupt occurs here
            self._reset()

    def _worker_done(self, task):
        assert task is self._worker_task
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
            self._worker_task = asyncio.ensure_future(self._worker())
            self._worker_task.add_done_callback(self._worker_done)

    async def _worker(self):
        """Dispatches events from the event queue."""
        while not (self._connection_task.done() and self.event_queue.empty()):
            event = await self.event_queue.get()
            self.logger.debug(event)
            await self._nw_evt_disp.dispatch(event)

    def _close(self, quitmsg: str = None):
        self.logger.info("closing network")
        self._connection.close()
        self.stopped = True

    def send_bytes(self, line: bytes):
        self._connection.writeline(line)

    def request_close(self, quitmsg: str = None):
        event = NetworkEvent(NetworkEventName.CLOSE_REQUEST, quitmsg)
        self.event_queue.put_nowait(event)


class NetworkContext(ShadowAttributesMixin):

    def __init__(self, network, *, logger: Logger=None):
        super().__init__()
        self.network = network
        if logger is None:
            logger = network.logger
        self.logger = logger

    def send_bytes(self, line: bytes):
        self.network.send_bytes(line)


# Core event handlers #############################################################################

@global_event(GlobalEventName.INIT_NETWORK_CTX, priority=Priority.CORE)
async def init_context(ctx):
    ctx.logger.debug("running init_context in network.py")

    @ctx.network_event.core(NetworkEventName.CONNECTED)
    async def on_connected(ctx, _):
        ctx.network.connected = True
        ctx.logger.info("connected!")

    @ctx.network_event.core(NetworkEventName.DISCONNECTED)
    async def on_disconnected(ctx, _):
        ctx.logger.info('connection closed by peer!')

    @ctx.network_event(NetworkEventName.CLOSE_REQUEST, priority=Priority.POST_CORE)
    async def on_close_request(ctx, _):
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
    async def on_msg_welcome(ctx, message):
        ctx.network.nickname = message.params[0]
        ctx.send_cmd('MODE', ctx.network.nickname, '+B')

        # join channels
        for channel, chanconf in ctx.network.config.get('channels', {}).items():
            key = chanconf.get('key', None)
            if key is not None:
                ctx.send_cmd('JOIN', channel, key)
            else:
                ctx.send_cmd('JOIN', channel)

    @ctx.message_event.core(ServerReply.RPL_ISUPPORT)
    async def on_msg_isupport(ctx, message):
        ctx.network.options.extend_from_message(message)

    @ctx.network_event.core(NetworkEventName.CONNECTED)
    async def register_connection(ctx, _):
        # testing
        network = ctx.network
        network.original_nickname = network.nickname = network.config['nick']
        network.user = network.config['user']
        network.realname = network.config['realname']
        ctx.send_cmd('NICK', network.nickname)
        ctx.send_cmd('USER', network.user, '*', '*', network.realname)

        @ctx.message_event.core(ServerReply.ERR_NICKNAMEINUSE)
        async def nick_in_use(ctx, _):
            def inc_suffix(m):
                num = m.group(1) or 0
                return str(int(num) + 1)
            ctx.network.nickname = re.sub(r"(\d*)$", inc_suffix, ctx.network.nickname)
            ctx.send_cmd('NICK', ctx.network.nickname)

        # Clear the above hooks since we only want to negotiate a nick until we found a free one
        @ctx.message_event.core(ServerReply.RPL_WELCOME)
        async def register_done(ctx, _):
            nick_in_use.unregister()
            register_done.unregister()
