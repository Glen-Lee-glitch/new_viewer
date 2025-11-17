import sys
from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QColor
from pynput import keyboard

# 단축키 입력을 Qt의 메인 스레드로 전달하기 위한 시그널 클래스
class HotkeyEmitter(QObject):
    copy_signal = pyqtSignal(str)
    toggle_overlay_signal = pyqtSignal()

    def emit_copy(self, index):
        self.copy_signal.emit(index)

    def emit_toggle(self):
        self.toggle_overlay_signal.emit()

hotkey_emitter = HotkeyEmitter()

class OverlayWindow(QWidget):
    def __init__(self, texts, parent=None):
        super().__init__(parent)
        self.texts = texts
        self.hotkey_listener = None
        
        self.initUI()
        
        hotkey_emitter.copy_signal.connect(self.copy_to_clipboard)
        hotkey_emitter.toggle_overlay_signal.connect(self.toggle_visibility)
        self.original_label_text = self.label.text()

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

        display_text = "--- 복사할 정보 (Ctrl+Alt+숫자) ---\n\n" + "\n".join(
            [f"{i+1}: {text}" for i, text in enumerate(self.texts)]
        )
        self.label = QLabel(display_text, self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.label.setStyleSheet("color: white; font-size: 20px; background-color: transparent; padding: 20px;")
        
        self.label.setWordWrap(True)
        self.label.adjustSize()
        self.label.move(
            (self.width() - self.label.width()) // 2,
            (self.height() - self.label.height()) // 2
        )

    def setup_hotkeys(self):
        """Initializes and starts the global hotkey listener."""
        hotkeys = {
            f'<ctrl>+<alt>+{i+1}': self._on_hotkey_pressed(i+1) for i in range(len(self.texts))
        }
        hotkeys['<ctrl>+<alt>+]'] = self._on_toggle_pressed
        
        self.hotkey_listener = keyboard.GlobalHotKeys(hotkeys)
        self.hotkey_listener.start()

    def _on_hotkey_pressed(self, index):
        return lambda: hotkey_emitter.emit_copy(str(index))

    def _on_toggle_pressed(self):
        hotkey_emitter.emit_toggle()

    def copy_to_clipboard(self, index_str):
        """단축키 신호를 받아 클립보드에 텍스트를 복사하는 슬롯"""
        try:
            index = int(index_str) - 1
            if 0 <= index < len(self.texts):
                text_to_copy = self.texts[index]
                QApplication.clipboard().setText(text_to_copy)
                
                self.label.setText(f"'{text_to_copy}'\n\n클립보드에 복사되었습니다.")
                QTimer.singleShot(2000, self.restore_label_text)
        except (ValueError, IndexError):
            pass

    def restore_label_text(self):
        """레이블 텍스트를 원래 목록으로 되돌립니다."""
        self.label.setText(self.original_label_text)

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
