import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from ui import dashboard


class DashboardSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.config = Path(self.folder.name) / "dashboard_config.ini"
        self.override = patch.object(dashboard, "CONFIG_PATH", self.config)
        self.override.start()
        dashboard.update_config("Dashboard", {"Mode": "Expeditions", "Map": "School Grounds", "ExpeditionDifficulty": "3"})

    def tearDown(self):
        self.override.stop()
        self.folder.cleanup()

    def test_route_and_urls_persist_without_automation(self):
        window = dashboard.DashboardWindow()
        with patch.object(dashboard, "send_command") as command:
            window.map_box.setCurrentText("Flower Forest")
            window.difficulty_box.setCurrentText("2")
            window.private_server.setText("https://example.com/?code=a%20b")
            window._start_macro()
            command.assert_not_called()
        values = dashboard.read_dashboard_values()
        self.assertEqual(values["map"], "Flower Forest")
        self.assertEqual(values["difficulty"], "2")
        self.assertIn("%20", values["private_server"])
        window.close()

    def test_setup_unit_slots_are_zero_through_six(self):
        values = dashboard.read_dashboard_values()
        dialog = dashboard.UnitSetupDialog(values)
        unit = dialog.table.cellWidget(0, 0)
        self.assertEqual([unit.itemText(i) for i in range(unit.count())],
                         [str(i) for i in range(7)])
        unit.setCurrentText("6")
        dialog.save()
        self.assertEqual(dashboard.load_unit_indexes(values)[0]["unit"], "6")

    def test_unit_indexes_saved_only_for_selected_route(self):
        values = dashboard.read_dashboard_values()
        dialog = dashboard.UnitSetupDialog(values)
        dialog.table.cellWidget(0, 0).setCurrentText("2")
        dialog.table.cellWidget(0, 1).setCurrentText("Weakest")
        dialog.table.cellWidget(0, 4).setValue(300)
        dialog.table.cellWidget(0, 5).setValue(200)
        dialog.save()
        index = dashboard.load_unit_indexes(values)[0]
        self.assertEqual((index["unit"], index["priority"], index["x"], index["y"]), ("2", "Weakest", "300", "200"))
        self.assertEqual(dashboard.load_unit_indexes(dict(values, map="Flower Forest"))[0]["unit"], "0")

    def test_runtime_has_no_play_click_diagnostics(self):
        from PySide6.QtWidgets import QPushButton
        window = dashboard.RuntimeWindow()
        try:
            texts = [button.text() for button in window.findChildren(QPushButton)]
            self.assertNotIn("TEST PLAY CLICK METHODS", texts)
            self.assertFalse(hasattr(window, "test_clicks_button"))
            self.assertFalse(hasattr(window, "_test_play_clicks"))
        finally:
            window.close()

    def test_runtime_has_no_stop_button_but_keeps_stop_hotkey_hint(self):
        from PySide6.QtWidgets import QPushButton, QLabel
        window = dashboard.RuntimeWindow()
        try:
            buttons = [button.text() for button in window.findChildren(QPushButton)]
            labels = [label.text() for label in window.findChildren(QLabel)]
            self.assertNotIn("STOP (F2)", buttons)
            self.assertIn("RETURN TO DASHBOARD", buttons)
            self.assertIn("F1: START   |   F2: STOP", labels)
            self.assertEqual(window.viewport_rect.height(), 860)
            self.assertEqual(window.viewport_rect.top(), 60)
            self.assertEqual(window.viewport_rect.bottom(), 919)
            self.assertEqual(window.viewport_rect.width(), 1060)
        finally:
            window.close()

    def test_session_stats_replace_header_and_compact_action_output(self):
        from PySide6.QtWidgets import QLabel
        window = dashboard.RuntimeWindow()
        try:
            labels = [label.text() for label in window.findChildren(QLabel)]
            self.assertIn("SESSION STATS", labels)
            self.assertIn("ACTION OUTPUT", labels)
            self.assertNotIn("MACRO RUNTIME", labels)
            self.assertEqual(set(window.stat_values),
                             {"TOTAL", "RUNS", "AVG RUN", "CURRENT RUN"})
            self.assertEqual((window.log.parentWidget().x(), window.log.parentWidget().y()), (18, 406))
            self.assertLess(window.log.height(), 430)
            self.assertEqual(window.index_editor.height(), 894)
        finally:
            window.close()

    def test_place_at_wave_persists_on_selected_route(self):
        values = dashboard.read_dashboard_values()
        dialog = dashboard.UnitSetupDialog(values)
        self.assertEqual(dialog.table.columnCount(), 7)
        wave = dialog.table.cellWidget(0, 6)
        wave.setText("9")
        dialog.save()
        entry = dashboard.load_unit_indexes(values)[0]
        self.assertEqual(entry["place_at_wave"], "9")
        self.assertEqual(dashboard.load_unit_indexes(dict(values, map="Flower Forest"))[0]["place_at_wave"], "")

    def test_runtime_retries_alignment_after_opening_without_moving(self):
        from unittest.mock import Mock
        window = dashboard.RuntimeWindow()
        window.show()
        try:
            window._embed_timer.stop()
            window._publish_viewport = Mock(side_effect=[False] * 2 + [True] * 8)
            window._embed_attempts = 0
            window._embed_successes = 0
            for _ in range(10):
                window._align_on_launch()
            self.assertEqual(window._publish_viewport.call_count, 10)
            self.assertEqual(window._embed_successes, 8)
            self.assertFalse(window._embed_timer.isActive())
        finally:
            window.close()
