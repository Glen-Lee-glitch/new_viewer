import sys
import pandas as pd
import pymysql
from contextlib import closing
from datetime import datetime
import time
import os
from PyQt6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QMessageBox, QWidget, QFileDialog)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from pynput import keyboard


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
    'connect_timeout': 5
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
            print(f"Executing query: {query % worker_name}")
            df = pd.read_sql(query, connection, params=(worker_name,))
            return df
    except Exception as e:
        raise ConnectionError(f"데이터 조회 중 오류 발생:\n{e}")

# ---------------------------------------------------------
# 2. 역순 텍스트 변환 위젯
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
        self.setFixedHeight(40)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.window():
                self.window().activateWindow()
            self.setFocus()
            
            current_text = self.text().strip()
            if not current_text:
                super().mousePressEvent(event)
                return

            reversed_text = reverse_text(current_text)
            self.setText(reversed_text)
            QApplication.clipboard().setText(reversed_text)

            self.setStyleSheet("border: 2px solid #00FF00; background-color: rgba(0, 255, 0, 100); color: white;")
            QTimer.singleShot(1000, self._remove_highlight)
            QTimer.singleShot(5000, self.clear)
        else:
            super().mousePressEvent(event)

    def _remove_highlight(self):
        self.setStyleSheet(self._original_stylesheet)

class InputAwareOverlayWindow(QWidget):
    """ReverseLineEdit를 담는 작은 오버레이 창"""
    def __init__(self, parent=None):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
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

    def paintEvent(self, event):
        pass

# ---------------------------------------------------------
# 3. Overlay Logic
# ---------------------------------------------------------
class HotkeyEmitter(QObject):
    copy_signal = pyqtSignal(int)
    copy_all_signal = pyqtSignal()
    toggle_overlay_signal = pyqtSignal()
    navigate_signal = pyqtSignal(str)
    close_overlay_signal = pyqtSignal()

    def emit_copy(self, index): self.copy_signal.emit(index)
    def emit_copy_all(self): self.copy_all_signal.emit()
    def emit_toggle(self): self.toggle_overlay_signal.emit()
    def emit_navigate(self, direction): self.navigate_signal.emit(direction)
    def emit_close(self): self.close_overlay_signal.emit()

