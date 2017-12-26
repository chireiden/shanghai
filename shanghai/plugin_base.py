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
# recursive imports:
# from .network import Network
# from .channel import Channel


class NetworkEventName(str, enum.Enum):
    CONNECTED = 'connected'  # params: ()
    DISCONNECTED = 'disconnected'  # params: ()
    CLOSE_REQUEST = 'close_request'  # params: (quitmsg: str)
    RAW_LINE = 'raw_line'  # params: (raw_line: bytes)

    # emitted by core plugins
    MESSAGE = 'message'  # params: (message: Message)
    PRIVATE_MESSAGE = 'private_message'  # params: (message: PrivateMessage)
    PRIVATE_NOTICE = 'private_notice'  # params: (message: PrivateNotice)


class ChannelEventName(str, enum.Enum):
    JOINED = 'joined'  # params: ()
    PARTED = 'parted'  # params: (message: Message)
    KICKED = 'kicked'  # params: (message: Message)
    DISCONNECTED = NetworkEventName.DISCONNECTED  # params: ()
    MESSAGE = 'channel_message'  # params: (message: ChannelMessage)
    NOTICE = 'channel_notice'  # params: (message: ChannelNotice)


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

    def __init__(self) -> None:
        super().__init__()
        self._encoding = self.network.config.get('encoding', 'utf-8')  # type: ignore
        self._fallback_encoding = self.network.config.get('fallback_encoding',  # type: ignore
                                                          'latin1')

    def send_line(self, line: str) -> None:
        self.network.send_byteline(line.encode(self._encoding))  # type: ignore

    def send_cmd(self, command: str, *params: str) -> None:
        args = [command, *params]
        if ' ' in args[-1]:
            args[-1] = f":{args[-1]}"
        self.send_line(' '.join(args))

    def send_msg(self, target, text) -> None:
        # TODO split messages that are too long into multiple, also newlines
        self.send_cmd('PRIVMSG', target, text)

    def send_notice(self, target, text) -> None:
        # TODO split messages that are too long into multiple, also newlines
        self.send_cmd('NOTICE', target, text)


class CtcpPluginMixin(MessagePluginMixin):

    """Base class for plugins that operate on CTCP messages.

    All message events accept a single `message` parameter
    of the type `shanghai.irc.CtcpMessage`.

    Recognized event names are any ctcp command value,
    e.g. 'VERSION' or 'TIME'.
    """
    def send_ctcp(self, target: str, command: str, text: str = "") -> None:
        if text:
            text = ' ' + text
        text = f"\x01{command}{text}\x01"
        self.send_msg(target, text)

    def send_ctcp_reply(self, target: str, command: str, text: str = "") -> None:
        if text:
            text = ' ' + text
        text = f"\x01{command}{text}\x01"
        self.send_notice(target, text)

    def send_action(self, target: str, text: str = "") -> None:
        self.send_ctcp(target, 'ACTION', text)


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


class ChannelPlugin(CtcpPluginMixin):

    """Base class for channel-specific plugins.

    Event names are listed
    in the `ChannelEventName` enum
    with their parameters.
    """

    def __init__(self, channel: 'shanghai.channel.Channel') -> None:
        self.channel = channel
        self.network = channel.network
        self.logger = channel.logger
        super().__init__()


class ChannelMessageMixin(CtcpPluginMixin):

    def say(self, text: str) -> None:
        self.send_msg(self.channel.name, text)  # type: ignore

    def me(self, text: str) -> None:
        self.send_action(self.channel.name, text)  # type: ignore
