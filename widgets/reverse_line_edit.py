from PyQt6.QtWidgets import QLineEdit, QApplication
from PyQt6.QtCore import QTimer, Qt
from core.etc_tools import reverse_text

class ReverseLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._original_stylesheet = self.styleSheet()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            current_text = self.text().strip()

            if not current_text:
                # 텍스트가 비어있으면 붙여넣기 등을 위해 기본 이벤트를 호출합니다.
                super().mousePressEvent(event)
                return

            reversed_text = reverse_text(current_text)
            self.setText(reversed_text)

            clipboard = QApplication.clipboard()
            clipboard.setText(reversed_text)

            self.setStyleSheet("border: 2px solid #00FF00;")
            QTimer.singleShot(5000, self._remove_highlight)
        else:
            # 좌클릭이 아니면 (예: 우클릭) 기본 컨텍스트 메뉴가 뜨도록 합니다.
            super().mousePressEvent(event)

    def _remove_highlight(self):
        self.setStyleSheet(self._original_stylesheet)
