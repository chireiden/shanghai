
from collections import abc as c_abc
from types import SimpleNamespace

from ruamel import yaml as ryaml


class ConfigurationError(ValueError):
    pass


class Server(SimpleNamespace):
    _default_ports = {True: 6697, False: 6667}

    def __init__(self, host, port=None, ssl=False):
        if port is None:
            port = self._default_ports[ssl]
        super().__init__(host=host, port=port, ssl=ssl)

    @classmethod
    def from_string(cls, string):
        host, _, port = string.partition(":")
        _, ssl, port = port.rpartition("+")
        port = int(port) if port else None
        ssl = bool(ssl)
        return cls(host, port, ssl)

    def __str__(self):
        return f"{self.host}:{'+' if self.ssl else ''}{self.port}"


class Configuration:

    """Interfaces a mapping in a way that allows dot-separated sub-keys.

    For example, `config['logging.enabled']` on a dict would be
    equivalent to `d['logging']['enabled']`,
    and `config.get('logging.enabled')` would be
    equivalent to `d.get('logging', {}).get('enabled')`.
    """

    def __init__(self, mapping=None):
        if mapping is None:
            mapping = {}
        if not isinstance(mapping, c_abc.Mapping):
            raise ValueError("Must be a mapping")
        self.mapping = mapping

    def get(self, item, default=None):
        """Get a value from the config mapping, with a default value.
        """
        try:
            return self[item]
        except KeyError as e:
            if e.args[0].startswith("Cannot find"):
                return default
            else:
                raise

    def __getitem__(self, key):
        node = self.mapping
        leafs = key.split(".")

        for i, leaf in enumerate(leafs):
            if not isinstance(node, c_abc.Mapping):
                raise KeyError(f"Element {'.'.join(leafs[:i])!r} is not a mapping")
            if not leaf:
                raise KeyError(f"Empty sub-key after {'.'.join(leafs[:i])!r}")
            if leaf not in node:
                break
            node = node[leaf]
        else:
            return node

        raise KeyError(f"Cannot find '{key}'")

    def __contains__(self, key):
        obj = object()
        return self.get(key, obj) is not obj


class FallbackConfiguration(Configuration):

    """Like Configuration, but can fallback to other Configurations if keys are not found."""

    def __init__(self, mapping, *fallback_configs: Configuration):
        super().__init__(mapping)
        # for fb_c in fallback_configs:
        #     if not isinstance(fb_c, Configuration):
        #         raise ValueError(f"{fb_c!r} is not an instance of {Configuration}")
        self.fallback_configs = fallback_configs

    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError as e:
            if not e.args[0].startswith("Cannot find"):
                raise

        obj = object()
        for config in self.fallback_configs:
            value = config.get(key, obj)
            if value is not obj:
                return value

        raise KeyError(f"Cannot find '{key}'")

    def __contains__(self, key):
        # if super().__contains__(key):
        #     return True
        # else:
        #     return any(key in config for config in self.fallback_configs)
        return any(config.__contains__(key) for config in (super(), *self.fallback_configs))

    def __repr__(self):
        mapping = self.mapping
        if len(mapping) > 5:
            mapping = "{...}"
        return f"{type(self).__name__}({mapping}, *fallback_configs={self.fallback_configs!r})"


class NetworkConfiguration(FallbackConfiguration):

    def __init__(self, name, mapping, *fallback_configs: Configuration):
        super().__init__(mapping, *fallback_configs)
        self.name = name

        self._require_keys({'nick', 'user', 'realname'})
        self._fix_channels(mapping)

        self.servers = self._parse_servers(mapping)

    @staticmethod
    def _fix_channels(mapping):
        # TODO move to channels core plugin
        for channel, channel_conf in mapping.get('channels', {}).items():
            if channel_conf is None:
                mapping['channels'][channel] = channel_conf = {}

            # replace channel names 'foobar' with '#foobar'
            if not channel.startswith(tuple('#&+!')):
                del mapping['channels'][channel]
                mapping['channels'][f'#{channel}'] = channel_conf

    def _parse_servers(self, mapping):
        servers = []
        servers_conf = mapping.get('servers')
        if not servers_conf:
            raise ConfigurationError(f"Network {self.name!r} has no servers")
        if not isinstance(servers_conf, list):
            raise ConfigurationError(f"Servers of Network {self.name!r} are not a list")
        for server_conf in mapping.get('servers', ()):
            if isinstance(server_conf, str):
                server = Server.from_string(server_conf)
            else:
                server = Server(**server_conf)
            servers.append(server)

        else:
            return servers

    def _require_keys(self, required_keys):
        missing_keys = sorted(key for key in required_keys if key not in self)
        if missing_keys:
            raise ConfigurationError(f"Network {self.name!r} is missing the following options: "
                                     f"{', '.join(missing_keys)}")

    def __repr__(self):
        mapping = self.mapping
        if len(mapping) > 5:
            mapping = "{...}"
        return (f"{type(self).__name__}({self.name!r}, {mapping}, "
                f"*fallback_configs={self.fallback_configs!r})")


class ShanghaiConfiguration(Configuration):

    def __init__(self, mapping):
        super().__init__(mapping)
        self.networks = list(self._parse_networks(mapping))

    @classmethod
    def from_filename(cls, filename):
        with open(filename, 'r', encoding='utf-8') as f:
            yaml_config = ryaml.safe_load(f)
        return cls(yaml_config)

    def _parse_networks(self, root):
        networks = root.get('networks', None)
        if networks is None:
            raise ConfigurationError("No networks found")

        return [NetworkConfiguration(name, mapping, self)
                for name, mapping in networks.items()]
