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

import types
from typing import Dict, List, Mapping, NamedTuple, Optional, Sequence, Union

from .server_reply import ServerReply
from ..logging import get_default_logger


_ESCAPE_SEQUENCES = {
    'n': '\n',
    'r': '\r',
    's': ' ',
    '\\': '\\',
    ':': ';',
}


class Prefix(NamedTuple):

    name: str
    ident: Optional[str] = None
    host: Optional[str] = None

    @classmethod
    def from_string(cls, prefix: str) -> 'Prefix':
        name = prefix.lstrip(':')
        ident = None
        host = None
        if '@' in name:
            name, host = name.split('@', 1)
            if '!' in name:
                name, ident = name.split('!', 1)
        return cls(name, ident, host)

    def __str__(self) -> str:
        ret = self.name
        if self.host:
            if self.ident:
                ret += f"!{self.ident}"
            ret += f"@{self.host}"
        return ret


class Message(NamedTuple):

    command: str
    prefix: Optional[Prefix] = None
    params: Sequence[str] = ()
    tags: Mapping[str, Union[str, bool]] = types.MappingProxyType({})  # immutable dict
    raw_line: str = None

    @staticmethod
    def escape(value: str) -> str:
        out_value = ''
        sequences = {v: k for k, v in _ESCAPE_SEQUENCES.items()}
        for char in value:
            if char in sequences:
                out_value += '\\' + sequences[char]
            else:
                out_value += char
        return out_value

    @staticmethod
    def unescape(value: str) -> str:
        out_value = ''
        escape = False
        for char in value:
            if escape:
                out_value += _ESCAPE_SEQUENCES.get(char, char)
                escape = False
            else:
                if char == '\\':
                    escape = True
                else:
                    out_value += char
        return out_value

    @classmethod
    def from_line(cls, line: str) -> 'Message':
        # https://tools.ietf.org/html/rfc2812#section-2.3.1
        # http://ircv3.net/specs/core/message-tags-3.2.html
        raw_line = line
        tags: Dict[str, Union[str, bool]] = {}
        prefix = None

        if line.startswith('@'):
            # irc tag
            tag_string, _, line = line.partition(" ")
            for tag in tag_string[1:].split(';'):
                if '=' in tag:
                    key, value = tag.split('=', 1)
                    tags[key] = cls.unescape(value)
                else:
                    tags[tag] = True

        if line.startswith(':'):
            prefix_str, _, line = line.partition(" ")
            prefix = Prefix.from_string(prefix_str)

        command, _, line = line.partition(" ")
        command = command.upper()  # TODO check if really case-insensitive
        if command.isdigit():
            try:
                command = ServerReply(command)
            except ValueError:
                get_default_logger().warning(f"unknown server reply code {command}; {raw_line}")

        params: List[str] = []
        while line:
            if line.startswith(':'):
                params.append(line[1:])
                line = ''
            else:
                param, _, line = line.partition(" ")
                params.append(param)

        return cls(command, prefix, params, tags, raw_line)

    def __repr__(self) -> str:
        return (f"{self.__class__.__name__}({self.command!r}, prefix={self.prefix!r},"
                f" params={self.params!r}, tags={self.tags!r})")


class CtcpMessage(Message):
    # http://www.kvirc.net/doc/doc_ctcp_handling.html

    @classmethod
    def from_message(cls, msg: Message):
        """Very primitive but should do the job for now."""
        if not msg.command == 'PRIVMSG':
            return None
        line = msg.params[1]
        if not line.startswith('\x01') or not line.endswith('\x01'):
            return None
        line = line[1:-1].rstrip()
        if not line:
            return None
        ctcp_cmd, _, ctcp_text = line.partition(' ')
        if not ctcp_cmd:
            return None
        ctcp_cmd = ctcp_cmd.upper()
        ctcp_params = ctcp_text.split()

        fields = {**msg._asdict(), 'command': ctcp_cmd, 'params': ctcp_params}
        return cls(**fields)  # type: ignore
