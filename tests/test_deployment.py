import unittest
from python_macro.deployment import requested_wave, eligible_unit_indexes


def index(slot="1", x="15", y="25", wave=""):
    return {"unit": slot, "x": x, "y": y, "place_at_wave": wave}


class WaveGatingTests(unittest.TestCase):
    def test_blank_is_immediate_and_waves_require_positive_integer(self):
        self.assertIsNone(requested_wave(""))
        self.assertEqual(requested_wave("10"), 10)
        self.assertEqual(requested_wave("9999"), 9999)
        for invalid in ("0", "-1", "1.5", "10000", "hello", "١", "1e3"):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                requested_wave(invalid)

    def test_skip_future_wave_but_continue_other_indexes(self):
        entries = [index(wave="5"), index(wave=""), index(wave="3"),
                   index(slot="0"), index(x=""), index(wave="2")]
        self.assertEqual(eligible_unit_indexes(entries, 1), [1])
        self.assertEqual(eligible_unit_indexes(entries, 2, {1}), [5])
        self.assertEqual(eligible_unit_indexes(entries, 3, {1, 5}), [2])
        self.assertEqual(eligible_unit_indexes(entries, 5, {1, 2, 5}), [0])
        self.assertEqual(eligible_unit_indexes(entries, 10, {0, 1, 2, 5}), [])

    def test_failed_placement_stays_ready(self):
        entries = [index(wave="6")]
        self.assertEqual(eligible_unit_indexes(entries, 6), [0])
        self.assertEqual(eligible_unit_indexes(entries, 7), [0])
        self.assertEqual(eligible_unit_indexes(entries, 7, {0}), [])

    def test_invalid_observed_wave_is_rejected(self):
        with self.assertRaises(ValueError):
            eligible_unit_indexes([index()], 0)
