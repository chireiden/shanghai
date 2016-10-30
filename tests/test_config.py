
import io
import re
import tempfile
from unittest import TestCase

from ruamel import yaml as ryaml

from shanghai.config import Configuration, NamedConfig, ConfigurationError

SAMPLE_YAML = '''\
# set global logging level
logging:
  level: INFO

networks:
  GLOBAL:
    nick: TestBot
    user: Shanghai
    realname: Sample Bot

  sample_network:
    encoding: utf-8
    fallback_encoding: latin1
    name: SampleNetwork
    servers:
      irc.example.org:
        port: 6697
        ssl: true
    channels:
      foochannel:
      barchannel: null
      otherchannel:
        key: some_key
      '##foobar':

  second_network:
    name: Network2
    servers:
      irc.foobar.net:
        ssl: true
'''

BROKEN_CONF_1 = '''\
# set global logging level
logging:
  level: INFO

networks:
  GLOBAL:
    foo: bar

  sample_network:
    encoding: utf-8
    fallback_encoding: latin1
    name: SampleNetwork
    servers:
      irc.example.org:
'''

BROKEN_CONF_2 = '''\
# set global logging level
logging:
  level: INFO

networks:
  GLOBAL:
    nick: TestBot
    user: testuser
    realname: Test Name

  sample_network:
    encoding: utf-8
    fallback_encoding: latin1
    name: SampleNetwork
'''


class TestConfig(TestCase):

    def setUp(self):
        self.fake_yaml = {
            'foo': 123,
            'bar': 'baz',
        }
        self.sample_yaml = ryaml.safe_load(io.StringIO(SAMPLE_YAML))
        self.broken_conf_1 = ryaml.safe_load(io.StringIO(BROKEN_CONF_1))
        self.broken_conf_2 = ryaml.safe_load(io.StringIO(BROKEN_CONF_2))

    def test_namedconfig(self):
        nc = NamedConfig('MyConf', foo=123, bar='spam')
        self.assertIn(repr(nc), [
            'MyConf(foo=123, bar=\'spam\')',
            'MyConf(bar=\'spam\', foo=123)',
            'MyConf(foo=123, bar="spam")',
            'MyConf(bar="spam", foo=123)',
        ])

    def test_config(self):
        c = Configuration(self.fake_yaml)

        value = c.get('foo', 456)
        self.assertEqual(value, 123)

        self.assertEqual(c.foo, 123)
        self.assertEqual(c.bar, 'baz')

        self.assertSequenceEqual(
            sorted(c.items()),
            sorted(self.fake_yaml.items())
        )

    def test_fileloading(self):

        with tempfile.NamedTemporaryFile('w+', encoding='utf-8') as f:
            ryaml.dump(self.fake_yaml, f)
            f.seek(0)
            c = Configuration.from_filename(f.name)

        self.assertDictEqual(
            c._yaml,
            self.fake_yaml
        )

    def test_clone_with_merge(self):
        # could probably be more thorough
        new_dict = Configuration.clone_with_merge(
            self.fake_yaml, {'spam': {'spaz': 'blah'}}
        )
        self.assertDictEqual(
            new_dict,
            {
                'foo': 123,
                'bar': 'baz',
                'spam': {'spaz': 'blah'},
            }
        )

    def test_network_attr(self):
        c = Configuration(self.sample_yaml)
        for network in c.networks:
            self.assertIn(network['name'], ('sample_network',
                                            'second_network'))

        c = Configuration(self.broken_conf_1)
        self.assertRaisesRegex(
            ConfigurationError,
            re.compile(r'is missing the following options'),
            list, c.networks)

        c = Configuration(self.broken_conf_2)
        self.assertRaisesRegex(
            ConfigurationError,
            re.compile(r'has no server'),
            list, c.networks)
