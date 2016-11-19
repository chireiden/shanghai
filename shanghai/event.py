
import asyncio
from collections import namedtuple, defaultdict
import functools
import enum

from .logging import current_logger

NetworkEvent = namedtuple("NetworkEvent", "name value")
NetworkEvent.__new__.__defaults__ = (None,)  # Make last argument optional


class NetworkEventName(str, enum.Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CLOSE_REQUEST = "close_request"
    MESSAGE = "message"
    RAW_LINE = "raw_line"


class Priority(int, enum.Enum):
    CORE = 0
    DEFAULT = -10


class _PrioritizedSetList:

    """Manages a list of sets, keyed by a priority level.

    Is always sorted by the level (descending).
    """

    def __init__(self):
        self.list = list()

    def add(self, priority: int, obj):
        if obj in self:
            raise ValueError("Object {!r} has already been added".format(obj))

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

    def remove(self, obj):
        for i, (prio, set_) in enumerate(self.list):
            if obj in set_:
                set_.remove(obj)
                if not set_:
                    del self.list[i]
                return
        else:
            raise ValueError("Object {!r} can not be found".format(obj))

    def __iter__(self):
        return iter(self.list)

    def __contains__(self, obj):
        return any(obj in set_ for _, set_ in self)

    def __bool__(self):
        return bool(self.list)

    # def sort(self):
    #     return self.list.sort(key=lambda e: e[0], reversed=True)


class EventDispatcher:

    """Allows to register handlers and to dispatch events to said handlers, by priority."""

    def __init__(self):
        self.event_map = defaultdict(_PrioritizedSetList)

    def register(self, name: str, coroutine, priority: int = Priority.DEFAULT):
        if not asyncio.iscoroutinefunction(coroutine):
            raise ValueError("callable must be a coroutine function (defined with `async def`)")

        self.event_map[name].add(priority, coroutine)

    async def dispatch(self, name: str, *args):
        if name not in self.event_map:
            return

        for priority, handlers in self.event_map[name]:
            current_logger.ddebug("Starting tasks for event '{}' with priority {}"
                                  .format(name, priority))
            tasks = [asyncio.ensure_future(h(*args)) for h in handlers]
            results = await asyncio.gather(*tasks)
            current_logger.ddebug("Results from event event '{}' with priority {}: {}"
                                  .format(name, priority, results))
            # TODO interpret results, handle exceptions


class NetworkEventDispatcher(EventDispatcher):

    async def dispatch(self, network, event: NetworkEvent):
        return await super().dispatch(event.name, network, event.value)


class MessageEventDispatcher(EventDispatcher):

    async def dispatch(self, network, msg):
        return await super().dispatch(msg.command, network, msg)


class OutMessageEventDispatcher(MessageEventDispatcher):
    pass


network_event_dispatcher = NetworkEventDispatcher()
message_event_dispatcher = MessageEventDispatcher()


# decorator
def network_event(name, priority=Priority.DEFAULT):
    if name not in NetworkEventName.__members__.values():
        raise ValueError("Unknown network event name '{}'".format(name))

    def deco(coroutine):
        network_event_dispatcher.register(name, coroutine, priority)
        return coroutine

    return deco


# decorator
def message_event(name, priority=Priority.DEFAULT):
    def deco(coroutine):
        message_event_dispatcher.register(name, coroutine, priority)
        return coroutine

    return deco

core_network_event = functools.partial(network_event, priority=Priority.CORE)
core_message_event = functools.partial(message_event, priority=Priority.CORE)
