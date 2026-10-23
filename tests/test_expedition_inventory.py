from unittest.mock import Mock
import unittest
import numpy as np
from python_macro.checkpoint_shop import ShopItem,next_purchase
from python_macro.unit_actions import UnitIndexer
from test_unit_actions import FastStop


class InventoryTests(unittest.TestCase):
    def test_expedition_ignores_wave_requirement(self):
        worker=UnitIndexer([dict(unit='1',x='10',y='20',place_at_wave='999')],Mock(),Mock(),Mock(),FastStop(),Mock(),slot_count=10)
        self.assertEqual(worker.next_ready(None),0)

    def test_repeat_anvil_uses_updated_price_and_balance(self):
        self.assertIsNotNone(next_purchase([ShopItem('Anvil',5000,(1,1))],15000))
        self.assertIsNotNone(next_purchase([ShopItem('Anvil',7500,(1,1))],10000))
        self.assertIsNone(next_purchase([ShopItem('Anvil',10000,(1,1))],2500))

    def test_slot_ten_is_only_valid_for_expedition_and_uses_zero_key(self):
        entry=dict(unit='10',x='10',y='20')
        normal=UnitIndexer([entry],Mock(),Mock(),Mock(),FastStop(),Mock())
        worker=UnitIndexer([entry],Mock(),Mock(),Mock(),FastStop(),Mock(),slot_count=10)
        self.assertIsNone(normal.next_ready(None))
        self.assertEqual(worker.next_ready(None),0)
        worker.capture=lambda:np.zeros((100,100,3),np.uint8)
        worker.key=Mock()
        worker.click=Mock()
        worker.snapshot=Mock(return_value=(worker.capture(),{'priority':'First'}))
        worker.placement_panel=Mock(return_value={'priority':'First'})
        worker.place(0,entry)
        worker.key.assert_called_once_with('0')
