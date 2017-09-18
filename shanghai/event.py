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

import asyncio
import functools
import enum
from typing import (Any, Awaitable, Callable, Container, DefaultDict, Hashable, Iterable,
                    Iterator, List, NamedTuple, Set, Tuple, TypeVar, cast)

from .logging import get_default_logger, Logger, LogLevels
from .util import repr_func
from .network import NetworkContext


class NetworkEvent(NamedTuple):
    name: str
    value: Any = None


class NetworkEventName(str, enum.Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CLOSE_REQUEST = "close_request"
    MESSAGE = "message"
    RAW_LINE = "raw_line"


class GlobalEventName(str, enum.Enum):
    INIT_NETWORK_CTX = "init_network_context"


class ReturnValue(enum.Enum):
    EAT = True
    NONE = None

    _all = (EAT, NONE)


class Priority(int, enum.Enum):
    PRE_CORE = 5
    CORE = 0
    POST_CORE = -5
    DEFAULT = -10

    @classmethod
    def lookup(cls, priority: int) -> int:
        for k, v in cls.__members__.items():
            if priority == v:
                return cast(Priority, v)
        else:
            return priority


HT = TypeVar('HT')
# Ideally, the following would be used,
# by mypy doesn't consider the callable to be hashable for some reason,
# HT = TypeVar('HT', bound=Hashable)


class _PrioritizedSetList(Iterable[Tuple[int, Set[HT]]], Container[HT]):

    """Manages a list of sets, keyed by a priority level.

    Is always sorted by the level (descending).
    """

    list: List[Tuple[int, Set[HT]]]

    def __init__(self) -> None:
        self.list = list()

    def add(self, priority: int, obj: HT) -> None:
        if obj in self:
            raise ValueError(f"Object {obj!r} has already been added")

        i = -1
        for i, (prio, set_) in enumerate(self.list):
            if priority > prio:
                break
            elif priority == prio:
                set_.add(obj)
                return
        else:
            i = i + 1  # 0 if empty; len(self.list) if priority < all others

        self.list.insert(i, (priority, {obj}))

    def remove(self, obj: HT) -> None:
        for i, (prio, set_) in enumerate(self.list):
            if obj in set_:
                set_.remove(obj)
                if not set_:
                    del self.list[i]
                return
        else:
            raise ValueError(f"Object {obj!r} can not be found")

    def __iter__(self) -> Iterator[Tuple[int, Set[HT]]]:
        return iter(self.list)

    def __contains__(self, obj: Any) -> bool:
        return any(obj in set_ for _, set_ in self)

    def __bool__(self) -> bool:
        return bool(self.list)

    # def sort(self):
    #     return self.list.sort(key=lambda e: e[0], reversed=True)


EventHandler = Callable[..., Awaitable['ReturnValue']]
DecoratorType = Callable[[EventHandler], EventHandler]


class EventDecorator:

    allowed_names: Container[str] = ()

    def __init__(self, dispatcher: 'EventDispatcher') -> None:
        self.dispatcher = dispatcher

    def __call__(self, name: str, priority: int = Priority.DEFAULT) -> DecoratorType:
        if name not in self.allowed_names:
            raise ValueError(f"Unknown event name {name!r}")

        def deco(coroutine: EventHandler) -> EventHandler:
            self.dispatcher.register(name, coroutine, priority)
            setattr(coroutine, 'unregistrer',
                    functools.partial(self.dispatcher.unregister, name, coroutine))
            return coroutine

        return deco

    def core(self, name: str) -> DecoratorType:
        return self(name, Priority.CORE)


class EventDispatcher:

    """Allows to register handlers and to dispatch events to said handlers, by priority."""

    event_map: DefaultDict[str, _PrioritizedSetList[EventHandler]]
    logger: Logger
    decorator: EventDecorator

    def __init__(self, logger: Logger = None) -> None:
        self.event_map = DefaultDict(_PrioritizedSetList)
        self.logger = logger or get_default_logger()

        self.decorator = EventDecorator(self)

    def unregister(self, name: str, coroutine: EventHandler) -> None:
        self.logger.ddebug(f"Unregistering event handler for event {name!r}: {coroutine}")
        self.event_map[name].remove(coroutine)

    def register(self, name: str, coroutine: EventHandler, priority: int = Priority.DEFAULT) \
            -> None:
        priority = Priority.lookup(priority)  # for pretty __repr__
        self.logger.ddebug(f"Registering event handler for event {name!r} ({priority!r}):"
                           f" {coroutine}")
        if not asyncio.iscoroutinefunction(coroutine):
            raise ValueError("callable must be a coroutine function (defined with `async def`)")

        self.event_map[name].add(priority, coroutine)

    async def dispatch(self, name: str, *args: Any) -> ReturnValue:
        self.logger.ddebug(f"Dispatching event {name!r} with arguments {args}")
        if name not in self.event_map:
            self.logger.ddebug(f"No event handlers for event {name!r}")
            return ReturnValue.NONE

        for priority, handlers in self.event_map[name]:
            priority = Priority.lookup(priority)  # for pretty __repr__

            # Use isEnabledFor because this will be called often
            is_ddebug = self.logger.isEnabledFor(LogLevels.DDEBUG)
            if is_ddebug:  # pragma: nocover
                self.logger.ddebug(f"Creating tasks for event {name!r} ({priority!r}),"
                                   f" from {set(repr_func(func) for func in handlers)}")
            tasks = [asyncio.ensure_future(h(*args)) for h in handlers]

            if is_ddebug:  # pragma: nocover
                self.logger.ddebug(f"Starting tasks for event {name!r} ({priority!r});"
                                   f" tasks: {tasks}")
            results = await asyncio.gather(*tasks, return_exceptions=True)

            if is_ddebug:  # pragma: nocover
                self.logger.ddebug(f"Results from event {name!r} ({priority!r}): {results}")

            eaten = False
            for handler, task, result in zip(handlers, tasks, results):
                if isinstance(result, Exception):
                    self.logger.exception(
                        f"Exception in event handler {repr_func(handler)!r} for event {name!r}"
                        f" ({priority!r}):",
                        exc_info=result
                    )

                elif result is ReturnValue.EAT:
                    self.logger.debug(f"Eating event {name!r} at priority {priority!r}"
                                      f" at the request of {repr_func(handler)}")
                    eaten = True
                elif result not in ReturnValue._all.value:
                    self.logger.warning(
                        f"Received unrecognized return value from {repr_func(handler)}"
                        f" for event {name!r} ({priority!r}): {result!r}"
                    )

            if eaten:
                return ReturnValue.EAT
        return ReturnValue.NONE


class GlobalEventDispatcher(EventDispatcher):

    def __init__(self, logger: Logger = None) -> None:
        super().__init__(logger)
        # https://github.com/python/typeshed/issues/1590
        self.decorator.allowed_names = set(GlobalEventName.__members__.values())  # type: ignore


class NetworkEventDispatcher(EventDispatcher):

    def __init__(self, context: NetworkContext, logger: Logger = None) -> None:
        super().__init__(logger)
        self.context = context
        # https://github.com/python/typeshed/issues/1590
        self.decorator.allowed_names = set(NetworkEventName.__members__.values())  # type: ignore

    async def dispatch_nwevent(self, event: NetworkEvent) -> ReturnValue:
        return await self.dispatch(event.name, self.context, event.value)


global_dispatcher = GlobalEventDispatcher()
global_event: EventDecorator = global_dispatcher.decorator
