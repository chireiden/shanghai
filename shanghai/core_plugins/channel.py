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

import re
import string

from shanghai.event import global_event, GlobalEventName, EventDispatcher, Priority
from shanghai.network import NetworkContext
from shanghai.util import ShadowAttributesMixin
from shanghai.irc.server_reply import ServerReply
from shanghai.logging import get_logger, Logger

from .message import Message

__plugin_name__ = 'Channel'
__plugin_version__ = '0.1.0'
__plugin_description__ = 'Track channel state'
__plugin_depends__ = ('message',)


class _Base:
    def __hash__(self):
        return hash(id(self))


class Channel(_Base):
    def __init__(self, name, modes=None):
        self.name = name
        self.modes = modes


class User(_Base):
    def __init__(self, nickname, ident='', host=''):
        self.nickname = nickname
        self.ident = ident
        self.host = host


class Join(_Base):
    def __init__(self, channel: Channel, user: User, info: dict=None):
        self.channel = channel
        self.user = user
        self.info = info if info is not None else {}


class ChannelContext(ShadowAttributesMixin):

    def __init__(self, network_context: NetworkContext, message: 'BaseMessage',
                 *, logger: Logger=None):
        self.network_context = network_context
        self.network = network_context.network
        self._message = message

        if logger is None:
            logger = get_logger('channel', f'{self._message.channel}@{self.network.name}',
                                self.network.config)
        self.logger = logger

    def say(self, message):
        self.network_context.send_msg(self._message.channel, message)

    def msg(self, target, message):
        self.network_context.send_msg(target, message)

    @property
    def members(self):
        member_list = []
        for lkey, joinobj in self.network_context.joins.items():
            if self.network_context.chan_eq(lkey[0], self._message.channel):
                member_list.append(joinobj.user)
        return member_list


class ChannelEventDispatcher(EventDispatcher):

    async def dispatch(self, context, msg):
        return await super().dispatch(msg.command, context, msg)


class BaseMessage(Message):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # some convenience accessors
        self.channel = self.params[0]
        self.line = self.params[-1]
        self.words = self.line.split()
        self.sender = self.prefix.name

    @classmethod
    def from_message(cls, message: Message):
        # command name is "ChannelMessage" etc.
        return cls(cls.__name__, prefix=message.prefix, params=message.params,
                   tags=message.tags, raw_line=message.raw_line)


class ChannelMessage(BaseMessage):
    def __repr__(self):
        return (f'<{self.__class__.__name__} type={self.command!r} '
                f'sender={self.prefix.name!r} source={self.params[0]!r} '
                f'message={self.params[-1]!r}>')


class PrivateMessage(BaseMessage):
    def __repr__(self):
        return (f'<{self.__class__.__name__} type={self.command!r} '
                f'sender={self.prefix.name!r} message={self.params[-1]!r}>')


class ChannelNotice(ChannelMessage):
    pass


class PrivateNotice(PrivateMessage):
    pass


async def on_names(ctx: NetworkContext, message: Message):

    if message.command == ServerReply.RPL_ENDOFNAMES:
        lchannel = ctx.chan_lower(message.params[1])
        if lchannel not in ctx.channels:
            ctx.logger.warn(f'Got message from channel we\'re not in: {message!r}')
        if lchannel in ctx.collecting_names:
            del ctx.collecting_names[lchannel]
        return

    lchannel = ctx.chan_lower(message.params[2])
    if lchannel not in ctx.channels:
        ctx.logger.warn(f'Got message from channel we\'re not in: {message!r}')
        return

    opt_namesx = ctx.network.options.get('NAMESX', False)
    opt_prefixes = ctx.network.options.get('PREFIX', '(ov)@+')
    prefix_regex = re.compile(r'^\((?P<mode>.*)\)(?P<prefix>.*)$')
    match = prefix_regex.match(opt_prefixes)
    if match is None:
        match = prefix_regex.match('(ov)@+')  # fallback
    if match is None:
        ctx.logger.warn('RPL_NAMREPLY has unexpected behaviour. '
                        'Either prefix or regex is wrong. '
                        f'Don\'t know what to do. {opt_prefixes!r} {prefix_regex!r}')
        return

    if not ctx.collecting_names.get(lchannel, False):
        ctx.collecting_names[lchannel] = True
        # restarting NAMES command, so we empty the join list for current channel
        for lkey in list(ctx.joins):  # lkey = (lchannel, lnick)
            if ctx.chan_eq(lkey[0], message.params[2]):
                del ctx.joins[lkey]

    # get list of nicknames and their modes if available
    # TODO: when CAP is implemented, this has to respect the "multi-prefix" capability as well.
    prefixed_nicks = message.params[3].split()
    for prefixed_nick in prefixed_nicks:
        if opt_namesx:
            nick = prefixed_nick.lstrip(match.group('prefix'))
        else:
            nick = prefixed_nick
            if nick[0] in match.group('prefix'):
                nick = prefixed_nick[1:]
        d = len(prefixed_nick) - len(nick)
        prefixes = prefixed_nick[:d-len(prefixed_nick)]
        modes = []
        for prefix in prefixes:
            i = match.group('prefix').index(prefix)
            modes.append(match.group('mode')[i])

        # add nick to channel
        lnick = ctx.nick_lower(nick)

        if lnick not in ctx.users:
            # TODO: CAP "multi-prefix"
            ctx.users[lnick] = User(nick, '', '')

        ctx.joins[(lchannel, lnick)] = Join(
            ctx.channels[lchannel],
            ctx.users[lnick],
            {'modes': modes}
        )


