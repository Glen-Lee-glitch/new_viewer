from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import QWidget

class NecessaryWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "necessary_widget.ui"
        uic.loadUi(str(ui_path), self)
