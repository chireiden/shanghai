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

from ..event import core_event
from ..plugin_base import NetworkPlugin
from ..irc import ServerReply

__plugin_name__ = 'Options'
__plugin_version__ = '0.1.0'
__plugin_description__ = 'Handles RPL_ISUPPORT messages'


class ParseOptionsPlugin(NetworkPlugin):

    @core_event(ServerReply.RPL_ISUPPORT)
    def on_msg_isupport(self, message):
        self.network.options.extend_from_message(message)

    # TODO find a better way to determine that all 005 messages have been seen
    @core_event(ServerReply.RPL_LUSERCLIENT)
    def on_msg_isupport_end(self, message):
        self.logger.info(f"Network supports: {self.network.options}")
