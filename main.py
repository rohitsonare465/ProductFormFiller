"""Application entry point for Product Form Filler."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Product Form Filler")
    app.setOrganizationName("ProductFormFiller")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
