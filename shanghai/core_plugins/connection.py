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

from shanghai.event import core_event, event, Priority
from shanghai.plugin_base import Plugin, MessagePlugin, NetworkEventName

__plugin_name__ = 'Connection'
__plugin_version__ = '0.1.0'
__plugin_description__ = "Handle connection termination and add some basic logging."


class ConnectionPlugin(Plugin, MessagePlugin):

    @core_event(NetworkEventName.CONNECTED)
    def on_connected(self) -> None:
        self.network.connected = True
        self.logger.info("connected!")

    @core_event(NetworkEventName.DISCONNECTED)
    def on_disconnected(self) -> None:
        self.network.connected = False
        self.logger.info("connection closed by peer")

    # Lower than core to allow other core plugins to eat the event
    @event(NetworkEventName.CLOSE_REQUEST, priority=Priority.POST_CORE)
    def on_close_request(self, quitmsg: str) -> None:
        if self.network.connected:
            if quitmsg:
                self.send_cmd('QUIT', quitmsg)
            else:
                self.send_cmd('QUIT')
            self.network._close()
        else:
            self.logger.info("closing connection prematurely")
            # Because we got "close_request" before "connected",
            # a connection has likely not been established yet.
            # So we cancel the task instead of closing the connection normally.
            if not self.network._connection_task.done():
                self.network._connection_task.cancel()
            self.network.stopped = True
