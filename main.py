"""Launch NEXUS."""
import sys

from PySide6.QtWidgets import QApplication

from nexus.window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NEXUS")
    app.setOrganizationName("NEXUS")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
