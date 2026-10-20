import json
import os
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import Mock, patch, call

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from ui import dashboard
from python_macro.hotkeys import RuntimeHotkeys, parse_hotkey, validate_hotkeys
from python_macro.notifications import Notifier, webhook_url


class SettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patch=patch.object(dashboard,'CONFIG_PATH',Path(self.temp.name)/'settings.ini')
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_defaults_and_custom_keybinds_persist_with_notifications(self):
        values=dashboard.read_dashboard_values()
        self.assertEqual((values['start_key'],values['stop_key']),('F1','F2'))
        settings=dashboard.SettingsWindow()
        settings.start_key.setText('Ctrl+F6')
        settings.stop_key.setText('F8')
        settings.show_rewards.setChecked(True)
        settings.ping_defeat.setChecked(False)
        settings._save_settings()
        values=dashboard.read_dashboard_values()
        self.assertEqual((values['start_key'],values['stop_key']),('Ctrl+F6','F8'))
        self.assertEqual(values['show_rewards'],'1')
        self.assertEqual(values['ping_defeat'],'0')
        user=Mock()
        keys=RuntimeHotkeys(5,user,start_key=values['start_key'],stop_key=values['stop_key'])
        keys.register()
        self.assertEqual(user.RegisterHotKey.call_args_list,
                         [call(5,keys.START,0x4002,0x75),call(5,keys.STOP,0x4000,0x77)])

    def test_duplicate_shortcuts_do_not_overwrite_settings(self):
        settings=dashboard.SettingsWindow()
        settings.start_key.setText('F2')
        settings._save_settings()
        self.assertIn('different',settings.settings_status.text())
        self.assertEqual(dashboard.read_dashboard_values()['start_key'],'F1')
        settings.close()

    def test_theme_applies_to_visible_widgets_and_persists(self):
        main=dashboard.DashboardWindow()
        settings=dashboard.SettingsWindow(main)
        before=main.start_button.styleSheet()
        settings.accent_color.setText('#225588')
        settings._apply_theme_colors()
        self.assertNotEqual(before,main.start_button.styleSheet())
        self.assertIn('#225588',main.start_button.styleSheet())
        self.assertEqual(dashboard.read_dashboard_values()['accent_color'],'#225588')
        settings.accent_color.setText('#663344')
        settings._save_settings()
        self.assertIn('#663344',main.start_button.styleSheet())
        main.close()

    def test_redundant_ui_removed(self):
        main=dashboard.DashboardWindow()
        settings=dashboard.SettingsWindow(main)
        labels=[v.text() for v in main.findChildren(QLabel)]
        self.assertNotIn('DEPLOYMENT',labels)
        self.assertNotIn('ROBLOX AUTO-DETECTED ON START',labels)
        self.assertEqual(main.start_button.text(),'START')
        self.assertNotIn('UPDATES',[v.text() for v in settings.findChildren(QLabel)])
        self.assertFalse(hasattr(settings,'automatic_check_toggle'))
        self.assertIn('Show rewards earned',[v.text() for v in settings.findChildren(QPushButton)])
        settings.close()
        main.close()

    def test_result_counts_once_and_resets_for_repeat(self):
        window=dashboard.RuntimeWindow()
        window._update_hud({'new_run':True})
        window._update_hud({'wave':(15,15)})
        window._update_hud({'result':'victory','duration':120})
        window._update_hud({'result':'victory','duration':120})
        self.assertEqual(window.stat_values['RUNS'].text(),'1')
        self.assertEqual(window.stat_values['WAVES COMPLETED'].text(),'15')
        window._update_hud({'new_run':True})
        window._update_hud({'wave':(5,15)})
        window._update_hud({'result':'defeat','duration':60})
        self.assertEqual(window.stat_values['RUNS'].text(),'2')
        self.assertEqual(window.stat_values['DEFEATS'].text(),'1')
        self.assertEqual(window.stat_values['AVG RUN'].text(),'00:01:30')
        self.assertEqual(window.stat_values['WAVES COMPLETED'].text(),'19')
        window.close()


class NotificationTests(unittest.TestCase):
    def settings(self,**changes):
        return dict(webhook='https://discord.com/api/webhooks/123/fake_token',
                    ping_victory='1',ping_defeat='0',ping_error='1',show_rewards='1',**changes)

    def opener(self):
        opener=Mock()
        response=Mock()
        response.status=200
        opener.open.return_value.__enter__=Mock(return_value=response)
        opener.open.return_value.__exit__=Mock(return_value=False)
        return opener

    def test_notifications_respect_toggles_and_no_webhook(self):
        opener=self.opener()
        notify=Notifier(self.settings(),Event(),Mock(),opener)
        self.assertFalse(notify.send('defeat'))
        notify.settings['webhook']=''
        self.assertFalse(notify.send('victory'))
        opener.open.assert_not_called()

    def test_reward_text_and_full_client_attachment(self):
        opener=self.opener()
        notify=Notifier(self.settings(discord_id='123456789012345678'),Event(),Mock(),opener)
        with tempfile.TemporaryDirectory() as directory:
            Path(directory,'reward-strip.png').write_bytes(b'reward-pixels')
            Path(directory,'roblox.png').write_bytes(b'full-client-pixels')
            Path(directory,'rewards.json').write_text(json.dumps({'rewards':['75x Gem'], 'stats':{'Total Kills':'300'}}))
            self.assertTrue(notify.send('victory',90,directory))
        request=opener.open.call_args.args[0]
        self.assertNotIn(b'reward-pixels',request.data)
        self.assertIn(b'full-client-pixels',request.data)
        self.assertIn(b'75x Gem',request.data)
        self.assertIn(b'Total Kills',request.data)
        self.assertIn(b'attachment://roblox.png',request.data)
        self.assertIn('wait=true',request.full_url)

    def test_reward_option_off_sends_only_summary(self):
        opener=self.opener()
        settings=self.settings()
        settings['show_rewards']='0'
        notify=Notifier(settings,Event(),Mock(),opener)
        self.assertTrue(notify.send('victory',45))
        payload=json.loads(opener.open.call_args.args[0].data)
        self.assertNotIn('image',payload['embeds'][0])
        self.assertEqual(payload['allowed_mentions']['parse'],[])

    def test_failures_do_not_raise_or_expose_url(self):
        opener=self.opener()
        opener.open.side_effect=OSError('secret webhook URL')
        log=Mock()
        self.assertFalse(Notifier(self.settings(),Event(),log,opener).send('victory'))
        self.assertNotIn('secret',str(log.call_args_list))

    def test_url_validation_and_shortcut_safety(self):
        for url in ('http://discord.com/api/webhooks/123/token',
                    'https://example.org/api/webhooks/123/token',
                    'https://discord.com.evil.test/api/webhooks/123/token'):
            with self.assertRaises(ValueError): webhook_url(url)
        for value in ('1','R','Ctrl+Ctrl+F','F25',''):
            with self.assertRaises(ValueError): parse_hotkey(value)
        with self.assertRaises(ValueError): validate_hotkeys('Ctrl+F1','CTRL+F1')
