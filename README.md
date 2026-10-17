# ScatterMacro

A black-and-wine-red Python launcher with independent macro installation and updates.

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
- Per-route unit indexes: unit slot, target mode, upgrade counts, and coordinates.
- Saved keybind preferences and other settings.

Current flow: Install -> Open -> choose route -> configure unit indexes and
settings -> Save Setup. Nothing is sent to Roblox. Navigation, detection, camera
setup, placing/upgrading units, card selection, rewards, repeat stage, global
hotkeys, and webhook delivery are not connected yet. Settings for those features
are preparation, not a claim that automation is running.

## Installation and updates

Catalog and launcher update checks run at startup. Updates has separate manual
checks for macros and the launcher. Opening an installed macro checks for a newer
version and offers installation first. Offline opening requires confirmation.

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
launcher-update.json identifies the runtime ZIP and its checksum.

Use Python 3.12, install ui/requirements-python.txt, then run python main.py.
Run python -m unittest discover -s tests. Run the setup source with
python anime_main.py --config-dir <your-config-folder>.

Never commit webhook URLs, private server links, or personal configurations.
Previous AHK installations are not migrated or removed.
