"""Session totals derived from confirmed wave progress, not OCR scan counts."""


class WaveTotals:
    def __init__(self):
        self.total = 0
        self.run_completed = 0
        self.last_wave = None
        self.run_total = None

    def observe(self, wave):
        if wave is None:
            return self.total
        current, maximum = wave
        if not (isinstance(current, int) and isinstance(maximum, int)
                and 0 <= current <= maximum and maximum > 0):
            return self.total
        # A confirmed zero marks a fresh match; stop/start alone does not.
        if current == 0 and self.last_wave not in (None, 0):
            self.run_completed = 0
            self.run_total = maximum
        if self.run_total is None:
            self.run_total = maximum
        if maximum != self.run_total:
            return self.total
        # The displayed wave is in progress. Do not count it as cleared yet.
        completed = max(0, current - 1)
        self.total += max(0, completed - self.run_completed)
        self.run_completed = max(self.run_completed, completed)
        self.last_wave = current
        return self.total

    def start_run(self):
        self.run_completed = 0
        self.last_wave = None
        self.run_total = None

    def finish_run(self):
        """Called only by an authoritative victory event, never Stop or defeat."""
        if self.run_total is not None:
            self.total += max(0, self.run_total - self.run_completed)
            self.run_completed = self.run_total
        return self.total
