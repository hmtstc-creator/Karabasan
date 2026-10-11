class IStrategy:
    INTERFACE_VERSION = 3
    # Gerçek motorda veri sağlayıcı (DataProvider) bot açılırken buraya konur.
    dp = None

    def __init__(self, config=None):
        self.config = config or {}

    def informative_pairs(self):
        return []
