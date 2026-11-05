#!/usr/bin/env python3
"""
Webtoon Raw Resizer & Enhancer
Main application entry point.
"""
import sys
from PySide6.QtWidgets import QApplication
from webtoon_resizer_qt import SmartResizerWindow

def main():
    app = QApplication(sys.argv)
    window = SmartResizerWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
