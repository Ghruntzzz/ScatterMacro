"""Publish verified launcher or macro assets before exposing their update feeds."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = "Ghruntz/ScatterMacro"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--macro", action="store_true")
    args = parser.parse_args()
    if args.macro:
        tag, name = "anime-expeditions-v0.1.2", "Anime Expeditions 0.1.2 - Installer Fix"
        paths = [ROOT / "dist/AnimeExpeditions-0.1.2-windows.zip"]
        notes = "Update Anime Expeditions through ScatterMacro. Story opens the runtime dashboard with Start/Stop and Action Output. RapidOCR and OpenCV detect Play, Story, then the selected visible map. Navigation stops after the map click. Unit indexes are edited in the runtime Unit Manager. Other modes remain setup-only. Global hotkeys, act/difficulty selection and in-game automation are not connected. Keep Roblox foreground; allow three seconds after Start to switch to it. Live game validation is still required."
    else:
        tag, name = "launcher-v0.3.0", "ScatterMacro 0.3.0"
        paths = [ROOT / "dist/ScatterMacro.exe", ROOT / "dist/ScatterLauncher-0.3.0-windows.zip"]
        notes = "Download ScatterMacro.exe and open it. No ZIP extraction or neighboring _internal folder is required. The executable installs its bundled runtime under LocalAppData/ScatterMacro/launcher and reuses it. Future managed updates switch to the newer runtime. The ZIP asset is for the built-in updater.\n\nAdds redesigned rounded wine-red loading screen, inline update checks without popups, and installable Anime Expeditions setup. Install Anime Expeditions from the library, then Open to configure it. Game automation is not connected yet. Settings remain in each macro's own config folder."
    if not all(path.is_file() for path in paths):
        raise SystemExit("Build the release assets first.")
    credentials = subprocess.run(
        ["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
        text=True, capture_output=True, check=True,
    )
    values = dict(line.split("=", 1) for line in credentials.stdout.splitlines() if "=" in line)
    auth = base64.b64encode(f"{values['username']}:{values['password']}".encode()).decode()

    def request(url, data=None, content_type="application/json", method=None):
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": "Basic " + auth,
            "Accept": "application/vnd.github+json",
            "Content-Type": content_type,
            "User-Agent": "ScatterMacro-release",
        })
        with urllib.request.urlopen(req, timeout=300) as response:
            return json.load(response)

    api = f"https://api.github.com/repos/{REPO}/releases"
    releases = request(api)
    release = next((item for item in releases if item["tag_name"] == tag), None)
    if release is None:
        release = request(api, json.dumps({
            "tag_name": tag, "name": name, "draft": True,
            "target_commitish": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "prerelease": args.macro, "body": notes,
        }).encode())
    for path in paths:
        digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        existing = next((item for item in release.get("assets", []) if item["name"] == path.name), None)
        if existing:
            if existing.get("digest") != digest:
                raise SystemExit("Existing release asset differs; refusing to replace it.")
            print("Already verified: " + path.name, flush=True)
            continue
        upload = release["upload_url"].split("{", 1)[0] + "?name=" + urllib.parse.quote(path.name)
        asset = request(upload, path.read_bytes(), "application/octet-stream" if path.suffix == ".exe" else "application/zip")
        if asset.get("digest") != digest or asset["size"] != path.stat().st_size:
            raise SystemExit("Uploaded asset verification failed; release left as draft.")
        print(asset["browser_download_url"], flush=True)
    release = request(release["url"], json.dumps({"draft": False}).encode(), method="PATCH")
    print(release["html_url"], flush=True)


if __name__ == "__main__":
    main()
