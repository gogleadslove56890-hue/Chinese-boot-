SUPPORTED_TIMEFRAMES = [
    60,
    300,
    900,
    1800,
    3600,
]

class Scanner:
    def __init__(self, market_provider, audit_log):
        self.market_provider = market_provider
        self.audit_log = audit_log
        self.mode = "manual"
        self.running = False

    @property
    def execution(self):
        return self

    @property
    def available(self):
        return True

    def start(self):
        self.running = True

    def stop(self):
        self.running = False
