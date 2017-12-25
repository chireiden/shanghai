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

import enum
from typing import Dict, Optional, Set, Type

from ..event import build_event, core_event, event, Priority, ReturnValue
from ..plugin_base import (ChannelEventName, MessagePluginMixin, NetworkPlugin, NetworkEventName,
                           OptionsPluginMixin)
from ..irc import ServerReply
from ..irc.message import (Prefix, Message, ChannelMessage, ChannelNotice,
                           PrivateMessage, PrivateNotice, TextMessage)
from ..channel import Channel

__plugin_name__ = 'Channel'
__plugin_version__ = '0.1.0'
__plugin_description__ = 'Track channel state'


class _ChannelStateEventName(str, enum.Enum):
    AFTER_KICKED = f'{__name__}_after_kicked'
    AFTER_PARTED = f'{__name__}_after_parted'
    AFTER_DISCONNECTED = f'{__name__}_after_disconnected'


class ChannelStatePlugin(NetworkPlugin, MessagePluginMixin, OptionsPluginMixin):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # set of channel names we are currently collecting members for
        self._collecting_names: Set[str] = set()  # {l(channel-name)}
        # _joins is a relational table that connects channels and users
        self._joins: Dict[(str, str), Dict] = {}  # {(l(channel-name), l(nickname)) -> info_dict}

    @core_event(NetworkEventName.DISCONNECTED)
    def on_disconnected(self):
        self._joins.clear()
        self._collecting_names.clear()
        evt = build_event(_ChannelStateEventName.AFTER_DISCONNECTED)
        return ReturnValue(insert_events=(evt,))

    @event(_ChannelStateEventName.AFTER_DISCONNECTED)
    def on_post_disconnected(self):
        self.network.channels.clear()

    @core_event('JOIN')
    async def on_join(self, message: Message):
        if not message.params:
            self.logger.warning(f'No channel given {message}')
            return
        channel = message.params[0]
        lchannel = self.chan_lower(channel)
        new_channel: Optional[Channel] = None

        if self.nick_eq(message.prefix.name, self.network.nickname):
            if lchannel not in self.network.channels:
                # we're joining a new channel,
                # so create a new Channel instance
                new_channel = Channel(self.network, lchannel, self._joins)
                self.network.channels[lchannel] = new_channel

        elif lchannel not in self.network.channels:
            self.logger.warning(f"Got message from channel we're not in: {message!r}")
            return

        # Add nickname to list and join channel.
        # This case is the same for both
        # when we and when other users join.
        # Also always overwrite in case the prefix/host was updated.
        lnick = self.nick_lower(message.prefix.name)
        self.network.users[lnick] = message.prefix

        if (lchannel, lnick) not in self._joins:
            self._joins[(lchannel, lnick)] = {'modes': ""}  # extra info dict, for e.g. modes

        if new_channel:
            return ReturnValue(schedule={new_channel._run()})

    @core_event(ServerReply.RPL_NAMREPLY)
    def on_names(self, message: Message):
        lchannel = self.chan_lower(message.params[2])
        if lchannel not in self.network.channels:
            self.logger.warning(f"Got message from channel we're not in: {message!r}")
            return

        if lchannel not in self._collecting_names:
            self._collecting_names.add(lchannel)
            # restarting NAMES command, so we empty the join list for current channel
            # TODO self.network.users isn't cleaned up here
            for lkey in tuple(self._joins):  # lkey = (lchannel, lnick)
                if self.chan_eq(lkey[0], message.params[2]):
                    del self._joins[lkey]

        # get list of nicknames and their modes if available
        # TODO: when CAP is implemented, this has to respect the "multi-prefix" capability as well.
        prefixed_nicks = message.params[3].split()
        for prefixed_nick in prefixed_nicks:
            prefixes, nick = self.network.options.split_prefixes(prefixed_nick)
            modes = self.network.options.prefixes_to_modes(prefixes)

            # add nick to channel
            lnick = self.nick_lower(nick)
            if lnick not in self.network.users:
                self.network.users[lnick] = Prefix(nick)

            self._joins[(lchannel, lnick)] = {'modes': modes}

    @core_event(ServerReply.RPL_ENDOFNAMES)
    def on_names_end(self, message: Message):
        lchannel = self.chan_lower(message.params[1])
        if lchannel not in self.network.channels:
            self.logger.warning(f"Got message from channel we're not in: {message!r}")
            return

        self._collecting_names.discard(lchannel)

    @core_event('PART')
    def on_part(self, message: Message):
        lchannel = self.chan_lower(message.params[0])

        if lchannel not in self.network.channels:
            self.logger.warning(f"Got message from channel we're not in: {message!r}")
            return

        nick = message.prefix.name
        if self._remove_nick_from_channel(nick, lchannel):
            evt = build_event(_ChannelStateEventName.AFTER_PARTED, lchannel=lchannel)
            return ReturnValue(insert_events=(evt,))

    @event(_ChannelStateEventName.AFTER_PARTED)
    def on_post_part(self, lchannel: str):
        channel = self.network.channels.get(lchannel)
        if channel:
            del self.network.channels[lchannel]
            channel._parted = True

    @core_event('KICK')
    async def on_kick(self, message: Message):
        lchannel = self.chan_lower(message.params[0])

        if lchannel not in self.network.channels:
            self.logger.warning(f'Got message from channel we\'re not in: {message!r}')
            return

        kicked = message.params[1]
        if self._remove_nick_from_channel(kicked, lchannel):
            evt = build_event(_ChannelStateEventName.AFTER_KICKED, lchannel=lchannel)
            return ReturnValue(insert_events=(evt,))

    @event(_ChannelStateEventName.AFTER_KICKED)
    def on_post_kick(self, lchannel: str):
        channel = self.network.channels.get(lchannel)
        if channel:
            del self.network.channels[lchannel]
            channel._parted = True

    @core_event('NICK')
    async def on_nick(self, message: Message):
        nick = message.prefix.name
        new_nick = message.params[0]

        lnick = self.nick_lower(nick)
        lnew_nick = self.nick_lower(new_nick)

        if lnick in self.network.users:
            self.network.users[lnew_nick] = self.network.users[lnick]._replace(name=new_nick)
            del self.network.users[lnick]

    @core_event('QUIT')
    async def on_quit(self, message: Message):
        nick = message.prefix.name
        lnick = self.nick_lower(nick)
        for lkey in list(self._joins):
            if self.nick_eq(lnick, lkey[1]):
                del self._joins[lkey]

        if lnick in self.network.users:
            del self.network.users[lnick]

    # Manipulation API
    def _remove_nick_from_channel(self, nick: str, lchannel: str) -> bool:
        """Removes the nick from _joins table and network's users registry.

        Returns whether *we* were removed from a channel.
        """
        lnick = self.nick_lower(nick)
        lnickself = self.nick_lower(self.network.nickname)

        if lnickself == lnick:
            # remove myself -> remove channel instance and all users, and remove
            # all user instances that are not visible anymore.

            # find all joins for that channel, remove them, and collect the nicks
            # that were on that channel.
            nicks_to_test = set()
            for lkey in list(self._joins):
                if self.chan_eq(lchannel, lkey[0]):
                    if lnickself != lkey[1]:
                        nicks_to_test.add(lkey[1])
                    del self._joins[lkey]

            # check if nicks that got removed are visible somewhere else
            for other_nick in list(nicks_to_test):
                for lkey in self._joins:
                    if other_nick == lkey[1]:
                        # nick is visible, remove it from the set
                        nicks_to_test.remove(other_nick)
                        break

            # remove invisible nicks
            for other_nick in nicks_to_test:
                lother_nick = self.nick_lower(other_nick)
                if lother_nick in self.network.users:
                    del self.network.users[lother_nick]

            return True

        else:
            # case: nick that is not me is removed
            # remove join, and test if user is still visible. if not, remove user
            if (lchannel, lnick) in self._joins:
                del self._joins[(lchannel, lnick)]

            for lkey in self._joins:
                if self.nick_eq(lnick, lkey[1]):
                    break
            else:
                # nick not found
                if lnick in self.network.users:
                    del self.network.users[lnick]

            return False


