from collections import namedtuple

NetworkEvent = namedtuple("NetworkEvent", "name value")
NetworkEvent.__new__.__defaults__ = (None,)  # Make last argument optional
