
import asyncio

from .network import Network


class Shanghai:

    def __init__(self, config, loop=None):
        self.config = config
        self.networks = {}
        self.loop = loop

    def init_networks(self):
        for netconf in self.config.networks:
            name = netconf['name']
            network = Network(name, netconf['config'])
            network_task = asyncio.ensure_future(network.run(), loop=self.loop)
            self.networks[name] = dict(
                task=network_task,
                network=network,
            )
            yield network_task

    def stop_networks(self):
        for network in self.networks.values():
            asyncio.ensure_future(network['network'].request_close(), loop=self.loop)
