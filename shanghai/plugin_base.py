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

from .logging import Logger
# from ..network import Network


class NetworkEventName(str, enum.Enum):
    CONNECTED = 'connected'  # params: ()
    DISCONNECTED = 'disconnected'  # params: ()
    CLOSE_REQUEST = 'close_request'  # params: (quitmsg: str)
    MESSAGE = 'message'  # params: (message: Message)
    RAW_LINE = 'raw_line'  # params: (raw_line: bytes)


class NetworkPlugin:

    """Base class for network-specific plugins.

    Standard event names are listed
    in the `NetworkEventName` enum
    with their parameters.

    Additional event names are any ServerReply value
    and any server command like 'KICK' or 'NOTICE'.
    All message events accept a single `message` parameter
    of the type `shanghai.irc.Message`.
    """

    def __init__(self, network: 'shanghai.network.Network', logger: Logger) -> None:
        self.network = network
        self.logger = logger
        super().__init__()

class MessagePluginMixin:

    """Mixin class providing message sending methods.

    All message events accept a single `message` parameter
    of the type `shanghai.irc.Message`.

    Recognized event names are any ServerReply value
    and any server command like 'KICK' or 'NOTICE'.
    """

    def __init__(self):
        super().__init__()
        self._encoding = self.network.config.get('encoding', 'utf-8')
        self._fallback_encoding = self.network.config.get('fallback_encoding', 'latin1')

    def send_line(self, line: str):
        self.network.send_byteline(line.encode(self._encoding))

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


class CtcpPluginMixin(MessagePluginMixin):

    """Base class for plugins that operate on CTCP messages.

    All message events accept a single `message` parameter
    of the type `shanghai.irc.CtcpMessage`.

    Recognized event names are any ctcp command value,
    e.g. 'VERSION' or 'TIME'.
    """
    def send_ctcp(self, target: str, command: str, text: str = ""):
        if text:
            text = ' ' + text
        text = f"\x01{command}{text}\x01"
        return self.send_msg(target, text)

    def send_ctcp_reply(self, target: str, command: str, text: str = ""):
        if text:
            text = ' ' + text
        text = f"\x01{command}{text}\x01"
        return self.send_notice(target, text)


class OptionsPluginMixin:

    @property
    def nick_lower(self):
        return self.network.options.nick_lower

    @property
    def chan_lower(self):
        return self.network.options.chan_lower

    @property
    def nick_eq(self):
        return self.network.options.nick_eq

    @property
    def chan_eq(self):
        return self.network.options.chan_eq
