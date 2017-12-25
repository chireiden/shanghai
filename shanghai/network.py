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
import time
from typing import Coroutine, Dict, Iterable, Iterator, List, Optional, Set

from .connection import Connection
from .config import NetworkConfiguration, Server
from .event import build_event, EventDispatcher
from .plugin_system import PluginManager
from .plugin_base import NetworkPlugin, NetworkEventName
from .irc import Options, Prefix
from .channel import Channel
from .logging import get_logger


class Network:
    """Sample Network class"""

    registered: bool
    # TODO use Prefix
    nickname: str
    user: str
    realname: str
    vhost: str
    options: Options
    channels: Dict[str, Channel]
    users: Dict[str, Prefix]

    event_queue: asyncio.Queue
    _connection: Connection
    _worker_task: asyncio.Task
    _connection_task: asyncio.Task

    def __init__(self, config: NetworkConfiguration, loop: asyncio.AbstractEventLoop = None) \
            -> None:
        self.name = config.name
        self.config = config
        self.loop = loop or asyncio.get_event_loop()
        self.logger = get_logger('network', self.name, config)
        self.plugin_managers: List[PluginManager] = []

        self._event_dispatcher = EventDispatcher(logger=self.logger)
        self._plugins: Set[NetworkPlugin] = set()
        self._sub_tasks: List[asyncio.Task] = []
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
        self.channels = {}
        self.users = {}

        self.stopped = False
        self.connected = False

        server = next(self._server_iter)
        self.event_queue = asyncio.Queue()
        self._connection = Connection(server, self.event_queue, self.loop, logger=self.logger)

    async def run(self) -> None:
        for retry in itertools.count(1):
            self._reset()
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
                break

            # We didn't stop, so try to reconnect after a timeout
            seconds = 10 * retry
            self.logger.info(f"Retry connecting in {seconds} seconds")
            await asyncio.sleep(seconds)  # TODO doesn't terminate if KeyboardInterrupt occurs here

        # we're leaving, so cancel subtasks
        if self._sub_tasks:
            for task in self._sub_tasks:
                task.cancel()

            await asyncio.wait(self._sub_tasks)

    def _worker_done(self, task: asyncio.Task) -> None:
        assert task is self._worker_task
        if task.cancelled():
            self._connection_task.cancel()

        elif task.exception():
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

        else:
            self.logger.debug("Worker task exited gracefully")
            return

    async def _worker(self) -> None:
        """Dispatches events from the event queue."""
        while not (self._connection_task.done() and self.event_queue.empty()):
            event = await self.event_queue.get()
            if event.name != NetworkEventName.RAW_LINE:
                # too spammy
                self.logger.debug(f"Dispatching {event}")
            result = await self._event_dispatcher.dispatch(event)
            if result:
                self._manage_subtasks(result.schedule)
                for new_event in result.append_events:
                    self.event_queue.put_nowait(new_event)

    def _manage_subtasks(self, new_coroutines: Optional[Iterable[Coroutine]]):
        """Clean up finished subtasks and add new ones."""
        new_tasks: List[asyncio.Task] = []
        for task in self._sub_tasks:
            if task.done():
                exc = task.exception()
                if exc:
                    self.logger.exception(f"A scheduled subtask failed: {task}", exc_info=exc)
            else:
                new_tasks.append(task)

        if new_coroutines:
            new_tasks.extend(self.loop.create_task(coro) for coro in new_coroutines)

        self._sub_tasks = new_tasks

    def _close(self, quitmsg: str = None) -> None:
        self.logger.info("closing network")
        self._connection.close()
        self.connected = False
        self.stopped = True

    def send_byteline(self, line: bytes) -> None:
        self._connection.writeline(line)

    def request_close(self, quitmsg: str = None) -> None:
        # TODO quitmsg
        evt = build_event(NetworkEventName.CLOSE_REQUEST, quitmsg=quitmsg)
        self.event_queue.put_nowait(evt)

    def load_plugins(self, manager: PluginManager):
        self.plugin_managers.append(manager)
        plugin_classes = set(manager.discover_plugins(NetworkPlugin))
        # TODO ignore/filter plugins according to config
        new_plugins = {plug(network=self, logger=self.logger)
                       for plug in plugin_classes}
        self._plugins |= new_plugins

        for plugin in new_plugins:
            self._event_dispatcher.register_plugin(plugin)
        # TODO store plugin instance somewhere for unregistering
