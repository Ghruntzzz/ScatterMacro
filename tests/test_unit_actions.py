from pathlib import Path
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import cv2
import numpy as np

from python_macro.unit_actions import UnitIndexer, Icon, priority_value, upgrade_value


class FastStop(Event):
    def wait(self, seconds=None):
        return self.is_set()


def entry(**changes):
    return {"unit":"1", "x":"20", "y":"30", "priority":"Last",
            "auto_upgrade":"2", "upgrade":"2", "place_at_wave":"", **changes}


class UnitActionTests(unittest.TestCase):
    def test_priority_and_upgrades_are_unambiguous(self):
        self.assertEqual(priority_value(["Priority", "First"]), "First")
        self.assertEqual(priority_value(["Priority Last"]), "Last")
        self.assertEqual(priority_value(["Priority", "None"]), "None")
        self.assertEqual(priority_value(["Priority None"]), "None")
        self.assertIsNone(priority_value([]))
        self.assertIsNone(priority_value(["None", "First"]))
        self.assertIsNone(priority_value(["First", "Last"]))
        self.assertIsNone(priority_value(["F1rst"]))
        self.assertEqual(upgrade_value(["Upgrade 0/7"]), (0,7))
        self.assertEqual(upgrade_value(["Upgrade 5/7"]), (5,7))
        self.assertEqual(upgrade_value(["Maxed"]), "max")
        self.assertIsNone(upgrade_value(["Upgrade O/7"]))
        self.assertIsNone(upgrade_value(["Upgrade 8/7"]))
        self.assertIsNone(upgrade_value(["Upgrade 1/7", "Upgrade 2/7"]))

    def test_strict_numerical_wave_order(self):
        entries = [entry(place_at_wave="5"), entry(place_at_wave="1")]
        worker = UnitIndexer(entries, None, None, None, FastStop(), Mock())
        self.assertIsNone(worker.next_ready(1))
        self.assertEqual(worker.next_ready(5), 0)
        worker.completed.add(0)
        self.assertEqual(worker.next_ready(5), 1)
        worker.completed.add(1)
        self.assertIsNone(worker.next_ready(5))

    def test_blank_wave_does_not_require_ocr(self):
        worker = UnitIndexer([entry()], None, None, None, FastStop(), Mock())
        self.assertEqual(worker.next_ready(None), 0)

    def test_action_order_exact_auto_count_and_max_level(self):
        for auto, goal in ((0,0), (2,2), (5,5)):
            with self.subTest(auto=auto, goal=goal):
                stop = FastStop()
                events, state = [], {"panel":False, "priority":"First", "level":0}
                image = np.zeros((100,100,3),np.uint8)
                def read(frame, **kwargs):
                    if not state["panel"]:
                        return None
                    return {"priority":state["priority"], "upgrade":(state["level"],3), "close":(80,10)}
                def click(x,y,shape):
                    if (x,y)==(20,30):
                        events.append("place")
                        state["panel"]=True
                    elif (x,y)==(50,50):
                        events.append("auto")
                    elif (x,y)==(80,10):
                        events.append("close")
                        state["panel"]=False
                    return True
                def key(value,seconds):
                    events.append(value)
                    if value=="R": state["priority"]="Last"
                    if value=="T": state["level"]+=1
                    return True
                client=SimpleNamespace(direct_click=click, hold_key=key)
                panel=SimpleNamespace(read=read, auto_position=lambda frame,panel:(50,50),
                                      close_icon=lambda frame:(80,10) if state["panel"] else None)
                worker=UnitIndexer([entry(auto_upgrade=str(auto),upgrade=str(goal))],client,
                                   lambda:image,panel,stop,Mock())
                worker.run(0)
                self.assertEqual(events,["1","place","R"]+["K"]*auto+["T"]*min(goal,3)+["close"])
                self.assertEqual(worker.completed,{0})

    def test_stop_sends_no_input(self):
        stop=FastStop()
        stop.set()
        client=Mock()
        worker=UnitIndexer([entry()],client,Mock(),Mock(),stop,Mock())
        with self.assertRaises(InterruptedError): worker.run(0)
        client.hold_key.assert_not_called()
        client.direct_click.assert_not_called()
        self.assertEqual(worker.completed,set())

    def test_closing_uses_only_images_not_ocr(self):
        image=np.zeros((100,100,3),np.uint8)
        panel=Mock()
        panel.close_icon.side_effect=[(80,10),None,None]
        client=Mock()
        client.direct_click.return_value=True
        worker=UnitIndexer([],client,lambda:image,panel,FastStop(),Mock())
        worker.close()
        panel.read.assert_not_called()
        client.direct_click.assert_called_once_with(80,10,image.shape)

    def test_none_priority_skips_r_but_keeps_auto_and_upgrade(self):
        worker=UnitIndexer([entry()],Mock(),Mock(),Mock(),FastStop(),Mock())
        image=np.zeros((100,100,3),np.uint8)
        panel={"priority":"None", "upgrade":(2,7), "close":(80,10)}
        worker.snapshot=Mock(side_effect=[(image,None),(image,panel)])
        worker.read_until=Mock(return_value=(image,panel))
        worker.close=Mock()
        worker.client.hold_key.return_value=True
        worker.client.direct_click.return_value=True
        worker.run(0)
        self.assertEqual([call.args[0] for call in worker.client.hold_key.call_args_list],
                         ["1","K","K"])
        self.assertEqual(worker.completed,{0})

    def test_icon_detection_rejects_multiple_buttons(self):
        assets=Path(__file__).resolve().parents[1]/"assets"
        for name in ("unit-close.png","unit-auto-upgrade.png"):
            icon=Icon(assets/name)
            tile=cv2.imread(str(assets/name))
            h,w=tile.shape[:2]
            frame=np.zeros((250,400,3),np.uint8)
            frame[40:40+h,40:40+w]=tile
            self.assertIsNotNone(icon(frame))
            frame[140:140+h,240:240+w]=tile
            self.assertIsNone(icon(frame))