async def on_join(ctx: NetworkContext, message: Message):
    if not message.params:
        ctx.logger.info(f'No channel given {message}')
        return
    channel = message.params[0]
    lchannel = ctx.chan_lower(channel)
    if ctx.nick_eq(message.prefix.name, ctx.network.nickname):
        # add channel if not already added
        if lchannel not in ctx.channels:
            ctx.channels[lchannel] = Channel(channel, [])

    # add nickname to list and join channel. This case is the same for both
    # when the bot joins and when other users join.
    if lchannel not in ctx.channels:
        ctx.logger.warn(f'Got message from channel we\'re not in: {message!r}')
        return
    lnick = ctx.nick_lower(message.prefix.name)
    if lnick not in ctx.users:
        ctx.users[lnick] = User(*message.prefix)
    if (lchannel, lnick) not in ctx.joins:
        ctx.joins[(lchannel, lnick)] = Join(
            ctx.channels[lchannel],
            ctx.users[lnick],
            {'modes': []}  # extra info dict, for e.g. modes
        )


async def on_part(ctx: NetworkContext, message: Message):
    lchannel = ctx.chan_lower(message.params[0])

    if lchannel not in ctx.channels:
        ctx.logger.warn(f'Got message from channel we\'re not in: {message!r}')
        return

    nick = message.prefix.name
    ctx.remove_nick_from_channel(nick, lchannel)


async def on_kick(ctx: NetworkContext, message: Message):
    lchannel = ctx.chan_lower(message.params[0])

    if lchannel not in ctx.channels:
        ctx.logger.warn(f'Got message from channel we\'re not in: {message!r}')
        return

    kicked = message.params[1]
    ctx.remove_nick_from_channel(kicked, lchannel)


async def on_nick(ctx: NetworkContext, message: Message):
    nick = message.prefix.name
    new_nick = message.params[0]

    lnick = ctx.nick_lower(nick)
    lnew_nick = ctx.nick_lower(new_nick)

    for lkey in list(ctx.joins):
        if ctx.nick_eq(lkey[1], lnick):
            lnew_key = (lkey[0], lnew_nick)
            ctx.joins[lnew_key] = ctx.joins[lkey]
            del ctx.joins[lkey]

    if lnick in ctx.users:
        ctx.users[lnew_nick] = ctx.users[lnick]
        ctx.users[lnew_nick].nickname = new_nick
        del ctx.users[lnick]

    # should we do this here?
    if ctx.nick_eq(nick, ctx.network.nickname):
        ctx.network.nickname = new_nick


async def on_quit(ctx: NetworkContext, message: Message):
    nick = message.prefix.name
    lnick = ctx.nick_lower(nick)
    for lkey in list(ctx.joins):
        if ctx.nick_eq(lnick, lkey[1]):
            del ctx.joins[lkey]

    if lnick in ctx.users:
        del ctx.users[lnick]


