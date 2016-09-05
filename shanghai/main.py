
import asyncio
from pprint import pprint
import sys

from .core import Shanghai
from .config import Configuration


def exception_handler(loop, context):
    print("exception_handler context:")
    pprint(context)
    if 'task' in context:
        context['task'].print_stack()


async def stdin_reader(loop, input_handler):
    try:
        if sys.platform == 'win32':
            # Windows can't use SelectorEventLoop.connect_read_pipe
            # and ProactorEventLoop.connect_read_pipe apparently
            # doesn't work with sys.* streams or files.
            # Instead, run polling in an executor (thread).
            # http://stackoverflow.com/questions/31510190/aysncio-cannot-read-stdin-on-windows
            while True:
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    break
                loop.create_task(input_handler(line))
        else:
            reader = asyncio.StreamReader()
            reader_protocol = asyncio.StreamReaderProtocol(reader)
            await loop.connect_read_pipe(lambda: reader_protocol, sys.stdin)

            while True:
                line_bytes = await reader.readline()
                line = line_bytes.decode(sys.stdin.encoding)
                if not line:
                    break
                loop.create_task(input_handler(line))

        print("stdin stream closed")
    except:
        import traceback
        traceback.print_exc()


def main():
    try:
        import uvloop
    except ImportError:
        # TODO: use a proper terminal color tool in the future (e.g. colorama)
        # ... and possibly hook it up with the logging module.
        print('\033[32;1mUsing default event loop.\033[0m')
    else:
        print('\033[32;1mUsing uvloop event loop.\033[0m')
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    config = Configuration.from_filename('shanghai.yaml')
    bot = Shanghai(config)
    network_tasks = list(bot.init_networks())
    print("networks:", ", ".join(bot.networks.keys()))

    async def input_handler(line):
        if ' ' not in line:
            return
        nw_name, irc_line = line.split(None, 1)
        if nw_name and irc_line:
            if nw_name not in bot.networks:
                print("network '{}' not found".format(nw_name))
                return
            network = bot.networks[nw_name]['network']
            network.connection.sendline(irc_line)

    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    loop.set_exception_handler(exception_handler)
    loop.create_task(stdin_reader(loop, input_handler))
    try:
        loop.run_until_complete(asyncio.wait(network_tasks, loop=loop))
    except KeyboardInterrupt:
        print("[!] cancelled by user")
        # schedule close event
        task = asyncio.wait([n['network'].stop_running("KeyboardInterrupt")
                             for n in bot.networks.values()],
                            loop=loop)
        loop.run_until_complete(task)
        # wait again until networks have disconnected
        loop.run_until_complete(asyncio.wait(network_tasks, loop=loop))
