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

import asyncio
from unittest import mock

import pytest

from shanghai import event
from shanghai import network
from shanghai.logging import Logger


@pytest.fixture
def loop():
    return asyncio.get_event_loop()


class TestPriority:

    def test_core_gt_default(self):
        assert event.Priority.CORE > event.Priority.DEFAULT


class TestNetworkEvent:

    def test_attributes(self):
        a, b = object(), object()
        evt = event.NetworkEvent(a, b)
        assert evt.name is a
        assert evt.value is b

    def test_default_argument(self):
        evt = event.NetworkEvent('string')
        assert evt.value is None


class TestPrioritizedSetList:

    def test_bool(self):
        prio_set_list = event._PrioritizedSetList()

        assert bool(prio_set_list) is False

        prio_set_list.add(0, None)
        assert bool(prio_set_list) is True

    def test_add(self):
        prio_set_list = event._PrioritizedSetList()
        objs = [(i,) for i in range(5)]

        prio_set_list.add(0, objs[0])
        assert prio_set_list.list == [(0, {objs[0]})]

        prio_set_list.add(0, objs[1])
        assert prio_set_list.list == [(0, {objs[0], objs[1]})]

        prio_set_list.add(10, objs[2])
        assert prio_set_list.list == [(10, {objs[2]}),
                                      (0,  {objs[0], objs[1]})]

        prio_set_list.add(-10, objs[3])
        assert prio_set_list.list == [( 10, {objs[2]}),           # noqa: E201
                                      (  0, {objs[0], objs[1]}),  # noqa: E201
                                      (-10, {objs[3]})]
        prio_set_list.add(-1, objs[4])
        assert prio_set_list.list == [( 10, {objs[2]}),           # noqa: E201
                                      (  0, {objs[0], objs[1]}),  # noqa: E201
                                      ( -1, {objs[4]}),           # noqa: E201
                                      (-10, {objs[3]})]

    def test_add_already_added(self):
        prio_set_list = event._PrioritizedSetList()
        obj = object()
        prio_set_list.add(0, obj)

        with pytest.raises(ValueError) as excinfo:
            prio_set_list.add(0, obj)
        excinfo.match(r"has already been added")

        with pytest.raises(ValueError) as excinfo:
            prio_set_list.add(1, obj)
        excinfo.match(r"has already been added")

    def test_contains(self):
        prio_set_list = event._PrioritizedSetList()
        obj = object()

        prio_set_list.add(0, obj)
        assert obj in prio_set_list

    def test_iter(self):
        prio_set_list = event._PrioritizedSetList()
        objs = [(i,) for i in range(5)]
        for i, obj in enumerate(objs):
            prio_set_list.add(-i, obj)

        for i, set_ in enumerate(prio_set_list):
            assert set_ == (-i, {objs[i]})

    def test_remove(self):
        prio_set_list = event._PrioritizedSetList()
        obj = (1,)

        prio_set_list.add(1, obj)
        assert prio_set_list
        prio_set_list.remove(obj)
        assert not prio_set_list

        with pytest.raises(ValueError) as excinfo:
            prio_set_list.remove(obj)
        excinfo.match(r"can not be found")


