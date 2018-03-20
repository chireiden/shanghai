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
from typing import (
    AbstractSet, Any, Callable, Container, Coroutine,
    DefaultDict, Dict, Iterable, Iterator, List, NamedTuple, Optional,
    Set, Tuple, TypeVar, Union,
    cast
)

from .logging import get_default_logger, Logger, LogLevels
from .util import repr_func


class ReturnValue(NamedTuple):
    eat: bool = False
    append_events: Iterable['Event'] = ()
    insert_events: Iterable['Event'] = ()
    schedule: AbstractSet[Coroutine] = frozenset()


# define shorthands
# ReturnValue.NONE = ReturnValue()
# ReturnValue.EAT = ReturnValue(True)


class Priority(int, enum.Enum):
    PRE_CORE = 5
    CORE = 0
    POST_CORE = -5
    PRE_DEFAULT = -10
    DEFAULT = -15
    POST_DEFAULT = -20

    @classmethod
    def lookup(cls, priority: int) -> int:
        for k, v in cls.__members__.items():
            if priority == v:
                return cast(Priority, v)
        else:
            return priority


class Event(NamedTuple):
    name: str
    args: Dict[str, Any] = None


def build_event(name: str, **kwargs: Any):
    return Event(name, kwargs)


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


SyncEventHandler = Callable[..., Optional[ReturnValue]]
AsyncEventHandler = Callable[..., Coroutine[Any, Any, Optional[ReturnValue]]]
EventHandler = Union[SyncEventHandler, AsyncEventHandler]


class HandlerInfo:

    event_name: str
    handler: EventHandler
    priority: int
    should_enable: bool
    is_async: bool

    def __init__(self, event_name: Optional[str],
                 handler: EventHandler,
                 priority: int,
                 enable: bool,
                 _prefix: str,
                 ) -> None:
        is_async = asyncio.iscoroutinefunction(handler)
        if not (is_async or callable(handler)):
            raise TypeError("Callable must be a function (`def`)"
                            " or coroutine function (`async def`)")
        self.handler = handler
        if not event_name:
            event_name = handler.__name__
            if event_name.startswith("on_"):
                event_name = event_name[3:]
        self.event_name = _prefix + event_name
        self.priority = Priority.lookup(priority)  # for pretty __repr__
        self.should_enable = enable
        self.is_async = is_async

    @classmethod
    def wrap(cls, *args, **kwargs) -> EventHandler:
        handler_info = cls(*args, **kwargs)
        handler_info.handler._h_info = handler_info  # type: ignore
        return handler_info.handler

    def __repr__(self):
        return (f"<{self.__class__.__name__}"
                f"(event_name={self.event_name}"
                f", handler={repr_func(self.handler)}"
                f", priority={self.priority}"
                f", should_enable={self.should_enable}"
                ")>")


def event(name_or_func: Union[str, EventHandler, None] = None,
          priority: int = Priority.DEFAULT,
          enable: bool = True,
          _prefix: str = "",
          ) -> Union[EventHandler, Callable[[Callable], EventHandler]]:
    """Decorate a plugin method as an event.

    If no name is provided,
    the event name is determined by the function name.
    It is still recommended to provide the name directly,
    since some event names are internal and provided via an enum,
    while server commands are upper-case and event names are case-sensitive.

    `_prefix` can be used with `functools.partial`
    to provide namespaced sub-events.
    """
    if isinstance(name_or_func, str):
        name = name_or_func
        return functools.partial(HandlerInfo.wrap, name,
                                 priority=priority, enable=enable, _prefix=_prefix)
    elif callable(name_or_func):
        func = name_or_func
        return HandlerInfo.wrap(None, func, priority, enable, _prefix)
    elif name_or_func is None:
        return functools.partial(event, priority=priority, enable=enable, _prefix=_prefix)
    else:
        raise TypeError("Expected string, callable or None as first argument")


core_event = functools.partial(event, priority=Priority.CORE)
CTCP_PREFIX = "ctcp_"
ctcp_event = functools.partial(event, _prefix=CTCP_PREFIX)


class HandlerInstance:

    """Holds dynamic content about a specific handler instance."""

    handler: EventHandler
    info: HandlerInfo
    enabled: bool

    def __init__(self, handler: EventHandler, info: HandlerInfo, enabled: bool) -> None:
        self.handler = handler
        self.info = info
        self.enabled = enabled

    @classmethod
    def from_handler(cls, handler: EventHandler) -> 'HandlerInstance':
        if not hasattr(handler, '_h_info'):
            raise ValueError("Event handler must be decorated with `@event`")
        h_info: HandlerInfo = handler._h_info  # type: ignore
        return cls(handler, h_info, h_info.should_enable)

    def __hash__(self):
        return hash(self.handler)


class ResultSet:
    def __init__(self):
        self.eat = False
        self.append_events: List[Event] = []
        self.insert_events: List[Event] = []
        self.schedule: Set[Coroutine] = set()

    def extend(self, other: Union['ResultSet', ReturnValue, None]):
        if other is None:
            return
        elif isinstance(other, (ReturnValue, ResultSet)):
            # I have no idea why mypy things this is an int
            self.eat |= other.eat  # type: ignore
            self.append_events.extend(other.append_events)
            self.insert_events.extend(other.insert_events)
            self.schedule |= other.schedule
        else:
            raise NotImplementedError()

    def __iadd__(self, other: Union['ResultSet', ReturnValue]) -> 'ResultSet':
        self.extend(other)
        return self


