import json
import tempfile
from pathlib import Path
from unittest.mock import Mock,patch
import unittest
from python_macro.shop_routes import ShopRoutes,MAPS
from python_macro.checkpoint_shop import ShopItem,purchase_plan,should_refresh

PATH=dict(version=1,mode='Keyboard',duration=1,events=[[0,'key','W',1],[1,'key','W',0]])


class ShopTests(unittest.TestCase):
    def test_four_independent_routes_and_default_override(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            defaults=ShopRoutes(root/'defaults')
            defaults.save(MAPS[0],PATH)
            store=ShopRoutes(root/'custom',defaults.root)
            self.assertEqual(store.load(MAPS[0])['path'],PATH)
            for name in MAPS:
                store.save(name,PATH)
                self.assertEqual(store.load(name)['map'],name)
            self.assertEqual(len(list(store.root.glob('*.json'))),4)

    def test_reject_wrong_map_and_non_wasd_routes(self):
        store=ShopRoutes(Path('unused'))
        with self.assertRaises(ValueError):
            store.validate(dict(version=1,map=MAPS[1],path=PATH),MAPS[0])
        with self.assertRaises(ValueError):
            store.path('../outside')
        with self.assertRaises(ValueError):
            store.validate(dict(version=1,map=MAPS[0],path=dict(PATH,mode='Mouse')),MAPS[0])

    def test_recording_save_does_not_touch_unit_configs(self):
        from PySide6.QtWidgets import QApplication
        from ui.shop_routes import ShopRoutesDialog
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            store=ShopRoutes(Path(folder))
            dialog=ShopRoutesDialog(store)
            self.assertEqual(dialog.map.count(),4)
            dialog.saved(json.dumps(PATH))
            self.assertEqual(store.load(MAPS[0])['path'],PATH)
            dialog.map.setCurrentIndex(1)
            self.assertIn('No route',dialog.info.text())
            dialog.close()

    def test_unbound_first_and_no_anvil_if_traits_present(self):
        items=[ShopItem('Anvil',5000,(1,1)),ShopItem('Foresaken',15000,(2,2)),ShopItem('Unbound',30000,(3,3))]
        self.assertEqual([i.name for i in purchase_plan(items,45000)],['Unbound','Foresaken'])
        self.assertEqual(purchase_plan(items,5000),[])

    def test_hammer_is_never_bought_and_does_not_block_refresh(self):
        hammer=ShopItem('Repair Hammer',15000,(1,1))
        self.assertEqual(purchase_plan([hammer],15000),[])
        self.assertTrue(should_refresh([hammer],1,False))
        anvil=ShopItem('Anvil',5000,(2,2))
        self.assertEqual(purchase_plan([hammer,anvil],20000),[anvil])

    def test_refresh_once_only_when_no_target_items(self):
        self.assertTrue(should_refresh([ShopItem('Unknown',5000,(1,1))],1,False))
        self.assertFalse(should_refresh([],1,True))
        self.assertFalse(should_refresh([],0,False))
        self.assertFalse(should_refresh([ShopItem('Unbound',30000,(1,1))],1,False))
