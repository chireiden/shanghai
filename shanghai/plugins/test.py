# Copyright © 2016  Lars Peter Søndergaard <lps@chireiden.net>
# Copyright © 2016  FichteFoll <fichtefoll2@googlemail.com>
#
# This file is part of Shanghai, an asynchronous multi-server IRC bot.
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

from shanghai.event import global_event, GlobalEventName, ReturnValue

__plugin_name__ = 'Test'
__plugin_version__ = 'β.γ.μ'
__plugin_description__ = 'bla blub'


async def channel_message(ctx, message):
    ctx.logger.debug(f'Got a channel message {message}')

    if message.words[0] == '!nicks':
        nick_list = []
        for member in ctx.members:
            nick = member.nickname
            nick = f'{nick[:1]}\N{ZERO WIDTH SPACE}{nick[1:]}'
            nick_list.append(nick)
        ctx.say(' '.join(nick_list))

    elif message.words[0] == '!channels':
        chan_list = []
        for chanobj in ctx.network_context.channels.values():
            _c_ctx = ctx.network_context.get_channel_context(chanobj.name)
            chan_list.append(f'{chanobj.name} ({len(_c_ctx.members)})')
        ctx.say(', '.join(chan_list))


async def private_message(ctx, message):
    ctx.logger.debug(f'Got a private message {message}')

    if message.words[0] == '!say':
        if len(message.words) >= 3:
            target_channel = message.words[1]
            text = ' '.join(message.words[2:])
            ctx.msg(target_channel, f'{message.sender} told me to say: {text}')


# just for testing
@global_event(GlobalEventName.INIT_NETWORK_CTX)
async def init_context(ctx):
    ctx.channel_event('ChannelMessage')(channel_message)
    ctx.channel_event('PrivateMessage')(private_message)

    @ctx.message_event('PRIVMSG')
    async def on_privmsg(ctx, message):
        line = message.params[-1]
        words = line.split()

        if words[0] == '!except':
            raise Exception('Test Exception')

        elif words[0] == '!quit':
            await ctx.network.request_close(line)

        elif words[0] == '!cancel':
            ctx.network._close()
            ctx.network.stopped = False

        elif words[0] == '!ctcp':
            if len(words) < 2:
                return
            ctx.send_ctcp(message.prefix.name, words[1], ' '.join(words[2:]))

        elif words[0] == '!eat':
            if len(words) == 2:
                return words[1]
            return ReturnValue.EAT
