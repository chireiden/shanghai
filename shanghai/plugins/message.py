"""Just for testing"""

from shanghai.event import (
    GlobalEventName, NetworkEventName, Priority,
    MessageEventDispatcher, global_event
)
from shanghai.irc import Message

__plugin_name__ = 'Message'
__plugin_version__ = '0.1.0'
__plugin_description__ = "Parses 'raw_line' network events and emits message events"


@global_event(GlobalEventName.INIT_NETWORK_CTX, priority=Priority.PRE_CORE)
async def init_context(ctx):
    msg_evt_disp = MessageEventDispatcher(ctx)
    ctx.add_attribute('message_event', msg_evt_disp.decorator)
    ctx.logger.debug("created MessageEventDispatcher")

    encoding = ctx.network.config.get('encoding', 'utf-8')
    fallback_encoding = ctx.network.config.get('fallback_encoding', 'latin1')

    @ctx.add_method
    def send_line(ctx, line: str):
        ctx.network._connection.writeline(line.encode(encoding))

    @ctx.add_method
    def send_cmd(self, command: str, *params: str):
        args = [command, *params]
        if ' ' in args[-1]:
            args[-1] = ':{}'.format(args[-1])
        ctx.send_line(' '.join(args))

    @ctx.add_method
    def send_msg(ctx, target, text):
        # TODO split messages that are too long into multiple, also newlines
        ctx.send_cmd('PRIVMSG', target, text)

    @ctx.add_method
    def send_notice(ctx, target, text):
        # TODO split messages that are too long into multiple, also newlines
        ctx.send_cmd('NOTICE', target, text)

    @ctx.network_event.core(NetworkEventName.RAW_LINE)
    async def on_raw_line(ctx, raw_line: bytes):
        try:
            line = raw_line.decode(encoding)
        except UnicodeDecodeError:
            line = raw_line.decode(fallback_encoding, 'replace')
        try:
            msg = Message.from_line(line)
        except Exception as exc:
            ctx.network.exception('-->', line)
            raise exc

        await msg_evt_disp.dispatch(msg)

    @ctx.network_event.core(NetworkEventName.CLOSE_REQUEST)
    async def on_close_request(ctx, quitmsg):
        if quitmsg:
            ctx.send_cmd('QUIT', quitmsg)
        else:
            ctx.send_cmd('QUIT')
