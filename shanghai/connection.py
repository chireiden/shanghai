# Copyright © 2016  Lars Peter Søndergaard <lps@chireiden.net>
# Copyright © 2016  FichteFoll <fichtefoll2@googlemail.com>
#
# This file is part of Shanghai, an asynchronous multi-server IRC bot.
#
# Shanghai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Shanghai is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Shanghai.  If not, see <http://www.gnu.org/licenses/>.

import asyncio

from .config import Server
from .event import NetworkEvent, NetworkEventName
from .logging import Logger, get_default_logger


class Connection:

    writer: asyncio.StreamWriter

    def __init__(self,
                 server: Server,
                 queue: asyncio.Queue,
                 loop: asyncio.AbstractEventLoop,
                 logger: Logger = None,
                 ) -> None:
        self.server = server
        self.queue = queue
        self.loop = loop
        if logger is None:
            logger = get_default_logger()
        self.logger = logger

    def writeline(self, line: bytes) -> None:
        self.logger.info("<", line)
        self.writer.write(line)
        self.writer.write(b'\r\n')

    def close(self) -> None:
        self.logger.debug("closing connection")
        self.writer.close()

    async def run(self) -> None:
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
                    event = NetworkEvent(NetworkEventName.RAW_LINE, line)
                    await self.queue.put(event)
        except asyncio.CancelledError:
            self.logger.info("Connection.run was cancelled")
        except ConnectionResetError as e:
            self.logger.warning(f"connection was reset; {e}")
        finally:
            self.close()
            await self.queue.put(NetworkEvent('disconnected', None))
