"""Publish only an opt-in launcher prerelease; never modify the macro updater."""
import base64
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "dist/ScatterLauncher-0.2.0-windows.zip"
REPO = "Ghruntz/ScatterMacro"
TAG = "launcher-v0.2.0"


def main():
    if not ARCHIVE.is_file():
        raise SystemExit("Build the launcher archive first.")
    credentials = subprocess.run(
        ["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
        text=True, capture_output=True, check=True,
    )
    values = dict(line.split("=", 1) for line in credentials.stdout.splitlines() if "=" in line)
    auth = base64.b64encode(f"{values['username']}:{values['password']}".encode()).decode()

    def request(url, data=None, content_type="application/json"):
        req = urllib.request.Request(url, data=data, headers={
            "Authorization": "Basic " + auth,
            "Accept": "application/vnd.github+json",
            "Content-Type": content_type,
            "User-Agent": "ScatterMacro-release",
        })
        with urllib.request.urlopen(req, timeout=300) as response:
            return json.load(response)

    api = f"https://api.github.com/repos/{REPO}/releases"
    try:
        release = request(f"{api}/tags/{TAG}")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise SystemExit(f"Release lookup failed: HTTP {error.code}") from None
        release = request(api, json.dumps({
            "tag_name": TAG,
            "name": "ScatterLauncher 0.2.0",
            "prerelease": False,
            "body": "Download and extract the entire ZIP, then open ScatterLauncher.exe. Keep _internal beside it. Users on 0.1.x must download this update manually once.\n\nRemoves Diagnostics and the dashboard preview. Adds visible loading screen, custom minimize/close controls, per-macro config folders, catalog refresh, separate macro/launcher update checks, macro update checks before launch, verified downloads, and a launcher update helper with rollback. Configurations are kept outside application files.\n\nAnime Expeditions automation is still being rebuilt and is not released for installation. This release does not claim to provide a working game macro. Future released macros will appear in the library without replacing the launcher.",
        }).encode())
    assets = release.get("assets", [])
    if any(asset["name"] == ARCHIVE.name for asset in assets):
        raise SystemExit("Preview asset already exists; refusing to replace it silently.")
    upload = release["upload_url"].split("{", 1)[0] + "?name=" + urllib.parse.quote(ARCHIVE.name)
    asset = request(upload, ARCHIVE.read_bytes(), "application/zip")
    print(release["html_url"])
    print(asset["browser_download_url"])


if __name__ == "__main__":
    main()
