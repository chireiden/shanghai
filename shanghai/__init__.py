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

from .network import Network
from .plugin_system import PluginSystem

__all__ = ('Shanghai')


class Shanghai:

    def __init__(self, config, loop=None):
        self.config = config
        self.networks = {}
        self.loop = loop

        self.core_plugins = PluginSystem('core_plugins', is_core=True)
        # TODO: load plugins from configuable location(s)
        self.user_plugins = PluginSystem('plugins')

        self.core_plugins.load_all_plugins()
        self.user_plugins.load_all_plugins()

    def init_networks(self):
        for netconf in self.config.networks:
            network = Network(netconf, loop=self.loop)
            network_task = asyncio.ensure_future(network.run(), loop=self.loop)
            self.networks[netconf.name] = dict(
                task=network_task,
                network=network,
            )
            yield network_task

    def stop_networks(self):
        for network in self.networks.values():
            network['network'].request_close()
