
import asyncio

from .config import Server
from .event import NetworkEvent
from .logging import Logger, get_default_logger


class Connection:

    def __init__(self, server: Server, queue,
                 loop: asyncio.AbstractEventLoop = None,
                 logger: Logger = None):
        self.server = server
        self.queue = queue
        self.loop = loop
        if logger is None:
            logger = get_default_logger()
        self.logger = logger

        self.writer = None  # type: asyncio.StreamWriter

    def writeline(self, line: bytes):
        self.logger.info("<", line)
        self.writer.write(line)
        self.writer.write(b'\r\n')

    def close(self):
        self.logger.debug("closing connection")
        self.writer.close()

    async def run(self):
        self.logger.info(f"connecting to {self.server}...")
        reader, writer = await asyncio.open_connection(
            self.server.host, self.server.port, ssl=self.server.ssl, loop=self.loop
        )
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
            self.logger.info("Connection.run was cancelled")
        except ConnectionResetError as e:
            self.logger.warning(f"connection was reset; {e}")
        finally:
            self.close()
            await self.queue.put(NetworkEvent('disconnected', None))
