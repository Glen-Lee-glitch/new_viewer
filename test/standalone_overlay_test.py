import sys
import pandas as pd
import pymysql
from contextlib import closing
from datetime import datetime

# pynput은 GUI와 별도로 작동하므로, import 실패 시 바로 알려주는 것이 좋음
try:
    from pynput import keyboard
except ImportError:
    print("="*50)
    print("ERROR: pynput 라이브러리를 찾을 수 없습니다.")
    print("터미널에서 'pip install pynput' 명령어로 설치해주세요.")
    print("="*50)
    sys.exit()

from PyQt6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QMessageBox, QWidget)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer


# ---------------------------------------------------------
# 1. DB Configuration & Manager
# ---------------------------------------------------------
DB_CONFIG = {
    'host': '192.168.0.114',
    'port': 3306,
    'user': 'my_pc_user',
    'password': '!Qdhdbrclf56',
    'db': 'greetlounge',
    'charset': 'utf8mb4',
    'connect_timeout': 5 # 연결 타임아웃 5초
}

def test_db_connection():
    """DB 연결을 테스트하고 결과를 반환합니다."""
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            return True, f"DB 연결 성공! (서버: {DB_CONFIG['host']})"
    except Exception as e:
        return False, f"DB 연결 실패:\n{e}"

def fetch_preprocessed_data(worker_name: str) -> pd.DataFrame:
    """preprocessed_data 테이블에서 특정 신청자(worker_name)의 데이터를 조회한다."""
    if not worker_name:
        return pd.DataFrame()
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = "SELECT * FROM preprocessed_data WHERE 신청자 = %s"
            print(f"Executing query: {query % worker_name}") # 디버깅용 쿼리 출력
            df = pd.read_sql(query, connection, params=(worker_name,))
            return df
    except Exception as e:
        # 오류를 그냥 출력하는 대신, 예외를 발생시켜 호출한 쪽에서 처리하도록 함
        raise ConnectionError(f"데이터 조회 중 오류 발생:\n{e}")

# ---------------------------------------------------------
# 2. Overlay Logic (from widgets/helper_overlay.py)
# ---------------------------------------------------------
class HotkeyEmitter(QObject):
    copy_signal = pyqtSignal(int)
    toggle_overlay_signal = pyqtSignal()
    navigate_signal = pyqtSignal(str)

    def emit_copy(self, index): self.copy_signal.emit(index)
    def emit_toggle(self): self.toggle_overlay_signal.emit()
    def emit_navigate(self, direction): self.navigate_signal.emit(direction)

