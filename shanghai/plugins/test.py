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

__plugin_name__ = 'Test'
__plugin_version__ = 'β.γ.μ'
__plugin_description__ = 'bla blub'


from ..irc.message import ChannelMessage, PrivateMessage
from ..plugin_base import (ChannelEventName, ChannelPlugin,
                           ChannelMessageMixin, MessagePluginMixin,
                           NetworkEventName, NetworkPlugin)
from ..event import event, ReturnValue


def _unhighlight(nick):
    return f'{nick[:1]}\N{ZERO WIDTH SPACE}{nick[1:]}'


class TestNetworkPlugin(NetworkPlugin, MessagePluginMixin):

    @event(NetworkEventName.PRIVATE_MESSAGE)
    def on_private_message(self, user, message: PrivateMessage):
        self.logger.debug(f'Got a private message {message}')

        if message.words[0] == '!echo':
            if len(message.words) >= 3:
                text = ' '.join(message.words[2:])
                self.send_msg(message.source, text)

        elif message.words[0] == '!say':
            if len(message.words) >= 3:
                text = ' '.join(message.words[2:])
                self.send_msg(message.source, f'{message.sender} told me to say: {text}')


class TestChannelPlugin(ChannelPlugin, ChannelMessageMixin):

    @event(ChannelEventName.JOINED)
    def on_joined(self):
        self.logger.info(f"Joined channel {self.channel}")

    @event(ChannelEventName.MESSAGE)
    def on_channel_message(self, message: ChannelMessage):
        self.logger.debug(f'Got a channel message {message}')
        first_word = message.words[0]

        if first_word == '!nicks':
            nick_list = [_unhighlight(member.prefix.name)
                         for member in self.channel.members]
            self.say(' '.join(nick_list))

        elif first_word == '!names':
            nick_list = []
            for member in self.channel.members:
                prefixes = self.network.options.modes_to_prefixes(member.modes)
                nick_list.append(f"{prefixes}{_unhighlight(member.prefix.name)}")
            self.say(' '.join(nick_list))

        elif first_word == '!channels':
            sorted_channels = sorted(self.network.channels.values(), key=lambda c: c.name)
            channel_strings = (f"{chan.name} ({len(chan.members)})"
                               for chan in sorted_channels)
            self.say(', '.join(channel_strings))

        elif first_word == '!except':
            raise Exception('Test Exception')

        elif first_word == '!quit':
            self.network.request_close(message.line)

        elif first_word == '!cancel':
            # this is private API, but we specifically want to "cancel" the worker
            self.network._close()
            self.network.stopped = False

        elif first_word == '!ctcp':
            if len(message.words) >= 2:
                self.send_ctcp(message.prefix.name, message.words[1], ' '.join(message.words[2:]))

        elif first_word == '!eat':
            if len(message.words) == 2:
                return message.words[1]
            return ReturnValue(eat=True)

        elif first_word == '!quote':
            _, line_to_send = message.line.split(maxsplit=1)
            self.send_line(line_to_send)

        elif first_word == '!say':
            if len(message.words) >= 2:
                text = ' '.join(message.words[1:])
                self.say(text)

        elif first_word == '!me':
            if len(message.words) >= 2:
                text = ' '.join(message.words[1:])
                self.me(text)

        elif first_word == '!join':
            if len(message.words) == 2:
                self.send_cmd('JOIN', message.words[1])

        elif first_word == '!part':
            if len(message.words) >= 2:
                channel_name = message.words[1]
                part_msg = ' '.join(message.words[2:])
            elif len(message.words) == 1:
                channel_name = self.channel.name
                part_msg = ""

            self.send_cmd('PART', channel_name, part_msg)
