
import asyncio
from collections import namedtuple, defaultdict
import functools
import enum

from .logging import get_default_logger, Logger, LogLevels
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


class ReturnValue(enum.Enum):
    EAT = True
    NONE = None

    _all = (EAT, NONE)


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

    def remove(self, obj):
        for i, (prio, set_) in enumerate(self.list):
            if obj in set_:
                set_.remove(obj)
                if not set_:
                    del self.list[i]
                return
        else:
            raise ValueError(f"Object {obj!r} can not be found")

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
                raise ValueError(f"Unknown event name {name!r}")

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
        self.logger.ddebug(f"Unregistering event handler for event {name!r}: {coroutine}")
        self.event_map[name].remove(coroutine)

    def register(self, name: str, coroutine, priority: int = Priority.DEFAULT):
        self.logger.ddebug(f"Registering event handler for event {name!r} (priority {priority}): "
                           f"{coroutine}")
        if not asyncio.iscoroutinefunction(coroutine):
            raise ValueError("callable must be a coroutine function (defined with `async def`)")

        self.event_map[name].add(priority, coroutine)

    async def dispatch(self, name: str, *args):
        self.logger.ddebug(f"Dispatching event {name!r} with arguments {args}")
        if name not in self.event_map:
            self.logger.ddebug(f"No event handlers for event {name!r}")
            return

        for priority, handlers in self.event_map[name]:
            # Use isEnabledFor because this will be called often
            is_ddebug = self.logger.isEnabledFor(LogLevels.DDEBUG)
            if is_ddebug:  # pragma: nocover
                self.logger.ddebug(f"Creating tasks for event {name!r} (priority {priority}), "
                                   f"from {set(repr_func(func) for func in handlers)}")
            tasks = [asyncio.ensure_future(h(*args)) for h in handlers]

            if is_ddebug:  # pragma: nocover
                self.logger.ddebug(f"Starting tasks for event {name!r} (priority {priority}); "
                                   f"tasks: {tasks}")
            results = await asyncio.gather(*tasks, return_exceptions=True)

            if is_ddebug:  # pragma: nocover
                self.logger.ddebug(f"Results from event {name!r} (priority {priority}): {results}")

            eaten = False
            for handler, task, result in zip(handlers, tasks, results):
                if isinstance(result, Exception):
                    self.logger.exception(
                        f"Exception in event handler {repr_func(handler)!r} for event {name!r} "
                        f"(priority {priority}):",
                        exc_info=result
                    )

                elif result is ReturnValue.EAT:
                    self.logger.debug(f"Eating event {name!r} at priority {priority} "
                                      f"at the request of {repr_func(handler)}")
                    eaten = True
                elif result not in ReturnValue._all.value:
                    self.logger.warning(
                        f"Received unrecognized return value from {repr_func(handler)} "
                        f"for event {name!r} (priority {priority}): {result!r}"
                    )

            if eaten:
                return ReturnValue.EAT


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