class OverlayWindow(QWidget):
    closed_signal = pyqtSignal()
    
    def __init__(self, texts, copy_data=None, order_list=None, order_per_item=None, parent=None):
        super().__init__(parent)
        self.texts = texts
        self.copy_data = copy_data or []
        self.order_list = order_list or []
        self.order_per_item = order_per_item or []
        self.current_index = 0
        self.hotkey_listener = None
        self.hotkey_emitter = HotkeyEmitter()
        
        self.input_aware_overlay = InputAwareOverlayWindow()
        
        self.initUI()
        
        self.hotkey_emitter.copy_signal.connect(self.copy_to_clipboard)
        self.hotkey_emitter.copy_all_signal.connect(self.copy_all_to_clipboard_history)
        self.hotkey_emitter.toggle_overlay_signal.connect(self.toggle_visibility)
        self.hotkey_emitter.navigate_signal.connect(self.navigate_text)
        self.hotkey_emitter.close_overlay_signal.connect(self.close_overlay_completely)

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

        # 순서 표시 레이블 (맨 위 상단 중앙)
        self.order_label = QLabel("", self)
        self.order_label.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop)
        self.order_label.setStyleSheet("color: white; font-size: 18px; background-color: rgba(0,0,0,150); padding: 15px; font-weight: bold; border-radius: 5px;")
        self.order_label.setWordWrap(True)
        self.order_label.setTextFormat(Qt.TextFormat.RichText)

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
        
        self._update_order_display()
        self._update_display_text()
        QTimer.singleShot(100, lambda: self.input_aware_overlay.raise_())

    def setup_hotkeys(self):
        hotkeys = {
            '<ctrl>+<alt>+<right>': self._on_navigate_pressed('next'),
            '<ctrl>+<alt>+<left>': self._on_navigate_pressed('prev'),
            '<ctrl>+<alt>+]': self._on_toggle_pressed,
            '<ctrl>+<alt>+[': self._on_copy_all_pressed,
            '<ctrl>+<alt>+/': self._on_close_pressed
        }
        
        if self.copy_data and len(self.copy_data) > 0:
            max_copy_count = max(len(d) for d in self.copy_data if d) if self.copy_data else 0
            for i in range(1, min(max_copy_count + 1, 9)):
                hotkeys[f'<ctrl>+<alt>+{i}'] = self._on_copy_pressed(i - 1)
        
        self.hotkey_listener = keyboard.GlobalHotKeys(hotkeys)
        self.hotkey_listener.start()

    def _on_navigate_pressed(self, direction): return lambda: self.hotkey_emitter.emit_navigate(direction)
    def _on_copy_pressed(self, index): return lambda: self.hotkey_emitter.emit_copy(index)
    def _on_copy_all_pressed(self): self.hotkey_emitter.emit_copy_all()
    def _on_toggle_pressed(self): self.hotkey_emitter.emit_toggle()
    def _on_close_pressed(self): self.hotkey_emitter.emit_close()

    def copy_to_clipboard(self, index):
        if not self.copy_data or self.current_index >= len(self.copy_data): return
        
        current_copy_list = self.copy_data[self.current_index]
        if 0 <= index < len(current_copy_list):
            text_to_copy = current_copy_list[index]
            if text_to_copy:
                QApplication.clipboard().setText(text_to_copy)
                self.copy_message_label.setText(f"{text_to_copy}\n\n클립보드에 복사되었습니다.")
                self.copy_message_label.show()
                self.copy_message_label.adjustSize()
                self._update_label_positions()
                QTimer.singleShot(2000, self._hide_copy_message)

    def copy_all_to_clipboard_history(self):
        """현재 항목의 모든 데이터를 역순으로 복사하여 클립보드 히스토리에 쌓습니다."""
        if not self.copy_data or self.current_index >= len(self.copy_data): return
        
        current_copy_list = self.copy_data[self.current_index]
        
        # 값이 있는 항목만 추출 (인덱스, 텍스트)
        items_to_copy = [(i, text) for i, text in enumerate(current_copy_list) if text]
        
        if not items_to_copy: return

        clipboard = QApplication.clipboard()
        total = len(items_to_copy)
        
        # 역순으로 복사 (큰 번호 -> 작은 번호)
        for step, (i, text) in enumerate(reversed(items_to_copy)):
            # 1. UI 갱신: 현재 어떤 항목을 복사 중인지 표시
            # (사용자가 멈춘 것으로 착각하지 않게 함)
            msg = f"클립보드 기록 저장 중... ({step+1}/{total})\n값: {text}"
            self.copy_message_label.setText(msg)
            self.copy_message_label.show()
            self.copy_message_label.adjustSize()
            self._update_label_positions()
            QApplication.processEvents()

            # 2. 클립보드 설정
            clipboard.setText(text)
            
            # 3. 안정적인 대기 (0.8초)
            # 윈도우 클립보드 히스토리가 락을 걸고 데이터를 저장할 시간을 충분히 줌
            # time.sleep만 쓰면 앱이 얼어버려서 윈도우 메시지 처리가 안 될 수 있음 -> processEvents 루프 사용
            end_time = time.time() + 0.8
            while time.time() < end_time:
                QApplication.processEvents()
                time.sleep(0.05)

        # 완료 메시지
        self.copy_message_label.setText(f"{total}개 항목 저장 완료!\n(Win + V 로 확인)")
        self.copy_message_label.adjustSize()
        self._update_label_positions()
        QTimer.singleShot(2000, self._hide_copy_message)

    def _split_text_into_columns(self, text):
        if not text: return "", ""
        items = [item.strip() for item in text.split('\n\n') if item.strip()]
        col1 = '\n\n'.join([item for item in items if '[Ctrl+Alt+' in item])
        col2 = '\n\n'.join([item for item in items if '[Ctrl+Alt+' not in item])
        return col1, col2
    
    def _update_order_display(self):
        """순서 리스트를 표시 형식으로 변환하여 레이블에 설정합니다. 현재 항목의 순서를 하이라이트합니다."""
        if self.order_list:
            current_order = None
            if self.current_index < len(self.order_per_item):
                current_order = self.order_per_item[self.current_index]
            
            order_parts = []
            for order in self.order_list:
                order_str = str(order)
                if current_order is not None and order == current_order:
                    order_str = f'<span style="background-color: #39FF14; color: #000000; font-weight: bold; padding: 2px 6px; border-radius: 3px;">{order_str}</span>'
                order_parts.append(order_str)
            
            order_text = " -> ".join(order_parts)
            html_text = f"본인 작업의 순서:<br>{order_text}"
            self.order_label.setText(html_text)
        else:
            self.order_label.setText("")
        self.order_label.adjustSize()
        if self.order_label.text():
            order_x = (self.width() - self.order_label.width()) // 2
            order_y = 50
            self.order_label.move(order_x, order_y)
            self.order_label.show()
        else:
            self.order_label.hide()
    
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
        
        if self.order_label.text():
            order_x = (self.width() - self.order_label.width()) // 2
            order_y = margin
            self.order_label.move(order_x, order_y)
            self.order_label.show()
        else:
            self.order_label.hide()
        
        self.col1_label.move(margin, margin + (self.order_label.height() + 20 if self.order_label.text() else 0))
        
        screen = QApplication.primaryScreen().geometry()
        input_overlay_x = screen.width() - self.input_aware_overlay.width() - margin
        input_overlay_y = margin
        self.input_aware_overlay.show_at_position(input_overlay_x, input_overlay_y)
        self.input_aware_overlay.raise_()
        self.input_aware_overlay.activateWindow()
        
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
        self._update_order_display()

    def toggle_visibility(self):
        is_visible = not self.isVisible()
        self.setVisible(is_visible)
        self.input_aware_overlay.setVisible(is_visible)
    
    def close_overlay_completely(self):
        self.closed_signal.emit()
        self.close()

    def closeEvent(self, event):
        if self.hotkey_listener:
            self.hotkey_listener.stop()
            self.hotkey_listener.join()
        self.input_aware_overlay.close()
        super().closeEvent(event)

