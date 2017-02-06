"""Just for testing"""

import asyncio
import time

from shanghai.event import NetworkEventName, GlobalEventName, global_event
from shanghai.irc import ServerReply
from shanghai.network import NetworkContext

__plugin_name__ = 'PING PONG'
__plugin_version__ = '0.1.0'
__plugin_description__ = 'Handles pinging and ponging with networks. Yeah.'

__plugin_depends__ = ['message']


def ms_time() -> int:
    return int(time.time() * 1000)


async def pinger(ctx: NetworkContext, ping_evt):
    while True:
        ctx.send_cmd('PING', f"LAG_{ms_time()}")
        ping_evt.set()
        await asyncio.sleep(30)


async def pong_waiter(ctx: NetworkContext, ping_evt, pong_evt):
    while True:
        await ping_evt.wait()
        ping_evt.clear()
        try:
            await asyncio.wait_for(pong_evt.wait(), 30, loop=ctx.network.loop)
        except asyncio.TimeoutError:
            ctx.logger.warning('Detected ping timeout')
            ctx.network._connection_task.cancel()
            return
        else:
            pong_evt.clear()


@global_event.core(GlobalEventName.INIT_NETWORK_CTX)
async def init_context(ctx: NetworkContext):
    ctx.logger.info('initializing context in "ping" plugin.', ctx)
    ctx.add_attribute('latency', 0)

    @ctx.message_event.core(ServerReply.RPL_WELCOME)
    async def on_welcome(ctx: NetworkContext, _):
        ping_evt, pong_evt = asyncio.Event(), asyncio.Event()

        pong_waiter_task = asyncio.ensure_future(pong_waiter(ctx, ping_evt, pong_evt),
                                                 loop=ctx.network.loop)
        pinger_task = asyncio.ensure_future(pinger(ctx, ping_evt), loop=ctx.network.loop)

        @ctx.message_event.core('PONG')
        async def pong(ctx: NetworkContext, msg):
            text = msg.params[1]
            if not text.startswith("LAG_"):
                return
            else:
                pong_evt.set()
                ms = int(text[4:])
                latency = ms_time() - ms
                ctx.set_attribute('latency', latency)
                ctx.logger.debug(f"latency: {latency / 1000:.3f}s")

        @ctx.network_event.core(NetworkEventName.DISCONNECTED)
        async def on_disconnected(ctx: NetworkContext, _):
            ctx.logger.debug("Cleaning up ping plugin tasks")
            pong.unregister()
            on_disconnected.unregister()

            ctx.set_attribute('latency', 0)
            pong_waiter_task.cancel()
            pinger_task.cancel()
            done, pending = await asyncio.wait([pinger_task, pong_waiter_task])
            if pending:
                ctx.logger.warning("pending", pending)

    # Realistically, we don't need this since we initiate the ping handshare ourselves,
    # but better safe then sorry.
    @ctx.message_event.core('PING')
    async def on_ping(ctx, message):
        ctx.send_cmd('PONG', *message.params)
