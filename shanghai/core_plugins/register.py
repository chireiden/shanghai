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

import re
from typing.re import Match

from ..event import core_event
from ..plugin_base import Plugin, MessagePlugin, NetworkEventName
from ..irc import Message, ServerReply

__plugin_name__ = 'Register'
__plugin_version__ = '0.1.0'
__plugin_description__ = "Handle registering with the network and nickname collisions"


class RegisterPlugin(Plugin, MessagePlugin):

    @core_event(NetworkEventName.CONNECTED)
    def on_connected(self) -> None:
        # testing
        network = self.network
        network.nickname = network.config['nick']
        network.user = network.config['user']
        network.realname = network.config['realname']
        self.send_cmd('NICK', network.nickname)
        self.send_cmd('USER', network.user, "*", "*", network.realname)

        # self.on_nick_in_use.enable()

    @core_event(ServerReply.ERR_NICKNAMEINUSE)
    def on_nick_in_use(self, message: Message) -> None:
        def inc_suffix(m: Match[str]) -> str:
            num = m.group(1) or 0
            return str(int(num) + 1)
        self.network.nickname = re.sub(r"(\d*)$", inc_suffix, self.network.nickname)
        self.send_cmd('NICK', self._nickname)

    @core_event(ServerReply.RPL_WELCOME)
    def on_welcome(self, message: Message) -> None:
        # Clear hook since we only want to negotiate a nick until we found a free one
        # self.on_nick_in_use.disable()

        self.network.nickname = message.params[0]
        self.send_cmd('MODE', self.network.nickname, '+B')

    @core_event('NICK')
    async def on_nick(self, message: Message):
        nick = message.prefix.name
        new_nick = message.params[0]

        if self.network.nick_eq(nick, self.network.nickname):
            self.network.nickname = new_nick
