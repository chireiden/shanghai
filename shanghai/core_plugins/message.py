# Shanghai - Multiserver Asyncio IRC Bot
# Copyright © 2016  Lars Peter Søndergaard <lps@chireiden.net>
# Copyright © 2016  FichteFoll <fichtefoll2@googlemail.com>
#
# This file is part of Shanghai.
#
# Shanghai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Shanghai is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Shanghai.  If not, see <http://www.gnu.org/licenses/>.

from shanghai.event import (
    GlobalEventName, NetworkEventName, Priority,
    EventDispatcher, global_event
)
from shanghai.irc import Message

__plugin_name__ = 'Message'
__plugin_version__ = '0.1.0'
__plugin_description__ = "Parses 'raw_line' network events and emits message events"


class MessageEventDispatcher(EventDispatcher):

    def __init__(self, context, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.context = context

    async def dispatch(self, msg):
        return await super().dispatch(msg.command, self.context, msg)


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
