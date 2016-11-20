
import asyncio

from .event import NetworkEvent
from .logging import current_logger


class Connection:

    def __init__(self, host: str, port: int, queue: asyncio.Queue,
                 ssl: bool = False, loop: asyncio.AbstractEventLoop = None):
        self.host = host
        self.port = port
        self.queue = queue
        self.ssl = ssl
        self.loop = loop
        if self.loop is None:
            self.loop = asyncio.get_event_loop()

        self.writer = None  # type: asyncio.StreamWriter

    def writeline(self, line: bytes):
        current_logger.info("<", line)
        self.writer.write(line)
        self.writer.write(b'\r\n')

    def close(self):
        current_logger.debug("closing connection")
        self.writer.close()

    async def run(self):
        current_logger.info("connecting to {s.host}:{ssl}{s.port}..."
                            .format(s=self, ssl="+" if self.ssl else ""))
        reader, writer = await asyncio.open_connection(
            self.host, self.port, ssl=self.ssl, loop=self.loop)
        self.writer = writer

        await self.queue.put(NetworkEvent('connected', self))

        try:
            while not reader.at_eof():
                line = await reader.readline()
                line = line.strip()
                current_logger.debug(">", line)
                if line:
                    await self.queue.put(NetworkEvent('raw_line', line))
        except asyncio.CancelledError:
            current_logger.info("Connection.run was cancelled")
        except ConnectionResetError as e:
            current_logger.warning("connection was reset; {}".format(e))
        finally:
            self.close()
            await self.queue.put(NetworkEvent('disconnected', None))
