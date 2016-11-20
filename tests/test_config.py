
import io
import os
import re
import tempfile

import pytest
from ruamel import yaml as ryaml

from shanghai.config import (
    Server, Configuration, ConfigurationError, ShanghaiConfiguration,
    # NetworkConfiguration, FallbackConfiguration
)

SAMPLE_YAML = '''\
nick: TestBot
user: Shanghai
realname: Sample Bot

# set global logging level
logging:
  level: INFO

networks:
  sample_network:
    encoding: utf-8
    fallback_encoding: latin1
    name: SampleNetwork
    servers:
      - host: irc.example.org
        ssl: true
      - irc.example.org:6667
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
foo: bar

networks:
  sample_network:
    encoding: utf-8
    fallback_encoding: latin1
    name: SampleNetwork
    servers:
      irc.example.org:
'''

BROKEN_CONF_2 = '''\
nick: TestBot
user: testuser
realname: Test Name

networks:
  sample_network:
    encoding: utf-8
    fallback_encoding: latin1
    name: SampleNetwork
'''


@pytest.fixture(scope='module')
def sample_yaml():
    return ryaml.safe_load(io.StringIO(SAMPLE_YAML))


@pytest.fixture(scope='module')
def broken_conf_1():
    return ryaml.safe_load(io.StringIO(BROKEN_CONF_1))


@pytest.fixture(scope='module')
def broken_conf_2():
    return ryaml.safe_load(io.StringIO(BROKEN_CONF_2))


class TestServer:

    def test_defaults(self):
        server = Server("host")
        assert server.host == "host"
        assert server.port == 6667
        assert server.ssl is False

        server = Server("host", ssl=True)
        assert server.host == "host"
        assert server.port == 6697
        assert server.ssl is True

    def test_from_string(self):
        server = Server.from_string("my_host:999")
        assert server.host == "my_host"
        assert server.port == 999
        assert server.ssl is False

        server = Server.from_string("my_host:+123")
        assert server.host == "my_host"
        assert server.port == 123
        assert server.ssl is True

    @pytest.mark.parametrize(
        "source,expected",
        [
            ("my_host:123", "my_host:123"),
            ("my_host:+123", "my_host:+123"),
            ("my_host:", "my_host:6667"),
            ("my_host:+", "my_host:+6697"),
        ]
    )
    def test_str(self, source, expected):
        server = Server.from_string(source)
        assert str(server) == expected


class TestConfig:

    fake_yaml = {
        'foo': 123,
        'bar': {
            'foo': 'baz',
            'bar': None,
        },
    }

    def test_get(self):
        c = Configuration(self.fake_yaml)

        assert c.get('foo', 456) == 123
        assert c.get('bar') == self.fake_yaml['bar']
        assert c.get('bar.foo') == "baz"
        assert c.get('bar.bar', 123) is None

        assert c.get('baz') is None
        assert c.get('baz', 123) == 123
        assert c.get('baz', 123) == 123
        assert c.get('bar.baz', 234) == 234
        assert c.get('baz.baz', 234) == 234

        with pytest.raises(KeyError) as excinfo:
            c.get('foo.baz')
        excinfo.match("Element ['\"]foo['\"] is not a mapping")

        with pytest.raises(KeyError) as excinfo:
            c.get('foo.baz.bar')
        excinfo.match("Element ['\"]foo['\"] is not a mapping")

    def test_getattr(self):
        c = Configuration(self.fake_yaml)

        with pytest.raises(KeyError) as excinfo:
            c['foo.baz']
        excinfo.match("Element ['\"]foo['\"] is not a mapping")

        with pytest.raises(KeyError) as excinfo:
            c['baz']
        excinfo.match("Cannot find ['\"]baz['\"]")

        with pytest.raises(KeyError) as excinfo:
            c['bar.baz']
        excinfo.match("Cannot find ['\"]bar.baz['\"]")

    def test_contains(self):
        c = Configuration(self.fake_yaml)

        assert "foo" in c
        assert "bar.foo" in c
        assert "baz" not in c
        assert "bar.baz" not in c


class TestShanghaiConfig:

    def test_fileloading(self, sample_yaml):
        # Reset channel mapping because they are being modified (currently)
        # TODO remove this once channels core plugin exists
        test_yaml = sample_yaml.copy()
        test_yaml['networks']['sample_network']['channels'] = {}
        test_yaml['networks']['second_network']['channels'] = {}

        # Cannot use tempfile.NamedTemporaryFile because of Windows's file locks
        fd, fname = tempfile.mkstemp('w')
        try:
            with open(fd, 'w', encoding='utf-8') as f:
                ryaml.dump(test_yaml, f)
            config = ShanghaiConfiguration.from_filename(fname)
        finally:
            os.remove(fname)

        assert config.mapping == test_yaml

    @pytest.mark.skip("TODO")
    def test_network_attr(self, sample_yaml, broken_conf_1, broken_conf_2):
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
