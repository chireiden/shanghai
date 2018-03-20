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

import pytest

from shanghai.irc import Prefix, Message, ServerReply
from shanghai.irc.message import CtcpMessage, TextMessage


class TestPrefix:

    @pytest.mark.parametrize(
        'string, expected',
        [
            (':nick!user@host', ('nick', 'user', 'host')),
            (':nick@host', ('nick', None, 'host')),
            # rfc2812 requires @host before !user
            (':nick!user', ('nick!user', None, None)),
            (':nick', ('nick', None, None)),
            # without colon
            ('nick!user@host', ('nick', 'user', 'host')),
            # nothing
            ('', ('', None, None)),
        ]
    )
    def test_from_string_and_str(self, string, expected):
        prefix = Prefix.from_string(string)
        assert tuple(prefix) == expected
        assert str(prefix) == string.lstrip(':')


class TestMessage:

    def test_privmsg(self):
        m = Message.from_line(':nick!user@host PRIVMSG #channel :Some message')
        assert m.params == ['#channel', 'Some message']
        assert m.command == 'PRIVMSG'

    def test_prefix(self):
        m = Message.from_line(':nick!user@host PRIVMSG #channel :msg')
        assert m.prefix == ('nick', 'user', 'host')

        # test no prefix
        m = Message.from_line('PRIVMSG #channel :message test')
        assert m.prefix is None
        assert m.command == 'PRIVMSG'
        assert m.params == ['#channel', 'message test']

    def test_numeric(self):
        m = Message.from_line(':prefix 001 params')
        assert m.command == ServerReply.RPL_WELCOME

        m = Message.from_line(':prefix 1234 foo')
        assert m.command == '1234'

    def test_tags(self):
        m = Message.from_line('@tag=value;tag2=val\\nue2;tag3 :prefix CMD p1 :p2 long')
        # test if all other args still work correctly
        assert m.command == 'CMD'
        assert m.params == ['p1', 'p2 long']
        assert m.prefix == ('prefix', None, None)

        # test the actual tags.
        assert m.tags == {'tag': 'value',
                          'tag2': 'val\nue2',
                          'tag3': True}

    def test_edge_cases(self):
        m = Message.from_line(':prefix COMMAND')
        assert m.params == []

    def test_escape(self):
        s = Message.escape('hello world\r\nfoo\\bar;=')
        assert s == 'hello\\sworld\\r\\nfoo\\\\bar\\:='

    def test_repr(self):
        # one cheap regex test on repr return value for coverage.
        import re
        m = Message.from_line(':nick!user@host PRIVMSG #channel :message')
        assert re.match(
            r'''(?x)
                Message\(["']PRIVMSG["'],\s*
                    prefix=Prefix\(
                        name=["']nick["'],\s*
                        ident=["']user["'],\s*
                        host=["']host["']\),\s*
                    params=\[["']\#channel["'],\s*["']message["']\],\s*
                    tags=\{\}\)''',
            repr(m)
        )


class TestCtcpMessage:

    def test_message(self):
        m = Message.from_line(':nick!user@host PRIVMSG #channel :\001PING PONG\001')
        cm = CtcpMessage.from_message(m)
        assert cm.command == "PING"
        assert cm.params == ["PONG"]
        assert cm.prefix == m.prefix

    def test_not_message(self):
        m = Message.from_line(':nick!user@host NOTICE #channel :\001not a PRIVMSG\001')
        assert CtcpMessage.from_message(m) is None

        m = Message.from_line(':nick!user@host PRIVMSG #channel :\001this is just bold text')
        assert CtcpMessage.from_message(m) is None

        m = Message.from_line(':nick!user@host PRIVMSG #channel :\001\001')  # what is this even
        assert CtcpMessage.from_message(m) is None

        m = Message.from_line(':nick!user@host PRIVMSG #channel :\001 or this\001')
        assert CtcpMessage.from_message(m) is None


class TestTextMessage:

    def test_attrs(self):
        m = Message.from_line(':nick!user@host PRIVMSG #channel :Some  message')
        tm = TextMessage.from_message(m)
        assert tm.sender == "nick"
        assert tm.target == "#channel"
        assert tm.line == "Some  message"
        assert tm.words == ["Some", "message"]
