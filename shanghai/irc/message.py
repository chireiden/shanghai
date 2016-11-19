
from collections import namedtuple

from .server_reply import ServerReply
from ..logging import current_logger


_ESCAPE_SEQUENCES = {
    'n': '\n',
    'r': '\r',
    's': ' ',
    '\\': '\\',
    ':': ';',
}


class Prefix(namedtuple("_Prefix", "name ident host")):

    __slots__ = ()

    @classmethod
    def from_string(cls, prefix):
        name = prefix.lstrip(':')
        ident = None
        host = None
        if '@' in name:
            name, host = name.split('@', 1)
            if '!' in name:
                name, ident = name.split('!', 1)
        return cls(name, ident, host)

    def __str__(self):
        fmt = "{s.name}"
        if self.host:
            if self.ident:
                fmt += "!{s.ident}"
            fmt += "@{s.host}"
        return fmt.format(s=self)


class Message:

    def __init__(self, command, *, prefix=None, params=None, tags=None,
                 raw_line=None):
        self.command = command
        self.prefix = prefix
        self.params = params if params is not None else []
        self.tags = tags if tags is not None else {}
        self.raw_line = raw_line

    @staticmethod
    def escape(value):
        out_value = ''
        sequences = {v: k for k, v in _ESCAPE_SEQUENCES.items()}
        for char in value:
            if char in sequences:
                out_value += '\\' + sequences.get(char)
            else:
                out_value += char
        return out_value

    @staticmethod
    def unescape(value):
        out_value = ''
        escape = False
        for char in value:
            if escape:
                out_value += _ESCAPE_SEQUENCES.get(char, char)
                escape = False
            else:
                if char == '\\':
                    escape = True
                else:
                    out_value += char
        return out_value

    @classmethod
    def from_line(cls, line):
        # https://tools.ietf.org/html/rfc2812#section-2.3.1
        # http://ircv3.net/specs/core/message-tags-3.2.html
        raw_line = line
        tags = {}
        prefix = None

        if line.startswith('@'):
            # irc tag
            tag_string, line = line.split(None, 1)
            for tag in tag_string[1:].split(';'):
                if '=' in tag:
                    key, value = tag.split('=', 1)
                    value = cls.unescape(value)
                else:
                    key, value = tag, True
                tags[key] = value

        if line.startswith(':'):
            prefix_str, line = line.split(None, 1)
            prefix = Prefix.from_string(prefix_str)

        command, *line = line.split(None, 1)
        command = command.upper()  # TODO check if really case-insensitive
        if command.isdigit():
            try:
                command = ServerReply(command)
            except ValueError:
                current_logger.warning("unknown server reply code {}; {}"
                                       .format(command, raw_line))

        params = []
        if line:
            line = line[0]
            while line:
                if line.startswith(':'):
                    params.append(line[1:])
                    line = ''
                else:
                    param, *line = line.split(None, 1)
                    params.append(param)
                    if line:
                        line = line[0]

        return cls(command, prefix=prefix, params=params, tags=tags,
                   raw_line=raw_line)

    def __repr__(self):
        return (
            '{s.__class__.__name__}({s.command!r}, prefix={s.prefix!r},'
            ' params={s.params!r}, tags={s.tags!r})'.format(s=self)
        )
