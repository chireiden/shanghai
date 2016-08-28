
import asyncio
import functools
import itertools
import re

from .connection import Connection
from .event import Event
from .irc import Options, ServerReply
from .logging import LogContext, current_logger


class Context:
    """Sample Context class

    Provide some environment for each event (e.g. network, connection)."""
    # TODO: Move this class into its own file later

    def __init__(self,
                 event: Event,
                 network: 'Network',
                 connection: Connection):
        self.event = event
        self.network = network
        self.connection = connection

    def __getattr__(self, name):
        if name in ('sendline', 'sendcmd', 'close'):
            return getattr(self.connection, name)


class Network:
    """Sample Network class"""

    def __init__(self, name, config):
        self.name = name
        self.config = config
        self.current_server_index = -1
        self.queue = None
        self.connection = None
        self.log_context = None
        self.reset()

    def reset(self):

        self.registered = False
        self.nickname = None
        self.user = None
        self.realname = None
        self.vhost = None
        self.options = Options()

        self.runner_task = None
        self.worker_task = None

        server = self.next_server()
        self.queue = asyncio.Queue()
        self.connection = Connection(server.host, server.port, self.queue,
                                     server.ssl)

    def next_server(self):
        servers = self.config['servers']
        self.current_server_index = ((self.current_server_index + 1)
                                     % len(servers))
        server = servers[self.current_server_index]
        current_logger.info(self.name, 'Using server', server)
        return server

    async def run(self):
        self.log_context = LogContext('network', self.name, self.config)
        self.log_context.push()

        def cancel_other_task_if_failed(task, other_task):
            current_logger.info('cancel_other_task_if_failed', task)
            if task.exception():
                task.print_stack()
                other_task.cancel()

        for retry in itertools.count(1):
            self.runner_task = asyncio.ensure_future(self.connection.run())
            self.worker_task = asyncio.ensure_future(self.worker())
            tasks = (self.runner_task, self.worker_task)

            for task, other_task in zip(tasks, reversed(tasks)):
                task.add_done_callback(
                    functools.partial(cancel_other_task_if_failed,
                                      other_task=other_task)
                )

            _, stopped = await asyncio.gather(self.runner_task,
                                              self.worker_task,
                                              return_exceptions=True)
            if stopped is True:
                self.log_context.pop()
                return

            # We didn't stop, so try to reconnect
            seconds = 30 * retry
            current_logger.info('Retry connecting in {} seconds'.format(seconds))
            await asyncio.sleep(seconds)
            self.reset()
        self.log_context.pop()

    def start_register(self):
        # testing
        self.original_nickname = self.nickname = self.config['nick']
        self.user = self.config['user']
        self.realname = self.config['realname']
        self.connection.sendcmd('NICK', self.nickname)
        self.connection.sendcmd('USER', self.user, '*', '*', self.realname)
        # TODO add listener for ERR_NICKNAMEINUSE here;
        # maybe also add a listener for RPL_WELCOME to clear this listener

    async def stop_running(self, quitmsg=None):
        await self.queue.put(Event('close_now', quitmsg))

    async def worker(self):
        """Sample worker."""
        self.registered = False

        # first item on queue should be "connected", with the connection
        # as its value
        event = await self.queue.get()
        assert event.name == "connected"
        # self.connection = event.value
        current_logger.info(event)
        stopped = False

        # start register process
        self.start_register()
        while True:
            event = await self.queue.get()
            current_logger.debug(event)
            # remember to forward these event to plugins
            if event.name == 'disconnected':
                current_logger.info('connection closed by peer!')
                break
            elif event.name == 'close_now':
                current_logger.info('closing connection!')
                await self.connection.close(event.value)
                stopped = True
                break

            # create context
            # context = Context(event, self, self.connection)
            if event.name == 'message':
                message = event.value

                if message.command == ServerReply.RPL_WELCOME:
                    self.nickname = message.params[0]
                    self.connection.sendcmd('MODE', self.nickname, '+B')

                    # join test channel
                    for channel, chanconf in self.config['channels'].items():
                        key = chanconf.get('key', None)
                        if key is not None:
                            self.connection.sendcmd('JOIN', channel, key)
                        else:
                            self.connection.sendcmd('JOIN', channel)

                elif message.command == ServerReply.RPL_ISUPPORT:
                    self.options.extend_from_message(message)

                elif message.command == ServerReply.ERR_NICKNAMEINUSE:
                    # TODO move this handler somewhere else
                    def inc_suffix(m):
                        num = m.group(1) or 0
                        return str(int(num) + 1)
                    self.nickname = re.sub(r"(\d*)$", inc_suffix,
                                           self.nickname)
                    self.connection.sendcmd('NICK', self.nickname)

            # TODO: dispatch event to handlers, e.g. plugins.
            # TODO: pass the context along

        current_logger.info('exiting.')
        return stopped
