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
from shanghai.logging import Logger, get_logger, LogLevels

# use this when debug log output is desired
debug_logger = get_logger('logging', 'debug')
debug_logger.setLevel(LogLevels.DDEBUG)


@pytest.fixture
def loop():
    return asyncio.get_event_loop()


@pytest.fixture
def evt():
    return event.build_event("event")


# base class to subclass for an actual plugin
class BasePlugin:
    pass


@pytest.fixture
def sample_plugin():
    class TestPlugin(BasePlugin):
        @event.event
        def on_test(self):
            pass

    return TestPlugin


class TestPriority:

    def test_type(self):
        assert isinstance(event.Priority.DEFAULT, int)

    def test_order(self):
        assert (event.Priority.PRE_CORE
                > event.Priority.CORE
                > event.Priority.POST_CORE
                > event.Priority.PRE_DEFAULT
                > event.Priority.DEFAULT
                > event.Priority.POST_DEFAULT)

    def test_lookup(self):
        assert event.Priority.lookup(event.Priority.CORE) is event.Priority.CORE
        assert event.Priority.lookup(event.Priority.CORE.value) is event.Priority.CORE
        assert event.Priority.lookup(-12312412) == -12312412


class TestEvent:

    def test_build_event(self):
        evt = event.build_event("evt_name", arg1="val1", arg2=None)
        assert evt.name == "evt_name"
        assert evt.args == {'arg1': "val1", 'arg2': None}


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


# Skipping HandlerInfo tests
# since that is only to be used with the `event` decorator anyway.
class TestEventDecorator:

    def test_no_param_usage(self):
        @event.event
        def func_name(self):
            pass

        @event.event
        def on_test(self):
            pass

        assert hasattr(on_test, '_h_info')
        h_info = on_test._h_info
        assert h_info.event_name == "test"
        assert func_name._h_info.event_name == "func_name"
        assert h_info.handler is on_test
        assert h_info.priority is event.Priority.DEFAULT
        assert h_info.should_enable
        assert not h_info.is_async

    def test_param_usage(self):
        @event.event('evt_test', priority=-12, enable=False)
        def on_test(self):
            pass

        assert hasattr(on_test, '_h_info')
        h_info = on_test._h_info
        assert h_info.event_name == 'evt_test'
        assert h_info.handler is on_test
        assert h_info.priority == -12
        assert not h_info.should_enable
        assert not h_info.is_async

    def test_async_handler(self):
        @event.event(enable=False)
        async def on_async_test(self):
            pass

        assert hasattr(on_async_test, '_h_info')
        h_info = on_async_test._h_info
        assert h_info.event_name == 'async_test'
        assert h_info.handler is on_async_test
        assert h_info.priority is event.Priority.DEFAULT
        assert not h_info.should_enable
        assert h_info.is_async

    def test_prefix(self):
        import functools
        other_event_deco = functools.partial(event.event, _prefix="__test_")

        @other_event_deco
        def on_test(self):
            pass

        assert hasattr(on_test, '_h_info')
        h_info = on_test._h_info
        assert h_info.event_name == '__test_test'

    def test_core_event_deco(self):
        @event.core_event
        def on_test(self):
            pass

        assert hasattr(on_test, '_h_info')
        h_info = on_test._h_info
        assert h_info.priority is event.Priority.CORE

    def test_non_callable(self):
        with pytest.raises(TypeError) as excinfo:
            event.event(123)
        excinfo.match(r"Expected string, callable or None as first argument")

        with pytest.raises(TypeError) as excinfo:
            event.event("name")([])
        excinfo.match(r"Callable must be a function \(`def`\)"
                      r" or coroutine function \(`async def`\)")


