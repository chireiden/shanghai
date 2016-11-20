
import asyncio

from .event import NetworkEvent
from .logging import Logger, get_default_logger


class Connection:

    def __init__(self, host: str, port: int, queue: asyncio.Queue,
                 ssl: bool = False, loop: asyncio.AbstractEventLoop = None,
                 logger: Logger = None):
        if logger is None:
            logger = get_default_logger()
        self.logger = logger

        self.host = host
        self.port = port
        self.queue = queue
        self.ssl = ssl
        self.loop = loop
        if self.loop is None:
            self.loop = asyncio.get_event_loop()

        self.writer = None  # type: asyncio.StreamWriter

    def writeline(self, line: bytes):
        self.logger.info("<", line)
        self.writer.write(line)
        self.writer.write(b'\r\n')

    def close(self):
        self.logger.debug("closing connection")
        self.writer.close()

    async def run(self):
        self.logger.info("connecting to {s.host}:{ssl}{s.port}..."
                         .format(s=self, ssl="+" if self.ssl else ""))
        reader, writer = await asyncio.open_connection(
            self.host, self.port, ssl=self.ssl, loop=self.loop)
        self.writer = writer

        await self.queue.put(NetworkEvent('connected', self))

        try:
            while not reader.at_eof():
                line = await reader.readline()
                line = line.strip()
                self.logger.debug(">", line)
                if line:
                    await self.queue.put(NetworkEvent('raw_line', line))
        except asyncio.CancelledError:
            self.logger.info("Connection.run cancelled")
        finally:
            self.close()
            await self.queue.put(NetworkEvent('disconnected', None))
