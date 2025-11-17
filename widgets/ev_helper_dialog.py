from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import QDialog, QApplication, QLineEdit
from PyQt6.QtCore import QTimer, Qt
from core.etc_tools import reverse_text


class EVHelperDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "ev_helper_dialog.ui"
        uic.loadUi(str(ui_path), self)

        self.lineEdit_reverse_tool.mousePressEvent = self._handle_reverse_tool_click
        self._original_stylesheet = self.lineEdit_reverse_tool.styleSheet()

    def _handle_reverse_tool_click(self, event):
        """lineEdit_reverse_tool 클릭 이벤트를 처리합니다."""
        if event.button() == Qt.MouseButton.LeftButton:
            current_text = self.lineEdit_reverse_tool.text()
            reversed_text = reverse_text(current_text)
            
            self.lineEdit_reverse_tool.setText(reversed_text)
            
            clipboard = QApplication.clipboard()
            clipboard.setText(reversed_text)
            
            self.lineEdit_reverse_tool.setStyleSheet("border: 2px solid #00FF00;")
            
            QTimer.singleShot(5000, self._remove_highlight)
        else:
            QLineEdit.mousePressEvent(self.lineEdit_reverse_tool, event)
        
    def _remove_highlight(self):
        """lineEdit_reverse_tool의 하이라이트를 제거합니다."""
        self.lineEdit_reverse_tool.setStyleSheet(self._original_stylesheet)
