import sys

from PySide6.QtWidgets import QApplication

from app.bootstrap import bootstrap


def main() -> None:
    app = QApplication(sys.argv)
    window = bootstrap()
    window.show()
    sys.exit(app.exec())