class ChannelEventsPlugin(NetworkPlugin, OptionsPluginMixin):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._joining_names: Set[str] = set()

    @core_event('JOIN')
    async def on_join(self, message: Message):
        lchannel = self.chan_lower(message.params[0])
        self._joining_names.add(lchannel)

    @event(ServerReply.RPL_ENDOFNAMES, priority=Priority.POST_CORE)
    async def on_names_end(self, message: Message):
        # dispatch the JOINED event after all members are known
        lchannel = self.chan_lower(message.params[0])
        if lchannel in self._joining_names:
            self._joining_names.discard(lchannel)
            channel = self.network.channels.get(lchannel)
            if channel:
                evt = build_event(ChannelEventName.JOINED)  # no useful args here
                return await channel._event_dispatcher.dispatch(evt)

    @event('PART', priority=Priority.POST_CORE)
    async def on_part(self, message: Message):
        channel_name = message.params[0]
        lchannel = self.chan_lower(channel_name)
        if self.nick_eq(self.network.nickname, message.prefix.name):
            evt = build_event(ChannelEventName.PARTED, message=message)
            channel = self.network.channels[lchannel]
            return await channel._event_dispatcher.dispatch(evt)

    @event('KICK', priority=Priority.POST_CORE)
    async def on_kick(self, message: Message):
        lchannel = self.chan_lower(message.params[0])
        kicked = message.params[1]
        if self.nick_eq(self.network.nickname, kicked):
            evt = build_event(ChannelEventName.KICKED, message=message)
            channel = self.network.channels[lchannel]
            return await channel._event_dispatcher.dispatch(evt)

    # TODO multiple events per handler
    @event('NOTICE', priority=Priority.POST_CORE)
    async def on_notice(self, message: Message):
        return await self.on_privmsg(message)

    @event('PRIVMSG', priority=Priority.POST_CORE)
    async def on_privmsg(self, message: Message):
        lchannel = self.chan_lower(message.params[0])
        opt_chantypes = self.network.options.get('CHANTYPES', '#&+')

        message_type: Type[TextMessage]
        evt_name: str
        if lchannel[0] in opt_chantypes:
            # target is a channel
            if lchannel not in self.network.channels:
                self.logger.warning(f"Got message from channel we're not in: {message!r}")
                return
            if message.command == 'PRIVMSG':
                message_type, evt_name = ChannelMessage, ChannelEventName.MESSAGE
            else:
                message_type, evt_name = ChannelNotice, ChannelEventName.NOTICE

            new_message = message_type.from_message(message)
            evt = build_event(evt_name, message=new_message)
            channel = self.network.channels[lchannel]
            return await channel._event_dispatcher.dispatch(evt)

        else:
            # we were the target
            if message.command == 'PRIVMSG':
                message_type, evt_name = PrivateMessage, NetworkEventName.PRIVATE_MESSAGE
            else:
                message_type, evt_name = PrivateNotice, NetworkEventName.PRIVATE_NOTICE

            new_message = message_type.from_message(message)
            evt = build_event(evt_name, message=new_message)
            return ReturnValue(insert_events=(evt,))

    # TODO mode changes

    @core_event(NetworkEventName.DISCONNECTED)
    async def on_disconnected(self):
        self._joining_names.clear()
        evt = build_event(ChannelEventName.DISCONNECTED)
        # TODO parallelize
        for channel in self.network.channels.values():
            await channel._event_dispatcher.dispatch(evt)


class JoinOnConnectPlugin(NetworkPlugin, MessagePluginMixin):

    @core_event(ServerReply.RPL_WELCOME)
    def on_msg_welcome(self, message: Message) -> None:
        for channel, chanconf in self.network.config.get('channels', {}).items():
            key = chanconf.get('key', None)
            if key is not None:
                self.send_cmd('JOIN', channel, key)
            else:
                self.send_cmd('JOIN', channel)
