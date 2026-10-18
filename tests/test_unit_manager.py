import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication
from ui.unit_manager import UnitManager


class UnitManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.entries = [dict(unit="None", priority="First", upgrade="0", auto_upgrade="0", x="", y="") for _ in range(104)]
        self.save, self.busy = Mock(), Mock(return_value=False)
        self.widget = UnitManager(self.entries, self.save, self.busy, Mock())

    def tearDown(self):
        self.widget.close()

    def test_edits_only_selected_index(self):
        self.widget.select(7)
        self.widget.fields['unit'].setCurrentText('3')
        self.assertEqual(self.save.call_args.args[0], 7)
        self.assertEqual(self.entries[7]['unit'], '3')
        self.assertEqual(self.entries[0]['unit'], 'None')

    def test_busy_prevents_save(self):
        self.busy.return_value = True
        self.widget.fields['upgrade'].setValue(5)
        self.save.assert_not_called()
        self.assertEqual(self.widget.fields['upgrade'].value(), 0)

    def test_last_page_and_clear(self):
        self.widget.select(103)
        self.assertFalse(self.widget.next.isEnabled())
        self.widget.fields['x'].setValue(0)
        self.widget.fields['y'].setValue(100)
        self.assertEqual(self.entries[103]['x'], '0')
        self.widget.clear_index()
        self.assertEqual(self.entries[103]['x'], '')

    def test_save_failure_restores_values(self):
        self.save.side_effect = OSError('locked')
        self.widget.fields['upgrade'].setValue(4)
        self.assertEqual(self.entries[0]['upgrade'], '0')
        self.assertEqual(self.widget.fields['upgrade'].value(), 0)
