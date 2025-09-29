from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget


class StampOverlayWidget(QWidget):
    """메인 윈도우 위에 나타나는 반투명 오버레이 위젯."""
    stamp_selected = pyqtSignal(str)  # 도장 선택 신호 (이미지 경로 전달)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "stamp_overlay.ui"
        uic.loadUi(str(ui_path), self)

        # 프레임 제거 + 투명 배경
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.hide()
        self._connect_signals()

    def _connect_signals(self):
        if hasattr(self, 'stamp_button_1'):
            self.stamp_button_1.clicked.connect(lambda: self._on_stamp_button_clicked("assets/도장1.png"))
        if hasattr(self, 'stamp_button_2'):
            self.stamp_button_2.clicked.connect(self._on_stamp_selected)
        if hasattr(self, 'stamp_button_3'):
            self.stamp_button_3.clicked.connect(self._on_stamp_selected)
        if hasattr(self, 'stamp_button_4'):
            self.stamp_button_4.clicked.connect(self._on_stamp_selected)
        if hasattr(self, 'stamp_button_5'):
            self.stamp_button_5.clicked.connect(self._on_stamp_selected)

    def _on_stamp_button_clicked(self, image_path: str):
        """도장 버튼 클릭 시, 선택된 도장 이미지 경로를 포함한 시그널을 발생시킨다."""
        self.stamp_selected.emit(image_path)
        try:
            self.releaseKeyboard()
        finally:
            self.hide()

    def _on_stamp_selected(self):
        print("성공")
        try:
            self.releaseKeyboard()
        finally:
            self.hide()

    def show_overlay(self, parent_size):
        self.setGeometry(0, 0, parent_size.width(), parent_size.height())
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.grabKeyboard()

    def mousePressEvent(self, event):
        # content_frame 밖을 클릭하면 닫기
        if hasattr(self, 'content_frame'):
            local_in_frame = self.content_frame.mapFrom(self, event.pos())
            if not self.content_frame.rect().contains(local_in_frame):
                try:
                    self.releaseKeyboard()
                finally:
                    self.hide()
                return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        # 숫자/숫자패드 1~5 모두 처리 (Keypad 여부는 modifiers로만 구분되므로 동일 키코드 수신)
        if event.key() in (
            Qt.Key.Key_1,
            Qt.Key.Key_2,
            Qt.Key.Key_3,
            Qt.Key.Key_4,
            Qt.Key.Key_5,
        ):
            print("성공")
            try:
                self.releaseKeyboard()
            finally:
                self.hide()
            return
        super().keyPressEvent(event)
