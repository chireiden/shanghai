from collections import namedtuple

Event = namedtuple("Event", "name value")
Event.__new__.__defaults__ = (None,)  # Make last argument optional
