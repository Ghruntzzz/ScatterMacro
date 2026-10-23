import unittest
from python_macro.session_stats import WaveTotals


class WaveTotalsTests(unittest.TestCase):
    def test_accumulates_across_runs_without_duplicate_scans(self):
        stats = WaveTotals()
        for wave in (0,1,1,2,2,5,5):
            stats.observe((wave,15))
        self.assertEqual(stats.total,4)
        stats.start_run()
        stats.observe((3,15))
        self.assertEqual(stats.total,6)

    def test_zero_reset_and_missing_or_regressing_reads(self):
        stats = WaveTotals()
        stats.observe((6,15))
        stats.observe(None)
        stats.observe((4,15))
        stats.observe((6,15))
        self.assertEqual(stats.total,5)
        stats.observe((0,15))
        stats.observe((3,15))
        self.assertEqual(stats.total,7)

    def test_final_wave_requires_explicit_completion(self):
        stats=WaveTotals()
        stats.observe((15,15))
        self.assertEqual(stats.total,14)
        self.assertEqual(stats.finish_run(),15)
        self.assertEqual(stats.finish_run(),15)