# ---------------------------------------------------------
# 4. Main Tester Dialog
# ---------------------------------------------------------
class TestLauncher(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EV Helper Overlay Tester")
        self.resize(400, 200)
        self.overlay = None
        self._overlay_texts = []
        self._overlay_copy_data = []
        self._overlay_order_list = []
        self._overlay_order_per_item = []
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        form_layout = QHBoxLayout()
        form_layout.addWidget(QLabel("작업자 이름(신청자):"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("DB '신청자' 컬럼의 이름")
        form_layout.addWidget(self.name_input)
        layout.addLayout(form_layout)

        excel_layout = QHBoxLayout()
        excel_layout.addWidget(QLabel("엑셀 파일 경로:"))
        self.excel_path_input = QLineEdit()
        self.excel_path_input.setPlaceholderText("업로드할 엑셀 파일 경로")
        self.excel_path_input.setReadOnly(True)
        excel_layout.addWidget(self.excel_path_input)
        
        self.select_excel_btn = QPushButton("파일 선택")
        self.select_excel_btn.clicked.connect(self.open_excel_file)
        excel_layout.addWidget(self.select_excel_btn)
        layout.addLayout(excel_layout)

        excel_upload_btn_layout = QHBoxLayout()
        self.upload_excel_btn = QPushButton("3. 엑셀 DB에 업로드")
        self.upload_excel_btn.clicked.connect(self.upload_excel_to_db)
        excel_upload_btn_layout.addWidget(self.upload_excel_btn)
        layout.addLayout(excel_upload_btn_layout)

        btn_layout = QHBoxLayout()
        self.test_db_btn = QPushButton("1. DB 연결 테스트")
        self.test_db_btn.clicked.connect(self.check_db)
        btn_layout.addWidget(self.test_db_btn)

        self.run_btn = QPushButton("2. 오버레이 실행")
        self.run_btn.clicked.connect(self.run_overlay)
        btn_layout.addWidget(self.run_btn)
        layout.addLayout(btn_layout)

        info_label = QLabel("단축키:\n- 토글: Ctrl+Alt+]\n- 전체복사: Ctrl+Alt+[\n- 이동: Ctrl+Alt+방향키(좌/우)\n- 복사: Ctrl+Alt+숫자(1~8)\n- 완전히 닫기: Ctrl+Alt+/")
        info_label.setStyleSheet("color: gray; padding-top: 10px;")
        layout.addWidget(info_label)
        
        self.setLayout(layout)

    def check_db(self):
        success, message = test_db_connection()
        if success:
            QMessageBox.information(self, "DB 연결", message)
        else:
            QMessageBox.critical(self, "DB 연결", message)

    def open_excel_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "엑셀 파일 선택", "", "Excel Files (*.xlsx *.xls)")
        if file_path:
            self.excel_path_input.setText(file_path)

    def upload_excel_to_db(self):
        excel_path = self.excel_path_input.text().strip()
        if not excel_path:
            QMessageBox.warning(self, "입력 오류", "엑셀 파일 경로를 입력해주세요.")
            return
        
        if not os.path.exists(excel_path):
            QMessageBox.warning(self, "파일 없음", "지정된 엑셀 파일이 존재하지 않습니다.")
            return
            
        try:
            df = pd.read_excel(excel_path)
            if df.empty:
                QMessageBox.information(self, "엑셀 데이터", "엑셀 파일에 데이터가 없습니다.")
                return
            
            mapped_df = map_to_table_columns(df)
            
            if mapped_df.empty:
                QMessageBox.information(self, "매핑 데이터", "매핑된 데이터가 없습니다. 엑셀 컬럼을 확인해주세요.")
                return

            if insert_to_database(mapped_df):
                QMessageBox.information(self, "업로드 성공", "엑셀 데이터가 성공적으로 데이터베이스에 업로드되었습니다.")
            else:
                QMessageBox.critical(self, "업로드 실패", "엑셀 데이터 업로드 중 오류가 발생했습니다.")

        except Exception as e:
            QMessageBox.critical(self, "처리 오류", f"엑셀 처리 중 오류가 발생했습니다:\n{e}")

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
        self._overlay_texts = []
        self._overlay_copy_data = []
        
        # 순서 데이터 수집
        order_list = []
        if '순서' in df.columns:
            for _, row in df.iterrows():
                order_value = row['순서']
                if pd.notna(order_value) and order_value is not None:
                    try:
                        order_int = int(order_value)
                        if order_int not in order_list:
                            order_list.append(order_int)
                    except (ValueError, TypeError):
                        pass
            order_list.sort()
        
        display_cols = ['주문시간', '성명', '생년월일', '성별', '신청차종', '출고예정일', '주소1', '주소2', '전화', '휴대폰', '이메일', '신청유형', '우선순위', 'RN', '보조금']
        optional_cols = ['다자녀수', '공동명의자', '공동생년월일']
        date_cols = ['생년월일', '주문시간', '출고예정일', '공동생년월일']
        base_copy_cols = ['성명', '주소1', '주소2', '전화', '휴대폰', '이메일']

        for _, row in df.iterrows():
            lines, copy_values = [], []
            
            # 현재 항목의 순서 저장
            item_order = None
            if '순서' in df.columns:
                order_value = row['순서']
                if pd.notna(order_value) and order_value is not None:
                    try:
                        item_order = int(order_value)
                    except (ValueError, TypeError):
                        pass
            self._overlay_order_per_item.append(item_order)
            
            has_joint = '공동명의자' in row and pd.notna(row['공동명의자']) and str(row['공동명의자']).strip() not in ['', 'nan', 'None']
            
            # 사업자번호/사업자명 존재 여부 확인
            has_business_num = False
            has_business_name = False
            business_num_value = ''
            business_name_value = ''
            
            if '사업자번호' in df.columns:
                business_num_value = str(row['사업자번호']).strip()
                if business_num_value and business_num_value != 'nan' and business_num_value != 'None' and business_num_value != '':
                    has_business_num = True
            
            if '사업자명' in df.columns:
                business_name_value = str(row['사업자명']).strip()
                if business_name_value and business_name_value != 'nan' and business_name_value != 'None' and business_name_value != '':
                    has_business_name = True
            
            # 동적 복사 칼럼 리스트 생성
            dynamic_copy_columns = ['성명']
            if has_business_num:
                dynamic_copy_columns.append('사업자번호')
            if has_business_name:
                dynamic_copy_columns.append('사업자명')
            dynamic_copy_columns.extend(['주소1', '주소2', '전화', '휴대폰', '이메일'])
            
            # 단축키 매핑 생성
            copy_column_to_shortcut = {}
            shortcut_num = 1
            for col in dynamic_copy_columns:
                copy_column_to_shortcut[col] = shortcut_num
                shortcut_num += 1
            
            if has_joint:
                copy_column_to_shortcut['공동명의자'] = shortcut_num
                shortcut_num += 1
            
            copy_column_to_shortcut['RN'] = shortcut_num
            
            # 필수 표시 칼럼 처리
            for col in display_cols:
                if col in df.columns:
                    value = str(row[col]).strip()
                    if value and value != 'nan' and value != 'None':
                        if col in date_cols:
                            value = self._format_date_value(value)
                        if col in copy_column_to_shortcut:
                            shortcut_num = copy_column_to_shortcut[col]
                            lines.append(f"[Ctrl+Alt+{shortcut_num}] {col}: {value}")
                        else:
                            lines.append(f"{col}: {value}")
            
            # 사업자번호/사업자명 처리
            if has_business_num:
                shortcut_num = copy_column_to_shortcut.get('사업자번호', 2)
                lines.append(f"[Ctrl+Alt+{shortcut_num}] 사업자번호: {business_num_value}")
            
            if has_business_name:
                shortcut_num = copy_column_to_shortcut.get('사업자명', 3)
                lines.append(f"[Ctrl+Alt+{shortcut_num}] 사업자명: {business_name_value}")
            
            # 선택적 칼럼 처리
            for col in optional_cols:
                if col in df.columns:
                    value = str(row[col]).strip()
                    if value and value != 'nan' and value != 'None' and value != '':
                        if col in date_cols:
                            value = self._format_date_value(value)
                        if col in copy_column_to_shortcut:
                            shortcut_num = copy_column_to_shortcut[col]
                            lines.append(f"[Ctrl+Alt+{shortcut_num}] {col}: {value}")
                        else:
                            lines.append(f"{col}: {value}")
            
            self._overlay_texts.append('\n\n'.join(lines))
            
            # 복사 가능한 칼럼 데이터 생성
            for col in dynamic_copy_columns:
                if col in df.columns:
                    value = str(row[col]).strip()
                    if value and value != 'nan' and value != 'None':
                        copy_values.append(value)
                    else:
                        copy_values.append('')
                else:
                    copy_values.append('')
            
            if has_joint:
                copy_values.append(str(row['공동명의자']).strip())
            
            if 'RN' in df.columns:
                rn_value = str(row['RN']).strip()
                if rn_value and rn_value != 'nan' and rn_value != 'None':
                    copy_values.append(rn_value)
            
            self._overlay_copy_data.append(copy_values)
        
        self._overlay_order_list = order_list

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
                self.overlay = OverlayWindow(
                    texts=self._overlay_texts, 
                    copy_data=self._overlay_copy_data,
                    order_list=self._overlay_order_list,
                    order_per_item=self._overlay_order_per_item
                )
                self.overlay.closed_signal.connect(self._on_overlay_closed)
                self.overlay.show()
                self.hide()
            else:
                QMessageBox.warning(self, "결과", "오버레이에 표시할 유효한 데이터가 없습니다.")
                
        except Exception as e:
            QMessageBox.critical(self, "실행 오류", f"오버레이 실행 중 오류가 발생했습니다:\n{e}")
    
    def _on_overlay_closed(self):
        """오버레이가 완전히 닫혔을 때 호출되는 메서드"""
        self.overlay = None
        self.show()
        self.activateWindow()

    def closeEvent(self, event):
        if self.overlay:
            self.overlay.close()
        super().closeEvent(event)

# ---------------------------------------------------------
# Excel Upload Logic
# ---------------------------------------------------------

TABLE_COLUMNS = [
    "순서", "신청자", "전처리", "지역", "RN", "주문시간", "성명", "생년월일", "성별",
    "사업자번호", "사업자명", "신청차종", "출고예정일", "주소1", "주소2", "전화",
    "휴대폰", "이메일", "신청유형", "우선순위", "다자녀수", "공동명의자", "공동생년월일", "보조금",
]

EXCEL_TO_TABLE = {
    "순서": "순서", "신청자": "신청자", "전처리": "전처리", "지역": "지역",
    "RN번호": "RN", "주문시간": "주문시간", "성명(대표자)": "성명",
    "생년월일(법인번호)": "생년월일", "성별": "성별", "사업자번호": "사업자번호",
    "사업자명": "사업자명", "신청차종": "신청차종", "출고예정일": "출고예정일",
    "주소1": "주소1", "주소2": "주소2", "전화": "전화", "휴대폰": "휴대폰",
    "이메일": "이메일", "신청유형": "신청유형", "우선순위": "우선순위",
    "다자녀수": "다자녀수", "공동명의자": "공동명의자", "공동 생년월일": "공동생년월일",
    "보조금": "보조금",
}

def to_text_date(value: object) -> str | None:
    if pd.isna(value):
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d")
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        parsed = pd.to_datetime(text_value, errors="raise")
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return text_value

def to_int(value: object) -> int | None:
    if pd.isna(value):
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None

def map_to_table_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    mapped = {}
    missing_columns = []

    for excel_col, table_col in EXCEL_TO_TABLE.items():
        if excel_col not in dataframe.columns:
            missing_columns.append((excel_col, table_col))
            continue

        series = dataframe[excel_col]

        if excel_col == "순서":
            mapped[table_col] = series.apply(to_int)
        elif excel_col == "생년월일(법인번호)":
            mapped[table_col] = series.apply(to_text_date)
        elif excel_col == "공동 생년월일":
            mapped[table_col] = series.apply(to_text_date)
        elif excel_col == "다자녀수":
            mapped[table_col] = series.apply(to_int)
        elif excel_col == "보조금":
            mapped[table_col] = series.apply(to_int)
        elif excel_col == "주문시간":
            mapped[table_col] = series.dt.strftime("%Y-%m-%d") if pd.api.types.is_datetime64_any_dtype(series) else series
        elif excel_col == "출고예정일":
            mapped[table_col] = series.dt.strftime("%Y-%m-%d") if pd.api.types.is_datetime64_any_dtype(series) else series
        else:
            mapped[table_col] = series

    mapped_df = pd.DataFrame(mapped)
    return mapped_df

def insert_to_database(dataframe: pd.DataFrame) -> bool:
    if dataframe.empty:
        print("삽입할 데이터가 없습니다.")
        return False
    
    insert_columns = [col for col in TABLE_COLUMNS if col in dataframe.columns]
    
    if not insert_columns:
        print("삽입할 칼럼이 없습니다.")
        return False
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            with connection.cursor() as cursor:
                columns_str = ", ".join([f"`{col}`" for col in insert_columns])
                placeholders = ", ".join(["%s"] * len(insert_columns))
                insert_query = f"""
                    INSERT INTO preprocessed_data ({columns_str})
                    VALUES ({placeholders})
                """
                
                update_query = """
                    UPDATE processed_data 
                    SET `순서` = %s 
                    WHERE RN = %s
                """
                
                inserted_count = 0
                updated_count = 0
                
                for _, row in dataframe.iterrows():
                    values = []
                    for col in insert_columns:
                        value = row[col]
                        if pd.isna(value):
                            values.append(None)
                        elif col == "순서":
                            order_value = to_int(value)
                            values.append(order_value)
                        elif col in ["주문시간", "출고예정일", "공동생년월일"]:
                            if isinstance(value, str):
                                values.append(value)
                            elif isinstance(value, (datetime, pd.Timestamp)):
                                values.append(value.strftime("%Y-%m-%d"))
                            else:
                                values.append(None)
                        else:
                            values.append(value)
                    
                    try:
                        cursor.execute(insert_query, values)
                        inserted_count += 1
                        
                        rn_value = row.get('RN')
                        order_value = to_int(row.get('순서'))
                        if rn_value and pd.notna(rn_value) and order_value is not None:
                            cursor.execute(update_query, (order_value, rn_value))
                            if cursor.rowcount > 0:
                                updated_count += 1
                    except Exception as e:
                        print(f"행 삽입 실패 (RN: {row.get('RN', 'N/A')}): {e}")
                        continue
                
                connection.commit()
                print(f"\n성공적으로 {inserted_count}개 행이 preprocessed_data에 삽입되었습니다.")
                if updated_count > 0:
                    print(f"성공적으로 {updated_count}개 행의 processed_data 순서가 업데이트되었습니다.")
                return True
                
    except Exception as e:
        print(f"데이터베이스 삽입 실패: {e}")
        import traceback
        traceback.print_exc()
        return False




# ---------------------------------------------------------

if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        launcher = TestLauncher()
        launcher.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"프로그램 실행 중 심각한 오류 발생: {e}")
