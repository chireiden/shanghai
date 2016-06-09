
import asyncio

from .event import Event
from .irc import Message


class Connection:

    def __init__(self, host, port, queue: asyncio.Queue, ssl=False, loop=None):
        self.host = host
        self.port = port
        self.queue = queue
        self.ssl = ssl
        self.loop = loop
        if self.loop is None:
            self.loop = asyncio.get_event_loop()

        self.writer = None

    def sendline(self, line):
        self.writer.write(line.encode('utf-8') + b'\r\n')
        print("<", line)

    def sendcmd(self, command, *params):
        args = [command, *params]
        if ' ' in args[-1]:
            args[-1] = ':{}'.format(args[-1])
        self.sendline(' '.join(args))

    async def close(self, quitmsg=None):
        if quitmsg:
            self.sendcmd('QUIT', quitmsg)
        await self.writer.drain()
        self.writer.close()

    async def run(self):
        reader, writer = await asyncio.open_connection(
            self.host, self.port, ssl=self.ssl, loop=self.loop)
        self.writer = writer

        await self.queue.put(Event('connected', self))

        while not reader.at_eof():
            line = await reader.readline()
            try:
                line = line.decode('utf-8')
            except UnicodeDecodeError:
                line = line.decode('latin1')
            line = line.strip()
            print(">", line)
            if line:
                try:
                    message = Message.from_line(line)
                except Exception as exc:
                    print('EXCEPTION!', exc)
                    print('--> ', line)
                    raise exc
                if message.command == 'PING':
                    self.sendcmd('PONG', *message.params)
                await self.queue.put(
                    Event('message', message))

        self.writer.close()
        await self.queue.put(Event('disconnected', None))
