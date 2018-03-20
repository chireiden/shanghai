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
from typing import Any, Dict, Generator

from .config import ShanghaiConfiguration
from .network import Network
from .plugin_system import PluginManager

__all__ = ('Shanghai')


class Shanghai:

    def __init__(self, config: ShanghaiConfiguration, loop: asyncio.AbstractEventLoop) -> None:
        self.config = config
        self.loop = loop
        self.networks: Dict[str, Dict[str, Any]] = {}

        self.plugin_managers = [
            # order matters
            PluginManager('core_plugins', is_core=True),
            PluginManager('plugins'),
            # TODO: load plugins from configurable location(s)
        ]

        for manager in self.plugin_managers:
            manager.load_all_plugins()

    def init_networks(self) -> Generator[asyncio.Task, None, None]:
        for netconf in self.config.networks:
            network = Network(netconf, loop=self.loop)
            for manager in self.plugin_managers:
                network.load_plugins(manager)

            network_task = self.loop.create_task(network.run())
            self.networks[netconf.name] = dict(
                task=network_task,
                network=network,
            )
            yield network_task

    def stop_networks(self) -> None:
        for network in self.networks.values():
            network['network'].request_close()
