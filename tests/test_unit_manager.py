import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication, QAbstractSpinBox, QComboBox, QSpinBox
from ui.unit_manager import UnitManager, PositionImage, configured_positions
import numpy as np


class UnitManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.entries = [dict(unit="0", priority="First", upgrade="0", auto_upgrade="0", x="", y="") for _ in range(104)]
        self.save, self.busy = Mock(), Mock(return_value=False)
        self.widget = UnitManager(self.entries, self.save, self.busy, Mock())

    def tearDown(self):
        self.widget.close()

    def test_unit_slot_range_zero_through_six(self):
        picker = self.widget.fields["unit"]
        self.assertEqual([picker.itemText(i) for i in range(picker.count())],
                         [str(i) for i in range(7)])
        self.assertEqual(picker.currentText(), "0")
        picker.setCurrentText("6")
        self.assertEqual(self.entries[0]["unit"], "6")
        self.widget.clear_index()
        self.assertEqual(self.entries[0]["unit"], "0")

    def test_legacy_none_and_prefixed_slots_load_as_valid_choices(self):
        self.entries[7]["unit"] = "None"
        self.widget.select(7)
        self.assertEqual(self.widget.fields["unit"].currentText(), "0")
        self.entries[8]["unit"] = "Unit 5"
        self.widget.select(8)
        self.assertEqual(self.widget.fields["unit"].currentText(), "5")
        self.assertEqual(self.widget.fields["unit"].count(), 7)
        self.save.assert_not_called()

    def test_edits_only_selected_index(self):
        self.widget.select(7)
        self.widget.fields['unit'].setCurrentText('3')
        self.assertEqual(self.save.call_args.args[0], 7)
        self.assertEqual(self.entries[7]['unit'], '3')
        self.assertEqual(self.entries[0]['unit'], '0')

    def test_busy_prevents_save(self):
        self.busy.return_value = True
        self.widget.fields['upgrade'].setCurrentText('5')
        self.save.assert_not_called()
        self.assertEqual(self.widget.fields['upgrade'].currentText(), '0')

    def test_last_page_and_clear(self):
        self.widget.select(103)
        self.assertFalse(self.widget.next.isEnabled())
        self.widget.fields['x'].setValue(0)
        self.widget.fields['y'].setValue(100)
        self.assertEqual(self.entries[103]['x'], '0')
        self.widget.clear_index()
        self.assertEqual(self.entries[103]['x'], '')

    def test_copy_paste_between_pages(self):
        self.widget.select(4)
        self.widget.fields["unit"].setCurrentText("4")
        self.widget.fields["upgrade"].setCurrentText("6")
        self.widget.copy_index()
        self.widget.select(103)
        self.assertEqual(self.widget.selected, 103)
        self.assertEqual(self.widget.page_indicator.text(), "PAGE 18 / 18")
        self.widget.paste_index()
        self.assertEqual(self.entries[103]["unit"], "4")
        self.assertEqual(self.entries[103]["upgrade"], "6")
        self.assertEqual(self.entries[4]["unit"], "4")

    def test_clear_position_keeps_upgrade_and_busy_prevents_paste(self):
        self.widget.fields["unit"].setCurrentText("2")
        self.widget.fields["upgrade"].setCurrentText("5")
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
        self.assertEqual(self.entries[2]["unit"], "0")

    def test_cards_select_real_index_and_show_coordinates_at_zero(self):
        self.widget.fields["x"].setValue(0)
        self.widget.fields["y"].setValue(90)
        self.assertIn("POS  0, 90", self.widget.cards[0].text())
        self.widget.cards[5].click()
        self.assertEqual(self.widget.selected, 5)
        self.assertEqual(self.widget.heading.text(), 'Index 006')

    def test_modern_panel_keeps_index_selection(self):
        self.assertEqual(self.widget.editor_card.objectName(), "editor-card")
        self.assertEqual(self.widget.heading.text(), "Index 001")
        self.assertEqual(self.widget.cards[0].property("selected"), True)
        self.widget.cards[4].click()
        self.assertEqual(self.widget.heading.text(), "Index 005")
        self.assertEqual(self.widget.selected, 4)

    def test_save_failure_restores_values(self):
        self.save.side_effect = OSError('locked')
        self.widget.fields['upgrade'].setCurrentText('4')
        self.assertEqual(self.entries[0]['upgrade'], '0')
        self.assertEqual(self.widget.fields['upgrade'].currentText(), '0')

    def test_position_fields_no_arrows_and_jump_removed(self):
        self.assertFalse(hasattr(self.widget, "index_picker"))
        for key in ("x", "y"):
            self.assertIsInstance(self.widget.fields[key], QSpinBox)
            self.assertEqual(self.widget.fields[key].buttonSymbols(), QAbstractSpinBox.NoButtons)

    def test_upgrade_dropdowns_save_values(self):
        for key in ("upgrade", "auto_upgrade"):
            self.assertIsInstance(self.widget.fields[key], QComboBox)
        self.assertEqual(self.widget.fields["upgrade"].itemText(15), "15")
        self.assertEqual(self.widget.fields["auto_upgrade"].itemText(6), "6")
        self.widget.fields["auto_upgrade"].setCurrentText("4")
        self.assertEqual(self.entries[0]["auto_upgrade"], "4")

    def test_existing_high_upgrade_levels_are_preserved(self):
        self.entries[9]["upgrade"] = "22"
        self.entries[9]["auto_upgrade"] = "9"
        self.widget.select(9)
        self.assertEqual(self.widget.fields["upgrade"].currentText(), "22")
        self.assertEqual(self.widget.fields["auto_upgrade"].currentText(), "9")
        self.save.assert_not_called()

    def test_saved_position_markers_include_zero_and_skip_invalid(self):
        entries = [dict(x="", y=""), dict(x="0", y="90"), dict(x="30", y="45"),
                   dict(x="5000", y="10"), dict(x="abc", y="40")]
        expected = [(2, 0, 90), (3, 30, 45)]
        self.assertEqual(configured_positions(entries, 100, 100), expected)
        image = PositionImage(np.zeros((100, 100, 4), dtype=np.uint8),
                              entries, selected=1, read_only=True)
        self.assertEqual(image.markers, expected)
        self.assertTrue(image.read_only)
        self.assertFalse(image.pixmap().isNull())

    def test_place_at_wave_matches_other_editor_fields(self):
        from PySide6.QtWidgets import QLineEdit
        field = self.widget.wave_input
        self.assertIsInstance(field, QLineEdit)
        self.assertEqual(field.objectName(), "place-at-wave")
        self.assertEqual(field.maximumWidth(), 16777215)
        stylesheet = self.widget.styleSheet()
        self.assertIn("QComboBox,QSpinBox,QLineEdit {", stylesheet)
        self.assertIn("QComboBox:focus,QSpinBox:focus,QLineEdit:focus", stylesheet)
        self.widget.resize(403, 794)
        self.widget.show()
        QApplication.processEvents()
        # The wave field occupies the same form column as other controls.
        self.assertEqual(field.width(), self.widget.fields["unit"].width())
        self.assertEqual(field.height(), self.widget.fields["unit"].height())

    def test_place_at_wave_textbox_saves_and_appears_on_cards(self):
        from PySide6.QtWidgets import QLineEdit
        self.assertIsInstance(self.widget.fields["place_at_wave"], QLineEdit)
        self.widget.wave_input.setText("12")
        self.widget.wave_input.editingFinished.emit()
        self.assertEqual(self.entries[0]["place_at_wave"], "12")
        self.assertEqual(self.save.call_args.args[1]["place_at_wave"], "12")
        self.assertIn("Wave 12", self.widget.cards[0].text())
        self.widget.copy_index()
        self.widget.select(3)
        self.widget.paste_index()
        self.assertEqual(self.entries[3]["place_at_wave"], "12")
        self.widget.clear_index()
        self.assertEqual(self.entries[3]["place_at_wave"], "")

    def test_blank_wave_is_immediate_and_legacy_rows_read_empty(self):
        self.assertEqual(self.widget.wave_input.text(), "")
        self.assertIn("Any wave", self.widget.cards[0].text())
        self.widget.select(7)
        self.assertEqual(self.widget.wave_input.text(), "")
        self.widget.wave_input.setText("5")
        self.widget.wave_input.editingFinished.emit()
        self.assertEqual(self.entries[7]["place_at_wave"], "5")
