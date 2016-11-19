"""Just for testing"""

import asyncio
import time

from shanghai.event import NetworkEventName, core_network_event, core_message_event
from shanghai.irc import ServerReply
from shanghai.logging import current_logger

__plugin_name__ = 'PING PONG'
__plugin_version__ = '0.1.0'
__plugin_description__ = 'Handles pinging and ponging with networks. Yeah.'


def ms_time() -> int:
    return int(time.time() * 1000)


async def pinger(network, ping_evt):
    while True:
        network.send_cmd('PING', "LAG_{}".format(ms_time()))
        ping_evt.set()
        await asyncio.sleep(30)


async def pong_waiter(network, ping_evt, pong_evt):
    while True:
        await ping_evt.wait()
        ping_evt.clear()
        try:
            await asyncio.wait_for(pong_evt.wait(), 30, loop=network.loop)
        except asyncio.TimeoutError:
            current_logger.warning('Detected ping timeout')
            network._connection_task.cancel()
            return
        else:
            pong_evt.clear()


@core_message_event(ServerReply.RPL_WELCOME)
async def on_welcome(network, _):
    network.add_attribute('latency')

    ping_evt, pong_evt = asyncio.Event(), asyncio.Event()

    pong_waiter_task = asyncio.ensure_future(pong_waiter(network, ping_evt, pong_evt),
                                             loop=network.loop)
    pinger_task = asyncio.ensure_future(pinger(network, ping_evt), loop=network.loop)

    @core_message_event('PONG')
    async def pong(network, msg):
        text = msg.params[1]
        if not text.startswith("LAG_"):
            return
        else:
            pong_evt.set()
            ms = int(text[4:])
            latency = ms_time() - ms
            network.set_attribute('latency', latency)
            current_logger.debug("latency:", latency)

    @core_network_event(NetworkEventName.DISCONNECTED)
    async def on_disconnected(network, _):
        current_logger.debug("Cleaning up ping plugin tasks")
        pong.unregister()
        on_disconnected.unregister()

        pong_waiter_task.cancel()
        pinger_task.cancel()
        done, pending = await asyncio.wait([pinger_task, pong_waiter_task])
        if pending:
            current_logger.warning("pending", pending)


# Realistically, we don't need this since we initiate the ping handshare ourselves,
# but better safe then sorry.
@core_message_event('PING')
async def on_ping(network, message):
    network.send_cmd('PONG', *message.params)
