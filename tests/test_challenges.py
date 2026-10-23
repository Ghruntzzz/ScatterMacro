from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import unittest
import numpy as np

from python_macro.challenges import Card,ChallengeFlow,menu_data,reset_seconds,ORDER,active_challenge
from python_macro.story_ingame import finish_match
from python_macro.story_verified import click_and_confirm
from python_macro.end_screen import reward_label
from test_unit_actions import FastStop


def label(text,x=400,y=90,w=160,h=16):
    return SimpleNamespace(text=text,corners=((x,y),(x+w,y),(x+w,y+h),(x,y+h)))


def menu(kind='weekly',available=True,remaining=10):
    result=[]
    for i,name in enumerate(('Regular','Daily','Weekly')):
        y=60+i*95
        result += [label(name+' Challenge',40,y,160,16),
                   label('Unavailable' if name.lower()==kind and not available else 'Rewards Available!',40,y+18,160,12),
                   label('Resets in 00:20:00',40,y+56,160,12)]
    for i in range(3 if kind=='regular' else 1):
        y=90+i*120
        result += [label(kind.title()+f' Challenge #{i+1}',400,y),
                   label('Crimson Shore - Act 4',400,y+20),
                   label(f'Daily Limit {remaining}/10',240,y+80,100,12)]
    return result


