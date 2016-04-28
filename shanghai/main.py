
import asyncio

from .client import Client, Event


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
    # TODO: Move this class into it's own file later

    async def worker(self, queue):
        """Sample worker."""
        registered = False
        loop = asyncio.get_event_loop()

        running = True

        def stop_running():
            nonlocal running
            running = False

        # first item on queue is the client
        client = await queue.get()

        while running:
            event = await queue.get()
            print(event)
            if event.name == 'disconnected':
                break

            # create context
            context = Context(event, self, client)

            # TODO: dispatch event to handlers, e.g. plugins.
            # TODO: pass the context along

            # testing
            if not registered:
                context.sendline('NICK fouiae')
                context.sendline('USER uiaeie * * :realname')
                context.sendline('JOIN #test')
                registered = True
                loop.call_later(10, stop_running)
        else:
            # we did not break, so we close normally
            print('closing connection!')
            await client.close('Normal bye bye!')


def main():
    loop = asyncio.get_event_loop()
    queue = asyncio.Queue(100)
    bot = Client('localhost', 6667, queue, loop=loop)

    network = Network()

    worker_task = network.worker(queue)
    bot_task = bot.run()
    loop.run_until_complete(asyncio.wait([
        worker_task,
        bot_task,
    ]))
