# ScatterMacro

A black-and-wine-red Python launcher with independent macro installation and updates.

## Windows

Download the ZIP from [Releases](https://github.com/Ghruntz/ScatterMacro/releases),
extract the whole archive, and run ScatterLauncher.exe inside ScatterLauncher.
Keep _internal beside the executable. Python is not required.
Users on 0.1.x need to download 0.2.0 manually once.

Includes a visible loading screen, custom window controls, Home, Installed, and
Updates. There is no Diagnostics page or preview dashboard.

Anime Expeditions is not released yet. Its automation is still being rebuilt;
the launcher does not install an unfinished dashboard as a working macro.

## Installation and updates

The launcher checks this repository's catalog and launcher update feed at startup.
Updates has separate manual checks for macros and the launcher. Opening an
installed macro checks its latest version first and offers an update. If offline,
users can explicitly choose to open the installed version.

Released macros install into %LOCALAPPDATA%/ScatterMacro/macros/<macro-id>.
Each has a persistent config folder and separate versioned program folders.
Macro configs and Open configs open these folders. Updates preserve settings.
Macros launch with --config-dir followed by their absolute configuration path.

Launcher updates download a checksum-verified package, close the old launcher,
replace it with an isolated helper, retain a backup, and reopen it. Copy failures
restore the previous installation. Running macro processes are not terminated.
New catalog entries can appear without updating the launcher.

## Publishing packages

catalog.json contains macro IDs, names, descriptions, and nullable versions.
Released entries also require url, sha256, and a root-level .exe entrypoint.
Macro ZIPs contain the executable at the archive root. Include all required OCR,
OpenCV and runtime dependencies in the macro package, not the launcher.

launcher-update.json contains version, url, and sha256. Publish the verified
release asset before updating this feed. Launcher ZIPs contain a ScatterLauncher
folder. Never overwrite existing release archives with different contents.

## Development

Use Python 3.12 and install ui/requirements-python.txt, then run python main.py.
Run python -m unittest discover -s tests. Build with tools/BuildLauncher.ps1.
The recovered dashboard source is retained for future macro development but is
not reachable from or bundled into this launcher.

Never commit webhook URLs, private server links, or user configurations. Previous
macro installations are not migrated or removed by this launcher.
