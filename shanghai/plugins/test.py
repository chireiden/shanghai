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


# just for testing
@global_event(GlobalEventName.INIT_NETWORK_CTX)
async def init_context(ctx):
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

        elif words[0] == '!nicks':
            channel = message.params[0]
            nick_list = []
            for lkey, joinobj in ctx.joins.items():
                if ctx.chan_cmp(lkey[0], channel):
                    nick = joinobj.user.nickname
                    nick = f'{nick[:1]}\N{ZERO WIDTH SPACE}{nick[1:]}'
                    nick_list.append(nick)
            ctx.send_cmd('PRIVMSG', channel, ' '.join(nick_list))

        elif words[0] == '!channels':
            channel = message.params[0]
            chan_list = []
            for lchannel, chanobj in ctx.channels.items():
                nick_count = 0
                for lkey, joinobj in ctx.joins.items():
                    if ctx.chan_cmp(lkey[0], chanobj.name):
                        nick_count += 1
                chan_list.append(f'{chanobj.name} ({nick_count})')
            ctx.send_cmd('PRIVMSG', channel, ', '.join(chan_list))
