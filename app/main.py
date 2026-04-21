import os
from pathlib import Path
import sys

from PySide6.QtGui import QIcon
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


def _resolve_app_icon() -> QIcon | None:
    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        base_dir = Path(__file__).resolve().parents[1]

    icon_path = base_dir / "assets" / "app.ico"
    if not icon_path.exists():
        return None

    icon = QIcon(str(icon_path))
    return icon if not icon.isNull() else None


def main() -> None:
    _hide_console_window()
    app = QApplication(sys.argv)
    icon = _resolve_app_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    window = bootstrap()
    if icon is not None:
        window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec())