# Manipulation API
def remove_nick_from_channel(ctx: NetworkContext, nick, channel):
    lnick = ctx.nick_lower(nick)
    lchannel = ctx.nick_lower(channel)

    if ctx.nick_eq(ctx.network.nickname, nick):
        # remove myself -> remove channel instance and all users, and remove
        # all user instances that are not visible anymore.

        # find all joins for that channel, remove them, and collect the nicks
        # that where on that channel.
        nicks_to_test = set()
        for lkey in list(ctx.joins):
            if ctx.chan_eq(lchannel, lkey[0]):
                if not ctx.nick_eq(ctx.network.nickname, lkey[1]):
                    nicks_to_test.add(lkey[1])
                del ctx.joins[lkey]

        # check if nicks that got removed are visible somewhere else
        for other_nick in list(nicks_to_test):
            for lkey in ctx.joins:
                if ctx.nick_eq(other_nick, lkey[1]):
                    # nick is visible, remove it from the set
                    nicks_to_test.remove(other_nick)
                    break

        # remove invisible nicks
        for other_nick in nicks_to_test:
            lother_nick = ctx.nick_lower(other_nick)
            if lother_nick in ctx.users:
                del ctx.users[lother_nick]

        # finally, remove the channel
        if lchannel in ctx.channels:
            del ctx.channels[lchannel]
        return

    # case: nick that is not me is removed
    # remove join, and test if user is still visible. if not, remove user
    if (lchannel, lnick) in ctx.joins:
        del ctx.joins[(lchannel, lnick)]

    for lkey in ctx.joins:
        if ctx.nick_eq(lnick, lkey[1]):
            break
    else:
        # nick not found
        if lnick in ctx.users:
            del ctx.users[lnick]


# nick/chan string API
def generate_case_table(ctx: NetworkContext):
    case_mapping = ctx.network.options.get('CASEMAPPING', 'rfc1459').lower()
    if case_mapping not in ('ascii', 'rfc1459', 'strict-rfc1459'):
        case_mapping = 'rfc1459'
    upper_str = string.ascii_uppercase
    lower_str = string.ascii_lowercase
    if case_mapping == 'rfc1459':
        upper_str += '[]\\^'
        lower_str += '{}|~'
    elif case_mapping == 'strict-rfc1459':
        upper_str += '[]\\'
        lower_str += '{}|'
    return str.maketrans(upper_str, lower_str)


def nick_lower(ctx: NetworkContext, nick: str):
    return nick.translate(ctx.case_table)


def chan_lower(ctx: NetworkContext, chan: str):
    return ctx.nick_lower(chan)


def nick_eq(ctx: NetworkContext, nick1: str, nick2: str):
    return ctx.nick_lower(nick1) == ctx.nick_lower(nick2)


def chan_eq(ctx: NetworkContext, chan1: str, chan2: str):
    return ctx.chan_lower(chan1) == ctx.chan_lower(chan2)


@global_event(GlobalEventName.INIT_NETWORK_CTX, priority=Priority.POST_CORE)
async def init_context(ctx: NetworkContext):
    ctx.add_attribute('case_table', generate_case_table(ctx))
    ctx.add_attribute('channels', {})  # l(channel-name) -> channel
    ctx.add_attribute('users', {})  # l(nickname) -> user
    ctx.add_attribute('joins', {})  # (l(channel-name), l(nickname)) -> (channel, user, info_dict)
    ctx.add_attribute('collecting_names', {})

    ctx.add_method(remove_nick_from_channel)

    ctx.add_method(nick_lower)
    ctx.add_method(chan_lower)
    ctx.add_method(nick_eq)
    ctx.add_method(chan_eq)

    ctx.message_event(ServerReply.RPL_NAMREPLY)(on_names)
    ctx.message_event(ServerReply.RPL_ENDOFNAMES)(on_names)
    ctx.message_event('JOIN')(on_join)
    ctx.message_event('PART')(on_part)
    ctx.message_event('KICK')(on_kick)
    ctx.message_event('NICK')(on_nick)
    ctx.message_event('QUIT')(on_quit)

    channel_contexts = {}
    channel_event_dispatcher = ChannelEventDispatcher()
    ctx.add_attribute('channel_event', channel_event_dispatcher.decorator)

    @ctx.add_method
    def get_channel_context(n_ctx: NetworkContext, channel: str):
        lchannel = n_ctx.chan_lower(channel)
        return channel_contexts[lchannel]

    @ctx.message_event('PRIVMSG')
    @ctx.message_event('NOTICE')
    async def on_privmsg(n_ctx: NetworkContext, message: Message):
        channel = message.params[0]
        lchannel = n_ctx.chan_lower(channel)

        opt_chantypes = n_ctx.network.options.get('CHANTYPES', '#&+')
        if channel.startswith(tuple(opt_chantypes)):
            if message.command == 'PRIVMSG':
                new_message = ChannelMessage.from_message(message)
            else:
                new_message = ChannelNotice.from_message(message)
        else:
            if message.command == 'PRIVMSG':
                new_message = PrivateMessage.from_message(message)
            else:
                new_message = PrivateNotice.from_message(message)

        if lchannel not in channel_contexts:
            c_ctx = ChannelContext(n_ctx, new_message)
            channel_contexts[lchannel] = c_ctx

        await channel_event_dispatcher.dispatch(channel_contexts[lchannel], new_message)
