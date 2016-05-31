
ESCAPE_SEQUENCES = {
    'n': '\n',
    'r': '\r',
    's': ' ',
    '\\': '\\',
    ':': ';',
}


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
        sequences = {v: k for k, v in ESCAPE_SEQUENCES.items()}
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
                out_value += ESCAPE_SEQUENCES.get(char, char)
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

        command, *line = line.split(None, 1)
        command = command.upper()

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


# TODO evaluate against specs
# http://www.irc.org/tech_docs/005.html
# http://www.irc.org/tech_docs/draft-brocklesby-irc-isupport-03.txt
class Options:
    """A simple case insensitive mapping of 005 RPL_ISUPPORT reply."""
    _fields = ('_options')

    def __init__(self):
        self._options = {}

    def __setitem__(self, key, value):
        self._options[key.lower()] = value

    def __setattr__(self, key, value):
        if key in self._fields:
            super().__setattr__(key, value)
        else:
            self._options[key.lower()] = value

    def __getitem__(self, item):
        return self._options[item.lower()]

    def __getattr__(self, item):
        return self._options[item.lower()]

    def __repr__(self):
        text = '{}(\n'.format(self.__class__.__name__)
        for key, value in sorted(self._options.items()):
            text += '    {}={!r}\n'.format(key, value)
        text += ')'
        return text
