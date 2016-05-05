
import asyncio
import itertools
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

    def __getattr__(self, name):
        if name in ('sendline', 'sendcmd', 'close'):
            return getattr(self.client, name)


class Network:
    """Sample Network class"""

    def __init__(self, name, config):
        self.name = name
        self.config = config
        self.current_server = -1
        self.registered = False
        self.runner_task = None
        self.worker_task = None
        self.queue = None
        self.client = None
        self.reset()

    def reset(self):
        self.registered = False

        self.runner_task = None
        self.worker_task = None

        server = self.next_server()
        self.queue = asyncio.Queue()
        self.client = Client(server.host, server.port, self.queue, server.ssl)

    def next_server(self):
        self.current_server = (self.current_server + 1) % \
            len(self.config['servers'])
        server = self.config['servers'][self.current_server]
        print(self.name, 'Jumping server', server)
        return server

    def runner_task_done(self, task):
        print(task)
        self.worker_task.cancel()

    def worker_task_done(self, task):
        print(task)
        self.runner_task.cancel()

    async def start(self):
        for retry in itertools.count(1):
            self.runner_task = asyncio.ensure_future(self.client.run())
            self.runner_task.add_done_callback(self.runner_task_done)

            self.worker_task = asyncio.ensure_future(self.worker())
            self.worker_task.add_done_callback(self.worker_task_done)

            await asyncio.gather(self.runner_task, self.worker_task,
                                 return_exceptions=True)
            seconds = 30 * retry
            print(self.name, 'Retry connecting in {} seconds'.format(seconds))
            await asyncio.sleep(seconds)
            self.reset()

    async def register(self):
        # testing
        nickname = self.config['nick']
        user = self.config['user']
        realname = self.config['realname']
        while '?' in nickname:
            nickname = nickname.replace('?', str(random.randrange(10)), 1)
        self.client.sendline('NICK {}'.format(nickname))
        self.client.sendline('USER {} * * :{}'.format(user, realname))
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
        # self.client = event.value
        print(self.name, event)

        running = True
        while running:
            if not self.registered:
                await self.register()

            event = await self.queue.get()
            print(self.name, event)
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
                    for channel in self.config['autojoin']:
                        if channel.key:
                            self.client.sendline(
                                'JOIN {} {}'.format(*channel))
                        else:
                            self.client.sendline(
                                'JOIN {}'.format(channel.channel))

            # TODO: dispatch event to handlers, e.g. plugins.
            # TODO: pass the context along
        else:
            # we did not break, so we close normally
            print(self.name, 'closing connection!')
            await self.client.close('Normal bye bye!')

        if running:
            print(self.name, 'connection closed by peer!')
        print(self.name, 'exiting.')
