from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import QDialog, QApplication, QLineEdit, QFileDialog, QMessageBox
from PyQt6.QtCore import QTimer, Qt
from core.etc_tools import reverse_text
from core.sql_manager import is_admin_user, fetch_preprocessed_data
from core.ui_helpers import ReverseToolHandler
import pandas as pd
from datetime import datetime

from widgets.helper_overlay import OverlayWindow


class EVHelperDialog(QDialog):
    def __init__(self, parent=None, worker_name: str = ""):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "ev_helper_dialog.ui"
        uic.loadUi(str(ui_path), self)

        # 역순 도구 핸들러 초기화
        self.reverse_tool_handler = ReverseToolHandler(self.lineEdit_reverse_tool)

        self.pushButton_select_excel.clicked.connect(self._select_excel_file)
        self.pushButton_select_excel.setVisible(False) # 엑셀 버튼 숨김

        # 관리자 여부 확인 후 '관리자' 그룹 표시/숨김 처리
        is_admin = is_admin_user(worker_name)
        self.groupBox_2.setVisible(is_admin)

        self.overlay = None
        self.worker_name = worker_name
        self._overlay_texts = [] # 오버레이에 표시할 텍스트 리스트
        self._overlay_copy_data = []  # 오버레이에 복사 가능한 칼럼 데이터 리스트
        
        self.open_helper_overlay.clicked.connect(self.open_overlay)
        self.close_helper_overlay.clicked.connect(self.close_overlay)
        
        # 초기화 시 데이터 로드
        self._load_data_from_db()

    def _select_excel_file(self):
        """(사용 안함) 엑셀 파일을 선택하는 다이얼로그를 엽니다."""
        pass

    def _format_date_value(self, value: str) -> str:
        """날짜/시간 문자열에서 날짜 부분만 추출합니다."""
        if not value or value == 'nan' or value == 'None':
            return ""
        
        # 다양한 날짜 형식 시도
        date_formats = [
            '%Y-%m-%d %H:%M:%S',  # 2025-01-01 12:00:00
            '%Y-%m-%d %H:%M',      # 2025-01-01 12:00
            '%Y/%m/%d %H:%M:%S',   # 2025/01/01 12:00:00
            '%Y/%m/%d %H:%M',      # 2025/01/01 12:00
            '%Y-%m-%d',            # 2025-01-01
            '%Y/%m/%d',            # 2025/01/01
            '%Y.%m.%d',            # 2025.01.01
        ]
        
        for fmt in date_formats:
            try:
                dt = datetime.strptime(value.strip(), fmt)
                return dt.strftime('%Y-%m-%d')  # 날짜 부분만 반환
            except ValueError:
                continue
        
        # 파싱 실패 시 원본 값 반환 (이미 YYYY-MM-DD 형식이면 그대로 사용됨)
        return value

    def _load_data_from_db(self):
        """DB에서 현재 작업자의 데이터를 조회하여 로드합니다."""
        try:
            df = fetch_preprocessed_data(self.worker_name)
            
            if not df.empty:
                # 표시할 칼럼 목록 정의
                display_columns = [
                    '주문시간', '성명', '생년월일', '성별', '신청차종', '출고예정일',
                    '주소1', '주소2', '전화', '휴대폰', '이메일', '신청유형', '우선순위', 'RN'
                ]
                
                # 값이 있을 때만 표시할 선택적 칼럼
                optional_columns = ['사업자번호', '사업자명', '다자녀수', '공동명의자', '공동생년월일']
                
                # 날짜 형식 칼럼 목록
                date_columns = ['생년월일', '주문시간', '출고예정일', '공동생년월일']
                
                self._overlay_texts = []
                self._overlay_copy_data = []  # 복사 가능한 칼럼 데이터 리스트
                
                # 복사 가능한 칼럼과 단축키 매핑
                copy_columns = ['성명', '주소1', '주소2', '전화', '휴대폰', '이메일']
                copy_column_to_shortcut = {col: i+1 for i, col in enumerate(copy_columns)}
                copy_column_to_shortcut['공동명의자'] = 7
                copy_column_to_shortcut['RN'] = 8  # 공동명의자가 있으면 8, 없으면 7
                
                for index, row in df.iterrows():
                    lines = []
                    
                    # 공동명의자 존재 여부 확인 (RN번호 단축키 결정용)
                    has_joint = False
                    if '공동명의자' in df.columns:
                        joint_value = str(row['공동명의자']).strip()
                        if joint_value and joint_value != 'nan' and joint_value != 'None' and joint_value != '':
                            has_joint = True
                    
                    # RN번호 단축키 결정 (공동명의자 유무에 따라)
                    rn_shortcut = 8 if has_joint else 7
                    copy_column_to_shortcut['RN'] = rn_shortcut
                    
                    # 필수 표시 칼럼 처리
                    for col in display_columns:
                        if col in df.columns:
                            value = str(row[col]).strip()
                            if value and value != 'nan' and value != 'None':  # 빈 값이나 NaN이 아닌 경우만
                                # 날짜 칼럼인 경우 날짜 부분만 추출
                                if col in date_columns:
                                    value = self._format_date_value(value)
                                
                                # 복사 가능한 칼럼인 경우 단축키 추가
                                if col in copy_column_to_shortcut:
                                    shortcut_num = copy_column_to_shortcut[col]
                                    lines.append(f"[Ctrl+Alt+{shortcut_num}] {col}: {value}")
                                else:
                                    lines.append(f"{col}: {value}")
                    
                    # 선택적 칼럼 처리 (값이 있을 때만)
                    for col in optional_columns:
                        if col in df.columns:
                            value = str(row[col]).strip()
                            if value and value != 'nan' and value != 'None' and value != '':  # 빈 값이 아닌 경우만
                                # 날짜 칼럼인 경우 날짜 부분만 추출
                                if col in date_columns:
                                    value = self._format_date_value(value)
                                
                                # 복사 가능한 칼럼인 경우 단축키 추가
                                if col in copy_column_to_shortcut:
                                    shortcut_num = copy_column_to_shortcut[col]
                                    lines.append(f"[Ctrl+Alt+{shortcut_num}] {col}: {value}")
                                else:
                                    lines.append(f"{col}: {value}")
                    
                    # 줄바꿈으로 연결하여 하나의 문자열로 만듦 (항목 간 간격을 위해 빈 줄 추가)
                    self._overlay_texts.append('\n\n'.join(lines))
                    
                    # 복사 가능한 칼럼 데이터 생성
                    copy_values = []
                    
                    for col in copy_columns:
                        if col in df.columns:
                            value = str(row[col]).strip()
                            if value and value != 'nan' and value != 'None':
                                copy_values.append(value)
                            else:
                                copy_values.append('')  # 빈 값도 추가하여 인덱스 유지
                    
                    # 공동명의자가 있으면 추가 (RN번호 전에)
                    if has_joint:
                        copy_values.append(joint_value)
                    
                    # RN번호 추가 (항상 마지막)
                    if 'RN' in df.columns:
                        rn_value = str(row['RN']).strip()
                        if rn_value and rn_value != 'nan' and rn_value != 'None':
                            copy_values.append(rn_value)
                    
                    self._overlay_copy_data.append(copy_values)
                
                # DB 로드 성공 시 메시지는 띄우지 않음 (자동 로드이므로)
            else:
                self._overlay_texts = []
                self._overlay_copy_data = []
                # 데이터가 없어도 조용히 넘어감

        except Exception as e:
            self._overlay_texts = []
            self._overlay_copy_data = []
            QMessageBox.critical(self, "오류", f"데이터 조회 중 오류가 발생했습니다:\n{e}")

    def open_overlay(self):
        """'열기' 버튼을 누르면 오버레이 창을 생성하고 표시합니다."""
        # 데이터가 없는 경우 다시 로드 시도
        if not self._overlay_texts:
            self._load_data_from_db()
            
        if not self._overlay_texts:
            QMessageBox.information(self, "데이터 없음", "표시할 데이터가 없습니다.\n본인에게 할당된 신청 건이 있는지 확인해주세요.")
            return
            
        if self.overlay is None or not self.overlay.isVisible():
            self.overlay = OverlayWindow(texts=self._overlay_texts, copy_data=self._overlay_copy_data)
            self.overlay.show()

    def close_overlay(self):
        """'닫기' 버튼을 누르면 오버레이 창을 닫습니다."""
        if self.overlay and self.overlay.isVisible():
            self.overlay.close()
            self.overlay = None
            
    def accept(self):
        """OK 버튼이 눌렸을 때 오버레이 창을 닫고 다이얼로그를 닫습니다."""
        self.close_overlay()
        super().accept()
    
    def reject(self):
        """Cancel 버튼이 눌렸을 때 오버레이 창을 닫고 다이얼로그를 닫습니다."""
        self.close_overlay()
        super().reject()
    
    def closeEvent(self, event):
        """다이얼로그가 닫힐 때 오버레이 창도 함께 닫히도록 합니다."""
        self.close_overlay()
        super().closeEvent(event)
