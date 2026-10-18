"""Versioned macro installation, isolated from persistent per-macro configuration."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import urllib.request
import zipfile

VERSION = "0.3.1"
UPDATE_URL = "https://raw.githubusercontent.com/Ghruntz/ScatterMacro/main/launcher-update.json"

CATALOG_URL = "https://raw.githubusercontent.com/Ghruntz/ScatterMacro/main/catalog.json"
DOWNLOAD_PREFIX = "https://github.com/Ghruntz/ScatterMacro/releases/download/"


def library_root():
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "ScatterMacro/macros"


def safe_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9._-]{0,119}", value):
        raise ValueError("Invalid package identifier")
    if value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]} or value.endswith("."):
        raise ValueError("Reserved package identifier")
    return value


def version_tuple(value):
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError("Invalid release version")
    return tuple(map(int, value.split(".")))


def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "ScatterMacro/" + VERSION, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("Update feed exceeds size limit")
    return json.loads(data)


def validate_catalog(catalog):
    seen = set()
    for macro in catalog["macros"]:
        identifier = safe_name(macro["id"])
        if identifier in seen or not isinstance(macro["name"], str):
            raise ValueError("Invalid catalog entry")
        seen.add(identifier)
        if macro.get("version"):
            validate_release(macro)
            safe_name(macro["entrypoint"])
    return catalog["macros"]


def validate_release(release):
    version_tuple(release["version"])
    if not release["url"].startswith(DOWNLOAD_PREFIX) or not re.fullmatch(r"[a-fA-F0-9]{64}", release["sha256"]):
        raise ValueError("Invalid release source or checksum")


def validate_update_feed(feed):
    """Validate the one manifest consumed by the launcher Updates tab.

    Keep the legacy launcher-update.json separate for installed 0.3.0 clients;
    new clients only need the catalog feed.
    """
    if not isinstance(feed, dict) or not isinstance(feed.get("launcher"), dict):
        raise ValueError("Invalid unified update feed")
    validate_release(feed["launcher"])
    return {"launcher": feed["launcher"], "macros": validate_catalog(feed)}


def download_release(release, target):
    validate_release(release)
    with urllib.request.urlopen(release["url"], timeout=30) as response, Path(target).open("wb") as output:
        digest, total = hashlib.sha256(), 0
        while block := response.read(1024 * 1024):
            total += len(block)
            if total > 512 * 1024 * 1024:
                raise ValueError("Download exceeds size limit")
            digest.update(block)
            output.write(block)
    if digest.hexdigest() != release["sha256"].lower():
        raise ValueError("Download checksum mismatch")


def extract_package(archive, stage):
    with zipfile.ZipFile(archive) as package:
        seen, total = set(), 0
        for member in package.infolist():
            path = PurePosixPath(member.filename.replace("\\", "/"))
            if path.is_absolute() or not path.parts or any(part in (".", "..") or ":" in part for part in path.parts):
                raise ValueError("Unsafe archive path")
            for part in path.parts:
                safe_name(part)
            key = str(path).lower()
            if key in seen or stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError("Duplicate or linked archive entry")
            seen.add(key)
            total += member.file_size
            if total > 1024 * 1024 * 1024 or len(seen) > 20000:
                raise ValueError("Package is too large")
            target = Path(stage).joinpath(*path.parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)


class Library:
    def __init__(self, root=None):
        self.root = Path(root) if root else library_root()

    def macro_dir(self, macro_id):
        return self.root / safe_name(macro_id)

    def config_dir(self, macro_id):
        return self.macro_dir(macro_id) / "config"

    def installed(self, macro_id):
        try:
            state = json.loads((self.macro_dir(macro_id) / "installed.json").read_text(encoding="utf-8"))
            executable = self.macro_dir(macro_id) / "versions" / safe_name(state["version"]) / safe_name(state["entrypoint"])
            return state if executable.is_file() else None
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def executable(self, macro_id):
        state = self.installed(macro_id)
        if not state:
            raise ValueError("Install this macro first")
        return self.macro_dir(macro_id) / "versions" / state["version"] / state["entrypoint"]

    def install_archive(self, macro, archive):
        macro_id, version = safe_name(macro["id"]), safe_name(macro["version"])
        entrypoint = safe_name(macro["entrypoint"])
        if not entrypoint.lower().endswith(".exe"):
            raise ValueError("Package entrypoint must be an executable")
        digest = hashlib.sha256(Path(archive).read_bytes()).hexdigest()
        if digest != macro["sha256"].lower():
            raise ValueError("Download checksum does not match; nothing installed")
        base = self.macro_dir(macro_id)
        versions = base / "versions"
        versions.mkdir(parents=True, exist_ok=True)
        destination = versions / version
        if destination.exists():
            raise ValueError("This package version already exists")
        with tempfile.TemporaryDirectory(prefix=".install-", dir=versions) as temporary:
            stage = Path(temporary)
            with zipfile.ZipFile(archive) as package:
                seen, total = set(), 0
                for member in package.infolist():
                    path = PurePosixPath(member.filename.replace("\\", "/"))
                    if path.is_absolute() or not path.parts or any(part in (".", "..") or ":" in part for part in path.parts):
                        raise ValueError("Unsafe archive path")
                    for part in path.parts:
                        safe_name(part)
                    key = str(path).lower()
                    if key in seen or stat.S_ISLNK(member.external_attr >> 16):
                        raise ValueError("Duplicate or linked archive entry")
                    seen.add(key)
                    total += member.file_size
                    if total > 1024 * 1024 * 1024 or len(seen) > 20000:
                        raise ValueError("Package is too large")
                    target = stage.joinpath(*path.parts)
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with package.open(member) as source, target.open("wb") as output:
                            shutil.copyfileobj(source, output)
            if not (stage / entrypoint).is_file():
                raise ValueError("Package executable is missing")
            os.replace(stage, destination)
        config = self.config_dir(macro_id)
        config.mkdir(parents=True, exist_ok=True)
        settings = config / "settings.ini"
        if not settings.exists():
            settings.write_text("[Macro]\nName=" + macro["name"] + "\n", encoding="utf-8")
        state = {"version": version, "entrypoint": entrypoint}
        temporary = base / "installed.json.tmp"
        temporary.write_text(json.dumps(state), encoding="utf-8")
        os.replace(temporary, base / "installed.json")

    def download_install(self, macro):
        url = macro["url"]
        if not url.startswith(DOWNLOAD_PREFIX):
            raise ValueError("Package must come from the ScatterMacro repository")
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".download-", dir=self.root) as folder:
            archive = Path(folder) / "package.zip"
            with urllib.request.urlopen(url, timeout=30) as response, archive.open("wb") as output:
                total = 0
                while block := response.read(1024 * 1024):
                    total += len(block)
                    if total > 512 * 1024 * 1024:
                        raise ValueError("Download exceeds size limit")
                    output.write(block)
            self.install_archive(macro, archive)
