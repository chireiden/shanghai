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

from ..event import core_event, build_event, ReturnValue
from ..plugin_base import Plugin, MessagePlugin, NetworkEventName
from ..irc import Message

__plugin_name__ = 'Message'
__plugin_version__ = '0.1.0'
__plugin_description__ = "Parses 'raw_line' network events and replaces them with message events"


class BuildMessagePlugin(Plugin, MessagePlugin):

    @core_event(NetworkEventName.RAW_LINE)
    def on_raw_line(self, raw_line: bytes):
        try:
            line = raw_line.decode(self._encoding)
        except UnicodeDecodeError:
            line = raw_line.decode(self._fallback_encoding, 'replace')
        try:
            msg = Message.from_line(line)
        except Exception as exc:
            self.network.exception('-->', line)
            raise

        msg_event = build_event(msg.command, message=msg)
        return ReturnValue(append_events=(msg_event,))
