from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import QWidget, QApplication, QLineEdit
from PyQt6.QtCore import QTimer, Qt
from core.etc_tools import reverse_text

class NecessaryWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "necessary_widget.ui"
        uic.loadUi(str(ui_path), self)
        
        self.lineEdit_reverse_tool.mousePressEvent = self._handle_reverse_tool_click
        self._original_stylesheet = self.lineEdit_reverse_tool.styleSheet()

    def _handle_reverse_tool_click(self, event):
        """lineEdit_reverse_tool 클릭 이벤트를 처리합니다."""
        if event.button() == Qt.MouseButton.LeftButton:
            current_text = self.lineEdit_reverse_tool.text()
            reversed_text = reverse_text(current_text)
            
            # 1. 텍스트를 역순으로 변경
            self.lineEdit_reverse_tool.setText(reversed_text)
            
            # 2. 클립보드에 복사
            clipboard = QApplication.clipboard()
            clipboard.setText(reversed_text)
            
            # 3. 하이라이트 적용
            self.lineEdit_reverse_tool.setStyleSheet("border: 2px solid #00FF00;")
            
            # 4. 5초 후 하이라이트 제거
            QTimer.singleShot(5000, self._remove_highlight)
        else:
            # 다른 마우스 버튼 클릭 시(예: 우클릭), QLineEdit의 기본 동작을 수행
            QLineEdit.mousePressEvent(self.lineEdit_reverse_tool, event)
        
    def _remove_highlight(self):
        """lineEdit_reverse_tool의 하이라이트를 제거합니다."""
        self.lineEdit_reverse_tool.setStyleSheet(self._original_stylesheet)
