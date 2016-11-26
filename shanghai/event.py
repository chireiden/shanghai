
import asyncio
from collections import namedtuple, defaultdict
import functools
import enum

from .logging import get_default_logger, Logger
from .util import repr_func

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

    allowed_names = None

    def __init__(self, dispatcher):
        self.dispatcher = dispatcher

    def __call__(self, name, priority=Priority.DEFAULT):
        if self.allowed_names:
            if name not in self.allowed_names:
                raise ValueError("Unknown event name '{}'".format(name))

        def deco(coroutine):
            self.dispatcher.register(name, coroutine, priority)
            coroutine.unregister = functools.partial(self.dispatcher.unregister, name, coroutine)
            return coroutine

        return deco

    def core(self, name):
        return self(name, Priority.CORE)


class EventDispatcher:

    """Allows to register handlers and to dispatch events to said handlers, by priority."""

    def __init__(self, logger: Logger = None):
        self.event_map = defaultdict(_PrioritizedSetList)
        self.logger = logger or get_default_logger()

        self.decorator = EventDecorator(self)

    def unregister(self, name: str, coroutine):
        self.logger.ddebug("Unregistering event handler for event {!r}: {}"
                           .format(name, coroutine))
        self.event_map[name].remove(coroutine)

    def register(self, name: str, coroutine, priority: int = Priority.DEFAULT):
        self.logger.ddebug("Registering event handler for event {!r} (priority {}): {}"
                           .format(name, priority, coroutine))
        if not asyncio.iscoroutinefunction(coroutine):
            raise ValueError("callable must be a coroutine function (defined with `async def`)")

        self.event_map[name].add(priority, coroutine)

    async def dispatch(self, name: str, *args):
        self.logger.ddebug("Dispatching event {!r} with arguments {}".format(name, args))
        if name not in self.event_map:
            self.logger.ddebug("No event handlers for event {!r}".format(name))
            return

        for priority, handlers in self.event_map[name]:
            # TODO prolly want to wrap this behind self.logger.isEnabledFor
            # because it's very verbose
            self.logger.ddebug("Creating tasks for event {!r} (priority {}), from {}"
                               .format(name, priority, {repr_func(func) for func in handlers}))
            tasks = [asyncio.ensure_future(h(*args)) for h in handlers]

            self.logger.ddebug("Starting tasks for event {!r} (priority {}); tasks: {}"
                               .format(name, priority, tasks))
            results = await asyncio.gather(*tasks)

            self.logger.ddebug("Results from event event {!r} (priority {}): {}"
                               .format(name, priority, results))
            # TODO interpret results, handle exceptions


class GlobalEventDispatcher(EventDispatcher):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.decorator.allowed_names = set(GlobalEventName.__members__.values())


class NetworkEventDispatcher(EventDispatcher):

    def __init__(self, context, *args, **kwargs):
        super().__init__()
        self.context = context
        self.decorator.allowed_names = set(NetworkEventName.__members__.values())

    async def dispatch(self, event: NetworkEvent):
        return await super().dispatch(event.name, self.context, event.value)


global_dispatcher = GlobalEventDispatcher()
global_event = global_dispatcher.decorator
