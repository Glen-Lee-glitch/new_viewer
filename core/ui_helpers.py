from PyQt6.QtWidgets import QLineEdit, QApplication
from PyQt6.QtCore import QTimer, Qt
from core.etc_tools import reverse_text

class ReverseToolHandler:
    def __init__(self, line_edit: QLineEdit):
        if not isinstance(line_edit, QLineEdit):
            raise TypeError("line_edit must be a QLineEdit instance.")
            
        self._line_edit = line_edit
        self._original_stylesheet = self._line_edit.styleSheet()
        self._is_reversed = False
        
        # 이벤트 및 시그널 연결
        self._line_edit.mousePressEvent = self._handle_click
        self._line_edit.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text):
        """텍스트가 변경되면 역순 처리 상태를 초기화합니다."""
        self._is_reversed = False

    def _handle_click(self, event):
        """클릭 이벤트를 처리합니다."""
        if event.button() == Qt.MouseButton.LeftButton:
            current_text = self._line_edit.text().strip()

            # 텍스트가 없거나 이미 역순 처리가 된 경우 기본 동작 수행
            if not current_text or self._is_reversed:
                QLineEdit.mousePressEvent(self._line_edit, event)
                return

            # 역순 변환 수행
            reversed_text = reverse_text(current_text)
            
            # 시그널을 잠시 막아 _on_text_changed가 호출되지 않도록 함
            self._line_edit.blockSignals(True)
            self._line_edit.setText(reversed_text)
            self._line_edit.blockSignals(False)
            
            # 상태 업데이트
            self._is_reversed = True

            # 클립보드 복사
            clipboard = QApplication.clipboard()
            clipboard.setText(reversed_text)

            # 하이라이트 적용
            self._line_edit.setStyleSheet("border: 2px solid #00FF00;")
            
            # 5초 후 초기화 (하이라이트 제거 및 텍스트 삭제)
            QTimer.singleShot(5000, self._clear_and_reset)
        else:
            QLineEdit.mousePressEvent(self._line_edit, event)

    def _clear_and_reset(self):
        """하이라이트를 제거하고 텍스트를 지웁니다."""
        self._line_edit.setStyleSheet(self._original_stylesheet)
        self._line_edit.setText("")
        # setText("")로 인해 textChanged가 발생하고 _is_reversed는 False가 됨
