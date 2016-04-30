

class Message:

    def __init__(self, command, *, prefix=None, params=None, tags=None,
                 raw_line=None):
        self.command = command
        self.prefix = prefix
        self.params = params if params is not None else []
        self.tags = tags if tags is not None else {}
        self.raw_line = raw_line

    @staticmethod
    def unescape(value):
        out_value = ''
        escape = False
        sequences = {
            'n': '\n',
            'r': '\r',
            's': ' ',
            '\\': '\\',
            ':': ';',
        }
        for char in value:
            if escape:
                out_value += sequences.get(char, char)
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
            # prefix
            prefix, line = line.split(None, 1)
            name = prefix[1:]
            ident = None
            host = None
            if '!' in name:
                name, ident = name.split('!', 1)
                if '@' in ident:
                    ident, host = ident.split('@', 1)
            elif '@' in name:
                name, host = name.split('@', 1)
            prefix = name, ident, host

        command, line = line.split(None, 1)
        command = command.upper()

        params = []
        if line:
            trailing = None
            if ' :' in ' ' + line:
                line, trailing = (' ' + line).split(' :', 1)
            if line:
                params = line.split()
            if trailing is not None:
                params.append(trailing)

        return cls(command, prefix=prefix, params=params, tags=tags,
                   raw_line=raw_line)

    def __repr__(self):
        return '{}({!r}, prefix={!r}, params={!r}, tags={!r})'.format(
            self.__class__.__name__, self.command, self.prefix,
            self.params, self.tags
        )
