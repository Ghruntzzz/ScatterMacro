from pathlib import Path
from threading import Event
from unittest.mock import Mock,patch
import tempfile
import unittest
import cv2
import numpy as np

from python_macro.boss_rush import BossRushFlow,GateRoutes,matches_details
from python_macro.unit_actions import UnitIndexer
from test_challenges import label


class BossRushTests(unittest.TestCase):
    def test_in_match_skips_navigation(self):
        flow=self.flow()
        flow.wait_details=Mock(return_value=True)
        flow.navigate=Mock()
        self.assertTrue(flow.ensure_match(Mock()))
        flow.navigate.assert_not_called()
        flow.wait_details.assert_called_once_with(timeout=3)

    def test_lobby_navigates_then_verifies_match(self):
        flow=self.flow()
        flow.wait_details=Mock(side_effect=[False,True])
        flow.navigate=Mock(return_value=True)
        self.assertTrue(flow.ensure_match(Mock()))
        flow.navigate.assert_called_once()

    def test_start_game_text_fallback(self):
        flow=self.flow()
        flow.game_start=Mock(return_value=None)
        flow.reader.read.return_value=[label('Start Game',20,50)]
        self.assertEqual(flow.game_start_target(np.zeros((200,400,3),np.uint8)),(100,58))

    def test_bundled_gate_routes_load_without_user_recordings(self):
        defaults=Path(__file__).resolve().parents[1]/'assets'/'boss-rush-gate-routes'
        with tempfile.TemporaryDirectory() as folder:
            routes=GateRoutes(Path(folder),defaults)
            for name in routes.names:
                route=routes.load(name)
                self.assertEqual(route['map'],name)
                self.assertTrue(route['path']['events'])
            custom=dict(version=1,mode='Keyboard',duration=1,events=[[0,'key','W',1],[1,'key','W',0]])
            routes.save('Gate 1',custom)
            self.assertEqual(routes.load('Gate 1')['path'],custom)

    def test_match_details_require_starting_area_not_menu(self):
        matches=[label('Boss Rush District 7 - Boss Rush',0,0),label('Hard Mode',0,20)]
        self.assertTrue(matches_details(matches))
        self.assertFalse(matches_details(matches+[label('Select Stage',0,100)]))
        self.assertFalse(matches_details([label('Boss Rush Special Gamemode',0,0)]))

    def flow(self):
        return BossRushFlow(Mock(),Mock(),Mock(),Event(),Mock(),Path('assets'),Mock())

    def test_navigation_order(self):
        flow=self.flow()
        flow.press=Mock(return_value=True)
        self.assertTrue(flow.navigate(Mock()))
        self.assertEqual([c.args[0] for c in flow.press.call_args_list],['Play','Boss Rush','Select Stage','Start'])

    def test_only_gate_six_chooses_boss_and_requires_dialog(self):
        flow=self.flow()
        frame=cv2.imread('assets/boss-rush-choice.png')
        flow.reader.read.return_value=[label('Continue',10,109),label('Fight Boss',125,109)]
        # Use screenshot geometry rather than the default test label width.
        from python_macro.ocr import TextMatch
        flow.reader.read.return_value=[TextMatch('Continue',1,((20,110),(100,110),(100,122),(20,122))),
                                      TextMatch('Fight Boss',1,((140,110),(215,110),(215,122),(140,122)))]
        for gate in range(1,6):
            self.assertLess(flow.decision_target(frame,gate)[0],120)
        self.assertGreater(flow.decision_target(frame,6)[0],120)
        self.assertIsNone(flow.decision_target(np.zeros_like(frame),6))

    def test_gate_routes_separate_and_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            routes=GateRoutes(Path(folder))
            path=dict(version=1,mode='Keyboard',duration=1,events=[[0,'key','W',1],[1,'key','W',0]])
            for name in routes.names:
                routes.save(name,path)
                self.assertEqual(routes.load(name)['map'],name)
            with self.assertRaises(ValueError):
                routes.path('Gate 7')

    def test_repeated_manual_path_runs_after_initial_run(self):
        entries=[dict(path='saved',path_repeat='Once'),dict(path='saved',path_repeat='Repeated')]
        indexer=UnitIndexer(entries,Mock(),Mock(),Mock(),Event(),Mock(),allow_paths=False)
        self.assertEqual(indexer.completed,{0})
        self.assertEqual(indexer.next_ready(None),1)

    def test_profile_ui_and_repeat_setting_persist(self):
        from PySide6.QtWidgets import QApplication
        from ui import dashboard
        from ui.unit_manager import EMPTY_INDEX
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder,patch.object(dashboard,'CONFIG_PATH',Path(folder)/'settings.ini'):
            dashboard.update_config('Dashboard',{'Mode':'Boss Rush','Map':'Gate map'})
            setup=dashboard.DashboardWindow()
            self.assertEqual(setup.mode_box.currentText(),'Boss Rush')
            self.assertFalse(hasattr(setup,'gate_routes_button'))
            self.assertTrue(setup.card_priority_button.isHidden())
            setup.close()
            window=dashboard.RuntimeWindow()
            self.assertFalse(hasattr(window,'runtime_gate_routes'))
            window._save_runtime_index(0,dict(EMPTY_INDEX,path_repeat='Repeated'))
            self.assertEqual(dashboard.load_unit_indexes(window.values)[0]['path_repeat'],'Repeated')
            gate=dashboard.active_unit_config(dict(mode='Boss Rush',map='Gate map'))
            boss=dashboard.active_unit_config(dict(mode='Boss Rush',map='Boss map'))
            self.assertNotEqual(gate,boss)
            window.close()

    def test_six_gate_flow_places_only_first_gate_and_boss(self):
        flow=self.flow()
        flow.routes.names=GateRoutes.names
        flow.routes.load.return_value={'path':{}}
        flow.navigate=Mock(return_value=True)
        flow.wait_details=Mock(return_value=True)
        flow.client.setup_camera.return_value=True
        state={'gate':0,'boss':False,'placed':False,'started':False}
        profiles=[]
        placements=[]
        decisions=[]
        def enter(gate):
            state.update(gate=gate,placed=False,started=False)
            return True
        flow.enter_gate=Mock(side_effect=enter)
        flow.decide=Mock(side_effect=lambda gate:decisions.append(gate) or True)
        flow.choice=Mock(side_effect=lambda frame: (1,1,20,20) if not state['boss'] and
                         (state['gate']>1 or state['placed']) else None)
        def profile(name):
            profiles.append(name)
            state.update(boss=name=='Boss map',placed=False,started=False)
        def start(*args,**kwargs):
            state['started']=True
            return True
        test=self
        class Indexer:
            def __init__(self,entries,*args,**kwargs):
                self.entries=entries
                self.completed=set()
            def next_ready(self,wave):
                return None if 0 in self.completed else 0
            def run(self,index):
                test.assertTrue(state['started'])
                placements.append('boss' if state['boss'] else state['gate'])
                state['placed']=True
                self.completed.add(index)
        monitor=Mock()
        monitor.snapshot.side_effect=lambda:dict(wave=None,outcome='victory' if state['boss'] and state['placed'] else None)
        completed=[]
        def finish(*args,**kwargs):
            completed.append(True)
            if len(completed)==2:
                flow.stop.set()
            return True
        with patch('python_macro.boss_rush.UnitIndexer',Indexer), \
             patch('python_macro.boss_rush.time.monotonic',side_effect=iter(range(1000))), \
             patch('python_macro.match_monitor.MatchMonitor',return_value=monitor), \
             patch('python_macro.story_ingame.start_game',side_effect=start), \
             patch('python_macro.story_ingame.finish_match',side_effect=finish):
            flow.run(Mock(),profile,lambda:[dict(unit='1')],Mock(),Mock(),None,Mock())
        self.assertEqual(decisions,list(range(1,7))*2)
        self.assertEqual(placements,[1,'boss',1,'boss'])
        self.assertEqual(profiles,['Gate map','Boss map']*2)
        monitor.close.assert_called_once()
