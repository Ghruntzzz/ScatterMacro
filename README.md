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
- Per-route modern PySide6 Unit Manager in the runtime dashboard: 104 selectable indexes,\n  unit slots 0–6, target/upgrade editing, copy/paste, reset, and client-relative position capture.\n  Numbered placement markers appear on the Roblox screenshot through Set position\n  or the read-only View markers control. Upgrade and auto-upgrade are dropdowns;\n  X/Y fields have no spinner arrows. The runtime omits the extra Stop button,\n  but the F2 stop hotkey remains available. Changes auto-save to the route's INI.
- Saved keybind preferences and other settings.

Current flow: Install -> Open -> choose route -> configure unit indexes and
settings -> Save Setup. Nothing is sent to Roblox. Navigation, detection, camera
setup, placing/upgrading units, card selection, rewards, repeat stage, global
hotkeys, wave reading, unit placement, and webhook delivery are not connected yet.\nA tested wave-gating helper can defer a unit index until its requested wave\nwithout blocking later ready indexes, but has not yet been wired into live play. Settings for those features
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

## Story click and map-list navigation

Story clicks now hover, perform a short two-pixel cursor jitter, return to the
target center, and only then click. If the chosen map is not visible after
opening Story, the runtime checks for the map, clicks the lower map-list area,
and scrolls downward in bounded steps, checking OCR after each step. The F2
stop hotkey interrupts scrolling and mouse movement. This assumes the map list
is beneath the lower-middle Roblox client area. Runtime startup retries Roblox
client alignment so the viewport fills without manually dragging the dashboard.
This automation still stops after selecting the Story map.

## Play icon recognition

The runtime searches for the supplied teal Play button using a bundled
multiscale image template (`assets/play-button-template.png`), not the tiny
Play text. It clicks the center of the icon, then waits for the Story menu
to become visible. Unconfirmed clicks are retried up to three times and
reported as errors rather than successes. The icon image is included in the
Windows macro package.

## Reliable click injection

Windows mouse clicks and wheel scrolling use the native `SendInput` API with
checked return values rather than `mouse_event`. The runtime verifies the
cursor's actual location, hovers, performs a quick 2px jitter before clicking,
then holds left button down for 120ms and always sends button-up (even on F2).
A failure to inject or position the pointer surfaces an explicit diagnostic.
Screen-state verification remains separate: the Play icon is not considered
clicked until the Story menu is detected.

## Native mouse movement and AHK-style retry

Roblox may show the pointer over a button without consuming a click when
`SetCursorPos` repositioning doesn't feed the game's mouse-motion path.
The runtime now injects actual Win32 mouse move packets during the brief
jitter and recenters before clicking. It first clicks using checked
`SendInput`, verifies that Story appears, and if it doesn't, retries
the Play icon using a Win32 Event-style click (similar to AHK's Event mode).
Both methods preserve F2 cancellation and mouse-button release. Since the
original Anime Expeditions AHK script is not present in this repository, the
exact historical command cannot be verified.

## Direct Story clicks and Roblox focus

Story navigation now explicitly requests and verifies Roblox foreground focus
before starting and before each click. It uses direct clicks (move once to the
detected target center, mouse down, then up) without hovering or jittering.
The first attempt uses checked SendInput, and an unconfirmed Play click can
retry in AHK-style Event mode. If Windows refuses foreground focus, the macro
reports an error rather than sending input to a different application.

## Play click-method tester

On the runtime dashboard, press **TEST PLAY CLICK METHODS** in Action Output
while Roblox is on the lobby screen. The worker searches for the supplied Play
icon and attempts, in order, direct SendInput, AHK-style mouse_event, virtual
desktop absolute-position SendInput, and window-message mouse click. After
each attempt it checks the screen for the Story menu, logs success or failure,
and **stops testing immediately after a verified success**. F2 stops the test.
The regular Story run uses this same check before proceeding to Story/map
navigation. The widget logs which click method worked; window messages can
be ignored by Roblox, and acceptance by Windows alone is not proof of success.
