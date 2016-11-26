
import asyncio

from .network import Network
from .plugin_system import PluginSystem

__all__ = ('Shanghai')


class Shanghai:

    def __init__(self, config, loop=None):
        self.config = config
        self.networks = {}
        self.loop = loop
        # not sure where else to put it. maybe an init_plugins here?
        # but this is just for testing for now.
        self.core_plugins = PluginSystem('core_plugins', is_core=True)
        self.user_plugins = PluginSystem('plugins')

        self.core_plugins.load_plugin('ctcp')
        self.core_plugins.load_plugin('message')
        self.core_plugins.load_plugin('ping')

        # TODO: load plugins from configuration
        self.user_plugins.load_plugin('test')

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
