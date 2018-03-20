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

import re
import string
from typing import Dict, Iterator, MutableMapping, Optional, Tuple, Union

from .message import Message
from .server_reply import ServerReply


DEFAULT_CASE_MAPPING = 'rfc1459'


def _generate_case_table(case_mapping: str) -> Dict[int, Optional[int]]:
    case_mapping = case_mapping.lower()
    if case_mapping not in ('ascii', 'rfc1459', 'strict-rfc1459'):
        # TODO log warning
        case_mapping = DEFAULT_CASE_MAPPING

    upper_str = string.ascii_uppercase
    lower_str = string.ascii_lowercase

    if case_mapping == 'rfc1459':
        upper_str += "[]\\^"
        lower_str += "{}|~"
    elif case_mapping == 'strict-rfc1459':
        upper_str += "[]\\"
        lower_str += "{}|"

    return str.maketrans(upper_str, lower_str)


OptionValue = Union[str, bool]


# TODO evaluate against specs
# http://www.irc.org/tech_docs/005.html
# http://www.irc.org/tech_docs/draft-brocklesby-irc-isupport-03.txt
class Options(MutableMapping[str, OptionValue]):

    """A case insensitive mapping of 005 RPL_ISUPPORT settings and convenience functions."""

    user_modes = 'ov'
    user_prefixes = '@+'
    _case_table = _generate_case_table(DEFAULT_CASE_MAPPING)

    def __init__(self, **kwargs: OptionValue) -> None:
        self._options = {k.upper(): v for k, v in kwargs.items()}

    def __setitem__(self, key: str, value: OptionValue) -> None:
        ukey = key.upper()
        self._options[ukey] = value

        if isinstance(value, str):  # isinstance check for mypy
            if ukey == 'PREFIX':
                self._parse_prefix(value)
            elif ukey == 'CASEMAPPING':
                self._case_table = _generate_case_table(value)

    def __getitem__(self, item: str) -> OptionValue:
        return self._options[item.upper()]

    def __delitem__(self, item: str) -> None:
        del self._options[item.upper()]

    def __iter__(self) -> Iterator[str]:
        return iter(self._options)

    def __len__(self) -> int:
        return len(self._options)

    def __repr__(self) -> str:
        params = ", ".join(f"{key}={value!r}"
                           for key, value in sorted(self._options.items()))
        return f"{self.__class__.__name__}({params})"

    def extend_from_message(self, message: Message) -> None:
        assert message.command == ServerReply.RPL_ISUPPORT
        assert message.params[-1] == "are supported by this server"

        for option in message.params[1:-1]:
            key, is_not_bool, value = option.partition('=')
            if is_not_bool:
                self[key] = value
            else:
                self[key] = True

    def _parse_prefix(self, value: str) -> None:
        if not value:
            # empty value means no prefixes
            self.user_modes = self.user_prefixes = ''
            return

        match = re.match(r'^\((.*)\)(.*)$', value)
        if match is None:
            # TODO log warning
            pass
        elif len(match.group(1)) != len(match.group(2)):
            # TODO log warning
            pass
        else:
            self.user_modes, self.user_modes = match.groups()

    def split_prefixes(self, prefixed_nick: str) -> Tuple[str, str]:
        nick = prefixed_nick
        prefixes = ''
        if self.get('NAMESX', False):
            nick = prefixed_nick.lstrip(self.user_prefixes)
            prefixes = prefixed_nick[:-len(nick)]
        elif nick[0] in self.user_prefixes:
            prefixes = prefixed_nick[0]
            nick = prefixed_nick[1:]
        return prefixes, nick

    def prefixes_to_modes(self, prefixes: str) -> str:
        table = str.maketrans(self.user_prefixes, self.user_modes)
        return prefixes.translate(table)

    def modes_to_prefixes(self, modes: str) -> str:
        table = str.maketrans(self.user_modes, self.user_prefixes)
        return modes.translate(table)

    def nick_lower(self, nick: str) -> str:
        return nick.translate(self._case_table)

    def chan_lower(self, chan: str) -> str:
        return self.nick_lower(chan)

    def nick_eq(self, nick1: str, nick2: str) -> bool:
        return self.nick_lower(nick1) == self.nick_lower(nick2)

    def chan_eq(self, chan1: str, chan2: str) -> bool:
        return self.chan_lower(chan1) == self.chan_lower(chan2)