class EventDispatcher:

    """Allows to register handlers and to dispatch events to those, by priority."""

    event_map: DefaultDict[str, _PrioritizedSetList[HandlerInstance]]
    logger: Logger

    def __init__(self, logger: Logger = None) -> None:
        self.event_map = DefaultDict(_PrioritizedSetList)
        self.logger = logger or get_default_logger()

    # def unregister(self, name: str, handler: EventHandler) -> None:
    #     self.logger.ddebug(f"Unregistering event handler for event {name!r}: {handler}")
    #     self.event_map[name].remove(handler)
    #     if not self.event_map[name]:
    #         del self.event_map[name]

    def register(self, handler_inst: HandlerInstance) -> None:
        h_info = handler_inst.info
        self.logger.ddebug("Registering event handler for event"
                           f" {h_info.event_name!r} ({h_info.priority!r}):"
                           f" {handler_inst.handler}")

        self.event_map[h_info.event_name].add(h_info.priority, handler_inst)

    def register_plugin(self, plugin: Any) -> List[HandlerInstance]:
        instances: List[HandlerInstance] = []
        for attr_name in dir(plugin):
            attr = getattr(plugin, attr_name)
            if hasattr(attr, '_h_info'):
                handler = cast(EventHandler, attr)
                handler_inst = HandlerInstance.from_handler(handler)
                self.register(handler_inst)
                instances.append(handler_inst)
        return instances

    async def dispatch(self, event: Event) -> Optional[ResultSet]:
        name = event.name

        if name not in self.event_map:
            self.logger.ddebug(f"No event handlers for event {name!r}")
            return None

        joined_result_set = ResultSet()
        for priority, handler_inst_set in self.event_map[name]:
            if not handler_inst_set:
                continue
            priority = Priority.lookup(priority)  # for pretty __repr__
            # Use isEnabledFor because this will be run often
            is_ddebug = self.logger.isEnabledFor(LogLevels.DDEBUG)

            coroutines: List[AsyncEventHandler] = []
            functions: List[SyncEventHandler] = []
            for handler_inst in handler_inst_set:
                if not handler_inst.enabled:
                    continue
                if handler_inst.info.is_async:
                    coroutines.append(handler_inst.handler)  # type: ignore
                else:
                    functions.append(handler_inst.handler)  # type: ignore

            # Collect results independently but evaluate them together
            handlers = cast(List[EventHandler], coroutines) + cast(List[EventHandler], functions)
            results: List[Union[ReturnValue, Exception]] = []

            if not handlers:
                self.logger.ddebug(f"No event handlers for event {name!r} at priority {priority}")
                return None

            if coroutines:
                tasks = [asyncio.ensure_future(h(**event.args)) for h in coroutines]
                if is_ddebug:
                    self.logger.ddebug(f"Starting tasks for event {name!r} ({priority!r});"
                                       f" tasks: {tasks}")
                results.extend(await asyncio.gather(*tasks, return_exceptions=True))

            if functions:
                for handler in functions:
                    try:
                        results.append(handler(**event.args))
                    except Exception as e:
                        results.append(e)

            if is_ddebug:
                self.logger.ddebug(f"Results from event {name!r} ({priority!r}):"
                                   f" {results}")

            result_set = self.handle_results(name, priority, handlers, results)

            joined_result_set += result_set
            if joined_result_set.eat:
                return joined_result_set

        for followup_event in joined_result_set.insert_events:
            self.logger.debug(f"Dispatching {followup_event!r} from event {name!r}")
            result_set = await self.dispatch(followup_event)
            joined_result_set += result_set

        # Clear these when we are done
        joined_result_set.insert_events = []
        return joined_result_set

    def handle_results(self, name, priority, handlers, results) -> ResultSet:
        result_set = ResultSet()
        for handler, result in zip(handlers, results):
            if isinstance(result, Exception):
                self.logger.exception(
                    f"Exception in event handler {repr_func(handler)!r} for event {name!r}"
                    f" ({priority!r}):",
                    exc_info=result
                )
                continue

            if result is None:
                continue
            elif not isinstance(result, (ResultSet, ReturnValue)):
                self.logger.warning(
                    f"Received unrecognized return value from {repr_func(handler)}"
                    f" for event {name!r} ({priority!r}): {result!r}"
                )
                continue

            if result.eat:
                self.logger.debug(f"Eating event {name!r} at priority {priority!r}"
                                  f" at the request of {repr_func(handler)}")
            if result.append_events:
                self.logger.ddebug(f"Appending events {result.append_events}"
                                   f" at the request of {repr_func(handler)}")
            if result.schedule:
                self.logger.debug(f"Scheduling tasks {result.append_events}"
                                  f" returned from {repr_func(handler)}")

            result_set += result

        return result_set
