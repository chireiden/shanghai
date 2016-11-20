
from .util import ShadowAttributesMixin
from .logging import Logger


class Context(ShadowAttributesMixin):

    def __init__(self, network, *, logger: Logger=None):
        super().__init__()
        self.network = network
        if logger is None:
            logger = network.logger
        self.logger = logger

    def send_cmd(self, *args, **kwargs):
        self.network.send_cmd(*args, **kwargs)

    def send_line(self, *args, **kwargs):
        self.network.send_line(*args, **kwargs)

    def send_msg(self, *args, **kwargs):
        self.network.send_msg(*args, **kwargs)

    def send_notice(self, *args, **kwargs):
        self.network.send_notice(*args, **kwargs)
