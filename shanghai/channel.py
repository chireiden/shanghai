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
from typing import Coroutine, Dict, Iterable, List, NamedTuple, Optional, Set, Tuple

from .event import EventDispatcher
from .irc import Prefix
from .logging import get_logger
from .plugin_base import ChannelPlugin


class Member(NamedTuple):
    prefix: Prefix
    modes: str = ""


class ChannelModes:
    # TODO
    pass


class Channel:
    # network: 'shanghai.network.Network'
    # name: str  # in lower case
    # modes: ChannelModes
    # _nw_join_list: Dict[Tuple[str, str], Dict]

    def __init__(self, network: 'shanghai.network.Network',
                 name: str,
                 nw_join_list: Dict[Tuple[str, str], Dict],
                 ) -> None:
        self.network = network
        self.name = name
        self._nw_join_list = nw_join_list

        # TODO build channel config
        self.config = self.network.config
        self.logger = get_logger('channel', f'{self.name}@{self.network.name}',
                                 self.config)
        self.modes = ChannelModes()
        self.event_queue: asyncio.Queue = asyncio.Queue()

        self._event_dispatcher = EventDispatcher(logger=self.logger)
        self._plugins: Set[ChannelPlugin] = set()
        self._sub_tasks: List[asyncio.Task] = []
        self._parted = False

        self.load_plugins()

    @property
    def members(self):
        members = set()
        for lkey in self._nw_join_list:
            if self.network.options.chan_eq(lkey[0], self.name):
                member = Member(self.network.users[lkey[1]], **self._nw_join_list[lkey])
                members.add(member)
        return members

    async def _run(self) -> None:
        # TODO discover plugins, ignoring some according to config
        await self._worker()

    async def _worker(self) -> None:
        """Dispatches events from the event queue."""
        while not (self._parted and self.event_queue.empty()):
            event = await self.event_queue.get()
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
            new_tasks.extend(self.network.loop.create_task(coro) for coro in new_coroutines)

        self._sub_tasks = new_tasks

    def load_plugins(self):
        for manager in self.network.plugin_managers:
            plugin_classes = set(manager.discover_plugins(ChannelPlugin))
            # TODO ignore/filter plugins according to config
            # TODO catch errors and log error message
            new_plugins = {plug(channel=self) for plug in plugin_classes}
            self._plugins |= new_plugins

            for plugin in new_plugins:
                self._event_dispatcher.register_plugin(plugin)
            # TODO store plugin instance somewhere for unregistering
