
import ruamel.yaml


class ConfigurationError(ValueError):
    pass


class NamedConfig:
    def __init__(self, name, **kwargs):
        self.name = name
        self._kwargs = kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __repr__(self):
        args = ', '.join('{}={!r}'.format(k, v) for
                         k, v in self._kwargs.items())
        return '{}({})'.format(self.name, args)


class Configuration:

    def __init__(self, yaml_config):
        self._yaml = yaml_config

    def __getattr__(self, item):
        return self._yaml[item]

    @classmethod
    def from_filename(cls, filename):
        with open(filename, 'r', encoding='utf-8') as f:
            yaml_config = ruamel.yaml.safe_load(f)
        return cls(yaml_config)

    @classmethod
    def clone_with_merge(cls, base: dict, additions: dict):
        target = base.copy()
        for key, value in additions.items():
            if isinstance(value, dict):
                value = cls.clone_with_merge(base.get(key, {}), value)
            target[key] = value
        return target

    @staticmethod
    def _network_config_sanity_tests(network_key, config):
        keys = set(config)
        needed_keys = {'name', 'nick', 'user', 'realname', 'servers'}
        diff = needed_keys - keys
        if diff:
            raise ConfigurationError(
                'Network {!r} is missing the following options: {}'.format(
                    network_key, ', '.join(diff)))

    @property
    def networks(self):
        global_config = self._yaml.get('networks', {}).get('GLOBAL', {})
        default_server = dict(
            port=6667,
            ssl=False,
        )

        for network_key, network_conf in \
                self._yaml.get('networks', {}).items():
            if network_key == 'GLOBAL':
                continue

            if 'channels' not in network_conf:
                network_conf['channels'] = {}

            for channel, channel_conf in network_conf['channels'].items():
                if channel_conf is None:
                    network_conf['channels'][channel] = channel_conf = {}
                # replace channel names 'foobar' with '#foobar'
                if not channel.startswith(('#', '&', '+', '!')):
                    del network_conf['channels'][channel]
                    network_conf['channels']['#{}'.format(channel)] = \
                        channel_conf

            if 'servers' not in network_conf:
                raise ConfigurationError('Network {!r} has no server'.format(
                    network_conf['name']))

            server_list = []
            for host, server_opts in network_conf['servers'].items():
                server_dict = {**default_server,
                               'host': host,
                               **(server_opts if server_opts is not None
                                  else {})}
                server = NamedConfig('Server', **server_dict)
                server_list.append(server)
            network_conf['servers'] = server_list

            config = self.clone_with_merge(global_config, network_conf)
            self._network_config_sanity_tests(network_key, config)
            yield {'name': network_key, 'config': config}
