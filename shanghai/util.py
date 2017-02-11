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

import functools
from typing import Union, Callable

from fullqualname import fullqualname


class ShadowAttributesMixin:

    """Mixin class that allows to add (and set) attributes without collisions.

    Instead of directly setting attributes (or using `setattr`) for the first time,
    use `add_attribute` or `add_method`.

    When changing adding attributes,
    use `set_attribute` (not designed to be used with 'methods').

    When removing attributes,
    use `remove_attribute`.
    """

    def __init__(self, *args, **kwargs):
        self._added_attributes = dict()

        super().__init__(*args, **kwargs)

    def add_attribute(self, name: str, value=None):
        """Allows to add attributes to an object.

        Use this instead of directly setting attributes (or with `setattr`).
        For adding methods, use add_method.
        """
        if hasattr(self, name) or name in self._added_attributes:
            raise KeyError("Attribute '{}' is already defined".format(name))
        self._added_attributes[name] = value

    def set_attribute(self, name: str, value=None):
        """Allows to modify added attributes to an object."""
        if name in self.__dict__:  # cannot use hasattr because that would call __getattr__
            raise KeyError(name)
        if name not in self._added_attributes:
            raise KeyError("Attribute '{}' is not defined".format(name))
        self._added_attributes[name] = value

    def has_attribute(self, name: str, value=None):
        """Check if an attribute exists already."""
        # TODO test how hasattr performs with our __getattr__
        return name in self.__dict__ or name in self._added_attributes

    def add_method(self, name_or_function: Union[str, Callable], function: Callable = None):
        """Allows to add methods to an object.

        Added functions will be called with an implicit `self` argment,
        like for normal methods.

        Also functions as a decorator and infers the attribute name from the function name.
        """
        if callable(name_or_function):
            if callable(function):
                raise ValueError("May only provide one callable")
            function = name_or_function
            name = function.__name__
        elif not callable(function):
            raise ValueError("Parameter is not callable")
        else:
            name = name_or_function

        self.add_attribute(name, functools.partial(function, self))

        return function

    def remove_attribute(self, name: str):
        """Allows for plugins to remove their added attributes to the network object."""
        if name not in self._added_attributes:
            raise KeyError("Attribute '{}' is not defined".format(name))
        del self._added_attributes[name]

    def __getattr__(self, name):
        if name in self._added_attributes:
            return self._added_attributes[name]
        else:
            raise AttributeError("{!r} has no attribute {!r}".format(self, name))
        #     super().__getattr__(name)


def repr_func(func: callable) -> str:
    """Represent a function with its full qualname instead of just its name and an address."""
    return "<{} {}>".format(type(func).__name__, fullqualname(func))
