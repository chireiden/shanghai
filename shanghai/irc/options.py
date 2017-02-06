
from .message import Message
from .server_reply import ServerReply


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
        text_list = [f"{self.__class__.__name__}("]
        for key, value in sorted(self._options.items()):
            text_list.append(f"    {key}={value!r},")
        text_list.append(")")
        return "\n".join(text_list)

    def extend_from_message(self, message: Message):
        assert message.command == ServerReply.RPL_ISUPPORT
        for option in message.params[1:-1]:
            if '=' in option:
                key, value = option.split('=', 1)
            else:
                key, value = option, True
            self[key] = value
