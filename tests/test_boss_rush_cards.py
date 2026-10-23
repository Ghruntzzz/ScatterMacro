from pathlib import Path
from unittest.mock import Mock
import unittest
import cv2

from python_macro.boss_rush_cards import BossCardSelector, CARD_PRIORITY, boss_card_order
from test_challenges import label
from test_unit_actions import FastStop


class BossCardTests(unittest.TestCase):
    def selector(self, priority=()):
        return BossCardSelector(Path('assets'), Mock(), Mock(), Mock(), FastStop(), Mock(), priority)

    def choices(self, names):
        return [m for i, name in enumerate(names) for m in
                (label(name, i * 250, 200), label('Select Upgrade', i * 250, 350))]

    def test_all_elements_and_buff_types_can_be_ranked(self):
        self.assertEqual(len(CARD_PRIORITY), 48)
        order = boss_card_order('Gale Range|Dark Resistance|Gale Range|Unknown')
        self.assertEqual(order[:2], ['Gale Range', 'Dark Resistance'])
        self.assertEqual(len(order), 48)

    def test_speed_and_element_damage(self):
        selector = self.selector(['Dark Speed', 'Light Element Damage'])
        self.assertEqual(selector.choose(self.choices(['Flame Range', 'Light Element Damage', 'Dark Speed']))['name'], 'Dark Speed')

    def test_priority_wins_even_for_previously_selected_cards(self):
        selector = self.selector(['Light Crit', 'Flame Damage'])
        selector.selected.add('Light Crit')
        self.assertEqual(selector.choose(self.choices(['Flame Damage', 'Light Crit', 'Dark Damage']))['name'], 'Light Crit')

    def test_range_and_resistance_and_all_three_required(self):
        selector = self.selector(['Dark Resistance', 'Light Range'])
        choices = self.choices(['Flame Resistance', 'Light Range', 'Dark Resistance'])
        self.assertEqual(selector.choose(choices)['name'], 'Dark Resistance')
        self.assertIsNone(selector.choose(choices[:-2]))
        self.assertIsNone(selector.choose(self.choices(['Unknown', 'Light Range', 'Dark Resistance'])))

    def test_reference_header_detected(self):
        selector = self.selector()
        self.assertIsNotNone(selector.header(cv2.imread('assets/boss-rush-card-screen.png')))

    def test_close_reads_recover_each_title(self):
        selector = self.selector(['Light Crit'])
        names = ['Flame Damage', 'Light Crit', 'Dark Damage']
        selector.reader.read.side_effect = [[label('Select Upgrade', i*250, 350) for i in range(3)]] + [
            [label(name, i*250, 200)] for i, name in enumerate(names)]
        matches = selector.read_choices(cv2.imread('assets/boss-rush-card-screen.png'))
        self.assertEqual(selector.choose(matches)['name'], 'Light Crit')
        self.assertEqual(selector.reader.read.call_count, 4)
