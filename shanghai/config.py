
from collections import namedtuple
import configparser

Server = namedtuple('Server', 'host port ssl')
Channel = namedtuple('Channel', 'channel key')


class Configuration:

    def __init__(self, filename):
        self.parser = configparser.ConfigParser(
            allow_no_value=True,
            comment_prefixes=(';', '%'),
        )
        with open(filename, 'r', encoding='utf-8') as f:
            self.parser.read_file(f)

    def get_section(self, name):
        values = {}
        for key, value in self.parser[name].items():
            if value.rstrip(' \t').startswith('\n'):
                lines_raw = value.splitlines()
                lines = []
                for line in lines_raw:
                    line = line.strip()
                    if not line:
                        continue
                    lines.append(line)
                value = lines
            values[key] = value
        return values

    @staticmethod
    def parse_autojoin(autojoin_raw):
        if isinstance(autojoin_raw, str):
            autojoin_raw = [autojoin_raw]
        autojoin = []
        for channel in autojoin_raw:
            if not channel.strip():
                continue
            channel, *rest = channel.split()
            key = None
            if rest:
                key = rest[0]
            autojoin.append(Channel(channel, key))
        return autojoin

    @staticmethod
    def parse_servers(server_list):
        if isinstance(server_list, str):
            server_list = [server_list]
        servers = []
        for server in server_list:
            if not server.strip():
                continue
            port = 6667
            ssl = False
            host = server
            if ':' in server:
                host, port = server.split(':', 1)
                if port.startswith('+'):
                    port = port[1:]
                    ssl = True
                port = int(port)
            servers.append(Server(host, port, ssl))
        return servers

    @property
    def networks(self):
        global_config = self.get_section('global')
        global_config['autojoin'] = self.parse_autojoin(
            global_config.get('autojoin', []))

        for network, servers in self.get_section('networks').items():

            try:
                values = self.get_section('network.' + network)
            except KeyError:
                values = {}
            values['autojoin'] = self.parse_autojoin(
                values.get('autojoin', []))
            values['servers'] = self.parse_servers(servers)

            yield {'name': network, 'config': {**global_config, **values}}
