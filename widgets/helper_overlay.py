import sys
from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QColor
from pynput import keyboard

class HotkeyEmitter(QObject):
    copy_signal = pyqtSignal(int)  # 복사 기능 추가 (인덱스 전달)
    toggle_overlay_signal = pyqtSignal()
    navigate_signal = pyqtSignal(str) # 탐색 시그널 추가

    def emit_copy(self, index):
        self.copy_signal.emit(index)

    def emit_toggle(self):
        self.toggle_overlay_signal.emit()
        
    def emit_navigate(self, direction): # 탐색 시그널 발생 메서드
        self.navigate_signal.emit(direction)

class OverlayWindow(QWidget):
    def __init__(self, texts, copy_data=None, parent=None):
        super().__init__(parent)
        self.texts = texts
        self.copy_data = copy_data or []  # 각 신청 건의 복사 가능한 칼럼 값 리스트
        self.current_index = 0
        self.hotkey_listener = None
        self.hotkey_emitter = HotkeyEmitter()
        
        self.initUI()
        
        self.hotkey_emitter.copy_signal.connect(self.copy_to_clipboard)
        self.hotkey_emitter.toggle_overlay_signal.connect(self.toggle_visibility)
        self.hotkey_emitter.navigate_signal.connect(self.navigate_text) # 탐색 시그널 연결

        self.setup_hotkeys()

    def initUI(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        # 초기 텍스트 설정
        display_text = ""
        if self.texts:
            display_text = self.texts[self.current_index]

        self.label = QLabel(display_text, self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color: white; font-size: 28px; background-color: transparent; padding: 20px; font-weight: bold;")
        
        self.label.setWordWrap(True)
        self.label.adjustSize()
        self.label.move(
            (self.width() - self.label.width()) // 2,
            (self.height() - self.label.height()) // 2
        )

    def setup_hotkeys(self):
        """Initializes and starts the global hotkey listener."""
        hotkeys = {
            '<ctrl>+<alt>+<right>': self._on_navigate_pressed('next'),
            '<ctrl>+<alt>+<left>': self._on_navigate_pressed('prev'),
            '<ctrl>+<alt>+]': self._on_toggle_pressed
        }
        
        # 현재 신청 건의 복사 가능한 칼럼 개수에 따라 숫자 키 단축키 추가 (최대 8개)
        if self.copy_data and len(self.copy_data) > 0:
            max_copy_count = max(len(copy_list) for copy_list in self.copy_data) if self.copy_data else 0
            for i in range(1, min(max_copy_count + 1, 9)):  # 1~8까지
                hotkeys[f'<ctrl>+<alt>+{i}'] = self._on_copy_pressed(i - 1)  # 0-based index
        
        self.hotkey_listener = keyboard.GlobalHotKeys(hotkeys)
        self.hotkey_listener.start()

    def _on_navigate_pressed(self, direction):
        return lambda: self.hotkey_emitter.emit_navigate(direction)

    def _on_copy_pressed(self, index):
        return lambda: self.hotkey_emitter.emit_copy(index)

    def _on_toggle_pressed(self):
        self.hotkey_emitter.emit_toggle()

    def copy_to_clipboard(self, index):
        """단축키 신호를 받아 클립보드에 텍스트를 복사하는 슬롯"""
        if not self.copy_data or self.current_index >= len(self.copy_data):
            return
        
        current_copy_list = self.copy_data[self.current_index]
        if 0 <= index < len(current_copy_list):
            text_to_copy = current_copy_list[index]
            if text_to_copy:  # 빈 값이 아닌 경우만 복사
                QApplication.clipboard().setText(text_to_copy)
                
                # 복사 완료 피드백 (2초간)
                original_text = self.label.text()
                self.label.setText(f"{text_to_copy}\n\n클립보드에 복사되었습니다.")
                QTimer.singleShot(2000, lambda: self.label.setText(original_text))
                
                # 텍스트가 바뀌면 라벨 크기와 위치를 다시 조절
                self.label.adjustSize()
                self.label.move(
                    (self.width() - self.label.width()) // 2,
                    (self.height() - self.label.height()) // 2
                )

    def navigate_text(self, direction):
        """방향키 신호를 받아 텍스트를 변경합니다."""
        if not self.texts:
            return
            
        if direction == 'next':
            self.current_index = (self.current_index + 1) % len(self.texts)
        elif direction == 'prev':
            self.current_index = (self.current_index - 1 + len(self.texts)) % len(self.texts)
        
        self.label.setText(self.texts[self.current_index])
        # 텍스트가 바뀌면 라벨 크기와 위치를 다시 조절
        self.label.adjustSize()
        self.label.move(
            (self.width() - self.label.width()) // 2,
            (self.height() - self.label.height()) // 2
        )

    def toggle_visibility(self):
        """단축키 신호를 받아 오버레이 창의 보이기/숨기기 상태를 토글합니다."""
        if self.isVisible():
            self.hide()
        else:
            self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(event.rect(), QColor(0, 0, 0, 60))

    def closeEvent(self, event):
        """Stops the hotkey listener when the window is closed."""
        if self.hotkey_listener:
            self.hotkey_listener.stop()
            self.hotkey_listener.join()
        super().closeEvent(event)
