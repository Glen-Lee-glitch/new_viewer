import sys
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QLineEdit
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QColor
from pynput import keyboard

# ---------------------------------------------------------
# 역순 텍스트 변환 위젯 (overlay_test.py에서 가져옴)
# ---------------------------------------------------------

def reverse_text(text: str) -> str:
    """주어진 텍스트를 역순으로 반환합니다."""
    return text[::-1]

class ReverseLineEdit(QLineEdit):
    """클릭 시 텍스트를 역순으로 변환하고 클립보드에 복사하는 QLineEdit"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._original_stylesheet = self.styleSheet()
        if not self._original_stylesheet:
            # 스타일 변경: 검은색 반투명 배경, 흰색 글씨, 흰색 테두리, 폰트 강조
            self._original_stylesheet = """
                QLineEdit { 
                    border: 2px solid white; 
                    background-color: rgba(0, 0, 0, 200); 
                    color: white; 
                    font-weight: bold;
                    font-size: 14px;
                    border-radius: 5px;
                }
            """
        self.setPlaceholderText("텍스트 붙여넣기 (클릭)")
        self.setStyleSheet(self._original_stylesheet)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(40) # 높이를 조금 더 키워서 시인성 확보

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 클릭 시 윈도우를 활성화하여 포커스 확보
            if self.window():
                self.window().activateWindow()
            self.setFocus()
            
            current_text = self.text().strip()

            if not current_text:
                # 텍스트가 비어있으면: 그냥 포커스만 주고 끝 (사용자가 Ctrl+V 할 수 있게)
                super().mousePressEvent(event)
                return

            # 텍스트가 있으면: 역순으로 변환하고 클립보드에 복사
            reversed_text = reverse_text(current_text)
            self.setText(reversed_text)
            QApplication.clipboard().setText(reversed_text)

            # 성공 시 시각적 피드백
            self.setStyleSheet("border: 2px solid #00FF00; background-color: rgba(0, 255, 0, 100); color: white;")
            QTimer.singleShot(1000, self._remove_highlight)
            
            # 5초 뒤 텍스트 초기화
            QTimer.singleShot(5000, self.clear)
        else:
            super().mousePressEvent(event)

    def _remove_highlight(self):
        self.setStyleSheet(self._original_stylesheet)

class InputAwareOverlayWindow(QWidget):
    """ReverseLineEdit를 담는 작은 오버레이 창"""
    def __init__(self, parent=None):
        # parent를 None으로 강제하여 독립적인 윈도우로 만듦
        super().__init__(None) 
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool # Tool 플래그 추가: 작업표시줄 분리 및 독립성 확보
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.reverse_line_edit = ReverseLineEdit(self)
        self.reverse_line_edit.setFixedSize(250, 40)
        self.setFixedSize(self.reverse_line_edit.size())
        self.reverse_line_edit.move(0, 0)

    def show_at_position(self, x, y):
        self.move(x, y)
        self.show()
        self.raise_()

        # activateWindow() 제거

    def paintEvent(self, event):
        pass # 배경 투명

# ---------------------------------------------------------
# 기존 오버레이 로직
# ---------------------------------------------------------

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
        
        # 역순 변환 위젯 추가
        self.input_aware_overlay = InputAwareOverlayWindow()
        
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

        # 기존 정보 레이블 (col1 - 왼쪽)
        self.col1_label = QLabel("", self)
        self.col1_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.col1_label.setStyleSheet("color: white; font-size: 20px; background-color: rgba(0,0,0,100); padding: 20px; font-weight: bold; border-radius: 5px;")
        self.col1_label.setWordWrap(True)
        
        # 기존 정보 레이블 (col2 - 오른쪽)
        self.col2_label = QLabel("", self)
        self.col2_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.col2_label.setStyleSheet("color: white; font-size: 20px; background-color: rgba(0,0,0,100); padding: 20px; font-weight: bold; border-radius: 5px;")
        self.col2_label.setWordWrap(True)
        
        # 복사 메시지 레이블 (오른쪽, 초기에는 숨김)
        self.copy_message_label = QLabel("", self)
        self.copy_message_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.copy_message_label.setStyleSheet("color: white; font-size: 20spx; background-color: rgba(0,0,0,100); padding: 15px; font-weight: bold; border-radius: 5px;")
        self.copy_message_label.setWordWrap(True)
        self.copy_message_label.hide()
        
        # 초기 텍스트 설정
        self._update_display_text()
        
        # 역순 변환 위젯을 확실하게 최상단으로 올림
        QTimer.singleShot(100, lambda: self.input_aware_overlay.raise_())

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
                
                # 복사 완료 피드백을 오른쪽 레이블에 표시 (2초간)
                self.copy_message_label.setText(f"{text_to_copy}\n\n클립보드에 복사되었습니다.")
                self.copy_message_label.show()
                self.copy_message_label.adjustSize()
                self._update_label_positions()
                
                # 2초 후 메시지 숨김
                QTimer.singleShot(2000, self._hide_copy_message)

    def _split_text_into_columns(self, text):
        """텍스트를 항목 리스트로 파싱하고 두 열로 나눕니다.
        col1: 복사 가능한 항목들 (단축키가 있는 항목)
        col2: 나머지 항목들
        """
        if not text:
            return "", ""
        
        # 빈 줄로 구분된 항목들을 추출
        items = [item.strip() for item in text.split('\n\n') if item.strip()]
        
        # 항목들을 두 그룹으로 나누기
        col1_items = []  # 복사 가능한 항목들
        col2_items = []  # 나머지 항목들
        
        for item in items:
            # [Ctrl+Alt+숫자] 패턴이 있으면 복사 가능한 항목
            if '[Ctrl+Alt+' in item:
                col1_items.append(item)
            else:
                col2_items.append(item)
        
        return '\n\n'.join(col1_items), '\n\n'.join(col2_items)
    
    def _update_display_text(self):
        """현재 인덱스의 텍스트를 두 열로 나누어 표시합니다."""
        display_text = ""
        if self.texts:
            display_text = self.texts[self.current_index]
        
        col1_text, col2_text = self._split_text_into_columns(display_text)
        
        self.col1_label.setText(col1_text)
        self.col2_label.setText(col2_text)
        
        self.col1_label.adjustSize()
        self.col2_label.adjustSize()
        
        self._update_label_positions()
    
    def _update_label_positions(self):
        """레이블들의 위치를 업데이트합니다."""
        margin = 50  # 화면 끝 여백
        
        # col1 레이블 (복사 가능) - 좌측 상단
        self.col1_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        col1_x = margin
        col1_y = margin
        self.col1_label.move(col1_x, col1_y)
        
        # 역순 변환 위젯 위치 설정 (우측 상단)
        screen = QApplication.primaryScreen().geometry()
        input_overlay_x = screen.width() - self.input_aware_overlay.width() - margin
        input_overlay_y = margin
        self.input_aware_overlay.show_at_position(input_overlay_x, input_overlay_y)
        # 역순 변환 위젯을 메인 오버레이보다 확실히 위로 올림
        self.input_aware_overlay.raise_()
        self.input_aware_overlay.activateWindow()
        
        # col2 레이블 (나머지) - 우측 하단
        self.col2_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        col2_x = self.width() - self.col2_label.width() - margin
        col2_y = self.height() - self.col2_label.height() - margin
        self.col2_label.move(col2_x, col2_y)
        
        # 복사 메시지 레이블을 우측 하단 (col2 근처)에 배치
        if self.copy_message_label.isVisible():
            copy_label_x = self.width() - self.copy_message_label.width() - margin
            # col2의 바로 위에 표시
            copy_label_y = col2_y - self.copy_message_label.height() - 20
            self.copy_message_label.move(copy_label_x, copy_label_y)

    def _hide_copy_message(self):
        """복사 메시지를 숨깁니다."""
        self.copy_message_label.hide()
        self._update_label_positions()
    
    def navigate_text(self, direction):
        """방향키 신호를 받아 텍스트를 변경합니다."""
        if not self.texts:
            return
            
        if direction == 'next':
            self.current_index = (self.current_index + 1) % len(self.texts)
        elif direction == 'prev':
            self.current_index = (self.current_index - 1 + len(self.texts)) % len(self.texts)
        
        # 텍스트를 두 열로 나누어 업데이트
        self._update_display_text()

    def toggle_visibility(self):
        """단축키 신호를 받아 오버레이 창의 보이기/숨기기 상태를 토글합니다."""
        is_visible = not self.isVisible()
        self.setVisible(is_visible)
        self.input_aware_overlay.setVisible(is_visible)

    def paintEvent(self, event):
        """
        배경을 그리는 paintEvent를 오버라이드합니다.
        이제 전체 화면을 어둡게 하지 않고 완전히 투명하게 둡니다.
        """
        # 중앙 영역을 투명하게 하기 위해 전체 배경을 칠하는 코드를 제거합니다.
        # painter = QPainter(self)
        # painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # painter.fillRect(event.rect(), QColor(0, 0, 0, 10))
        pass

    def closeEvent(self, event):
        """Stops the hotkey listener when the window is closed."""
        if self.hotkey_listener:
            self.hotkey_listener.stop()
            self.hotkey_listener.join()
        self.input_aware_overlay.close() # 역순 변환 위젯도 함께 닫기
        super().closeEvent(event)
