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

from ..event import build_event, core_event, ctcp_event, CTCP_PREFIX, ReturnValue
from ..irc import Message, CtcpMessage
from ..plugin_base import CtcpPlugin

__plugin_name__ = 'CTCP'
__plugin_version__ = '0.1.0'
__plugin_description__ = 'CTCP Message processing'


class DefaultCtcpPlugin(CtcpPlugin):
    # example ctcp_event hook
    @ctcp_event('VERSION')
    async def version_request(self, message: CtcpMessage):
        source = message.prefix[0]
        self.send_ctcp_reply(source, 'VERSION',
                             "Shanghai v37 - https://github.com/chireiden/shanghai")

    @core_event('PRIVMSG')
    async def privmsg(self, message: Message):
        ctcp_msg = CtcpMessage.from_message(message)
        if not ctcp_msg:
            return

        evt = build_event(CTCP_PREFIX + ctcp_msg.command, message=ctcp_msg)
        return ReturnValue(insert_events=(evt,))
