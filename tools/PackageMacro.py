"""Package and validate against the existing launcher's strict installer."""
import hashlib
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python_macro.library import Library, safe_name


def package_macro(source, archive):
    source, archive = Path(source), Path(archive)
    omitted = {"_internal/rapidocr/models/.gitkeep",
               "_internal/setuptools/_vendor/jaraco/text/Lorem ipsum.txt"}
    files = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if relative.as_posix() in omitted:
            continue
        for part in relative.parts:
            safe_name(part)
        files.append((path, relative.as_posix()))
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        for path, relative in files:
            output.write(path, relative)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="macro-install-check-") as temporary:
        library = Library(temporary)
        library.install_archive({"id": "anime-expeditions", "name": "Anime Expeditions",
                                 "version": "0.1.60", "entrypoint": "AnimeExpeditions.exe",
                                 "sha256": digest}, archive)
        if not library.executable("anime-expeditions").is_file():
            raise RuntimeError("Packaged executable missing")
    print("Installer verification passed. SHA256: " + digest)


if __name__ == "__main__":
    package_macro(ROOT / "dist/AnimeExpeditions", ROOT / "dist/AnimeExpeditions-0.1.60-windows.zip")
