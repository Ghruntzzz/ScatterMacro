"""Python launcher; --dashboard opens the recovered macro interface."""
import sys

if "--dashboard" in sys.argv:
    from ui.dashboard import main
else:
    from ui.launcher import main

if __name__ == "__main__":
    raise SystemExit(main())