class TestHandlerInstance:

    def test_from_handler(self):
        @event.event
        def handler():
            pass

        h_inst = event.HandlerInstance.from_handler(handler)
        assert h_inst.info is handler._h_info
        assert h_inst.enabled
        assert h_inst.handler is handler._h_info.handler

    def test_from_not_handler(self):
        def func():
            pass

        with pytest.raises(ValueError) as excinfo:
            event.HandlerInstance.from_handler(func)
        excinfo.match(r"Event handler must be decorated with `@event`")

    def test_hash(self):
        @event.event
        def handler():
            pass

        h_inst = event.HandlerInstance.from_handler(handler)
        h_inst2 = event.HandlerInstance.from_handler(handler)
        assert h_inst is not h_inst2
        assert hash(h_inst) == hash(h_inst2)
        assert h_inst != h_inst2


class TestResultSet:

    def test_extend(self, evt, loop):
        async def corofunc():
            pass

        coro = corofunc()
        coro2 = corofunc()
        # silence "coroutine never awaited" warnings
        loop.run_until_complete(coro)
        loop.run_until_complete(coro2)

        rval = event.ReturnValue(append_events=[evt])
        rval2 = event.ReturnValue(eat=True, schedule={coro})
        rval3 = event.ReturnValue(append_events=[evt], insert_events=[evt],
                                  schedule={coro, coro2})

        rset = event.ResultSet()
        rset2 = event.ResultSet()

        rset.extend(rval)
        assert not rset.eat
        assert rset.append_events == [evt]
        rset.extend(rval2)
        assert rset.eat
        assert rset.schedule == {coro}
        rset2.extend(rval3)
        rset.extend(rset2)
        rset.extend(None)
        assert rset.eat
        assert rset.append_events == [evt, evt]
        assert rset.insert_events == [evt]
        assert rset.schedule == {coro, coro2}

    def test_iadd(self, evt):
        rval = event.ReturnValue(append_events=[evt])
        rval2 = event.ReturnValue(eat=True, append_events=[evt])
        rset = event.ResultSet()

        rset += rval
        rset += rval2
        rset += None
        assert rset.eat
        assert rset.append_events == [evt, evt]

    def test_type(self):
        rset = event.ResultSet()
        with pytest.raises(NotImplementedError):
            rset.extend([])
        with pytest.raises(NotImplementedError):
            rset.extend(False)


