class AuditLog:
    def __init__(self):
        self.entries = []

    def record(self, *args, **kwargs):
        self.entries.append({
            "args": args,
            "kwargs": kwargs,
        })

    def log(self, *args, **kwargs):
        self.record(*args, **kwargs)

    def recent(self):
        return list(self.entries)

    def get_entries(self):
        return list(self.entries)

    def clear(self):
        self.entries.clear()
