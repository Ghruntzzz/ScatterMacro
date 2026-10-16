import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from python_macro.library import Library, extract_package
from python_macro.updater import replace_install


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.library = Library(self.root / "macros")

    def tearDown(self):
        self.temp.cleanup()

    def package(self, version):
        archive = self.root / (version + ".zip")
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("macro.exe", b"fixture, not executable")
        return {"id": "example", "name": "Example", "version": version,
                "entrypoint": "macro.exe", "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}, archive

    def test_update_preserves_config(self):
        self.library.install_archive(*self.package("1.0.0"))
        config = self.library.config_dir("example") / "settings.ini"
        config.write_text("user settings")
        self.library.install_archive(*self.package("1.1.0"))
        self.assertEqual(config.read_text(), "user settings")
        self.assertEqual(self.library.installed("example")["version"], "1.1.0")

    def test_bad_checksum_not_installed(self):
        macro, archive = self.package("1.0.0")
        macro["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.library.install_archive(macro, archive)
        self.assertIsNone(self.library.installed("example"))

    def test_traversal_rejected(self):
        archive = self.root / "bad.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("../outside.txt", "bad")
        with self.assertRaises(ValueError):
            extract_package(archive, self.root / "stage")
        self.assertFalse((self.root / "outside.txt").exists())

    def installation(self):
        old, new = self.root / "installed", self.root / "package"
        for folder, text in ((old, "old"), (new, "new")):
            folder.mkdir()
            (folder / "ScatterLauncher.exe").write_text(text)
        (old / "settings.ini").write_text("keep")
        return old, new

    def test_launcher_update_keeps_backup_and_settings(self):
        old, new = self.installation()
        backup = replace_install(new, old)
        self.assertEqual((old / "ScatterLauncher.exe").read_text(), "new")
        self.assertEqual((old / "settings.ini").read_text(), "keep")
        self.assertEqual((backup / "ScatterLauncher.exe").read_text(), "old")

    def test_launcher_update_rolls_back_copy_failure(self):
        old, new = self.installation()
        with patch("python_macro.updater.shutil.copytree", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                replace_install(new, old)
        self.assertEqual((old / "ScatterLauncher.exe").read_text(), "old")
        self.assertEqual((old / "settings.ini").read_text(), "keep")