class TestEventDispatchers:

    @pytest.fixture
    def dispatcher(self):
        return event.EventDispatcher()

    def test_register(self, dispatcher):

        async def coroutinefunc(*args):
            return True

        dispatcher.register("some_name", coroutinefunc)
        assert coroutinefunc in dispatcher.event_map["some_name"]

    def test_unregister(self, dispatcher):

        async def coroutinefunc(*args):
            return True

        dispatcher.register("some_name", coroutinefunc)
        dispatcher.unregister("some_name", coroutinefunc)
        assert coroutinefunc not in dispatcher.event_map["some_name"]
        with pytest.raises(ValueError) as excinfo:
            dispatcher.unregister("some_name", coroutinefunc)
        excinfo.match(r"Object .* can not be found")

    def test_register_callable(self, dispatcher):

        with pytest.raises(ValueError) as excinfo:
            dispatcher.register("some_name", lambda: None)
        excinfo.match(r"callable must be a coroutine function")

    def test_dispatch(self, dispatcher, loop):
        name = "some_name"
        args = list(range(10))
        called = 0

        async def coroutinefunc(*local_args):
            nonlocal called
            assert list(local_args) == args
            called += 1

        dispatcher.register(name, coroutinefunc)
        loop.run_until_complete(dispatcher.dispatch(name, *args))
        loop.run_until_complete(dispatcher.dispatch(name + '_', *args))

        assert called == 1

    def test_dispatch_priority(self, dispatcher, loop):
        name = "some_name"
        called = list()

        async def coroutinefunc():
            called.append(coroutinefunc)

        async def coroutinefunc2():
            called.append(coroutinefunc2)

        dispatcher.register(name, coroutinefunc)
        dispatcher.register(name, coroutinefunc2, priority=event.Priority.DEFAULT + 1)
        loop.run_until_complete(dispatcher.dispatch(name))

        assert called == [coroutinefunc2, coroutinefunc]

    def test_network_dispatch(self, loop):
        context = mock.Mock()
        dispatcher = network.NetworkEventDispatcher(context)
        evt = event.NetworkEvent("name", 456)
        called = False

        async def coroutinefunc(ctx, value):
            nonlocal called
            assert ctx is context
            assert value == 456
            called = True

        dispatcher.register("name", coroutinefunc)
        loop.run_until_complete(dispatcher.dispatch_nwevent(evt))

        assert called

    def test_dispatch_eat(self, loop):
        logger = mock.Mock(Logger)
        dispatcher = event.EventDispatcher(logger=logger)
        called = [False] * 3

        async def coroutinefunc():
            called[0] = True

        async def coroutinefunc2():
            called[1] = True
            return event.ReturnValue.EAT

        async def coroutinefunc3():
            called[2] = True

        dispatcher.register("name", coroutinefunc, event.Priority.DEFAULT + 1)
        dispatcher.register("name", coroutinefunc2)
        dispatcher.register("name", coroutinefunc3, event.Priority.DEFAULT - 1)
        result = loop.run_until_complete(dispatcher.dispatch("name"))
        assert result is event.ReturnValue.EAT
        assert called == [True, True, False]

    def test_dispatch_exception(self, loop):
        logger = mock.Mock(Logger)
        dispatcher = event.EventDispatcher(logger=logger)
        called = False

        async def coroutinefunc():
            nonlocal called
            called = True
            raise ValueError("yeah")

        dispatcher.register("name", coroutinefunc)
        assert not logger.exception.called
        loop.run_until_complete(dispatcher.dispatch("name"))
        assert logger.exception.call_count == 1
        assert called

    def test_dispatch_unknown_return(self, loop):
        logger = mock.Mock(Logger)
        dispatcher = event.EventDispatcher(logger=logger)
        called = False

        async def coroutinefunc():
            nonlocal called
            called = True
            return "some arbitrary value"

        dispatcher.register("name", coroutinefunc)
        assert not logger.warning.called
        loop.run_until_complete(dispatcher.dispatch("name"))
        assert logger.warning.call_count == 1
        assert called


class TestEventDecorator:

    @pytest.fixture
    def nw_evt_disp(self):
        context = mock.Mock()
        return network.NetworkEventDispatcher(context)

    def test_calls_register(self):
        dispatcher = mock.Mock(event.EventDispatcher)
        deco = event.EventDecorator(dispatcher)
        evt_name = "evt"

        @deco(evt_name)
        async def on_connected(ctx, _):
            pass

        dispatcher.register.assert_called_with(evt_name, on_connected, event.Priority.DEFAULT)

        on_connected.unregister()
        dispatcher.unregister.assert_called_with(evt_name, on_connected)

    def test_core_calls_register(self):
        dispatcher = mock.Mock(event.EventDispatcher)
        deco = event.EventDecorator(dispatcher)
        evt_name = "core_evt"

        @deco.core(evt_name)
        async def on_connected(ctx, _):
            pass

        dispatcher.register.assert_called_with(evt_name, on_connected, event.Priority.CORE)

        on_connected.unregister()
        dispatcher.unregister.assert_called_with(evt_name, on_connected)

    def test_network_event(self, nw_evt_disp):
        deco = nw_evt_disp.decorator
        evt_name = event.NetworkEventName.CONNECTED

        @deco(evt_name)
        async def on_connected(ctx, _):
            pass

        prio_set_list = nw_evt_disp.event_map[evt_name]
        assert on_connected in prio_set_list

    def test_network_event_exists(self, nw_evt_disp):
        deco = nw_evt_disp.decorator

        with pytest.raises(ValueError) as excinfo:
            @deco(123)
            async def x():
                pass
        excinfo.match(f"Unknown event name 123")

        with pytest.raises(ValueError) as excinfo:
            @deco('name')
            async def xx():
                pass
        excinfo.match(f"Unknown event name 'name'")
