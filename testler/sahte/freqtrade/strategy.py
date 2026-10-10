class IStrategy:
    INTERFACE_VERSION = 3

    def __init__(self, config=None):
        self.config = config or {}
