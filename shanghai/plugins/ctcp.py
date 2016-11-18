
from shanghai.irc.message import Message
from shanghai.event import EventDispatcher, message_event, message_event_dispatcher

__plugin_name__ = 'CTCP Plugin'
__plugin_version__ = '0.0.1'
__plugin_description__ = 'CTCP Message processing.'


class CtcpMessage(Message):

    def __repr__(self):
        return '<CTCP command={!r} params={!r}>'.format(self.command, self.params)


def build_ctcp(target, command, params):
    args = [command, *params]
    return 'PRIVMSG', target, '\x01{}\x01'.format(' '.join(args))


def build_ctcp_reply(target, command, params):
    args = [command, *params]
    return 'NOTICE', target, '\x01{}\x01'.format(' '.join(args))


def parse_ctcp(line):
    """Very primitive but should do the job for now."""
    if not line.startswith('\x01') or not line.endswith('\x01'):
        return
    line = line[1:-1].rstrip()
    if not line:
        return
    ctcp_cmd, *ctcp_params = line.split(' ', 1)
    if not ctcp_cmd:
        return
    ctcp_cmd = ctcp_cmd.upper()
    if ctcp_params:
        ctcp_params = ctcp_params[0].split()
    return ctcp_cmd, ctcp_params


@message_event('PRIVMSG')
async def privmsg(network, msg: Message):
    result = parse_ctcp(msg.params[1])
    if result is None:
        return
    ctcp_cmd, ctcp_params = result
    new_msg = CtcpMessage('CTCP_' + ctcp_cmd, prefix=msg.prefix, params=ctcp_params)
    await message_event_dispatcher.dispatch(network, new_msg)


@message_event('NOTICE')
async def privmsg(network, msg: Message):
    if not msg.params or len(msg.params) < 2:
        return
    result = parse_ctcp(msg.params[1])
    if result is None:
        return
    ctcp_cmd, ctcp_params = result
    new_msg = CtcpMessage('CTCP_REPLY_' + ctcp_cmd, prefix=msg.prefix, params=ctcp_params)
    await message_event_dispatcher.dispatch(network, new_msg)


@message_event('CTCP_VERSION')
async def version_request(network, msg: CtcpMessage):
    network.send_cmd(*build_ctcp_reply(msg.prefix[0], 'VERSION', ['Shanghai v37']))
