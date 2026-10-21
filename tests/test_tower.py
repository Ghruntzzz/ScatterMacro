from pathlib import Path
from unittest.mock import Mock,patch
import unittest
import cv2
import numpy as np
from python_macro.tower import TowerFlow,visible_floors
from ui.dashboard import active_unit_config
from test_challenges import label
from test_unit_actions import FastStop


class TowerTests(unittest.TestCase):
    def flow(self,kind='Trait Tower'):
        return TowerFlow(Mock(),Mock(),Mock(),FastStop(),Mock(),Path('assets'),kind)

    def test_highest_numeric_floor_not_reward_numbers(self):
        flow=self.flow()
        matches=[label('Floor',100,20),label('9',150,45),label('Floor 12',300,150),
                 label('250',100,400),label('25x Gem',100,450)]
        flow.reader.read.return_value=matches
        self.assertEqual([n for n,_ in visible_floors(matches)],[9,12])
        self.assertEqual(flow.highest_floor(np.zeros((600,800,3),np.uint8)),(380,158))

    def test_ambiguous_and_missing_floors_do_not_click(self):
        flow=self.flow()
        flow.floors=Mock(return_value=[(4,(10,10)),(4,(20,20))])
        self.assertIsNone(flow.highest_floor(None))
        flow.floors.return_value=[]
        self.assertIsNone(flow.highest_floor(None))

    def test_both_routes_use_shared_stage_and_start(self):
        for kind in ('Trait Tower','Traitless Tower'):
            flow=self.flow(kind)
            flow.press=Mock(return_value=True)
            with patch('python_macro.tower.click_once',return_value=True) as select_tab:
                self.assertTrue(flow.navigate(Mock()))
            select_tab.assert_called_once()
            self.assertEqual(select_tab.call_args.args[0],kind)
            self.assertEqual([c.args[0] for c in flow.press.call_args_list],
                             ['Play','Tower','Floor','Select Stage','Start'])

    def test_tab_card_floor_is_not_a_selectable_floor(self):
        matches=[label('Tower',150,10,40,12),label('Floor 99',135,25,60,14),
                 label('Floor',300,170,50,16),label('1',315,195,20,28)]
        self.assertEqual(visible_floors(matches),[(1,(325,209))])

    def test_tab_image_excludes_floor_when_ocr_misses_heading(self):
        flow=self.flow()
        flow.tab_icons={'Trait Tower':Mock(return_value=(170,18,44,14))}
        flow.reader.read.return_value=[label('Floor 99',135,25,60,14),
                                       label('Floor 3',300,190,60,20)]
        self.assertEqual(flow.floors(np.zeros((600,800,3),np.uint8)),[(3,(330,200))])

    def test_unchanged_tab_is_clicked_once_then_floor_is_selected(self):
        flow=self.flow()
        frame=np.zeros((600,800,3),np.uint8)
        flow.capture.return_value=frame
        flow.tower_tab=Mock(return_value=(170,25))
        flow.press=Mock(return_value=True)
        self.assertTrue(flow.navigate(Mock()))
        flow.client.direct_click.assert_called_once_with(170,25,frame.shape)
        self.assertIn('Floor',[c.args[0] for c in flow.press.call_args_list])

    def test_cancel_does_not_continue(self):
        flow=self.flow()
        flow.press=Mock(return_value=False)
        self.assertFalse(flow.navigate(Mock()))
        self.assertEqual(flow.press.call_count,1)

    def test_static_tab_templates_match_without_floor_number(self):
        for kind,asset in [('Trait Tower','trait'),('Traitless Tower','traitless')]:
            flow=self.flow(kind)
            frame=cv2.imread('assets/tower-'+asset+'-tab.png')
            frame[24:]=0
            self.assertIsNotNone(flow.tab_icons[kind](frame))

    def test_tower_profiles_are_separate_by_type_and_map(self):
        paths={active_unit_config(dict(mode='Tower',tower_type=kind,map=name))
               for kind in ('Trait Tower','Traitless Tower') for name in ('East Town','Rose Kingdom')}
        self.assertEqual(len(paths),4)
        for path in paths:
            self.assertNotEqual(path.name,'Auto.ini')

    def test_map_requires_repeated_match_details(self):
        flow=self.flow()
        flow.capture.return_value=np.zeros((600,800,3),np.uint8)
        flow.reader.read.return_value=[label('Traitless Tower East Town Floor 12')]
        self.assertEqual(flow.wait_map(['East Town','Rose Kingdom']),'East Town')
        self.assertEqual(flow.reader.read.call_count,2)
