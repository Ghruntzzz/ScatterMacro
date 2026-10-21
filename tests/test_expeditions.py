from pathlib import Path
from unittest.mock import Mock,patch
import unittest
import cv2
import numpy as np

from python_macro.expeditions import ExpeditionFlow
from test_challenges import label
from test_unit_actions import FastStop


class ExpeditionTests(unittest.TestCase):
    def flow(self,difficulty='1'):
        return ExpeditionFlow(Mock(),Mock(),Mock(),FastStop(),Mock(),Path('assets'),'East Town',difficulty)

    def test_map_and_difficulty_validation(self):
        for name,difficulty in [('Unknown','1'),('East Town','4')]:
            with self.assertRaises(ValueError):
                ExpeditionFlow(Mock(),Mock(),Mock(),FastStop(),Mock(),Path('assets'),name,difficulty)

    def test_navigation_reuses_stage_and_start(self):
        flow=self.flow()
        flow.press=Mock(return_value=True)
        flow.set_difficulty=Mock(return_value=True)
        self.assertTrue(flow.navigate(Mock()))
        self.assertEqual([c.args[0] for c in flow.press.call_args_list],
                         ['Play','Expedition','East Town','Select Stage','Start'])

    def test_difficulty_steps_both_directions(self):
        for initial,target in [(1,3),(3,1),(2,2)]:
            flow=self.flow(str(target))
            value=[initial]
            flow.difficulty_reading=Mock(side_effect=lambda f:(value[0],(115,64)))
            flow.plus=Mock(return_value=(192,53,43,42))
            flow.minus=Mock(return_value=(38,53,42,42))
            frame=np.zeros((92,234,3),np.uint8)
            flow.capture.return_value=frame
            def press(name,locate,advanced):
                self.assertEqual(locate(frame),(192,53) if value[0]<target else (38,53))
                value[0]+=1 if value[0]<target else -1
                self.assertTrue(advanced(frame,frame))
                return True
            flow.press=Mock(side_effect=press)
            self.assertTrue(flow.set_difficulty())
            self.assertEqual(flow.press.call_count,abs(target-initial))

    def test_unreadable_difficulty_does_not_click(self):
        flow=self.flow()
        flow.difficulty_reading=Mock(return_value=None)
        with self.assertRaises(RuntimeError):
            flow.set_difficulty()
        flow.client.direct_click.assert_not_called()

    def test_continue_waits_for_unit_setup_and_never_uses_cancel(self):
        flow=self.flow()
        frame=np.zeros((160,400,3),np.uint8)
        flow.capture.return_value=frame
        flow.game_start=Mock(return_value=None)
        flow.confirm=Mock(return_value=(150,60))
        flow.reader.read.return_value=[label('Continue',0,90),label('Cancel',200,90)]
        indexer=Mock()
        indexer.all_done.return_value=False
        flow.service(indexer)
        flow.client.direct_click.assert_not_called()
        indexer.all_done.return_value=True
        flow.last_service=0
        flow.service(indexer)
        flow.client.direct_click.assert_called_once_with(80,98,frame.shape)

    def test_start_game_is_serviced_during_unit_setup(self):
        flow=self.flow()
        frame=np.zeros((160,400,3),np.uint8)
        flow.capture.return_value=frame
        flow.game_start=Mock(return_value=(100,100))
        flow.service(Mock())
        flow.client.direct_click.assert_called_once_with(100,100,frame.shape)

    def test_return_to_spawn_clicks_small_icon_then_closes_settings(self):
        flow=self.flow()
        frame=cv2.imread('assets/expedition-teleport-row.png')
        flow.capture.return_value=frame
        flow.press=Mock(return_value=True)
        with patch('python_macro.story_verified.click_once') as click:
            click.side_effect=lambda name,locate,*args: self.assertGreater(locate(frame)[0],230) or True
            self.assertTrue(flow.return_to_payload())
        self.assertEqual([c.args[0] for c in flow.press.call_args_list],['Settings','Close Settings'])
        self.assertEqual(click.call_args.args[0],'Teleport To Spawn')
