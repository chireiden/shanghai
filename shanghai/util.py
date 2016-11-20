
import functools


class ShadowAttributesMixin:

    """Mixin class that allows to add (and set) attributes without collisions.

    Supports instance and class attributes.
    """

    # classattributes
    _added_cls_attributes = dict()
    _added_cls_methods = set()

    def __init__(self, *args, **kwargs):
        self._added_attributes = dict()

        super().__init__(*args, **kwargs)

    def add_attribute(self, name, value=None):
        """Allows for plugins to add attributes to the network object.

        Use this instead of directly setting attributes (or with `setattr`).
        For adding methods, use add_method.
        """
        if hasattr(self, name) or name in self._added_attributes:
            raise KeyError("Attribute '{}' is already defined".format(name))
        self._added_attributes[name] = value

    def set_attribute(self, name, value=None):
        """Allows for plugins to modify their added attributes to the network object."""
        if name not in self._added_attributes:
            raise KeyError("Attribute '{}' is not defined; {}".format(name))
        self._added_attributes[name] = value

    def remove_attribute(self, name):
        """Allows for plugins to remove their added attributes to the network object."""
        if name not in self._added_attributes:
            raise KeyError("Attribute '{}' is not defined".format(name))
        del self._added_attributes[name]

    @classmethod
    def add_cls_attribute(cls, name, value=None):
        """Allows for plugins to add attributes to the network class.

        Use this instead of directly setting attributes (or with `setattr`).
        For adding methods, use add_method.
        """
        if hasattr(cls, name) or name in cls._added_cls_attributes:
            raise KeyError("Attribute '{}' is already defined".format(name))
        cls._added_cls_attributes[name] = value

    @classmethod
    def set_cls_attribute(cls, name, value=None):
        """Allows for plugins to modify their added attributes to the network class."""
        if name not in cls._added_cls_attributes:
            raise KeyError("Attribute '{}' is not defined".format(name))
        cls._added_cls_attributes[name] = value

    @classmethod
    def add_cls_method(cls, name, method):
        """Allows for plugins to add methods to the network class.

        Use this instead of directly setting attributes (or with `setattr`).
        """
        if not callable(method):
            raise ValueError("Not callable")

        cls.add_cls_attribute(name, method)
        cls._added_cls_methods.add(name)

    @classmethod
    def remove_cls_attribute(cls, name, value):
        """Allows for plugins to remove their added attributes to the network class."""
        if name not in cls._added_cls_attributes:
            raise KeyError("Attribute '{}' is not defined".format(name))
        del cls._added_cls_attributes[name]

    def __getattr__(self, name):
        if name in self._added_attributes:
            attr = self._added_attributes[name]
            if name in self.added_methods:
                # Wrap callable with `self` because it would be missing otherwise.
                return functools.partial(attr, self)
            else:
                return attr
        elif name in self._added_cls_attributes:
            attr = self._added_cls_attributes[name]
            if name in self._added_cls_methods:
                return functools.partial(attr, self)
            else:
                return attr
        else:
            super().__getattr__(name)
