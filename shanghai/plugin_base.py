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

import enum

# from ..network import Network
from .logging import Logger


class Plugin:
    """This is the base class for all plugins. Maybe?"""
    pass


class NetworkEventName(str, enum.Enum):
    CONNECTED = 'connected'
    DISCONNECTED = 'disconnected'
    CLOSE_REQUEST = 'close_request'
    MESSAGE = 'message'
    RAW_LINE = 'raw_line'


class NetworkPlugin:

    """Base class for network-specific plugins.

    Shows the accepted hooks and their parameters.
    Event names are also available in the `NetworkEventName` enum.
    """

    def __init__(self, *args, network: 'shanghai.network.Network', logger: Logger, **kwargs) \
            -> None:
        super().__init__(*args, **kwargs)
        self.network = network
        self.logger = logger

    # def on_connected(self):
    #     pass

    # def on_disconnected(self):
    #     pass

    # def on_close_request(self, quitmsg: str):
    #     pass

    # def on_raw_line(self, raw_line: bytes):
    #     pass


class MessagePlugin(NetworkPlugin):

    """Base class for plugins that utilize messages.

    All message events accept a single `message` parameter
    of the type `shanghai.irc.Message`.

    Recognized event names are any ServerReply value
    and any server command like 'KICK' or 'NOTICE'.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._encoding = self.network.config.get('encoding', 'utf-8')
        self._fallback_encoding = self.network.config.get('fallback_encoding', 'latin1')

    def send_line(self, line: str):
        self.network._connection.writeline(line.encode(self._encoding))

    def send_cmd(self, command: str, *params: str):
        args = [command, *params]
        if ' ' in args[-1]:
            args[-1] = f":{args[-1]}"
        self.send_line(' '.join(args))

    def send_msg(self, target, text):
        # TODO split messages that are too long into multiple, also newlines
        self.send_cmd('PRIVMSG', target, text)

    def send_notice(self, target, text):
        # TODO split messages that are too long into multiple, also newlines
        self.send_cmd('NOTICE', target, text)


class CtcpPlugin(MessagePlugin):

    """Base class for plugins that operate on CTCP messages.

    All message events accept a single `message` parameter
    of the type `shanghai.irc.CtcpMessage`.

    Recognized event names are any ctcp command value,
    e.g. 'VERSION' or 'TIME'.
    """
    def send_ctcp(self, target: str, command: str, text: str = None):
        if text:
            text = ' ' + text
        text = f"\x01{command}{text}\x01"
        return self.send_msg(target, text)

    def send_ctcp_reply(self, target: str, command: str, text: str = None):
        if text:
            text = ' ' + text
        text = f"\x01{command}{text}\x01"
        return self.send_notice(target, text)
