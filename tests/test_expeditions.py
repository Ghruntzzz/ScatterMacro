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

    def test_map_click_is_inside_card_not_detail_title(self):
        flow=self.flow()
        flow.map_card=Mock(return_value=(110,100,200,100))
        flow.reader.read.return_value=[label('East Town',20,120),label('East Town',250,30)]
        frame=np.zeros((400,600,3),np.uint8)
        self.assertEqual(flow.map_target(frame),(100,128))
        flow.reader.read.return_value=[label('East Town',250,30)]
        self.assertIsNone(flow.map_target(frame.copy()))
        flow.map_card.return_value=None
        self.assertIsNone(flow.map_target(frame.copy()))

    def test_map_card_references_match_menu(self):
        frame=cv2.imread('tests/fixtures/expedition-map-menu.png')
        for name in ('School Grounds','Flower Forest','Rose Kingdom','East Town'):
            flow=ExpeditionFlow(Mock(),Mock(),Mock(),FastStop(),Mock(),Path('assets'),name,'1')
            hit=flow.map_card(frame)
            self.assertIsNotNone(hit,name)
            self.assertLess(hit[0],225)

    def test_navigation_reuses_stage_and_start(self):
        flow=self.flow()
        flow.press=Mock(return_value=True)
        flow.set_difficulty=Mock(return_value=True)
        self.assertTrue(flow.navigate(Mock()))
        self.assertEqual([c.args[0] for c in flow.press.call_args_list],
                         ['Play','Expedition','East Town','Select Stage','Start'])

    def test_difficulty_steps_plus_only(self):
        for initial,target in [(1,3),(1,2),(1,1)]:
            flow=self.flow(str(target))
            value=[initial]
            flow.difficulty_reading=Mock(side_effect=lambda f:(value[0],(115,64)))
            flow.plus=Mock(return_value=(192,53,43,42))
            frame=np.zeros((92,234,3),np.uint8)
            flow.capture.return_value=frame
            def click(x,y,shape):
                self.assertEqual((x,y),(192,53))
                value[0]+=1
                return True
            flow.client.direct_click.side_effect=click
            self.assertTrue(flow.set_difficulty())
            self.assertEqual(flow.client.direct_click.call_count,target-1)

    def test_difficulty_failed_confirmation_never_adds_clicks(self):
        flow=self.flow('3')
        flow.capture.return_value=np.zeros((92,234,3),np.uint8)
        flow.difficulty_reading=Mock(return_value=(1,(115,64)))
        flow.plus=Mock(return_value=(192,53,43,42))
        with self.assertRaises(RuntimeError):
            flow.set_difficulty()
        self.assertEqual(flow.client.direct_click.call_count,2)

    def test_higher_difficulty_stops_without_clicking(self):
        flow=self.flow('1')
        flow.difficulty_reading=Mock(return_value=(3,(115,64)))
        flow.press=Mock()
        with self.assertRaises(RuntimeError):
            flow.set_difficulty()
        flow.press.assert_not_called()

    def test_plus_hover_is_cleared_between_difficulty_clicks(self):
        flow=self.flow('3')
        frame=np.zeros((92,234,3),np.uint8)
        flow.capture.return_value=frame
        state={'value':1,'hover':False}
        flow.difficulty_reading=Mock(side_effect=lambda f:(state['value'],(115,64)))
        flow.plus=Mock(side_effect=lambda f:None if state['hover'] else (192,53,43,42))
        def click(*args):
            self.assertFalse(state['hover'])
            state['value']+=1
            state['hover']=True
            return True
        def park(*args):
            state['hover']=False
            return True
        flow.client.direct_click.side_effect=click
        flow.client.park_cursor.side_effect=park
        self.assertTrue(flow.set_difficulty())
        self.assertEqual(state['value'],3)
        self.assertEqual(flow.client.park_cursor.call_count,2)

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
        flow.continue_button=Mock(return_value=(80,98,160,35))
        flow.second_continue=Mock(return_value=None)
        flow.cards.handle=Mock(return_value=False)
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
        flow.cards.handle=Mock(return_value=False)
        flow.service(Mock())
        flow.client.direct_click.assert_called_once_with(100,100,frame.shape)
        flow.client.park_cursor.assert_called_once_with(frame.shape)

    def test_second_continue_wins_when_both_visible(self):
        flow=self.flow()
        frame=np.zeros((500,600,3),np.uint8)
        flow.capture.return_value=frame
        flow.cards.handle=Mock(return_value=False)
        flow.game_start=Mock(return_value=None)
        flow.continue_button=Mock(return_value=(80,98,160,35))
        flow.second_continue=Mock(return_value=(280,298,160,35))
        flow.reader.read.return_value=[label('Continue',0,90),label('Continue',200,290)]
        indexer=Mock()
        indexer.all_done.return_value=True
        flow.service(indexer)
        flow.client.direct_click.assert_called_once_with(280,298,frame.shape)
        flow.last_service=0
        flow.service(indexer)
        flow.client.direct_click.assert_called_once()

    def test_second_continue_reference_is_clicked_but_not_cancel(self):
        flow=self.flow()
        frame=cv2.imread('assets/expedition-continue-second.png')
        self.assertIsNotNone(flow.second_continue(frame))
        flow.capture.return_value=frame
        flow.cards.handle=Mock(return_value=False)
        flow.game_start=Mock(return_value=None)
        flow.confirm=Mock(return_value=None)
        flow.continue_button=Mock(return_value=None)
        flow.reader.read.return_value=[label('Continue',0,5)]
        indexer=Mock()
        indexer.all_done.return_value=True
        flow.service(indexer)
        flow.client.direct_click.assert_called_once_with(80,13,frame.shape)
        flow.client.direct_click.reset_mock()
        flow.last_service=0
        flow.capture.return_value=frame.copy()
        flow.reader.read.return_value=[label('Cancel',0,5)]
        flow.service(indexer)
        flow.client.direct_click.assert_not_called()

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
