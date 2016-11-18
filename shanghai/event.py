
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
        # TODO prevent duplicates
        for i, (prio, set_) in enumerate(self.list):
            if priority > prio:
                self.list.insert(i, obj)
                break
            elif priority == prio:
                set_.add(obj)
                break
        else:
            self.list.append((priority, {obj}))

    def remove(self, obj):
        # TODO remove set entirely if empty
        raise NotImplementedError()

    def __iter__(self):
        return iter(self.list)

    # def sort(self):
    #     return self.list.sort(key=lambda e: e[0], reversed=True)


class EventDispatcher:

    """Allows to register handlers and to dispatch events to said handlers, by priority."""

    def __init__(self):
        self.event_map = defaultdict(_PrioritizedSetList)

    def register(self, name: str, coroutine, priority: int = Priority.DEFAULT):
        self.event_map[name].add(priority, coroutine)

    async def dispatch(self, name: str, *args):
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
    def deco(coroutine):
        if name not in NetworkEventName.__members__.values():
            raise ValueError("Unknown network event name '{}'".format(name))
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


@core_network_event('message')
async def message_event_worker(network, msg):
    await message_event_dispatcher.dispatch(network, msg)
    # TODO interpret results?
