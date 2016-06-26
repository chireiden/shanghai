
from . import Message


# TODO evaluate against specs
# http://www.irc.org/tech_docs/005.html
# http://www.irc.org/tech_docs/draft-brocklesby-irc-isupport-03.txt
class Options:
    """A simple case insensitive mapping of 005 RPL_ISUPPORT reply."""
    _fields = ('_options',)

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

    def extend_from_message(self, message: Message):
        for option in message.params[1:-1]:
            if '=' in option:
                key, value = option.split('=', 1)
            else:
                key, value = option, True
            self[key] = value
