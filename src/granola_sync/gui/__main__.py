"""Entry point for `python -m granola_sync.gui` and PyInstaller.

Uses absolute imports so PyInstaller can run this script standalone
(no enclosing package context).
"""

from granola_sync.gui.app import main

if __name__ == "__main__":
    main()
