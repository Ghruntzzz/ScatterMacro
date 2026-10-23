"""ScatterMacro launcher and isolated update helper."""
import sys

if "--apply-update" in sys.argv:
    from python_macro.updater import main
else:
    from ui.launcher import main

if __name__ == "__main__":
    raise SystemExit(main())
