import os
import sys

from PySide6.QtWidgets import QApplication

from app.bootstrap import bootstrap


def _hide_console_window() -> None:
    if os.name != "nt":
        return
    if os.environ.get("FINANCE_TOOL_SHOW_CONSOLE") == "1":
        return

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


def main() -> None:
    _hide_console_window()
    app = QApplication(sys.argv)
    window = bootstrap()
    window.show()
    sys.exit(app.exec())
