# ScatterMacro

A Python macro launcher with a black and wine-red interface, a per-game library,
and read-only Roblox capture diagnostics. This is a fresh project with no AHK,
FindText, or process-memory access.

## Windows preview

Download the ZIP from [Releases](https://github.com/Ghruntz/ScatterMacro/releases),
extract the entire archive, and open `ScatterLauncher.exe` inside the
`ScatterLauncher` folder. Keep `_internal` beside the executable. Python does
not need to be installed to run the packaged preview.

The preview includes the launcher, Anime Expeditions dashboard preview, library
search, and manual Roblox client capture. Game automation, macro installation,
automatic updates, and OCR diagnostics are not ready yet. Start does not run
a game macro. No unfinished automation is silently enabled.

## Development

Use Python 3.12 in a virtual environment, install `ui/requirements-python.txt`,
then run `python main.py`. Use `--dashboard` for the recovered interface.
Run `python -m unittest discover -s tests` for the launcher and vision tests.
OpenCV handles preprocessing; an OCR engine still needs integration.
Desktop capture requires a visible, unobstructed Roblox window.

## Privacy and saved data

Never commit webhook URLs, user IDs, private server links, personal settings,
or unit/index configurations. This preview does not migrate or delete files
from an existing macro installation. They remain in the old folder.

## Planned work

- Install/update released macro packages safely from this repository.
- Rebuild game modes one at a time using Python and OpenCV plus OCR.
- Add hotkeys, configuration migration, and repeat/webhook state handling.
- Expand diagnostics with detection regions, recognized text, and timing.
