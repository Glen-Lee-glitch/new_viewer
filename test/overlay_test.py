import sys
from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QPainter, QColor
from pynput import keyboard

# 단축키 입력을 Qt의 메인 스레드로 전달하기 위한 시그널 클래스
class HotkeyEmitter(QObject):
    change_text_signal = pyqtSignal(str)

    def emit_change(self, direction):
        self.change_text_signal.emit(direction)

# 전역 Emitter 인스턴스
hotkey_emitter = HotkeyEmitter()

class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        # 표시할 텍스트 목록
        self.texts = [
            "첫 번째 도움말 텍스트입니다.",
            "이것은 두 번째 정보입니다.",
            "마지막으로 세 번째 팁입니다."
        ]
        self.current_text_index = 0
        self.initUI()
        
        # 시그널과 텍스트 변경 함수(슬롯) 연결
        hotkey_emitter.change_text_signal.connect(self.change_text)

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

        # 오버레이에 표시될 텍스트 레이블 (첫 번째 텍스트로 초기화)
        self.label = QLabel(self.texts[self.current_text_index], self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color: white; font-size: 24px; background-color: rgba(0,0,0,100); padding: 10px; border-radius: 5px;")
        
        # 레이블 위치 계산
        label_width = 800
        label_height = 100
        self.label.setGeometry(
            (self.width() - label_width) // 2, 
            (self.height() - label_height) // 2, 
            label_width, 
            label_height
        )

    def change_text(self, direction):
        """단축키 신호를 받아 텍스트를 변경하는 슬롯"""
        if direction == 'next':
            self.current_text_index = (self.current_text_index + 1) % len(self.texts)
        elif direction == 'prev':
            self.current_text_index = (self.current_text_index - 1 + len(self.texts)) % len(self.texts)
        
        self.label.setText(self.texts[self.current_text_index])

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(event.rect(), QColor(0, 0, 0, 60)) # 반투명 회색 배경

# --- 단축키가 눌렸을 때 호출될 함수들 ---
def on_next_text():
    hotkey_emitter.emit_change('next')

def on_prev_text():
    hotkey_emitter.emit_change('prev')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # 전역 단축키 리스너 설정
    hotkey_listener = keyboard.GlobalHotKeys({
        '<ctrl>+<alt>+<right>': on_next_text,
        '<ctrl>+<alt>+<left>': on_prev_text
    })
    hotkey_listener.start() # 리스너를 별도 스레드에서 시작

    overlay = OverlayWindow()
    overlay.show()
    
    exit_code = app.exec()
    hotkey_listener.stop() # 애플리케이션 종료 시 리스너 중지
    sys.exit(exit_code)
