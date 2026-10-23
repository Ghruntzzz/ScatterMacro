from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.PackageMacro import package_macro


class MacroPackagingTests(unittest.TestCase):
    def test_build_only_files_are_omitted_and_package_installs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            source.mkdir()
            (source / "AnimeExpeditions.exe").write_bytes(b"fixture")
            for name in ("_internal/rapidocr/models/.gitkeep",
                         "_internal/setuptools/_vendor/jaraco/text/Lorem ipsum.txt"):
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("unused")
            archive = root / "package.zip"
            package_macro(source, archive)
            with zipfile.ZipFile(archive) as package:
                self.assertEqual(package.namelist(), ["AnimeExpeditions.exe"])

    def test_unexpected_invalid_filename_is_not_silently_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            source.mkdir()
            (source / "needed file.dat").write_text("keep")
            with self.assertRaisesRegex(ValueError, "Invalid package identifier"):
                package_macro(source, root / "package.zip")
