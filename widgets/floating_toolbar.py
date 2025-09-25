from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget

class FloatingToolbarWidget(QWidget):
    """pdf_view_widget 위에 떠다니는 이동 가능한 툴바."""
    stamp_menu_requested = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "floating_toolbar.ui"
        uic.loadUi(str(ui_path), self)
        
        # 창 테두리 없애기 (parent 위젯에 자연스럽게 떠있도록)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        # 스타일 스코프 고정
        self.setObjectName("floatingToolbar")
        self._apply_styles()
        
        self._is_dragging = False
        self._drag_start_position = None

        # 스탬프 버튼 클릭 시 오버레이 표시 요청
        if hasattr(self, 'pushButton_stamp'):
            try:
                self.pushButton_stamp.clicked.connect(self.stamp_menu_requested.emit)
            except Exception:
                pass

    def mousePressEvent(self, event):
        # 'drag_handle_frame' 위에서 마우스를 눌렀는지 확인
        if self.drag_handle_frame.underMouse():
            if event.button() == Qt.MouseButton.LeftButton:
                self._is_dragging = True
                self._drag_start_position = event.globalPosition().toPoint() - self.pos()
                self.setCursor(Qt.CursorShape.SizeAllCursor) # 커서를 '+' 모양으로 변경
                event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            self.move(event.globalPosition().toPoint() - self._drag_start_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor) # 커서를 원래대로 복원
            event.accept()

    def _apply_styles(self):
        """FloatingToolbar 전용 QSS 스타일을 적용한다."""
        self.setStyleSheet(
            """
            #floatingToolbar QPushButton {
                padding: 4px 10px;
                border-radius: 6px;
                font-weight: 500;
                min-height: 28px;
            }
            #floatingToolbar QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.08);
            }
            #floatingToolbar QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.14);
            }
            #floatingToolbar QPushButton#pushButton_stamp {
                background-color: #E91E63; /* pink 500 */
                color: white;
            }
            #floatingToolbar QPushButton#pushButton_setting {
                background-color: #607D8B; /* blue grey 500 */
                color: white;
            }
            #floatingToolbar #drag_handle_frame {
                background-color: rgba(255, 255, 255, 0.25);
                border-radius: 3px;
            }
            """
        )
