
import asyncio
import io
import itertools
import re
import time

from .connection import Connection
from .event import Event
from .irc import Message, Options, ServerReply
from .logging import LogContext, current_logger, with_log_context


class Context:
    """Sample Context class

    Provide some environment for each event (e.g. network)."""
    # TODO: Move this class into its own file later

    def __init__(self,
                 event: Event,
                 network: 'Network'):
        self.event = event
        self.network = network

    def __getattr__(self, name):
        if name in ('sendline', 'sendcmd', 'close'):
            return getattr(self.network, name)


class Network:
    """Sample Network class"""

    def __init__(self, name, config):
        self.name = name
        self.config = config
        self.current_server_index = -1
        self.queue = None
        self.connection = None
        self.encoding = self.config.get('encoding', 'utf-8')
        self.fallback_encoding = self.config.get('fallback_encoding', 'latin1')
        self.ping_timeout_handle = None
        self.send_ping_handle = None
        self.reset()

    def reset(self):
        self.registered = False
        self.nickname = None
        self.user = None
        self.realname = None
        self.vhost = None
        self.options = Options()

        self.connection_task = None
        self.worker_task = None
        self.stopped = False

        self.unset_ping_timeout_handlers()

        server = self.next_server()
        self.queue = asyncio.Queue()
        self.connection = Connection(server.host, server.port, self.queue,
                                     server.ssl)

    def next_server(self):
        servers = self.config['servers']
        self.current_server_index = ((self.current_server_index + 1)
                                     % len(servers))
        server = servers[self.current_server_index]
        current_logger.info('Using server', server)
        return server

    def _make_log_context(self, *args, **kwargs):
        return LogContext('network', self.name, self.config)

    @with_log_context(_make_log_context)
    async def run(self):

        for retry in itertools.count(1):
            self.connection_task = asyncio.ensure_future(self.connection.run())
            self.worker_task = asyncio.ensure_future(self.worker())
            self.worker_task.add_done_callback(self.worker_done)

            try:
                await self.connection_task
            except:
                current_logger.exception("Connection Task errored")

            assert self.worker_task.done()
            if self.stopped:
                return

            # We didn't stop, so try to reconnect after a timeout
            seconds = 10 * retry
            current_logger.info('Retry connecting in {} seconds'.format(seconds))
            await asyncio.sleep(seconds)
            self.reset()

    def worker_done(self, task):
        assert task is self.worker_task
        if task.cancelled():
            self.connection_task.cancel()
        else:
            exception = task.exception()
            if exception:
                f = io.StringIO()
                task.print_stack(file=f)
                current_logger.error(f.getvalue())
                current_logger.warning("Restarting worker task")
                self.worker_task = asyncio.ensure_future(self.worker(restarted=True))
                self.worker_task.add_done_callback(self.worker_done)
            else:
                current_logger.debug("Worker task exited gracefully")

    def start_register(self):
        # testing
        self.original_nickname = self.nickname = self.config['nick']
        self.user = self.config['user']
        self.realname = self.config['realname']
        self.sendcmd('NICK', self.nickname)
        self.sendcmd('USER', self.user, '*', '*', self.realname)
        # TODO add listener for ERR_NICKNAMEINUSE here;
        # maybe also add a listener for RPL_WELCOME to clear this listener

    def ping_timeout(self):
        current_logger.info('Detected ping timeout.')
        self.connection_task.cancel()

    def send_ping(self):
        current_logger.info('Sending ping to test if connection is alive.')
        self.sendcmd('PING', int(time.time()))

    def unset_ping_timeout_handlers(self):
        if self.ping_timeout_handle is not None:
            self.ping_timeout_handle.cancel()
            self.ping_timeout_handle = None
        if self.send_ping_handle is not None:
            self.send_ping_handle.cancel()
            self.send_ping_handle = None

    def set_ping_timeout_handlers(self):
        loop = asyncio.get_event_loop()
        # TODO: take timeouts from config
        # suggestions:
        # - ping_timeout_handle - minimun: 5 minutes; maximum: unlimited
        # - send_ping_handle - minimum: 4 minutes; maximum: ping_timeout_handle - 1 minute
        self.ping_timeout_handle = loop.call_later(5 * 60, self.ping_timeout)
        self.send_ping_handle = loop.call_later(4 * 60, self.send_ping)

    async def init_worker(self):
        # First item on queue should be "connected", with the connection
        # as its value
        event = await self.queue.get()
        if event.name == 'close_now':
            current_logger.info('closing connection prematurely')
            # Because we got "close_now" before "connected" a connection might not be
            # established yet.
            # So we set an exception instead of closing the connection.
            self.connection_task.cancel()
            self.stopped = True
            return
        else:
            assert event.name == "connected"
            assert self.connection == event.value
            current_logger.info("connected!")

        # start register process
        self.start_register()

    async def worker(self, restarted=False):
        """Sample worker."""

        if not restarted:
            await self.init_worker()

        while not self.stopped:
            event = await self.queue.get()
            current_logger.debug(event)

            # remember to forward these event to plugins
            if event.name == 'raw_line':
                try:
                    line = event.value.decode(self.encoding)
                except UnicodeDecodeError:
                    line = event.value.decode(self.fallback_encoding,
                                              'replace')
                try:
                    message = Message.from_line(line)
                except Exception as exc:
                    current_logger.exception('-->', line)
                    raise exc
                if message.command == 'PING':
                    self.sendcmd('PONG', *message.params)
                await self.queue.put(Event('message', message))
            elif event.name == 'disconnected':
                current_logger.info('connection closed by peer!')
                break
            elif event.name == 'close_now':
                current_logger.info('closing connection')
                self.close(event.value)
                break

            # create context
            # context = Context(event, self)
            if event.name == 'message':
                self.unset_ping_timeout_handlers()
                self.set_ping_timeout_handlers()

                message = event.value
                if message.command == 'PRIVMSG':
                    if message.params[-1].startswith('!except'):
                        raise Exception('Test Exception')

                if message.command == ServerReply.RPL_WELCOME:
                    self.nickname = message.params[0]
                    self.sendcmd('MODE', self.nickname, '+B')

                    # join test channel
                    for channel, chanconf in self.config['channels'].items():
                        key = chanconf.get('key', None)
                        if key is not None:
                            self.sendcmd('JOIN', channel, key)
                        else:
                            self.sendcmd('JOIN', channel)

                elif message.command == ServerReply.RPL_ISUPPORT:
                    self.options.extend_from_message(message)

                elif message.command == ServerReply.ERR_NICKNAMEINUSE:
                    # TODO move this handler somewhere else
                    def inc_suffix(m):
                        num = m.group(1) or 0
                        return str(int(num) + 1)
                    self.nickname = re.sub(r"(\d*)$", inc_suffix,
                                           self.nickname)
                    self.sendcmd('NICK', self.nickname)

            # TODO: dispatch event to handlers, e.g. plugins.
            # TODO: pass the context along

        current_logger.info('exiting.')

    def sendline(self, line: str):
        self.connection.writeline(line.encode(self.encoding))

    def sendcmd(self, command: str, *params: str):
        args = [command, *(str(p) for p in params)]
        if ' ' in args[-1]:
            args[-1] = ':{}'.format(args[-1])
        self.sendline(' '.join(args))

    def close(self, quitmsg: str = None):
        if quitmsg:
            self.sendcmd('QUIT', quitmsg)
        self.connection.close()
        self.stopped = True
