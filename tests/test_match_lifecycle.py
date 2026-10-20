from pathlib import Path
from threading import Event
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from python_macro.end_screen import interpret_end, save_rewards, EndScreenReader
from python_macro.match_monitor import MatchMonitor
from python_macro.story_ingame import already_in_match, finish_match, run_matches, RoundEnded
from python_macro.unit_actions import UnitIndexer, UnitPanel, AbilitySwitch
from test_unit_actions import FastStop, entry


def label(text, x=30, y=20, w=90, h=18):
    return SimpleNamespace(text=text, corners=((x,y),(x+w,y),(x+w,y+h),(x,y+h)))


class LifecycleTests(unittest.TestCase):
    def test_outcomes_require_context_and_are_unambiguous(self):
        self.assertIsNone(interpret_end([label("Victory")], [])['outcome'])
        for name in ("Victory", "Defeat"):
            found = interpret_end([label(name), label("Game Stats")], [label("Repeat Stage")])
            self.assertEqual(found['outcome'], name.lower())
            self.assertEqual(found['repeat'], (75,29))
        self.assertIsNone(interpret_end([label("Victory"), label("Defeat")],
                                       [label("Repeat Stage")])['outcome'])

    def test_reward_prompt_ignores_parentheses_and_changing_numbers(self):
        for page in ("[1/6]", "[8/12]", ""):
            self.assertTrue(interpret_end([], [label("(Click anywhere to continue) " + page)])['reward'])
        self.assertFalse(interpret_end([], [label("75x Gem")])['reward'])

    def test_remaining_reward_count_and_final_close(self):
        found=interpret_end([], [label('(Click anywhere to continue) [3/6]')])
        self.assertEqual(found['reward_clicks'],4)
        found=interpret_end([], [label('(Click anywhere to close) [6/6]')])
        self.assertTrue(found['reward'])
        self.assertEqual(found['reward_clicks'],1)
        self.assertEqual(interpret_end([], [label('Click anywhere to continue [6/3]')])['reward_clicks'],1)

    def test_repeat_search_tracks_translated_modal_not_screen_bottom(self):
        reader=Mock()
        reader.read.side_effect=[[label('Victory',197,214,70,32)],
                                 [label('Repeat Stage',385,602,80,18)]]
        frame=np.zeros((860,1120,3),np.uint8)
        reading=EndScreenReader(reader,FastStop()).read(frame)
        region=reader.read.call_args.args[1]
        self.assertLessEqual(region.y,602)
        self.assertGreater(region.y+region.height,620)
        self.assertEqual(reading['repeat'],(425,611))
        self.assertEqual(reading['outcome'],'victory')

    def test_already_in_match_is_confirmed_twice_without_navigation(self):
        reader = Mock()
        reader.read.return_value = [label("Story East Town - Act 1"), label("Normal Mode")]
        frame = np.zeros((800,1200,3), np.uint8)
        self.assertTrue(already_in_match(lambda:frame, reader, FastStop(), "East Town", "Act 1", "Normal"))
        self.assertEqual(reader.read.call_count, 2)
        with self.assertRaisesRegex(RuntimeError, "different Story match"):
            already_in_match(lambda:frame, reader, FastStop(), "Other Map", "Act 1", "Normal")

    def test_rewards_click_until_disappear_count_once_retry_repeat_until_start(self):
        frame = np.zeros((500,700,3), np.uint8)
        reward = dict(reward=True, outcome=None, repeat=None, matches=[])
        result = dict(reward=False, outcome="victory", repeat=(240,410), matches=[])
        empty = dict(reward=False, outcome=None, repeat=None, matches=[])
        status, client = Mock(), Mock()
        client.direct_click.return_value = True
        with patch("python_macro.story_ingame.EndScreenReader") as factory:
            factory.return_value.read.side_effect = [reward,reward,empty,result,result,result,empty,result,result]
            start = Mock(side_effect=[None,None,None,(10,10)])
            self.assertTrue(finish_match(lambda:frame, client, Mock(), FastStop(), Mock(),
                                         status, None, 0, start))
        self.assertEqual(client.direct_click.call_count, 4)
        self.assertEqual([c.args[:2] for c in client.direct_click.call_args_list],
                         [(350,60),(350,60),(240,410),(240,410)])
        status.assert_called_once()
        self.assertEqual(status.call_args.args[0]['result'], 'victory')

    def test_reward_batch_clicks_remaining_pages_without_rescanning(self):
        frame=np.zeros((500,700,3),np.uint8)
        stop=FastStop()
        client=Mock()
        scans=[]
        def read(frame):
            scans.append(client.direct_click.call_count)
            if len(scans)==1:
                return dict(reward=True,reward_clicks=4,outcome=None,repeat=None)
            stop.set()
            return dict(reward=False,outcome=None,repeat=None)
        with patch('python_macro.story_ingame.EndScreenReader') as factory:
            factory.return_value.read.side_effect=read
            finish_match(lambda:frame,client,Mock(),stop,Mock(),Mock(),None,0,Mock())
        self.assertEqual(scans,[0,4])

    def test_reward_batch_stops_immediately_on_stop(self):
        frame=np.zeros((500,700,3),np.uint8)
        stop=FastStop()
        client=Mock()
        client.direct_click.side_effect=lambda *args: stop.set()
        with patch('python_macro.story_ingame.EndScreenReader') as factory:
            factory.return_value.read.return_value=dict(reward=True,reward_clicks=6,outcome=None,repeat=None)
            finish_match(lambda:frame,client,Mock(),stop,Mock(),Mock(),None,0,Mock())
        self.assertEqual(client.direct_click.call_count,1)

    def test_repeat_creates_fresh_indexes_without_camera_or_navigation(self):
        stop = FastStop()
        frame = np.zeros((500,700,3), np.uint8)
        client, status = Mock(), Mock()
        monitor = Mock()
        monitor.snapshot.return_value = dict(outcome="victory", reward=False, wave=(15,15))
        with patch("python_macro.story_ingame.MatchMonitor", return_value=monitor), \
             patch("python_macro.story_ingame.start_game", side_effect=[True,True,False]) as start, \
             patch("python_macro.story_ingame.finish_match", return_value=True) as finish, \
             patch("python_macro.story_ingame.UnitPanel"), \
             patch("python_macro.story_ingame.UnitIndexer") as indexer, \
             patch("python_macro.story_ingame.StartButtonLocator"):
            provider = Mock(return_value=[entry()])
            run_matches(lambda:frame, client, Mock(), stop, Mock(), Path('assets'), [],
                        status, lambda:frame, None, provider)
        self.assertEqual(start.call_count,3)
        self.assertEqual(finish.call_count,2)
        self.assertEqual(indexer.call_count,2)
        self.assertEqual(provider.call_count,2)
        client.setup_camera.assert_not_called()
        monitor.close.assert_called_once()

    def test_background_monitor_updates_while_main_thread_waits(self):
        delivered = Event()
        frame = np.zeros((500,700,3), np.uint8)
        readings = []
        def status(value):
            readings.append(value)
            if value['wave'] == (3,15):
                delivered.set()
        monitor = MatchMonitor(lambda:frame, Path('assets'), status, reader_factory=Mock)
        with patch('python_macro.story_ingame.HudReader') as hud, \
             patch('python_macro.match_monitor.EndScreenReader') as end:
            hud.return_value.wave.return_value = (3,15)
            end.return_value.read.return_value = dict(outcome=None,reward=False)
            monitor.start()
            monitor.reset()
            try:
                self.assertTrue(delivered.wait(3))
                self.assertEqual(monitor.snapshot()['wave'],(3,15))
            finally:
                monitor.close()
        self.assertGreaterEqual(len(readings),2)

    def test_heartbeat_interrupts_upgrade_before_another_key(self):
        heartbeat = Mock(side_effect=RoundEnded())
        worker = UnitIndexer([],Mock(),Mock(),Mock(),FastStop(),Mock(),heartbeat=heartbeat)
        with self.assertRaises(RoundEnded):
            worker.key('T')
        worker.client.hold_key.assert_not_called()

    def test_worker_skips_navigation_for_confirmed_match(self):
        from ui.story_navigation import StoryWorker
        worker = StoryWorker('East Town', None)
        with patch('python_macro.capture.single_roblox_window',return_value=(123,'Roblox',10)), \
             patch('ui.story_navigation.RobloxClient') as client, \
             patch('ui.story_navigation.navigate_story') as navigation, \
             patch('python_macro.story_ingame.already_in_match',return_value=True), \
             patch('python_macro.story_ingame.run_story_ingame') as ingame:
            client.return_value.focus_roblox.return_value=True
            worker.run()
        navigation.assert_not_called()
        self.assertTrue(ingame.call_args.kwargs['match_confirmed'])

    def test_ability_detection_accepts_red_off_but_not_green_on(self):
        assets=Path(__file__).resolve().parents[1]/'assets'
        panel=UnitPanel(None,Event(),assets)
        frame=np.zeros((400,500,3),np.uint8)
        close=cv2.imread(str(assets/'unit-close.png'))
        ability=cv2.imread(str(assets/'unit-ability-off.png'))
        frame[10:10+close.shape[0],330:330+close.shape[1]]=close
        frame[160:160+ability.shape[0],200:200+ability.shape[1]]=ability
        self.assertIsNotNone(panel.ability_position(frame))
        hsv=cv2.cvtColor(ability,cv2.COLOR_BGR2HSV)
        hsv[:,:,0]=60
        frame[160:160+ability.shape[0],200:200+ability.shape[1]]=cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR)
        self.assertIsNone(panel.ability_position(frame))

    def test_ability_click_targets_red_knob_at_intermediate_scales(self):
        assets=Path(__file__).resolve().parents[1]/'assets'
        panel=UnitPanel(None,Event(),assets)
        close=cv2.imread(str(assets/'unit-close.png'))
        original=cv2.imread(str(assets/'unit-ability-off.png'))
        for scale in (.7, .95, 1.1, 1.35):
            frame=np.zeros((400,500,3),np.uint8)
            frame[10:10+close.shape[0],330:330+close.shape[1]]=close
            tile=cv2.resize(original,None,fx=scale,fy=scale)
            frame[160:160+tile.shape[0],200:200+tile.shape[1]]=tile
            point=panel.ability_position(frame)
            self.assertIsNotNone(point,scale)
            x,y=point
            b,g,r=map(int,frame[y,x])
            self.assertGreater(r,g+50)
            self.assertGreater(r,b+50)

    def test_real_panel_switch_outside_panel_is_found_at_multiple_scales(self):
        assets=Path(__file__).resolve().parents[1]/'assets'
        panel=UnitPanel(None,Event(),assets)
        source=cv2.imread(str(Path(__file__).parent/'fixtures/unit-ability-panel.png'))
        for scale in (.8,1,1.5):
            tile=cv2.resize(source,None,fx=scale,fy=scale)
            frame=np.zeros((tile.shape[0]+100,tile.shape[1]+200,3),np.uint8)
            frame[40:40+tile.shape[0],70:70+tile.shape[1]]=tile
            found=panel.ability_state(frame)
            self.assertIsNotNone(found,scale)
            self.assertEqual(found[0],'off')
            self.assertLess(abs(found[1][0]-(70+461*scale)),4)
            self.assertLess(abs(found[1][1]-(40+35*scale)),4)

    def test_missing_panel_does_not_complete_ability_check(self):
        panel=Mock()
        panel.close_icon.return_value=None
        worker=UnitIndexer([],Mock(),Mock(),panel,FastStop(),Mock())
        self.assertFalse(worker.enable_ability())
        worker.client.direct_click.assert_not_called()

    def test_switch_masks_ignore_background_and_recognize_both_states(self):
        detector=AbilitySwitch(Path(__file__).resolve().parents[1]/'assets')
        for state in ('off','on'):
            _,tile,mask,kx,ky=next(t for t in detector.tiles if t[0]==state and abs(t[1].shape[0]-50)<=1)
            for background in ((180,80,40),(30,170,190),(220,220,220)):
                frame=np.full((180,200,3),background,np.uint8)
                crop=frame[50:50+tile.shape[0],70:70+tile.shape[1]]
                crop[mask>0]=tile[mask>0]
                found=detector(frame)
                self.assertIsNotNone(found,(state,background))
                self.assertEqual(found[0],state)
                self.assertLess(abs(found[1][0]-(70+kx)),4)
                self.assertLess(abs(found[1][1]-(50+ky)),4)

    def test_ability_click_does_not_rescan_or_log_confirmation(self):
        panel=Mock()
        panel.close_icon.return_value=(350,15,25,25)
        panel.ability_state.side_effect=[('off',(200,150))]+[None]*5
        frame=np.zeros((400,500,3),np.uint8)
        worker=UnitIndexer([],Mock(),lambda:frame,panel,FastStop(),Mock())
        self.assertTrue(worker.enable_ability())
        self.assertEqual(worker.client.direct_click.call_count,1)
        self.assertEqual(panel.ability_state.call_count,1)
        worker.log.assert_not_called()

    def test_preflight_waits_three_seconds_even_when_play_is_visible(self):
        clock=[0.0]
        stop=Mock()
        stop.is_set.return_value=False
        def wait(seconds):
            clock[0]+=seconds
            return False
        stop.wait.side_effect=wait
        reader=Mock()
        reader.read.return_value=[]
        frame=np.zeros((500,700,3),np.uint8)
        with patch('python_macro.story_ingame.time.monotonic',side_effect=lambda:clock[0]):
            self.assertFalse(already_in_match(lambda:frame,reader,stop,'East Town','Act 1','Normal',find_play=lambda frame:(10,10)))
        self.assertAlmostEqual(clock[0],3)
        self.assertGreater(reader.read.call_count,3)

    def test_green_ability_is_not_clicked(self):
        panel=Mock()
        panel.close_icon.return_value=(350,15,25,25)
        panel.ability_state.return_value=('on',(200,170))
        worker=UnitIndexer([],Mock(),Mock(),panel,FastStop(),Mock())
        self.assertTrue(worker.enable_ability())
        worker.client.direct_click.assert_not_called()

    def test_monitor_reset_clears_old_result_and_wave(self):
        monitor=MatchMonitor(Mock(),Path('assets'),Mock())
        monitor.state=dict(outcome='victory',reward=True,wave=(15,15))
        monitor.reset()
        self.assertEqual(monitor.snapshot(),dict(outcome=None,reward=False,wave=None))

    def test_ability_check_at_wave_once_and_restores_current_panel(self):
        frame=np.zeros((400,500,3),np.uint8)
        panel, client = Mock(), Mock()
        panel.close_icon.return_value=(350,15,25,25)
        panel.ability_state.side_effect=[('off',(200,150)),('on',(200,170))]
        client.direct_click.return_value=True
        worker=UnitIndexer([entry(auto_ability_wave='5'),entry()],client,lambda:frame,panel,FastStop(),Mock())
        worker.placed={0:(20,30),1:(40,50)}
        worker.active_index=1
        worker.close=Mock()
        worker.check_abilities(4)
        client.direct_click.assert_not_called()
        worker.check_abilities(5)
        self.assertEqual([c.args[:2] for c in client.direct_click.call_args_list],[(20,30),(200,150),(40,50)])
        self.assertEqual(worker.ability_checked,{0})
        worker.check_abilities(6)
        self.assertEqual(client.direct_click.call_count,3)

    def test_reward_capture_contains_only_dynamic_reward_area(self):
        frame=cv2.imread(str(Path(__file__).parent/'fixtures/victory-screen.png'))
        reading={'outcome':'victory','matches':[label('Gained Rewards',48,255,120,18),
                 label('Repeat Stage',206,401,80,18),label('View Party',351,401,80,18)]}
        with tempfile.TemporaryDirectory() as directory:
            target=save_rewards(frame,reading,directory)
            self.assertFalse((target/'result.png').exists())
            strip=cv2.imread(str(target/'reward-strip.png'))
            self.assertLess(strip.shape[0],frame.shape[0]//3)
            metadata=json.loads((target/'rewards.json').read_text())
            self.assertEqual(len(metadata['images']),6)
            self.assertEqual(metadata['strip_image'],'reward-strip.png')
