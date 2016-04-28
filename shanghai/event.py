

class Event:
    """Sample Event class

    Carry an event name/typo and the message if available."""
    # TODO: Move this class into it's own file later
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __repr__(self):
        if self.value:
            return 'Event({!r}, {!r})'.format(self.name, self.value)
        return 'Event({!r})'.format(self.name)
