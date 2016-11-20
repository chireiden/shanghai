
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
        self.plugin_system = PluginSystem()
        self.plugin_system.load_plugin('ping')
        self.plugin_system.load_plugin('ctcp')
        self.plugin_system.load_plugin('test')

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
