from pathlib import Path
from unittest.mock import Mock
import unittest
import cv2
import numpy as np
from python_macro.expedition_inventory import HammerInventory,payload_health
from python_macro.checkpoint_shop import ShopItem,next_purchase
from python_macro.expeditions import ExpeditionFlow
from python_macro.unit_actions import UnitIndexer
from test_challenges import label
from test_unit_actions import FastStop


class InventoryTests(unittest.TestCase):
    def test_counts_two_individual_slots_not_other_screen_hammers(self):
        tile=cv2.imread('assets/shop-inventory-hammer.png')
        h,w=tile.shape[:2]
        frame=np.zeros((600,900,3),np.uint8)
        frame[510:510+h,40:40+w]=tile
        frame[510:510+h,140:140+w]=tile
        frame[100:100+h,40:40+w]=tile
        self.assertEqual(len(HammerInventory(Path('assets/shop-inventory-hammer.png')).find(frame)),2)

    def test_only_reads_health_near_payload(self):
        self.assertEqual(payload_health([label('Payload',300,100),label('800/1,000',300,125)]),(800,1000))
        self.assertIsNone(payload_health([label('800/1,000',300,125)]))

    def test_heal_once_until_inventory_confirms_consumption(self):
        flow=ExpeditionFlow(Mock(),Mock(),Mock(),FastStop(),Mock(),Path('assets'),'East Town','1')
        flow.hammers.find=Mock(return_value=[(100,550),(200,550)])
        flow.reader.read.return_value=[label('Payload',300,100),label('800/1,000',300,125)]
        frame=np.zeros((600,900,3),np.uint8)
        self.assertTrue(flow.heal_if_needed(frame))
        flow.last_health_check=0
        self.assertFalse(flow.heal_if_needed(frame))
        flow.client.direct_click.assert_called_once_with(100,550,frame.shape)

    def test_healthy_payload_never_uses_hammer(self):
        flow=ExpeditionFlow(Mock(),Mock(),Mock(),FastStop(),Mock(),Path('assets'),'East Town','1')
        flow.hammers.find=Mock(return_value=[(100,550)])
        flow.reader.read.return_value=[label('Payload',300,100),label('1,000/1,000',300,125)]
        self.assertFalse(flow.heal_if_needed(np.zeros((600,900,3),np.uint8)))
        flow.client.direct_click.assert_not_called()

    def test_repeat_anvil_uses_updated_price_and_balance(self):
        self.assertIsNotNone(next_purchase([ShopItem('Anvil',5000,(1,1))],15000,False,2))
        self.assertIsNotNone(next_purchase([ShopItem('Anvil',7500,(1,1))],10000,False,2))
        self.assertIsNone(next_purchase([ShopItem('Anvil',10000,(1,1))],2500,False,2))

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
