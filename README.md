# ScatterMacro

A black-and-wine-red Python launcher with independently installable packages and one unified update feed.

## Open the launcher

Download **ScatterMacro.exe** from [Releases](https://github.com/Ghruntz/ScatterMacro/releases)
and open it. No ZIP extraction, Python installation, or neighboring _internal
folder is required. The EXE installs its embedded runtime under
%LOCALAPPDATA%/ScatterMacro/launcher/<version> and reuses it. Keep the downloaded
EXE wherever you prefer; it opens the latest installed managed runtime.

The launcher has a rounded animated loading screen, custom window controls,
Home, Installed, and Updates. Update checks report inline and never spawn a
window or a helper process. Only installing a launcher update restarts it.

## Anime Expeditions setup

Select Install on Anime Expeditions, then Open. The installed setup app provides:
- Mode, map, act, and difficulty configuration.
- Private-server and Discord settings, saved locally.
- Per-route modern PySide6 Unit Manager in the runtime dashboard: 104 selectable indexes,\n  unit/target/upgrade editing, copy/paste, reset, and client-relative position capture.\n  Changes auto-save to the currently selected route's existing INI profile.
- Saved keybind preferences and other settings.

Current flow: Install -> Open -> choose route -> configure unit indexes and
settings -> Save Setup. Nothing is sent to Roblox. Navigation, detection, camera
setup, placing/upgrading units, card selection, rewards, repeat stage, global
hotkeys, and webhook delivery are not connected yet. Settings for those features
are preparation, not a claim that automation is running.

## Installation and updates

The launcher checks one catalog.json feed on startup for updates to both the launcher
and every macro. One **Check for updates** button refreshes the Updates tab;
each available update has its own Install/Update action. Opening an installed macro
uses that same feed to check for a newer version first. Offline opening requires
confirmation. Unreleased macro versions remain hidden until their verified
release assets are published.

Macros install into %LOCALAPPDATA%/ScatterMacro/macros/<macro-id>. Each has a
persistent config folder and separate versioned program folders. Macro configs
and Open configs open those folders. Updates preserve settings. Macro programs
receive --config-dir followed by their absolute configuration path.

Launcher updates verify SHA-256 before extraction. Managed installs stage the
new runtime alongside the old one and atomically change current.txt. The
standalone EXE follows that pointer on subsequent opens. Existing legacy folder
installations use a backup-and-replace updater. Running macros are not killed.

The ZIP assets are internal updater packages; regular users download the EXE.

## Publishing and development

catalog.json requires id, name, version, url, sha256 and a root-level .exe
entrypoint for released macro packages. setup_only marks configuration-only
packages. Macros provide their own dependencies, independent of the launcher.

Build the macro first with tools/BuildAnimeExpeditions.ps1, then update its
checksum in catalog.json and build the launcher with tools/BuildLauncher.ps1.
Publish both verified assets before exposing catalog/update feeds.
The `launcher` field in `catalog.json` identifies the launcher runtime ZIP and
checksum. `launcher-update.json` remains available for compatibility with older
0.3.0 launchers. Only publish new version information to either feed after
building, releasing, and verifying the actual Windows assets.

Use Python 3.12, install ui/requirements-python.txt, then run python main.py.
Run python -m unittest discover -s tests. Run the setup source with
python anime_main.py --config-dir <your-config-folder>.

Never commit webhook URLs, private server links, or personal configurations.
Previous AHK installations are not migrated or removed.
