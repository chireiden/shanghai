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

from ..event import ctcp_event
from ..irc import CtcpMessage
from ..plugin_base import CtcpPluginMixin, NetworkPlugin

__plugin_name__ = 'CTCP'
__plugin_version__ = '0.1.0'
__plugin_description__ = 'Default CTCP event handlers'


class DefaultCtcpPlugin(NetworkPlugin, CtcpPluginMixin):

    @ctcp_event('VERSION')
    async def on_ctcp_version(self, message: CtcpMessage):
        source = message.prefix[0]
        self.send_ctcp_reply(source, 'VERSION',
                             "Shanghai v37 - https://github.com/chireiden/shanghai")
