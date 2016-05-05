
import random

from .client import Client
from .event import Event


class Context:
    """Sample Context class

    Provide some environment for each event (e.g. network, client)."""
    # TODO: Move this class into it's own file later

    def __init__(self,
                 event: Event,
                 network: 'Network',
                 client: Client):
        self.event = event
        self.network = network
        self.client = client

    def sendline(self, line):
        self.client.sendline(line)


class Network:
    """Sample Network class"""

    def __init__(self, queue):
        self.registered = False
        self.queue = queue
        self.client = None

    async def register(self):
        # testing
        self.client.sendline('NICK Shanghai{:03d}'.format(
            random.randrange(1000)))
        self.client.sendline('USER uiaeie * * :realname')
        self.registered = True

    async def stop_running(self):
        await self.queue.put(Event('close_now', None))

    async def worker(self):
        """Sample worker."""
        self.registered = False

        # first item on queue should be "connected", with the client
        # as its value
        event = await self.queue.get()
        assert event.name == "connected"
        self.client = event.value
        print(event)

        running = True
        while running:
            if not self.registered:
                await self.register()

            event = await self.queue.get()
            print(event)
            if event.name == 'disconnected':
                break
            elif event.name == 'close_now':
                running = False

            # create context
            context = Context(event, self, self.client)  # noqa
            if event.name == 'message':
                message = event.value
                if message.command == '001':
                    # join test channel
                    self.client.sendline('JOIN #test')

            # TODO: dispatch event to handlers, e.g. plugins.
            # TODO: pass the context along
        else:
            # we did not break, so we close normally
            print('closing connection!')
            await self.client.close('Normal bye bye!')

        if running:
            print('connection closed by peer!')
        print('exiting.')
