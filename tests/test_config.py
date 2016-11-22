
import os
import tempfile
from textwrap import dedent

import pytest
from ruamel import yaml as ryaml

from shanghai.config import (
    Server, Configuration, ConfigurationError, ShanghaiConfiguration,
    FallbackConfiguration, NetworkConfiguration,
)


@pytest.fixture(scope='module')
def load():
    def _load(yaml_string):
        return ryaml.safe_load(dedent(yaml_string))
    return _load


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

    def test_init(self):
        assert Configuration()

        with pytest.raises(ValueError) as excinfo:
            Configuration([])
        excinfo.match("Must be a mapping")

        with pytest.raises(ValueError) as excinfo:
            Configuration("str")
        excinfo.match("Must be a mapping")

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


class TestNetworkConfig():

    @pytest.fixture
    def base_yaml(self, load):
        return load("""\
            name: Network2
            nick: Nick
            user: User
            realname: Realname
            servers:
              - irc.foobar.net:+
        """)

    def test_init(self, base_yaml):
        nw_c = NetworkConfiguration("my_netw", base_yaml)
        assert nw_c.name == "my_netw"

    def test_require_keys(self, base_yaml):
        test_yaml = base_yaml.copy()

        del test_yaml['nick']
        with pytest.raises(ConfigurationError) as excinfo:
            NetworkConfiguration("my_netw", test_yaml)
        excinfo.match("Network ['\"]my_netw['\"] is missing the following options: nick")

        del test_yaml['user']
        del test_yaml['realname']
        with pytest.raises(ConfigurationError) as excinfo:
            NetworkConfiguration("my_netw", test_yaml)
        excinfo.match("Network ['\"]my_netw['\"] is missing the following options: "
                      "nick, realname, user")

    def test_parse_servers(self, base_yaml):
        nw_c = NetworkConfiguration("my_netw", base_yaml)
        assert len(nw_c.servers) == 1
        assert isinstance(nw_c.servers[0], Server)
        assert nw_c.servers[0].host == "irc.foobar.net"
        assert nw_c.servers[0].port == 6697
        assert nw_c.servers[0].ssl is True

        del base_yaml['servers'][0]
        with pytest.raises(ConfigurationError) as excinfo:
            NetworkConfiguration("my_netw", base_yaml)
        excinfo.match("Network ['\"]my_netw['\"] has no servers")

        base_yaml['servers'] = "a string"
        with pytest.raises(ConfigurationError) as excinfo:
            NetworkConfiguration("my_netw", base_yaml)
        excinfo.match("Servers of Network ['\"]my_netw['\"] are not a list")

        del base_yaml['servers']
        with pytest.raises(ConfigurationError) as excinfo:
            NetworkConfiguration("my_netw", base_yaml)
        excinfo.match("Network ['\"]my_netw['\"] has no servers")

    @pytest.mark.skip("feature to be moved elsewhere")
    def test_fix_channels(self):
        pass


class TestShanghaiConfig:

    @pytest.fixture
    def sample_yaml(self, load):
        return load('''\
            nick: TestBot
            realname: Sample Bot

            logging:
              level: INFO

            encoding: utf-16

            networks:
              sample_network:
                user: Shanghai
                fallback_encoding: cp1252
                servers:
                  - host: irc.example.org
                    ssl: true
                  - irc.example.org:6667
                # TODO readd this once channels core plugin exists and it's not modified anymore
                #channels:
                #  foochannel:
                #  barchannel: null
                #  otherchannel:
                #    key: some_key
                #  '##foobar':

              second_network:
                nick: NickOverride
                user: Shanghai2
                servers:
                  - host: irc.foobar.net
                    ssl: true
        ''')

    def test_init(self, sample_yaml):
        config = ShanghaiConfiguration(sample_yaml)
        assert config['logging.level'] == 'INFO'

    def test_parse_networks(self, sample_yaml):
        config = ShanghaiConfiguration(sample_yaml)
        networks = config.networks
        assert len(networks) == 2
        assert isinstance(networks[0], NetworkConfiguration)

        netw_map = {netw.name: netw for netw in networks}
        assert netw_map['sample_network']['nick'] == "TestBot"
        assert netw_map['sample_network']['user'] == "Shanghai"
        assert netw_map['sample_network']['encoding'] == "utf-16"

        assert netw_map['second_network']['nick'] == "NickOverride"
        assert netw_map['second_network']['user'] == "Shanghai2"

        del sample_yaml['networks']
        with pytest.raises(ConfigurationError) as excinfo:
            ShanghaiConfiguration(sample_yaml)
        excinfo.match("No networks found")

    def test_fileloading(self, sample_yaml):
        # Cannot use tempfile.NamedTemporaryFile because of Windows's file locks
        fd, fname = tempfile.mkstemp('w')
        try:
            with open(fd, 'w', encoding='utf-8') as f:
                ryaml.dump(sample_yaml, f)
            config = ShanghaiConfiguration.from_filename(fname)
        finally:
            os.remove(fname)

        assert config.mapping == sample_yaml
