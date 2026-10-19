from pathlib import Path
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from python_macro.story_ingame import matches_story, parse_wave, parse_yen, run_story_ingame
from python_macro.input import RobloxClient


class FastStop(Event):
    def wait(self, seconds=None):
        return self.is_set()


class StoryIngameTests(unittest.TestCase):
    def test_camera_and_unit_keys_use_matching_scan_code_down_and_up(self):
        client = RobloxClient.__new__(RobloxClient)
        client.user = Mock()
        packets = []
        def send(count, pointer, size):
            key = pointer._obj.ki
            packets.append((key.wVk, key.wScan, key.dwFlags))
            return 1
        client.user.SendInput.side_effect = send
        for key, scan in (("I",0x17),("O",0x18),("1",2),("2",3),("3",4),
                          ("4",5),("5",6),("6",7),("R",0x13),("T",0x14),("K",0x25)):
            client.user.MapVirtualKeyW.return_value = scan
            client._key(key)
            client._key(key, release=True)
            self.assertEqual(packets[-2:], [(0,scan,8),(0,scan,10)])
        client.user.MapVirtualKeyW.return_value = 0
        count = len(packets)
        with self.assertRaisesRegex(RuntimeError, "could not map"):
            client._key("1")
        self.assertEqual(len(packets), count)

    def test_match_requires_all_selected_details(self):
        found = ["Story East Town - Act 1", "Normal Mode"]
        self.assertTrue(matches_story(found, "East Town", "Act 1", "Normal"))
        self.assertTrue(matches_story(["Story", "EastTown-Act1", "Normal Mod"],
                                      "East Town", "Act 1", "Normal"))
        for map_name, act, difficulty in [("School Grounds", "Act 1", "Normal"),
                                          ("East Town", "Act 2", "Normal"),
                                          ("East Town", "Act 1", "Hard")]:
            self.assertFalse(matches_story(found, map_name, act, difficulty))
        self.assertFalse(matches_story(["Story East Town Act 10", "Normal Mode"],
                                       "East Town", "Act 1", "Normal"))
        self.assertFalse(matches_story(["East Town Act 1", "Normal Mode"],
                                       "East Town", "Act 1", "Normal"))

    def test_readings_do_not_guess_missing_digits(self):
        self.assertEqual(parse_wave(["0 / 15 wave"]), (0,15))
        self.assertEqual(parse_wave(["wave", "12/15"]), (12,15))
        self.assertIsNone(parse_wave(["16/15"]))
        self.assertIsNone(parse_wave(["1/15", "2/15"]))
        self.assertIsNone(parse_wave(["00:00 time"]))
        self.assertEqual(parse_yen(["1,250"]), 1250)
        self.assertIsNone(parse_yen(["6OO"]))
        self.assertIsNone(parse_yen(["600", "800"]))

    def test_hold_releases_key_on_stop_and_focus_loss(self):
        for lose_focus in (False, True):
            client = RobloxClient.__new__(RobloxClient)
            client.stop = Mock()
            client.stop.is_set.return_value = False
            client.stop.wait.return_value = not lose_focus
            client.check_focus = Mock(side_effect=[None, RuntimeError("lost focus")] if lose_focus else None)
            client._key = Mock()
            if lose_focus:
                with self.assertRaises(RuntimeError):
                    client.hold_key("I", 3)
            else:
                self.assertFalse(client.hold_key("I", 3))
            self.assertEqual(client._key.call_args_list[-1].args, ("I",))
            self.assertTrue(client._key.call_args_list[-1].kwargs["release"])

    def test_camera_once_then_start_then_hud_until_stop(self):
        stop = FastStop()
        image = np.zeros((900,1200,3),np.uint8)
        reader = Mock()
        reader.read.return_value = [SimpleNamespace(text=t) for t in
                                    ["Story East Town Act 1", "Normal Mode"]]
        client = Mock()
        client.setup_camera.return_value = True
        client.start_click.return_value = True
        log, readings = Mock(), []
        entries = [{"unit":"1", "x":"5", "y":"5", "place_at_wave":"2"}]
        def status(value):
            if value.get("new_run"):
                return
            readings.append(value)
            if len(readings) == 2:
                stop.set()
        with patch("python_macro.story_ingame.StartButtonLocator") as locator, \
             patch("python_macro.story_ingame.HudReader") as hud, \
             patch("python_macro.story_ingame.UnitIndexer") as indexing, \
             patch("python_macro.story_ingame.UnitPanel"):
            indexing.return_value.next_ready.side_effect = [None, 0]
            locator.return_value.side_effect = [(50,50,0.99), None, None]
            hud.return_value.wave.return_value = (2,15)
            hud.return_value.yen.return_value = 600
            run_story_ingame("East Town","Act 1","Normal", Mock(return_value=image),
                             client, reader, stop, log, Path("assets"), entries, status)
        self.assertEqual(reader.read.call_count, 2)
        client.setup_camera.assert_called_once()
        client.start_click.assert_called_once()
        self.assertEqual(readings[0]["eligible_indexes"], [])
        self.assertEqual(readings[1]["eligible_indexes"], [0])

    def test_camera_order_and_right_button_release(self):
        client = RobloxClient.__new__(RobloxClient)
        client.stop = FastStop()
        client.hold_key = Mock(return_value=True)
        client.capture = Mock(return_value=np.zeros((900,1200,3),np.uint8))
        client._validated_point = Mock(return_value=(SimpleNamespace(x=600,y=450), None))
        client._move = Mock()
        client._send_mouse = Mock()
        client.check_focus = Mock()
        self.assertTrue(client.setup_camera())
        self.assertEqual([call.args for call in client.hold_key.call_args_list], [("I",1),("O",1)])
        self.assertEqual(client._send_mouse.call_args_list[0].args, (0x0008,))
        self.assertEqual(client._send_mouse.call_args_list[-1].args, (0x0010,))
        client.check_focus.side_effect = RuntimeError("lost focus")
        client._send_mouse.reset_mock()
        with self.assertRaises(RuntimeError):
            client.setup_camera()
        self.assertEqual(client._send_mouse.call_args_list[-1].args, (0x0010,))

    def test_stopped_flow_sends_no_camera_or_click_input(self):
        stop = FastStop()
        stop.set()
        client = Mock()
        run_story_ingame("East Town","Act 1","Normal", Mock(), client, Mock(), stop,
                         Mock(), Path("assets"))
        client.setup_camera.assert_not_called()
        client.start_click.assert_not_called()
