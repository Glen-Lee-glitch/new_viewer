from PyQt6.QtWidgets import QLineEdit, QApplication
from PyQt6.QtCore import QTimer, Qt
from .etc_tools import reverse_text

class ReverseToolHandler:
    def __init__(self, line_edit: QLineEdit):
        if not isinstance(line_edit, QLineEdit):
            raise TypeError("line_edit must be a QLineEdit instance.")
            
        self._line_edit = line_edit
        self._original_stylesheet = self._line_edit.styleSheet()
        self._line_edit.mousePressEvent = self._handle_click

    def _handle_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            current_text = self._line_edit.text().strip()

            if not current_text:
                QLineEdit.mousePressEvent(self._line_edit, event)
                return

            reversed_text = reverse_text(current_text)
            self._line_edit.setText(reversed_text)
            QApplication.clipboard().setText(reversed_text)
            self._line_edit.setStyleSheet("border: 2px solid #00FF00;")
            QTimer.singleShot(5000, self._remove_highlight)
        else:
            QLineEdit.mousePressEvent(self._line_edit, event)

    def _remove_highlight(self):
        self._line_edit.setStyleSheet(self._original_stylesheet)
