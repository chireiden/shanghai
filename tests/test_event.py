
import unittest

from shanghai import event


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

