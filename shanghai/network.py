
import asyncio
import io
import itertools
import re
import time

from .connection import Connection
from .event import (NetworkEvent, NetworkEventName,
                    network_event_dispatcher, message_event_dispatcher,
                    core_network_event, core_message_event)
from .irc import Message, Options, ServerReply
from .logging import LogContext, current_logger, with_log_context
from .util import ShadowAttributesMixin


class Network(ShadowAttributesMixin):
    """Sample Network class"""

    def __init__(self, name, config, loop=None):
        super().__init__()

        self.name = name
        self.config = config
        self.loop = loop

        self.encoding = self.config.get('encoding', 'utf-8')
        self.fallback_encoding = self.config.get('fallback_encoding', 'latin1')

        self.event_queue = None

        self._server_iter = itertools.cycle(self.config['servers'])
        self._connection = None
        self._worker_task_failure_timestamps = []

        self._reset()

    def _reset(self):
        self.registered = False
        self.nickname = None
        self.user = None
        self.realname = None
        self.vhost = None
        self.options = Options()

        self._connection_task = None
        self._worker_task = None
        self.stopped = False

        server = next(self._server_iter)
        self.event_queue = asyncio.Queue()
        self._connection = Connection(server.host, server.port, self.event_queue, server.ssl)

    def _make_log_context(self, *args, **kwargs):
        return LogContext('network', self.name, self.config)

    @with_log_context(_make_log_context)
    async def run(self):

        for retry in itertools.count(1):
            self._connection_task = asyncio.ensure_future(self._connection.run())
            self._worker_task = asyncio.ensure_future(self._worker())
            self._worker_task.add_done_callback(self._worker_done)

            try:
                await self._connection_task
            except:
                current_logger.exception("Connection Task errored")

            # Wait until worker task emptied the queue (and terminates)
            await self._worker_task
            if self.stopped:
                return

            # We didn't stop, so try to reconnect after a timeout
            seconds = 10 * retry
            current_logger.info('Retry connecting in {} seconds'.format(seconds))
            await asyncio.sleep(seconds)
            self._reset()

    def _worker_done(self, task):
        assert task is self._worker_task
        if task.cancelled():
            self._connection_task.cancel()
        else:
            if not task.exception():
                current_logger.debug("Worker task exited gracefully")
                return

            f = io.StringIO()
            task.print_stack(file=f)
            current_logger.error(f.getvalue())

            now = time.time()
            self._worker_task_failure_timestamps.append(time.time())
            if len(self._worker_task_failure_timestamps) == 5:
                if self._worker_task_failure_timestamps.pop(0) >= now - 10:
                    current_logger.error("Worker task exceeded exception threshold; terminating")
                    self._close("Exception threshold exceeded")
                    return

            current_logger.warning("Restarting worker task")
            self._worker_task = asyncio.ensure_future(self._worker(restarted=True))
            self._worker_task.add_done_callback(self._worker_done)

    def start_register(self):
        # testing
        self.original_nickname = self.nickname = self.config['nick']
        self.user = self.config['user']
        self.realname = self.config['realname']
        self.send_cmd('NICK', self.nickname)
        self.send_cmd('USER', self.user, '*', '*', self.realname)
        # TODO add listener for ERR_NICKNAMEINUSE here;
        # maybe also add a listener for RPL_WELCOME to clear this listener

    async def _init_worker(self):
        # First item on queue should be "connected", with the connection
        # as its value
        event = await self.event_queue.get()
        if event.name == 'close_now':
            current_logger.info('closing connection prematurely')
            # Because we got "close_now" before "connected",
            # a connection has likely not been established yet.
            # So we cancel the task instead of closing the connection.
            self._connection_task.cancel()
            self.stopped = True
            return
        else:
            assert event.name == "connected", event
            assert self._connection == event.value, (event, self._connection)
            await network_event_dispatcher.dispatch(self, event)

        # start register process
        self.start_register()

    async def _worker(self, restarted=False):
        """Dispatches events from the event queue."""

        if not restarted:
            await self._init_worker()

        while not (self._connection_task.done() and self.event_queue.empty()):
            event = await self.event_queue.get()
            current_logger.debug(event)
            await network_event_dispatcher.dispatch(self, event)

        current_logger.debug('exiting worker task')

    def send_line(self, line: str):
        self._connection.writeline(line.encode(self.encoding))

    def send_cmd(self, command: str, *params: str):
        args = [command, *params]
        if ' ' in args[-1]:
            args[-1] = ':{}'.format(args[-1])
        self.send_line(' '.join(args))

    def send_msg(self, target, text):
        # TODO split messages that are too long into multiple, also newlines
        self.send_cmd('PRIVMSG', target, text)

    def send_notice(self, target, text):
        # TODO split messages that are too long into multiple, also newlines
        self.send_cmd('NOTICE', target, text)

    def _close(self, quitmsg: str = None):
        current_logger.info("closing network")
        if quitmsg:
            self.send_cmd('QUIT', quitmsg)
        else:
            self.send_cmd('QUIT')
        self._connection.close()
        self.stopped = True

    async def request_close(self, quitmsg: str = None):
        # TODO use Queue.put_nowait?
        close_event = NetworkEvent(NetworkEventName.CLOSE_REQUEST, quitmsg)
        await self.event_queue.put(close_event)


# Core event handlers #############################################################################


@core_network_event(NetworkEventName.RAW_LINE)
async def on_raw_line(network, raw_line: bytes):
    try:
        line = raw_line.decode(network.encoding)
    except UnicodeDecodeError:
        line = raw_line.decode(network.fallback_encoding, 'replace')
    try:
        msg = Message.from_line(line)
    except Exception as exc:
        current_logger.exception('-->', line)
        raise exc

    # TODO use message_event_dispatcher.dispatch directly?
    await message_event_dispatcher.dispatch(network, msg)


@core_network_event(NetworkEventName.CONNECTED)
async def on_connected(network, _):
    current_logger.info("connected!")


@core_network_event(NetworkEventName.DISCONNECTED)
async def on_disconnected(network, _):
    current_logger.info('connection closed by peer!')


@core_network_event(NetworkEventName.CLOSE_REQUEST)
async def on_close_request(network, quitmsg):
    current_logger.info('closing connection')
    network._close(quitmsg)


@core_message_event(ServerReply.RPL_WELCOME)
async def on_msg_welcome(network, message):
    if message.command == ServerReply.RPL_WELCOME:
        network.nickname = message.params[0]
        network.send_cmd('MODE', network.nickname, '+B')

        # join test channel
        for channel, chanconf in network.config['channels'].items():
            key = chanconf.get('key', None)
            if key is not None:
                network.send_cmd('JOIN', channel, key)
            else:
                network.send_cmd('JOIN', channel)


@core_message_event(ServerReply.RPL_ISUPPORT)
async def on_msg_isupport(network, message):
    network.options.extend_from_message(message)


@core_message_event(ServerReply.ERR_NICKNAMEINUSE)
async def on_msg_nickinuse(network, _):
    def inc_suffix(m):
        num = m.group(1) or 0
        return str(int(num) + 1)
    network.nickname = re.sub(r"(\d*)$", inc_suffix, network.nickname)
    network.send_cmd('NICK', network.nickname)
