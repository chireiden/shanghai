
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

    def __init__(self, config, loop=None):
        super().__init__()

        self.name = config.name
        self.config = config
        self.loop = loop

        self.encoding = self.config.get('encoding', 'utf-8')
        self.fallback_encoding = self.config.get('fallback_encoding', 'latin1')

        self.event_queue = None

        self._server_iter = itertools.cycle(self.config.servers)
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
        self.connected = False

        server = next(self._server_iter)
        self.event_queue = asyncio.Queue()
        self._connection = Connection(server, self.event_queue, self.loop)

    def _make_log_context(self, *args, **kwargs):
        return LogContext('network', self.name, {})

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
            await asyncio.sleep(seconds)  # TODO doesn't terminate if KeyboardInterrupt occurs here
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
            self._worker_task = asyncio.ensure_future(self._worker())
            self._worker_task.add_done_callback(self._worker_done)

    async def _worker(self):
        """Dispatches events from the event queue."""
        while not (self._connection_task.done() and self.event_queue.empty()):
            event = await self.event_queue.get()
            current_logger.debug(event)
            await network_event_dispatcher.dispatch(self, event)

    def _close(self, quitmsg: str = None):
        current_logger.info("closing network")
        if quitmsg:
            self.send_cmd('QUIT', quitmsg)
        else:
            self.send_cmd('QUIT')
        self._connection.close()
        self.stopped = True

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

    def request_close(self, quitmsg: str = None):
        event = NetworkEvent(NetworkEventName.CLOSE_REQUEST, quitmsg)
        self.event_queue.put_nowait(event)


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

    await message_event_dispatcher.dispatch(network, msg)


@core_network_event(NetworkEventName.CONNECTED)
async def on_connected(network, _):
    network.connected = True
    current_logger.info("connected!")


@core_network_event(NetworkEventName.DISCONNECTED)
async def on_disconnected(network, _):
    current_logger.info('connection closed by peer!')


@core_network_event(NetworkEventName.CLOSE_REQUEST)
async def on_close_request(network, quitmsg):
    if network.connected:
        current_logger.info('closing connection')
        network._close(quitmsg)
    else:
        current_logger.info('closing connection prematurely')
        # Because we got "close_now" before "connected",
        # a connection has likely not been established yet.
        # So we cancel the task instead of closing the connection.
        if not network._connection_task.done():
            network._connection_task.cancel()
        network.stopped = True


@core_message_event(ServerReply.RPL_WELCOME)
async def on_msg_welcome(network, message):
    network.nickname = message.params[0]
    network.send_cmd('MODE', network.nickname, '+B')

    # join channels
    for channel, chanconf in network.config['channels'].items():
        key = chanconf.get('key', None)
        if key is not None:
            network.send_cmd('JOIN', channel, key)
        else:
            network.send_cmd('JOIN', channel)


@core_message_event(ServerReply.RPL_ISUPPORT)
async def on_msg_isupport(network, message):
    network.options.extend_from_message(message)


@core_network_event(NetworkEventName.CONNECTED)
async def register_connection(network, _):
    # testing
    network.original_nickname = network.nickname = network.config['nick']
    network.user = network.config['user']
    network.realname = network.config['realname']
    network.send_cmd('NICK', network.nickname)
    network.send_cmd('USER', network.user, '*', '*', network.realname)

    @core_message_event(ServerReply.ERR_NICKNAMEINUSE)
    async def nick_in_use(network, _):
        def inc_suffix(m):
            num = m.group(1) or 0
            return str(int(num) + 1)
        network.nickname = re.sub(r"(\d*)$", inc_suffix, network.nickname)
        network.send_cmd('NICK', network.nickname)

    # Clear the above hooks since we only want to negotiate a nick until we found a free one
    @core_message_event(ServerReply.RPL_WELCOME)
    async def register_done(network, _):
        nick_in_use.unregister()
        register_done.unregister()
