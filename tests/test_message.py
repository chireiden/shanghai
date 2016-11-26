
import pytest

from shanghai.irc import Prefix, Message, ServerReply


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


class TestMessage():

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