class OverlayWindow(QWidget):
    def __init__(self, texts, copy_data=None, parent=None):
        super().__init__(parent)
        self.texts = texts
        self.copy_data = copy_data or []
        self.current_index = 0
        self.hotkey_listener = None
        self.hotkey_emitter = HotkeyEmitter()
        
        self.initUI()
        
        self.hotkey_emitter.copy_signal.connect(self.copy_to_clipboard)
        self.hotkey_emitter.toggle_overlay_signal.connect(self.toggle_visibility)
        self.hotkey_emitter.navigate_signal.connect(self.navigate_text)

        self.setup_hotkeys()

    def initUI(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(QApplication.primaryScreen().geometry())

        label_style = "color: white; font-size: 20px; background-color: rgba(0,0,0,100); padding: 20px; font-weight: bold; border-radius: 5px;"
        
        self.col1_label = QLabel("", self)
        self.col1_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.col1_label.setStyleSheet(label_style)
        self.col1_label.setWordWrap(True)
        
        self.col2_label = QLabel("", self)
        self.col2_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.col2_label.setStyleSheet(label_style)
        self.col2_label.setWordWrap(True)
        
        self.copy_message_label = QLabel("", self)
        self.copy_message_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.copy_message_label.setStyleSheet("color: white; font-size: 20px; background-color: rgba(0,0,0,100); padding: 15px; font-weight: bold; border-radius: 5px;")
        self.copy_message_label.setWordWrap(True)
        self.copy_message_label.hide()
        
        self._update_display_text()

    def setup_hotkeys(self):
        hotkeys = {
            '<ctrl>+<alt>+<right>': self._on_navigate_pressed('next'),
            '<ctrl>+<alt>+<left>': self._on_navigate_pressed('prev'),
            '<ctrl>+<alt>+]': self._on_toggle_pressed
        }
        
        if self.copy_data and len(self.copy_data) > 0:
            max_copy_count = max(len(d) for d in self.copy_data if d) if self.copy_data else 0
            for i in range(1, min(max_copy_count + 1, 9)):
                hotkeys[f'<ctrl>+<alt>+{i}'] = self._on_copy_pressed(i - 1)
        
        self.hotkey_listener = keyboard.GlobalHotKeys(hotkeys)
        self.hotkey_listener.start()

    def _on_navigate_pressed(self, direction): return lambda: self.hotkey_emitter.emit_navigate(direction)
    def _on_copy_pressed(self, index): return lambda: self.hotkey_emitter.emit_copy(index)
    def _on_toggle_pressed(self): self.hotkey_emitter.emit_toggle()

    def copy_to_clipboard(self, index):
        if not self.copy_data or self.current_index >= len(self.copy_data): return
        
        current_copy_list = self.copy_data[self.current_index]
        if 0 <= index < len(current_copy_list):
            text_to_copy = current_copy_list[index]
            if text_to_copy:
                QApplication.clipboard().setText(text_to_copy)
                self.copy_message_label.setText(f"'{text_to_copy}'\n복사 완료")
                self.copy_message_label.show()
                self.copy_message_label.adjustSize()
                self._update_label_positions()
                QTimer.singleShot(2000, self._hide_copy_message)

    def _split_text_into_columns(self, text):
        if not text: return "", ""
        items = [item.strip() for item in text.split('\n\n') if item.strip()]
        col1 = '\n\n'.join([item for item in items if '[Ctrl+Alt+' in item])
        col2 = '\n\n'.join([item for item in items if '[Ctrl+Alt+' not in item])
        return col1, col2
    
    def _update_display_text(self):
        display_text = self.texts[self.current_index] if self.texts else ""
        col1_text, col2_text = self._split_text_into_columns(display_text)
        self.col1_label.setText(col1_text)
        self.col2_label.setText(col2_text)
        self.col1_label.adjustSize()
        self.col2_label.adjustSize()
        self._update_label_positions()
    
    def _update_label_positions(self):
        margin = 50
        self.col1_label.move(margin, margin)
        col2_x = self.width() - self.col2_label.width() - margin
        col2_y = self.height() - self.col2_label.height() - margin
        self.col2_label.move(col2_x, col2_y)
        if self.copy_message_label.isVisible():
            copy_x = self.width() - self.copy_message_label.width() - margin
            copy_y = col2_y - self.copy_message_label.height() - 20
            self.copy_message_label.move(copy_x, copy_y)

    def _hide_copy_message(self): self.copy_message_label.hide()
    
    def navigate_text(self, direction):
        if not self.texts: return
        if direction == 'next': self.current_index = (self.current_index + 1) % len(self.texts)
        else: self.current_index = (self.current_index - 1 + len(self.texts)) % len(self.texts)
        self._update_display_text()

    def toggle_visibility(self): self.setVisible(not self.isVisible())

    def closeEvent(self, event):
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        super().closeEvent(event)

# ---------------------------------------------------------
# 3. Main Tester Dialog
# ---------------------------------------------------------
class TestLauncher(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EV Helper Overlay Tester")
        self.resize(400, 200)
        self.overlay = None
        self._overlay_texts = []
        self._overlay_copy_data = []
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        form_layout = QHBoxLayout()
        form_layout.addWidget(QLabel("작업자 이름(신청자):"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("DB '신청자' 컬럼의 이름")
        form_layout.addWidget(self.name_input)
        layout.addLayout(form_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        self.test_db_btn = QPushButton("1. DB 연결 테스트")
        self.test_db_btn.clicked.connect(self.check_db)
        btn_layout.addWidget(self.test_db_btn)

        self.run_btn = QPushButton("2. 오버레이 실행")
        self.run_btn.clicked.connect(self.run_overlay)
        btn_layout.addWidget(self.run_btn)
        layout.addLayout(btn_layout)

        info_label = QLabel("단축키:\n- 토글: Ctrl+Alt+]\n- 이동: Ctrl+Alt+방향키(좌/우)\n- 복사: Ctrl+Alt+숫자(1~8)")
        info_label.setStyleSheet("color: gray; padding-top: 10px;")
        layout.addWidget(info_label)
        
        self.setLayout(layout)

    def check_db(self):
        """DB 연결 테스트 버튼 클릭 시 호출"""
        success, message = test_db_connection()
        if success:
            QMessageBox.information(self, "DB 연결", message)
        else:
            QMessageBox.critical(self, "DB 연결", message)

    def _format_date_value(self, value: str) -> str:
        if not value or pd.isna(value) or str(value).lower() in ['nan', 'none']: return ""
        val_str = str(value)
        formats = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M', '%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d']
        for fmt in formats:
            try: return datetime.strptime(val_str.strip(), fmt).strftime('%Y-%m-%d')
            except ValueError: continue
        return val_str

    def process_data(self, df):
        """데이터프레임을 오버레이용 텍스트/데이터로 변환"""
        self._overlay_texts, self._overlay_copy_data = [], []
        
        # ... (기존 로직과 동일, 간결하게 재구성)
        display_cols = ['주문시간', '성명', '생년월일', '성별', '신청차종', '출고예정일', '주소1', '주소2', '전화', '휴대폰', '이메일', '신청유형', '우선순위', 'RN']
        optional_cols = ['사업자번호', '사업자명', '다자녀수', '공동명의자', '공동생년월일']
        date_cols = ['생년월일', '주문시간', '출고예정일', '공동생년월일']
        copy_cols = ['성명', '주소1', '주소2', '전화', '휴대폰', '이메일']

        for _, row in df.iterrows():
            lines, copy_values = [], []
            has_joint = '공동명의자' in row and pd.notna(row['공동명의자']) and str(row['공동명의자']).strip() not in ['', 'nan', 'None']
            
            shortcut_map = {col: i + 1 for i, col in enumerate(copy_cols)}
            if has_joint: shortcut_map['공동명의자'] = 7
            shortcut_map['RN'] = 8 if has_joint else 7

            all_cols = display_cols + [c for c in optional_cols if c in row and pd.notna(row[c]) and str(row[c]).strip() not in ['', 'nan', 'None']]
            
            for col in all_cols:
                if col in row and pd.notna(row[col]):
                    val = str(row[col]).strip()
                    if val in ['', 'nan', 'None']: continue
                    
                    val = self._format_date_value(val) if col in date_cols else val
                    
                    if col in shortcut_map: lines.append(f"[Ctrl+Alt+{shortcut_map[col]}] {col}: {val}")
                    else: lines.append(f"{col}: {val}")

            self._overlay_texts.append('\n\n'.join(lines))
            
            copy_values.extend([str(row.get(c, '') or '').strip() for c in copy_cols])
            if has_joint: copy_values.append(str(row['공동명의자']).strip())
            copy_values.append(str(row.get('RN', '') or '').strip())
            self._overlay_copy_data.append(copy_values)

    def run_overlay(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "입력 오류", "이름을 입력해주세요.")
            return

        if self.overlay and self.overlay.isVisible():
            self.overlay.close()
        
        try:
            df = fetch_preprocessed_data(name)
            if df.empty:
                QMessageBox.information(self, "결과", f"'{name}'에 대한 데이터가 없습니다.\nDB의 '신청자' 컬럼을 확인해주세요.")
                return
            
            self.process_data(df)
            
            if self._overlay_texts:
                self.overlay = OverlayWindow(self._overlay_texts, self._overlay_copy_data)
                self.overlay.show()
            else:
                QMessageBox.warning(self, "결과", "오버레이에 표시할 유효한 데이터가 없습니다.")
                
        except Exception as e:
            QMessageBox.critical(self, "실행 오류", f"오버레이 실행 중 오류가 발생했습니다:\n{e}")

    def closeEvent(self, event):
        if self.overlay:
            self.overlay.close()
        super().closeEvent(event)

if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        launcher = TestLauncher()
        launcher.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"프로그램 실행 중 심각한 오류 발생: {e}")
