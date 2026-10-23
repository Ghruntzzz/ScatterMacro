import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from python_macro.library import Library, extract_package
from python_macro.updater import replace_install
from python_macro import updater


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

    def test_managed_update_switches_pointer_and_keeps_old_version(self):
        managed = self.root / "launcher"
        old = managed / "0.2.0"
        old.mkdir(parents=True)
        (old / "ScatterLauncher.exe").write_text("old")
        (managed / "current.txt").write_text("0.2.0")
        package = self.root / "package"
        package.mkdir()
        executable = package / "ScatterLauncher.exe"
        executable.write_text("new")
        with patch.object(updater, "library_root", return_value=self.root / "macros"), \
             patch.object(updater.sys, "argv", ["app", "--apply-update", "--target", str(old), "--pid", "123"]), \
             patch.object(updater.sys, "executable", str(executable)), \
             patch.object(updater, "wait_for_exit"), \
             patch.object(updater.subprocess, "Popen") as launch:
            self.assertEqual(updater.main(), 0)
        self.assertEqual((managed / "current.txt").read_text(), updater.VERSION)
        self.assertEqual((old / "ScatterLauncher.exe").read_text(), "old")
        self.assertEqual((managed / updater.VERSION / "ScatterLauncher.exe").read_text(), "new")
        self.assertEqual(Path(launch.call_args.args[0][0]).parent, managed / updater.VERSION)


class UnifiedFeedTests(unittest.TestCase):
    def test_catalog_validates_launcher_and_independent_macros(self):
        from python_macro.library import validate_update_feed
        release = {"version": "0.3.0",
                   "url": "https://github.com/Ghruntz/ScatterMacro/releases/download/test/package.zip",
                   "sha256": "a" * 64}
        macro = dict(release, id="anime-expeditions", name="Anime Expeditions",
                     entrypoint="AnimeExpeditions.exe")
        feed = validate_update_feed({"launcher": release, "macros": [macro]})
        self.assertEqual(feed["launcher"]["version"], "0.3.0")
        self.assertEqual(feed["macros"][0]["id"], "anime-expeditions")

    def test_missing_or_invalid_launcher_rejected(self):
        from python_macro.library import validate_update_feed
        with self.assertRaises(ValueError):
            validate_update_feed({"macros": []})
        with self.assertRaises(ValueError):
            validate_update_feed({"launcher": {"version": "bad"}, "macros": []})
