
import asyncio
from unittest import mock

import pytest

from shanghai import event


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
    def dispatcher(self,):
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
        dispatcher = event.NetworkEventDispatcher(context)
        evt = event.NetworkEvent("name", 456)
        called = False

        async def coroutinefunc(ctx, value):
            nonlocal called
            assert ctx is context
            assert value == 456
            called = True

        dispatcher.register("name", coroutinefunc)
        loop.run_until_complete(dispatcher.dispatch(evt))

        assert called


class TestEventDecorator:

    @pytest.fixture
    def nw_evt_disp(self):
        context = mock.Mock()
        return event.NetworkEventDispatcher(context)

    def test_calls_register(self):
        dispatcher = mock.Mock(event.EventDispatcher)
        deco = event.EventDecorator(dispatcher)

        @deco('evt')
        async def on_connected(ctx, _):
            pass

        dispatcher.register.assert_called_with('evt', on_connected, event.Priority.DEFAULT)

        on_connected.unregister()
        dispatcher.unregister.assert_called_with('evt', on_connected)

    def test_core_calls_register(self):
        dispatcher = mock.Mock(event.EventDispatcher)
        deco = event.EventDecorator(dispatcher)

        @deco.core('core_evt')
        async def on_connected(ctx, _):
            pass

        dispatcher.register.assert_called_with('core_evt', on_connected, event.Priority.CORE)

        on_connected.unregister()
        dispatcher.unregister.assert_called_with('core_evt', on_connected)

    def test_network_event(self, nw_evt_disp):
        deco = nw_evt_disp.decorator

        @deco(event.NetworkEventName.CONNECTED)
        async def on_connected(ctx, _):
            pass

        prio_set_list = nw_evt_disp.event_map[event.NetworkEventName.CONNECTED]
        assert on_connected in prio_set_list

    def test_network_event_exists(self, nw_evt_disp):
        deco = nw_evt_disp.decorator

        with pytest.raises(ValueError):
            @deco(123)
            async def x():
                pass

        with pytest.raises(ValueError):
            @deco('name')
            async def xx():
                pass
