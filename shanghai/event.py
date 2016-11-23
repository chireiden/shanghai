
import asyncio
from collections import namedtuple, defaultdict
import functools
import enum

from .logging import get_default_logger

NetworkEvent = namedtuple("NetworkEvent", "name value")
NetworkEvent.__new__.__defaults__ = (None,)  # Make last argument optional


class NetworkEventName(str, enum.Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CLOSE_REQUEST = "close_request"
    MESSAGE = "message"
    RAW_LINE = "raw_line"


class GlobalEventName(str, enum.Enum):
    INIT_NETWORK_CTX = "init_network_context"


class Priority(int, enum.Enum):
    PRE_CORE = 5
    CORE = 0
    POST_CORE = -5
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


class EventDecorator:

    def __init__(self, dispatcher):
        self.dispatcher = dispatcher

    def __call__(self, name, priority=Priority.DEFAULT):
        def deco(coroutine):
            self.dispatcher.register(name, coroutine, priority)
            coroutine.unregister = functools.partial(self.dispatcher.unregister, name, coroutine)
            return coroutine

        return deco

    def core(self, name):
        return self(name, Priority.CORE)


class EventDispatcher:

    """Allows to register handlers and to dispatch events to said handlers, by priority."""

    def __init__(self):
        self.event_map = defaultdict(_PrioritizedSetList)

    def unregister(self, name: str, coroutine):
        self.event_map[name].remove(coroutine)

    def register(self, name: str, coroutine, priority: int = Priority.DEFAULT):
        if not asyncio.iscoroutinefunction(coroutine):
            raise ValueError("callable must be a coroutine function (defined with `async def`)")

        self.event_map[name].add(priority, coroutine)

    async def dispatch(self, name: str, *args):
        get_default_logger().ddebug("Dispatching event {!r} with arguments {}".format(name, args))
        if name not in self.event_map:
            get_default_logger().ddebug("No event handlers for event {!r}".format(name))
            return

        for priority, handlers in self.event_map[name]:
            get_default_logger().ddebug("Creating tasks for event {!r} (priority {}), from {}"
                                        .format(name, priority, handlers))
            tasks = [asyncio.ensure_future(h(*args)) for h in handlers]

            get_default_logger().ddebug("Starting tasks for event {!r} (priority {}); tasks: {}"
                                        .format(name, priority, tasks))
            results = await asyncio.gather(*tasks)

            get_default_logger().ddebug("Results from event event {!r} (priority {}): {}"
                                        .format(name, priority, results))
            # TODO interpret results, handle exceptions

    @property
    def decorator(self):
        return EventDecorator(self)

    # decorator
    # def decorator(self, name, priority=Priority.DEFAULT):
    #     def deco(coroutine):
    #         self.register(name, coroutine, priority)
    #         coroutine.unregister = functools.partial(self.unregister, name, coroutine)
    #         return coroutine

    #     return deco


class GlobalEventDispatcher(EventDispatcher):

    @property
    def decorator(self):
        # if name not in GlobalEventName.__members__.values():
        #     raise ValueError("Unknown global event name '{}'".format(name))
        return super().decorator


class NetworkEventDispatcher(EventDispatcher):

    def __init__(self, context):
        super().__init__()
        self.context = context

    async def dispatch(self, event: NetworkEvent):
        return await super().dispatch(event.name, self.context, event.value)

    @property
    def decorator(self):
        # if name not in NetworkEventName.__members__.values():
        #     raise ValueError("Unknown network event name '{}'".format(name))
        return super().decorator


class MessageEventDispatcher(EventDispatcher):

    def __init__(self, context):
        super().__init__()
        self.context = context

    async def dispatch(self, msg):
        return await super().dispatch(msg.command, self.context, msg)


global_dispatcher = GlobalEventDispatcher()
global_event = global_dispatcher.decorator
