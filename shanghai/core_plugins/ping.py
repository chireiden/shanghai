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
import time
from typing import List

from ..event import core_event
from ..plugin_base import MessagePlugin, NetworkEventName
from ..irc import ServerReply, Message

__plugin_name__ = 'PING PONG'
__plugin_version__ = '0.1.0'
__plugin_description__ = 'Handles pinging and ponging with networks. Yeah.'


def ms_time() -> int:
    return int(time.time() * 1000)


class PingPlugin(MessagePlugin):

    tasks: List[asyncio.Task]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ping_evt, self.pong_evt = asyncio.Event(), asyncio.Event()
        self.tasks = []

    async def pinger(self):
        while True:
            self.send_cmd('PING', f"LAG_{ms_time()}")
            self.ping_evt.set()
            await asyncio.sleep(60)

    async def pong_waiter(self):
        while True:
            await self.ping_evt.wait()
            self.ping_evt.clear()
            try:
                await asyncio.wait_for(self.pong_evt.wait(), 60, loop=self.network.loop)
            except asyncio.TimeoutError:
                self.logger.warning('Detected ping timeout')
                self.network._connection_task.cancel()
                return
            else:
                self.pong_evt.clear()

    @core_event(ServerReply.RPL_WELCOME)
    def on_welcome(self, message):
        self.ping_evt.clear()
        self.pong_evt.clear()

        loop = self.network.loop
        assert not self.tasks
        # could also return these in a ReturnValue
        self.tasks = [loop.create_task(self.pong_waiter()),
                      loop.create_task(self.pinger())]

    @core_event('PONG')
    def pong(self, message: Message):
        text = message.params[1]
        if not text.startswith("LAG_"):
            return
        else:
            self.pong_evt.set()
            ms = int(text[4:])
            latency = ms_time() - ms
            self.logger.debug(f"latency: {latency / 1000:.3f}s")

    @core_event(NetworkEventName.DISCONNECTED)
    async def on_disconnected(self):
        self.logger.debug("Cleaning up ping plugin tasks")

        if self.tasks:
            for task in self.tasks:
                if task:
                    task.cancel()
            done, pending = await asyncio.wait(self.tasks)
            if pending:
                self.logger.warning("pending", pending)
            self.tasks = []

    # Realistically, we don't need this since we initiate the ping handshare ourselves,
    # but better safe then sorry.
    @core_event('PING')
    async def on_ping(ctx, message):
        ctx.send_cmd('PONG', *message.params)
