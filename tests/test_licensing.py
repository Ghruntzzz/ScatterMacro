import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python_macro import licensing
from python_macro.library import validate_update_feed


class LicensingTests(unittest.TestCase):
    def test_dpapi_storage_round_trip_and_no_plaintext_key(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(licensing, '_path', return_value=Path(folder) / 'access.dat'):
            data = {'device': 'a' * 64, 'key': 'TESTONLY1234'}
            licensing._save(data)
            self.assertNotIn(b'TESTONLY1234', licensing._path().read_bytes())
            self.assertEqual(licensing._load(), data)

    def test_key_activation_requires_success_before_saving_key(self):
        with patch.object(licensing, '_load', return_value=None), patch.object(licensing, '_save') as saved, \
             patch.object(licensing, '_request', side_effect=licensing.LicenseError('denied')):
            with self.assertRaises(licensing.LicenseError):
                licensing.verify_key('TESTONLY1234')
            self.assertNotIn('key', saved.call_args.args[0])

    def test_successful_activation_persists_server_session(self):
        with patch.object(licensing, '_load', return_value={'device': 'a' * 64}), patch.object(licensing, '_save'), \
             patch.object(licensing, '_request', return_value={'ok': True, 'session': 'signed-session', 'expiresAt': 900}) as request:
            result = licensing.verify_key('TESTONLY1234')
            self.assertEqual(result.session, 'signed-session')
            self.assertEqual(request.call_args.args[1]['deviceId'], 'a' * 64)

    def test_restore_revalidates_with_server_not_local_flag(self):
        credentials = {'device': 'a' * 64, 'key': 'TESTONLY1234', 'activated': True}
        with patch.object(licensing, '_load', return_value=credentials), \
             patch.object(licensing, 'verify_key', side_effect=licensing.LicenseError('revoked')) as verify:
            with self.assertRaises(licensing.LicenseError):
                licensing.restore_access()
            verify.assert_called_once_with('TESTONLY1234')

    def test_package_credentials_never_sent_to_other_hosts(self):
        with patch.object(licensing, 'check_session') as check:
            for url in ('https://github.com/example.zip', 'https://evil.example/download/packages/anime-expeditions/a.zip',
                        licensing.ORIGIN + '.evil.example/download/packages/anime-expeditions/a.zip'):
                with self.assertRaises(licensing.LicenseError):
                    licensing.package_request(url)
            check.assert_not_called()

    def test_private_package_requires_live_session(self):
        with patch.object(licensing, 'check_session', side_effect=licensing.LicenseError('expired')):
            with self.assertRaises(licensing.LicenseError):
                licensing.package_request(licensing.ORIGIN + '/download/packages/anime-expeditions/0.2.0/a.zip')

    def test_cloudflare_update_manifest_is_accepted(self):
        release = {'version': '0.4.0', 'url': licensing.ORIGIN + '/download/packages/launcher/0.4.0/ScatterLauncher-0.4.0-windows.zip', 'sha256': 'a' * 64}
        self.assertEqual(validate_update_feed({'launcher': release, 'macros': []})['launcher'], release)

    def test_no_redirect_can_leak_device_credentials(self):
        with self.assertRaises(licensing.LicenseError):
            licensing.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example')
