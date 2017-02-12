
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