class TestEventDispatcher:

    @pytest.fixture
    def dispatcher(self):
        return event.EventDispatcher()

    def test_register(self, dispatcher):
        name = "some_name"

        @event.event(name)
        async def corofunc(*args):
            return True

        h_inst = event.HandlerInstance.from_handler(corofunc)
        dispatcher.register(h_inst)
        assert h_inst in dispatcher.event_map["some_name"]

    def test_register_plugin(self, dispatcher):
        name = "some_name"

        class AClass:
            @event.event(name)
            def handler(self):
                pass

            @event.event(name)
            async def hander(self):
                pass

        obj = AClass()
        h_insts = dispatcher.register_plugin(obj)
        assert len(dispatcher.event_map) == 1
        assert len(h_insts) == 2
        for h_inst in h_insts:
            assert h_inst in dispatcher.event_map[name]

    def test_dispatch(self, dispatcher, loop):
        name = "some_name"
        args = dict(zip(map(str, range(10)), range(10, 20)))
        called = 0

        @event.event(name)
        async def corofunc(**local_args):
            nonlocal called
            assert local_args == args
            called += 1

        h_inst = event.HandlerInstance.from_handler(corofunc)
        dispatcher.register(h_inst)
        evt = event.Event(name, args)
        evt2 = evt._replace(name=evt.name + "_")
        loop.run_until_complete(dispatcher.dispatch(evt))
        loop.run_until_complete(dispatcher.dispatch(evt2))

        assert called == 1

    def test_dispatch_priority(self, dispatcher, loop, evt):
        called = list()

        @event.event(evt.name, priority=0)
        async def corofunc():
            called.append(corofunc)

        @event.event(evt.name, priority=1)
        def corofunc2():
            called.append(corofunc2)

        h_inst = event.HandlerInstance.from_handler(corofunc)
        h_inst2 = event.HandlerInstance.from_handler(corofunc2)
        dispatcher.register(h_inst)
        dispatcher.register(h_inst2)
        loop.run_until_complete(dispatcher.dispatch(evt))

        assert called == [corofunc2, corofunc]

    def test_dispatch_disabled(self, dispatcher, loop, evt):
        called = 0

        @event.event(evt.name, enable=False)
        async def corofunc():
            nonlocal called
            called += 1

        h_inst = event.HandlerInstance.from_handler(corofunc)
        dispatcher.register(h_inst)
        loop.run_until_complete(dispatcher.dispatch(evt))
        assert called == 0

    # TODO test disabled

    def test_dispatch_exception(self, loop, evt):
        logger = mock.Mock(Logger)
        dispatcher = event.EventDispatcher(logger=logger)
        called = 0

        @event.event(evt.name)
        async def corofunc():
            nonlocal called
            called += 1
            raise ValueError("yeah async")

        @event.event(evt.name)
        def handler():
            nonlocal called
            called += 1
            raise ValueError("yeah sync")

        dispatcher.register(event.HandlerInstance.from_handler(corofunc))
        dispatcher.register(event.HandlerInstance.from_handler(handler))
        assert not logger.exception.called
        loop.run_until_complete(dispatcher.dispatch(evt))
        assert called == 2
        assert logger.exception.call_count == 2

    def test_dispatch_unknown_return(self, loop, evt):
        logger = mock.Mock(Logger)
        dispatcher = event.EventDispatcher(logger=logger)
        called = False

        @event.event(evt.name)
        async def corofunc():
            nonlocal called
            called = True
            return "some arbitrary value"

        dispatcher.register(event.HandlerInstance.from_handler(corofunc))
        assert not logger.warning.called
        loop.run_until_complete(dispatcher.dispatch(evt))
        assert called
        assert logger.warning.call_count == 1

    def test_dispatch_eat(self, loop, evt):
        dispatcher = event.EventDispatcher()
        called = [False] * 3

        @event.event(evt.name, priority=1)
        def corofunc():
            called[0] = True

        @event.event(evt.name, priority=0)
        async def corofunc2():
            called[1] = True
            return event.ReturnValue(eat=True)

        @event.event(evt.name, priority=-1)
        async def corofunc3():
            called[2] = True

        dispatcher.register(event.HandlerInstance.from_handler(corofunc))
        dispatcher.register(event.HandlerInstance.from_handler(corofunc2))
        dispatcher.register(event.HandlerInstance.from_handler(corofunc3))
        result = loop.run_until_complete(dispatcher.dispatch(evt))
        assert result.eat
        assert called == [True, True, False]

    def test_dispatch_nested_insert(self, loop, evt):
        dispatcher = event.EventDispatcher()
        called = [0] * 3
        evt1 = evt
        evt2 = evt._replace(name=evt.name + "_")
        evt3 = evt._replace(name=evt.name + "__")

        @event.event(evt.name)
        def corofunc1():
            called[0] += 1
            return event.ReturnValue(insert_events=[evt2], append_events=[evt])

        @event.event(evt2.name)
        def corofunc2():
            called[1] += 1
            return event.ReturnValue(insert_events=[evt3], append_events=[evt2])

        @event.event(evt3.name)
        def corofunc3():
            called[2] += 1

            async def corofunc():
                pass

            return event.ReturnValue(append_events=[evt3], schedule={corofunc()})

        dispatcher.register(event.HandlerInstance.from_handler(corofunc1))
        dispatcher.register(event.HandlerInstance.from_handler(corofunc2))
        dispatcher.register(event.HandlerInstance.from_handler(corofunc3))
        result = loop.run_until_complete(dispatcher.dispatch(evt))
        assert called == [1, 1, 1]
        assert result.append_events == [evt1, evt2, evt3]
        assert len(result.schedule) == 1
        # prevent warnings again
        loop.run_until_complete(next(iter(result.schedule)))

    # TODO other ReturnValue tests
