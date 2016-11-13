
import asyncio

from .network import Network


class Shanghai:

    def __init__(self, config):
        self.config = config
        self.networks = {}

    def init_networks(self):
        for netconf in self.config.networks:
            name = netconf['name']
            network = Network(name, netconf['config'])
            network_task = asyncio.ensure_future(network.run())
            self.networks[name] = dict(
                task=network_task,
                network=network,
            )
            network.mainloop_task = network_task
            yield network_task

    def stop_networks(self):
        for network in self.networks.values():
            network['network'].close()
