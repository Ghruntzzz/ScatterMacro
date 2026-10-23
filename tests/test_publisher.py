import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.PublishCloudflare import publisher_request, USER_AGENT
from python_macro.library import download_release, CLOUDFLARE_PREFIX, VERSION


class DownloadClientTests(unittest.TestCase):
    def test_publisher_identifies_itself_and_preserves_authentication(self):
        request = publisher_request('https://example.com', method='PUT', data=b'part',
                                    headers={'Authorization': 'Bearer test'})
        self.assertEqual(request.get_header('User-agent'), USER_AGENT)
        self.assertEqual(request.get_header('Authorization'), 'Bearer test')
        self.assertEqual(request.method, 'PUT')
        self.assertEqual(request.data, b'part')

    def test_launcher_update_identifies_itself_and_checks_download(self):
        content = b'package fixture'
        release = {'version': '0.4.1', 'url': CLOUDFLARE_PREFIX + 'launcher/0.4.1/update.zip',
                   'sha256': hashlib.sha256(content).hexdigest()}
        with tempfile.TemporaryDirectory() as folder:
            with patch('urllib.request.urlopen', return_value=io.BytesIO(content)) as fetch:
                target = Path(folder) / 'update.zip'
                download_release(release, target)
                self.assertEqual(target.read_bytes(), content)
                self.assertEqual(fetch.call_args.args[0].get_header('User-agent'), 'ScatterMacro/' + VERSION)
