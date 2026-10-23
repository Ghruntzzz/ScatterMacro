import json
import tempfile
from pathlib import Path
from unittest.mock import Mock,patch
import unittest
import cv2
from python_macro.expedition_cards import choose_card,priority_order,offered_cards,CardSelector
from test_challenges import label
from test_unit_actions import FastStop


class CardTests(unittest.TestCase):
    def setUp(self):
        self.catalog=json.loads(Path('assets/expedition-card-catalog.json').read_text())['cards']
        self.choices=[c for c in self.catalog if c['name'] in ('Razor Focus','Hemorrhage','Bat Cavalry')]

    def test_new_cards_first_then_highest_priority_when_all_used(self):
        priority=['Buff','DOT','Followup Attack']
        self.assertEqual(choose_card(self.choices,priority,set())['name'],'Razor Focus')
        self.assertEqual(choose_card(self.choices,priority,{'Razor Focus'})['name'],'Hemorrhage')
        self.assertEqual(choose_card(self.choices,priority,{c['name'] for c in self.choices})['name'],'Razor Focus')

    def test_category_first_then_tier(self):
        choices=[c for c in self.catalog if c['category'] in ('Economy','Buff')]
        self.assertEqual(choose_card(choices,['Buff','Economy'],set())['name'],'Razor Focus')
        self.assertEqual(choose_card(choices,['Economy','Buff'],set())['name'],'Whetstone Cache')

    def test_requires_three_readable_unique_choices(self):
        matches=[]
        for i,card in enumerate(self.choices):
            matches += [label(card['name'],i*250,200),label('Select Upgrade',i*250,350)]
        self.assertEqual(len(offered_cards(matches,self.catalog)),3)
        self.assertEqual(offered_cards(matches[:-2],self.catalog),[])

    def test_one_click_until_modal_disappears_then_history_reset(self):
        frame=cv2.imread('assets/expedition-card-screen.png')
        matches=[]
        for i,card in enumerate(self.choices):
            matches += [label(card['name'],i*250,200),label('Select Upgrade',i*250,350)]
        reader=Mock()
        client=Mock()
        selector=CardSelector(Path('assets'),reader,client,lambda:frame,FastStop(),Mock())
        selector.read_choices=Mock(side_effect=[matches,matches,[],[]])
        selector.header=Mock(side_effect=[(10,10),(10,10),(10,10),None,None])
        self.assertTrue(selector.handle(frame))
        client.direct_click.assert_called_once()
        self.assertEqual(selector.selected,{'Razor Focus'})
        selector.reset()
        self.assertEqual(selector.selected,set())

    def test_anvil_priority_and_all_three_required(self):
        selector=CardSelector(Path('assets'),Mock(),Mock(),Mock(),FastStop(),Mock())
        matches=[]
        for i,name in enumerate(('Damage','Range','Spa')):
            matches.extend([label(name,i*250,200),label('Select Upgrade',i*250,350)])
        self.assertEqual(selector.choose(matches)['name'],'Range')
        self.assertIsNone(selector.choose(matches[:-2]))
        matches.extend([label('Legendary Upgrade',i*250,230) for i in range(3)])
        matches.append(label('Damage',250,300))
        self.assertEqual(selector.choose(matches)['name'],'Range')

    def test_anvil_screenshot_header(self):
        selector=CardSelector(Path('assets'),Mock(),Mock(),Mock(),FastStop(),Mock())
        self.assertIsNotNone(selector.anvil_header(cv2.imread('assets/expedition-anvil-screen.png')))
        self.assertIsNone(selector.anvil_header(cv2.imread('assets/expedition-card-screen.png')))

    def test_close_scans_recover_all_titles(self):
        frame=cv2.imread('assets/expedition-card-screen.png')
        reader=Mock()
        buttons=[label('Select Upgrade',i*250,350) for i in range(3)]
        reader.read.side_effect=[buttons]+[[label(c['name'],i*250,200)] for i,c in enumerate(self.choices)]
        selector=CardSelector(Path('assets'),reader,Mock(),Mock(),FastStop(),Mock())
        self.assertIsNotNone(selector.choose(selector.read_choices(frame)))
        self.assertEqual(reader.read.call_count,4)
        self.assertEqual(reader.read.call_args.kwargs['scale'],3)

    def test_priority_menu_reorder_and_settings_round_trip(self):
        from PySide6.QtWidgets import QApplication
        from ui.card_priority import CardPriorityDialog
        from ui import dashboard
        app=QApplication.instance() or QApplication([])
        dialog=CardPriorityDialog([])
        dialog.list.setCurrentRow(1)
        dialog.move_item(-1)
        self.assertEqual(dialog.order()[0],'Buff')
        with tempfile.TemporaryDirectory() as directory,patch.object(dashboard,'CONFIG_PATH',Path(directory)/'settings.ini'):
            dashboard.update_config('Dashboard',{'CardPriority':'|'.join(dialog.order())})
            self.assertEqual(priority_order(dashboard.read_dashboard_values()['card_priority']),dialog.order())
        dialog.close()

    def test_history_resets_only_when_match_indexer_changes(self):
        from python_macro.expeditions import ExpeditionFlow
        flow=ExpeditionFlow(Mock(),Mock(),Mock(),FastStop(),Mock(),Path('assets'),'East Town','1')
        flow.cards=Mock()
        flow.cards.handle.return_value=False
        flow.game_start=Mock(return_value=None)
        indexer=Mock()
        indexer.all_done.return_value=False
        flow.service(indexer)
        flow.last_service=0
        flow.service(indexer)
        flow.cards.reset.assert_called_once()
        flow.last_service=0
        fresh=Mock()
        fresh.all_done.return_value=False
        flow.service(fresh)
        self.assertEqual(flow.cards.reset.call_count,2)
