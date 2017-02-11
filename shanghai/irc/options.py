# Copyright © 2016  Lars Peter Søndergaard <lps@chireiden.net>
# Copyright © 2016  FichteFoll <fichtefoll2@googlemail.com>
#
# This file is part of Shanghai, an asynchronous multi-server IRC bot.
#
# Shanghai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Shanghai is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Shanghai.  If not, see <http://www.gnu.org/licenses/>.

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
        text = '{}(\n'.format(self.__class__.__name__)
        for key, value in sorted(self._options.items()):
            text += '    {}={!r}\n'.format(key, value)
        text += ')'
        return text

    def extend_from_message(self, message: Message):
        assert message.command == ServerReply.RPL_ISUPPORT
        for option in message.params[1:-1]:
            if '=' in option:
                key, value = option.split('=', 1)
            else:
                key, value = option, True
            self[key] = value
