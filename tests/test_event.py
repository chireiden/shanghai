
import asyncio
import unittest
from unittest import mock

from shanghai import event, logging


class TestPriority(unittest.TestCase):

    def test_core_gt_default(self):
        assert event.Priority.CORE > event.Priority.DEFAULT


class TestNetworkEvent(unittest.TestCase):

    def test_attributes(self):
        a, b = object(), object()
        evt = event.NetworkEvent(a, b)
        assert evt.name is a
        assert evt.value is b

    def test_default_argument(self):
        evt = event.NetworkEvent('string')
        assert evt.value is None


class TestPrioritizedSetList(unittest.TestCase):

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

        with self.assertRaises(ValueError):
            prio_set_list.add(0, obj)

        with self.assertRaises(ValueError):
            prio_set_list.add(1, obj)

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

        with self.assertRaises(ValueError):
            prio_set_list.remove(obj)


class TestEventDispatchers(unittest.TestCase):

    def setUp(self):
        config = {
            'disable-logging': True,
            'disable-logging-output': True,
        }
        self.log_context = logging.LogContext('test', 'test', config=config)
        self.log_context.push()

    def tearDown(self):
        self.log_context.pop()

    def test_register(self):
        dispatcher = event.EventDispatcher()

        async def coroutinefunc(*args):
            return True

        dispatcher.register("some_name", coroutinefunc)
        assert coroutinefunc in dispatcher.event_map["some_name"]

    def test_register_callable(self):
        dispatcher = event.EventDispatcher()

        with self.assertRaises(ValueError):
            dispatcher.register("some_name", lambda: None)

    def test_dispatch(self):
        dispatcher = event.EventDispatcher()
        name = "some_name"
        args = list(range(10))

        async def coroutinefunc(*local_args):
            assert args == list(local_args)

        dispatcher.register(name, coroutinefunc)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(dispatcher.dispatch(name, *args))

    # TODO more dispatch tests

    @unittest.skip("TODO")
    def test_network_dispatch(self):
        pass

    @unittest.skip("TODO")
    def test_message_dispatch(self):
        pass


class TestDecorators(unittest.TestCase):

    def test_network_event(self):
        @event.network_event(event.NetworkEventName.CONNECTED)
        async def on_connected(network, _):
            pass

        prio_set_list = event.network_event_dispatcher.event_map[event.NetworkEventName.CONNECTED]
        assert on_connected in prio_set_list

    def test_network_event_exists(self):
        with self.assertRaises(ValueError):
            @event.network_event(123)
            async def x():
                pass

        with self.assertRaises(ValueError):
            @event.network_event('name')
            async def xx():
                pass

    @mock.patch("shanghai.event.message_event_dispatcher", autospec=True)
    def test_message_event_mock(self, dispatcher):
        @event.message_event('PRIVMSG')
        async def on_connected(network, _):
            pass

        dispatcher.register.assert_called_with('PRIVMSG', on_connected, event.Priority.DEFAULT)

    def test_message_event(self):
        @event.message_event('PRIVMSG')
        async def on_connected(network, _):
            pass

        prio_set_list = event.message_event_dispatcher.event_map['PRIVMSG']
        assert on_connected in prio_set_list
