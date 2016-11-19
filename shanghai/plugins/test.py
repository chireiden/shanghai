"""Just for testing"""

from shanghai.event import message_event

__plugin_name__ = 'Test'
__plugin_version__ = 'β.γ.μ'
__plugin_description__ = 'bla blub'


# just for testing
@message_event('PRIVMSG')
async def on_privmsg(network, message):
    line = message.params[-1]
    words = line.split()

    if words[0] == '!except':
        raise Exception('Test Exception')

    elif words[0] == '!quit':
        await network.request_close(line)

    elif words[0] == '!ctcp':
        if len(words) < 2:
            return
        network.send_ctcp(message.prefix.name, words[1], ' '.join(words[2:]))