class ChallengeTests(unittest.TestCase):
    def flow(self,settings=None,clock=lambda:0):
        return ChallengeFlow(Mock(),Mock(),Mock(),FastStop(),Mock(),Path('assets'),settings or {},clock)

    def test_menu_reads_priority_cards_and_unavailable(self):
        tabs,cards=menu_data(menu())
        self.assertTrue(tabs['weekly']['available'])
        self.assertEqual(cards[0].key,'weekly')
        self.assertEqual((cards[0].map_name,cards[0].act),('Crimson Shore','Act 4'))
        tabs,cards=menu_data(menu(available=False))
        self.assertFalse(tabs['weekly']['available'])
        self.assertEqual(cards,[])
        tabs,cards=menu_data(menu('regular',remaining=0))
        self.assertEqual([c.key for c in cards],['regular1','regular2','regular3'])
        self.assertFalse(self.flow().permitted(cards[0]))

    def test_cooldown_time_parsing(self):
        self.assertEqual(reset_seconds('Resets in 26:05'),1565)
        self.assertEqual(reset_seconds('Resets in 26:26:05'),95165)
        self.assertIsNone(reset_seconds('Resets in 26:99'))

    def test_selection_order_respects_every_checkbox(self):
        self.assertEqual(self.flow().enabled,list(ORDER))
        flow=self.flow({'challenge_weekly':'0','challenge_regular2':'0'})
        self.assertEqual(flow.enabled,['daily','regular1','regular3'])

    def test_selector_advances_weekly_daily_then_regular(self):
        flow=self.flow()
        flow.cooldown=Mock(return_value=None)
        flow.press=Mock(return_value=True)
        tabs={kind:dict(available=True) for kind in ('weekly','daily','regular')}
        cards=[Card(key,'East Town','Act 1',(20,20),None,600) for key in ORDER]
        flow.read_menu=Mock(return_value=(tabs,cards))
        self.assertEqual(flow.select().key,'weekly')
        flow.completed()
        self.assertEqual(flow.select().key,'daily')
        flow.completed()
        self.assertEqual(flow.select().key,'regular1')

    def test_cooldown_backs_out_and_selects_next_regular(self):
        now=[0]
        flow=self.flow({'challenge_weekly':'0','challenge_daily':'0'},clock=lambda:now[0])
        tabs={kind:dict(available=True) for kind in ('weekly','daily','regular')}
        cards=[Card('regular'+str(i),'Rose Kingdom','Act 2',(20,20),10,600) for i in (1,2,3)]
        flow.read_menu=Mock(return_value=(tabs,cards))
        flow.press=Mock(return_value=True)
        flow.cooldown=Mock(side_effect=[671,None])
        self.assertEqual(flow.select().key,'regular2')
        self.assertEqual([c.args[0] for c in flow.press.call_args_list],
                         ['Challenge stage','Back','Challenge stage','Select Stage','Start'])
        self.assertFalse(flow.permitted(cards[0]))
        now[0]=672
        self.assertTrue(flow.permitted(cards[0]))

    def test_available_in_is_a_cooldown_not_select_stage(self):
        flow=self.flow()
        flow.ocr.unique=Mock(return_value=(400,398))
        flow.ocr.matches=[label('Available in 11:11')]
        self.assertEqual(flow.cooldown(object()),671)

    def test_challenge_template_avoids_ocr_when_found(self):
        flow=self.flow()
        flow.challenge=Mock(return_value=(100,100))
        flow.text=Mock()
        self.assertEqual(flow.challenge_target(object()),(100,100))
        flow.text.assert_not_called()

    def test_tab_images_ignore_reset_timer(self):
        import cv2
        flow=self.flow()
        for kind in ('regular','daily'):
            frame=cv2.imread('assets/challenge-'+kind+'.png')
            frame[50:]=255
            flow.read_menu=Mock(side_effect=AssertionError('Unexpected OCR'))
            self.assertIsNotNone(flow.tab_target(kind,frame))

    def test_weekly_unavailable_image_never_selects_tab(self):
        import cv2
        flow=self.flow()
        frame=cv2.imread('assets/challenge-weekly-unavailable.png')
        frame[50:]=255
        flow.read_menu=Mock(side_effect=AssertionError('Unexpected OCR'))
        self.assertIsNone(flow.tab_target('weekly',frame))

    def test_new_map_profile_is_empty_then_saves_and_reloads(self):
        import tempfile
        from ui import dashboard
        from ui.story_navigation import StoryWorker
        from ui.unit_manager import EMPTY_INDEX
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory, patch.object(dashboard,'CONFIG_PATH',Path(directory)/'settings.ini'):
            window=dashboard.RuntimeWindow()
            worker=StoryWorker('Auto',None,reader=Mock(),entries=[dict(EMPTY_INDEX)]*104,mode='Challenges')
            worker.profile_changed.connect(window._challenge_profile)
            entries=worker.challenge_entries('Flower Forest','Act 2')
            self.assertTrue(all(e['unit']=='0' for e in entries))
            self.assertEqual(window.unit_config_path,dashboard.active_unit_config(dict(mode='Story',map='Flower Forest',act='Act 2')))
            window._save_runtime_index(0,dict(EMPTY_INDEX,unit='1',x='10',y='20'))
            worker.challenge_entries('Rose Kingdom','Act 1')
            self.assertEqual(window.unit_indexes[0]['unit'],'0')
            worker.challenge_entries('Flower Forest','Act 5')
            self.assertEqual(window.unit_indexes[0]['unit'],'1')
            worker.map_entries('Raid','Spirit City','Act 1')
            window._save_runtime_index(0,dict(EMPTY_INDEX,unit='2',x='10',y='20'))
            worker.map_entries('Raid','Spirit City','Act 2')
            self.assertEqual(window.unit_indexes[0]['unit'],'0')
            worker.map_entries('Raid','Spirit City','Act 1')
            self.assertEqual(window.unit_indexes[0]['unit'],'2')
            window.close()

    def test_detected_story_and_raid_routes(self):
        from python_macro.story_ingame import detected_route
        self.assertEqual(detected_route(['Story East Town - Act 3','Normal Mode']),
                         ('Story','East Town','Act 3','Normal'))
        self.assertEqual(detected_route(['Raid','Snowy Castle - Act 2']),
                         ('Raid','Snowy Castle','Act 2','Normal'))
        self.assertEqual(detected_route(['Story Flower Forest - Infinite','Hard Mode']),
                         ('Story','Flower Forest','Infinite','Hard'))
        self.assertIsNone(detected_route(['Story East Town - Act 3','Select Stage']))

    def test_live_new_index_waits_for_coordinates(self):
        from python_macro.unit_actions import UnitIndexer
        from ui.unit_manager import EMPTY_INDEX
        entries=[dict(EMPTY_INDEX,unit='1')]
        indexer=UnitIndexer(entries,Mock(),Mock(),Mock(),FastStop(),Mock(),allow_incomplete=True)
        self.assertIsNone(indexer.next_ready(None))
        entries[0].update(x='10',y='20')
        self.assertEqual(indexer.next_ready(None),0)

    def test_existing_match_changes_profile_instead_of_rejecting_other_map(self):
        from python_macro.story_ingame import already_in_match
        reader=Mock()
        reader.read.return_value=[label('Raid Snowy Castle - Act 2')]
        callback=Mock()
        frame=np.zeros((500,700,3),np.uint8)
        self.assertTrue(already_in_match(lambda:frame,reader,FastStop(),'East Town','Act 1','Normal',on_detect=callback))
        callback.assert_called_once_with('Raid','Snowy Castle','Act 2','Normal')

    def test_unavailable_selection_waits_and_remains_cancellable(self):
        flow=self.flow()
        tabs={kind:dict(available=False) for kind in ('weekly','daily','regular')}
        flow.read_menu=Mock(return_value=(tabs,[]))
        flow.stop.wait=Mock(return_value=True)
        self.assertIsNone(flow.select())
        flow.stop.wait.assert_called_once_with(30)
        flow.client.direct_click.assert_not_called()

    def test_success_limits_and_resets(self):
        clock=[0]
        flow=self.flow(clock=lambda:clock[0])
        for key,limit in (('weekly',1),('daily',1),('regular1',10)):
            card=Card(key,'East Town','Act 1',(10,20),None,30)
            flow.current=card
            for _ in range(limit):
                self.assertTrue(flow.permitted(card))
                flow.completed()
            self.assertFalse(flow.permitted(card))
        clock[0]=31
        self.assertTrue(flow.permitted(flow.current))

    def test_partially_used_regular_limit(self):
        flow=self.flow()
        card=Card('regular2','East Town','Act 1',(10,20),2,30)
        flow.current=card
        self.assertTrue(flow.permitted(card))
        flow.completed()
        self.assertTrue(flow.permitted(card))
        flow.completed()
        self.assertFalse(flow.permitted(card))

    def test_victory_uses_party_transition_not_repeat(self):
        client=Mock()
        result=dict(outcome='victory',reward=False,repeat=(20,30),matches=[])
        frame=np.zeros((200,400,3),np.uint8)
        next_match=Mock(return_value=True)
        notify=Mock()
        with patch('python_macro.story_ingame.EndScreenReader') as factory:
            factory.return_value.read.return_value=result
            self.assertTrue(finish_match(lambda:frame,client,Mock(),FastStop(),Mock(),Mock(),
                                         None,0,Mock(return_value=None),on_result=notify,next_match=next_match))
        notify.assert_called_once()
        next_match.assert_called_once()
        client.direct_click.assert_not_called()

    def test_defeat_uses_repeat_without_consuming_challenge(self):
        client=Mock()
        result=dict(outcome='defeat',reward=False,repeat=(20,30),matches=[])
        frame=np.zeros((200,400,3),np.uint8)
        next_match=Mock()
        with patch('python_macro.story_ingame.EndScreenReader') as factory:
            factory.return_value.read.return_value=result
            self.assertTrue(finish_match(lambda:frame,client,Mock(),FastStop(),Mock(),Mock(),
                                         None,0,Mock(return_value=(50,50)),next_match=next_match))
        next_match.assert_not_called()
        client.direct_click.assert_called_once()

    def test_return_path_party_change_challenge(self):
        flow=self.flow()
        flow.press=Mock(return_value=True)
        self.assertTrue(flow.return_to_menu())
        self.assertEqual([c.args[0] for c in flow.press.call_args_list],['View Party','Change Gamemode','Challenge'])

    def test_no_enabled_challenges_does_not_click(self):
        flow=self.flow({'challenge_'+key:'0' for key in ORDER})
        with self.assertRaises(RuntimeError):
            flow.select()
        flow.client.direct_click.assert_not_called()

    def test_story_profile_is_reloaded_for_each_selected_map(self):
        from python_macro.challenges import run_challenges
        frame=np.zeros((200,400,3),np.uint8)
        first=Card('weekly','Rose Kingdom','Act 2',(0,0),None,600)
        second=Card('daily','East Town','Act 4',(0,0),None,600)
        profiles=Mock(side_effect=lambda name,act:[name,act])
        notifier=SimpleNamespace(settings={},send=Mock())
        with patch('python_macro.challenges.ChallengeFlow') as factory, \
             patch('python_macro.story_ingame.run_story_ingame') as run, \
             patch('python_macro.story_ingame.prepare_match',return_value=True):
            flow=factory.return_value
            flow.enabled=['weekly','daily']
            flow.read_menu.return_value=({'weekly':{},'daily':{},'regular':{}},[])
            flow.select.side_effect=[first,second]
            run_challenges(lambda:frame,Mock(),Mock(),FastStop(),Mock(),Path('assets'),{},[],Mock(),
                           Mock(),None,Mock(),notifier,Mock(),route_entries=profiles)
            provider=run.call_args.kwargs['entries_provider']
            self.assertEqual(provider(),['Rose Kingdom','Act 2'])
            self.assertTrue(run.call_args.kwargs['next_match']())
            self.assertEqual(provider(),['East Town','Act 4'])
            self.assertEqual(provider(),['East Town','Act 4'])

    def test_active_match_extracts_dynamic_map_and_act(self):
        card=active_challenge([label('Weekly Challenge'),label('Crimson Shore - Act 4')])
        self.assertEqual((card.key,card.map_name,card.act),('weekly','Crimson Shore','Act 4'))
        self.assertIsNone(active_challenge(menu('daily')))

    def test_start_waits_then_relocates_moving_button(self):
        frame=np.zeros((200,400,3),np.uint8)
        locate=Mock(side_effect=[(10,10),(10,35),(10,35),(10,35)])
        click=Mock(return_value=True)
        stop=FastStop()
        with patch.object(stop,'wait',wraps=stop.wait) as wait:
            self.assertTrue(click_and_confirm('Start',locate,lambda after,before:True,lambda:frame,
                                              click,stop,Mock(),stable_seconds=.45))
        click.assert_called_once_with(10,35,frame.shape)
        self.assertEqual(wait.call_count,2)

    def test_long_reward_names_merge_without_duplication(self):
        matches=[label('1x',y=0),label('Splrit of the',y=70),label('Spirit of the Moonbla de',y=80)]
        self.assertEqual(reward_label(matches,0,100),'1x Spirit of the Moonblade')
        self.assertEqual(reward_label([label('1,000x',y=0),label('Unlt EXP',y=75),label('Unit EXP',y=77)],0,100),'1,000x Unit EXP')
