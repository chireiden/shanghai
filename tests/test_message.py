
from unittest import TestCase
from shanghai.irc import Prefix, Message, ServerReply
from shanghai.logging import get_logger, set_logging_config, set_default_logger


class TestPrefix(TestCase):

    def test_from_string(self):
        prefix = Prefix.from_string(":nick")
        assert prefix == ("nick", None, None)

    def test_prefix(self):
        prefix = Prefix.from_string(':nick!user@host')
        assert prefix == ('nick', 'user', 'host')

        prefix = Prefix.from_string(':nick@host')
        assert prefix == ('nick', None, 'host')

        # rfc2812 requires @host before !user
        prefix = Prefix.from_string(':nick!user')
        assert prefix == ('nick!user', None, None)

        prefix = Prefix.from_string(':nick')
        assert prefix == ('nick', None, None)

        # without colon
        prefix = Prefix.from_string('nick!user@host')
        assert prefix == ('nick', 'user', 'host')

        # nothing
        prefix = Prefix.from_string('')
        assert prefix == ('', None, None)


class TestMessage(TestCase):

    def setUp(self):
        set_logging_config({
            'logging': {
                'disable': True
            }
        })
        self.logger = get_logger('test', 'test')
        set_default_logger(self.logger)

    def test_privmsg(self):
        m = Message.from_line(':nick!user@host PRIVMSG #channel :Some message')
        self.assertEqual(m.params, ['#channel', 'Some message'])
        self.assertEqual(m.command, 'PRIVMSG')

    def test_prefix(self):
        m = Message.from_line(':nick!user@host PRIVMSG #channel :msg')
        self.assertEqual(m.prefix, ('nick', 'user', 'host'))

        # test no prefix
        m = Message.from_line('PRIVMSG #channel :message test')
        self.assertIsNone(m.prefix)
        self.assertEqual(m.command, 'PRIVMSG')
        self.assertEqual(m.params, ['#channel', 'message test'])

    def test_numeric(self):
        m = Message.from_line(':prefix 001 params')
        self.assertEqual(m.command, ServerReply.RPL_WELCOME)

        m = Message.from_line(':prefix 1234 foo')
        self.assertEqual(m.command, '1234')

    def test_tags(self):
        m = Message.from_line('@tag=value;tag2=val\\nue2;tag3 :prefix CMD p1 :p2 long')
        # test if all other args still work correctly
        self.assertEqual(m.command, 'CMD')
        self.assertEqual(m.params, ['p1', 'p2 long'])
        self.assertEqual(m.prefix, ('prefix', None, None))

        # test the actual tags.
        self.assertEqual(m.tags, {'tag': 'value',
                                  'tag2': 'val\nue2',
                                  'tag3': True})

    def test_edge_cases(self):
        m = Message.from_line(':prefix COMMAND')
        self.assertEqual(m.params, [])

    def test_escape(self):
        s = Message.escape('hello world\r\nfoo\\bar;=')
        self.assertEqual(s, 'hello\\sworld\\r\\nfoo\\\\bar\\:=')

    def test_repr(self):
        # one cheap regex test on repr return value for coverage.
        import re
        m = Message.from_line(':nick!user@host PRIVMSG #channel :message')
        self.assertRegex(
            repr(m),
            re.compile(r'''
                Message\(["']PRIVMSG["'],\s*
                    prefix=Prefix\(
                        name=["']nick["'],\s*
                        ident=["']user["'],\s*
                        host=["']host["']\),\s*
                    params=\[["']\#channel["'],\s*["']message["']\],\s*
                    tags=\{\}\)''', re.X))
