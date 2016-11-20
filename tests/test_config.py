
import io
import os
import re
import tempfile

import pytest
from ruamel import yaml as ryaml

from shanghai.config import (
    Server, Configuration, ConfigurationError, ShanghaiConfiguration,
    FallbackConfiguration, # NetworkConfiguration,
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

    @pytest.fixture(scope='class')
    def fake_yaml(self):
        return {
            'foo': 123,
            'bar': {
                'foo': "baz",
                'bar': None,
            },
            'ellipsis': ...,
        }

    @pytest.fixture(scope='class')
    def c(self, fake_yaml):
        return Configuration(fake_yaml)

    def test_get(self, c, fake_yaml):
        assert c.get('foo', 456) == 123
        assert c.get('bar') == fake_yaml['bar']
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
            c.get('bar..baz')
        excinfo.match("Empty sub-key after ['\"]bar['\"]")

    def test_getitem(self, c, fake_yaml):
        assert c['foo'] == 123
        assert c['bar'] == fake_yaml['bar']
        assert c['bar.foo'] == "baz"
        assert c['bar.bar'] is None
        assert c['ellipsis'] is ...

        with pytest.raises(KeyError) as excinfo:
            c['foo.baz']
        excinfo.match("Element ['\"]foo['\"] is not a mapping")

        with pytest.raises(KeyError) as excinfo:
            c['foo.baz.bar']
        excinfo.match("Element ['\"]foo['\"] is not a mapping")

        with pytest.raises(KeyError) as excinfo:
            c['baz']
        excinfo.match("Cannot find ['\"]baz['\"]")

        with pytest.raises(KeyError) as excinfo:
            c['bar.baz']
        excinfo.match("Cannot find ['\"]bar.baz['\"]")

        with pytest.raises(KeyError) as excinfo:
            c['bar..baz']
        excinfo.match("Empty sub-key after ['\"]bar['\"]")

    def test_contains(self, c):
        assert 'foo' in c
        assert 'bar.foo' in c
        assert 'baz' not in c
        assert 'bar.baz' not in c
        assert 'ellipsis' in c


class TestFallbackConfig:

    @pytest.fixture(scope='class')
    def fake_yaml(self):
        return {
            'foo': 456,
            'ellipsis': ...,
        }

    @pytest.fixture(scope='class')
    def fake_fallback_yaml(self):
        return {
            'foo': 123,
            'bar': {
                'foo': "baz",
                'bar': None,
            },
        }

    @pytest.fixture(scope='class')
    def fb_c(self, fake_yaml, fake_fallback_yaml):
        return FallbackConfiguration(fake_yaml, Configuration(fake_fallback_yaml))

    def test_get(self, fb_c, fake_fallback_yaml):
        assert fb_c.get('foo') == 456
        assert fb_c.get('bar') == fake_fallback_yaml['bar']
        assert fb_c.get('bar.foo') == 'baz'

        assert fb_c.get('bar.baz') is None

        with pytest.raises(KeyError) as excinfo:
            fb_c.get('foo.baz')
        excinfo.match("Element ['\"]foo['\"] is not a mapping")

        with pytest.raises(KeyError) as excinfo:
            fb_c.get('bar..baz')
        excinfo.match("Empty sub-key after ['\"]bar['\"]")

    def test_getitem(self, fb_c, fake_fallback_yaml):
        assert fb_c['foo'] == 456
        assert fb_c['bar'] == fake_fallback_yaml['bar']
        assert fb_c['bar.foo'] == "baz"
        assert fb_c['bar.bar'] is None
        assert fb_c['ellipsis'] is ...

        with pytest.raises(KeyError) as excinfo:
            fb_c['foo.baz']
        excinfo.match("Element ['\"]foo['\"] is not a mapping")

        with pytest.raises(KeyError) as excinfo:
            fb_c['bar.foo.bar']
        excinfo.match("Element ['\"]bar.foo['\"] is not a mapping")

        with pytest.raises(KeyError) as excinfo:
            fb_c['baz']
        excinfo.match("Cannot find ['\"]baz['\"]")

        with pytest.raises(KeyError) as excinfo:
            fb_c['bar.baz']
        excinfo.match("Cannot find ['\"]bar.baz['\"]")

        with pytest.raises(KeyError) as excinfo:
            fb_c['bar..baz']
        excinfo.match("Empty sub-key after ['\"]bar['\"]")

    def test_contains(self, fb_c):
        assert 'foo' in fb_c
        assert 'bar.foo' in fb_c
        assert 'baz' not in fb_c
        assert 'bar.baz' not in fb_c
        assert 'ellipsis' in fb_c


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
