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

    def test_jump_and_copy_paste_between_pages(self):
        self.widget.select(4)
        self.widget.fields["unit"].setCurrentText("4")
        self.widget.fields["upgrade"].setValue(6)
        self.widget.copy_index()
        self.widget.index_picker.setValue(104)
        self.assertEqual(self.widget.selected, 103)
        self.assertEqual(self.widget.page_indicator.text(), "PAGE 18 / 18")
        self.widget.paste_index()
        self.assertEqual(self.entries[103]["unit"], "4")
        self.assertEqual(self.entries[103]["upgrade"], "6")
        self.assertEqual(self.entries[4]["unit"], "4")

    def test_clear_position_keeps_upgrade_and_busy_prevents_paste(self):
        self.widget.fields["unit"].setCurrentText("2")
        self.widget.fields["upgrade"].setValue(5)
        self.widget.fields["x"].setValue(0)
        self.widget.fields["y"].setValue(50)
        self.widget.clear_position()
        self.assertEqual(self.entries[0]["x"], "")
        self.assertEqual(self.entries[0]["y"], "")
        self.assertEqual(self.entries[0]["upgrade"], "5")
        self.widget.copy_index()
        self.widget.select(2)
        self.busy.return_value = True
        self.widget.paste_index()
        self.assertEqual(self.entries[2]["unit"], "None")

    def test_cards_select_real_index_and_show_coordinates_at_zero(self):
        self.widget.fields["x"].setValue(0)
        self.widget.fields["y"].setValue(90)
        self.assertIn("POS  0, 90", self.widget.cards[0].text())
        self.widget.cards[5].click()
        self.assertEqual(self.widget.selected, 5)
        self.assertEqual(self.widget.index_picker.value(), 6)

    def test_modern_panel_keeps_index_selection(self):
        self.assertEqual(self.widget.editor_card.objectName(), "editor-card")
        self.assertEqual(self.widget.heading.text(), "Index 001")
        self.assertEqual(self.widget.cards[0].property("selected"), True)
        self.widget.cards[4].click()
        self.assertEqual(self.widget.heading.text(), "Index 005")
        self.assertEqual(self.widget.selected, 4)

    def test_save_failure_restores_values(self):
        self.save.side_effect = OSError('locked')
        self.widget.fields['upgrade'].setValue(4)
        self.assertEqual(self.entries[0]['upgrade'], '0')
        self.assertEqual(self.widget.fields['upgrade'].value(), 0)
