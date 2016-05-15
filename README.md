[![Build Status](https://travis-ci.org/chireiden/shanghai.svg?branch=master)](https://travis-ci.org/chireiden/shanghai)

# Shanghai (multi server asyncio IRC bot)

IRC: #chireiden @ Freenode

## Some Notes

### Primary structure

An outer most class `Shanghai` representing the main application. It loads and
holds the configuration, and the main loop is probably executed somewhere
around there (a method `run_forever` or something, that simply calles the event
loops `run_forever`). There should only be one instance of this class.

It's possible to define multiple networks in the configuration. Each one is
represented with an instance of a `Network` class. Network instances are held
by the Shanghai instance (in an array networks or something). Each network may
have configuration that's unique for this network (e.g. different nickname).

A network has a list of server/port tuples. Each should be tried in sequence
if connection to one of them fails.

An instance of a `State` class is assigned to each network, that contains all
the channels, users, modes and other information the bot sees on the network
it's connected to. On a reconnect the state instance simpley gets discarded and
a new one is created.

A `Connection` (or `Protocol` or `Server`) instance is assigned to the network
that's used for retrieving new events (IRC lines) in the form of `Message`
instances and for sending messages to the server. The dispatching should not be
done by the connection instance itself. The network instance should pull the
messages from the connection instead and dispatching is then either done by the
network instance or the Shanghai instance (not sure here, since plugins might
want to override some default event behaviour).

### Plugins

Plugins are either located in a designated subdirectory (default `./plugins`?
or maybe definable via configuration?) or somewhere in `sys.path` and are named
using the `shanghai_*` pattern, similar to Flask extensions.

Which plugins to load must be defined in the configuration. It should be
possible to load plugins only for certain networks or even certain channels.

Maybe a plugin should be able to define what
[capabilities](http://ircv3.net/irc/) it provides and what it conflicts with
(to avoid loading conflicting plugins) and what plugins it depends on.

There might be *global* plugins, providing non-IRC related functionality (so
enabling it for a network or not does not make much sense), for example a
plugin that provides a way for other plugins to store data in a database.