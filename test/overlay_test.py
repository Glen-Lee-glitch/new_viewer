import sys
from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QColor
from pynput import keyboard

# 단축키 입력을 Qt의 메인 스레드로 전달하기 위한 시그널 클래스
class HotkeyEmitter(QObject):
    copy_signal = pyqtSignal(str)
    toggle_overlay_signal = pyqtSignal() # 토글 시그널 추가

    def emit_copy(self, index):
        self.copy_signal.emit(index)

    def emit_toggle(self): # 토글 시그널을 보내는 메서드 추가
        self.toggle_overlay_signal.emit()

# 전역 Emitter 인스턴스
hotkey_emitter = HotkeyEmitter()

class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        # 클립보드에 복사할 텍스트 목록
        self.texts = [
            "이경구",
            "경기도 고양시 뭐뭐로 31-0",
            "101동 201호",
            "010-2888-3555",
            "gyeonggoo.lee@greetlounge.com",
            "RN123456789"
        ]
        self.initUI()
        
        # 시그널과 클립보드 복사 함수(슬롯) 연결
        hotkey_emitter.copy_signal.connect(self.copy_to_clipboard)
        # 토글 시그널과 슬롯 연결 추가
        hotkey_emitter.toggle_overlay_signal.connect(self.toggle_visibility)
        self.original_label_text = self.label.text() # 피드백 후 원래 텍스트로 되돌리기 위해 저장

    def initUI(self):
        # 윈도우 플래그 설정
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowTransparentForInput
        )
        
        # 반투명 배경 설정
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 전체 화면으로 설정
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        # 오버레이에 표시될 텍스트 레이블 (전체 목록 표시)
        display_text = "--- 복사할 정보 (Ctrl+Alt+숫자) ---\n\n" + "\n".join(
            [f"{i+1}: {text}" for i, text in enumerate(self.texts)]
        )
        self.label = QLabel(display_text, self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.label.setStyleSheet("color: white; font-size: 20px; background-color: transparent; padding: 20px;")
        
        # 레이블 크기 및 위치 자동 조절
        self.label.setWordWrap(True)
        self.label.adjustSize()
        # 화면 중앙에 배치
        self.label.move(
            (self.width() - self.label.width()) // 2,
            (self.height() - self.label.height()) // 2
        )

    def copy_to_clipboard(self, index_str):
        """단축키 신호를 받아 클립보드에 텍스트를 복사하는 슬롯"""
        try:
            index = int(index_str) - 1  # 단축키는 1 기반, 리스트 인덱스는 0 기반
            if 0 <= index < len(self.texts):
                text_to_copy = self.texts[index]
                QApplication.clipboard().setText(text_to_copy)
                
                # 사용자에게 복사 완료 피드백
                self.label.setText(f"'{text_to_copy}'\n\n클립보드에 복사되었습니다.")
                # 2초 후에 원래 텍스트로 복원
                QTimer.singleShot(2000, self.restore_label_text)
        except (ValueError, IndexError):
            pass # 숫자가 아니거나 범위를 벗어나면 무시

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
        painter.fillRect(event.rect(), QColor(0, 0, 0, 60)) # 반투명 회색 배경

# --- 단축키가 눌렸을 때 호출될 함수 ---
def on_hotkey_pressed(index):
    return lambda: hotkey_emitter.emit_copy(str(index))

def on_toggle_pressed(): # 토글 함수 추가
    hotkey_emitter.emit_toggle()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # OverlayWindow 인스턴스를 먼저 생성해야 self.texts에 접근 가능
    overlay = OverlayWindow()

    # 전역 단축키 리스너 설정 (1부터 6까지)
    hotkeys = {
        f'<ctrl>+<alt>+{i+1}': on_hotkey_pressed(i+1) for i in range(len(overlay.texts))
    }
    # 토글 단축키 추가
    hotkeys['<ctrl>+<alt>+]'] = on_toggle_pressed
    
    hotkey_listener = keyboard.GlobalHotKeys(hotkeys)
    hotkey_listener.start() # 리스너를 별도 스레드에서 시작

    overlay.show()
    
    exit_code = app.exec()
    hotkey_listener.stop() # 애플리케이션 종료 시 리스너 중지
    sys.exit(exit_code)
