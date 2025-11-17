from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import QDialog, QApplication, QLineEdit, QFileDialog, QMessageBox
from PyQt6.QtCore import QTimer, Qt
from core.etc_tools import reverse_text
from core.sql_manager import is_admin_user
import pandas as pd
from datetime import datetime

from widgets.helper_overlay import OverlayWindow


class EVHelperDialog(QDialog):
    def __init__(self, parent=None, worker_name: str = ""):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "ev_helper_dialog.ui"
        uic.loadUi(str(ui_path), self)

        self.lineEdit_reverse_tool.mousePressEvent = self._handle_reverse_tool_click
        self._original_stylesheet = self.lineEdit_reverse_tool.styleSheet()

        self.pushButton_select_excel.clicked.connect(self._select_excel_file)

        # 관리자 여부 확인 후 '관리자' 그룹 표시/숨김 처리
        is_admin = is_admin_user(worker_name)
        self.groupBox_2.setVisible(is_admin)

        self.overlay = None # 이 줄을 다시 추가합니다.
        self.worker_name = worker_name
        self._overlay_texts = [] # 오버레이에 표시할 텍스트 리스트
        self._overlay_copy_data = []  # 오버레이에 복사 가능한 칼럼 데이터 리스트
        
        self.open_helper_overlay.clicked.connect(self.open_overlay)
        self.close_helper_overlay.clicked.connect(self.close_overlay)

    def _handle_reverse_tool_click(self, event):
        """lineEdit_reverse_tool 클릭 이벤트를 처리합니다."""
        if event.button() == Qt.MouseButton.LeftButton:
            current_text = self.lineEdit_reverse_tool.text()
            reversed_text = reverse_text(current_text)
            
            self.lineEdit_reverse_tool.setText(reversed_text)
            
            clipboard = QApplication.clipboard()
            clipboard.setText(reversed_text)
            
            self.lineEdit_reverse_tool.setStyleSheet("border: 2px solid #00FF00;")
            
            QTimer.singleShot(5000, self._remove_highlight)
        else:
            QLineEdit.mousePressEvent(self.lineEdit_reverse_tool, event)
        
    def _remove_highlight(self):
        """lineEdit_reverse_tool의 하이라이트를 제거합니다."""
        self.lineEdit_reverse_tool.setStyleSheet(self._original_stylesheet)

    def _select_excel_file(self):
        """엑셀 파일을 선택하는 다이얼로그를 엽니다."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "엑셀 파일 선택",
            "",
            "Excel Files (*.xlsx *.xls);;All Files (*)"
        )
        if file_path:
            self.lineEdit_excel_file.setText(file_path)
            self._process_excel_file(file_path)

    def _format_date_value(self, value: str) -> str:
        """날짜/시간 문자열에서 날짜 부분만 추출합니다."""
        if not value or value == 'nan':
            return value
        
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
        
        # 파싱 실패 시 원본 값 반환
        return value

    def _process_excel_file(self, file_path: str):
        """엑셀 파일을 읽고 현재 작업자와 일치하는 신청 건의 정보를 추출합니다."""
        try:
            df = pd.read_excel(file_path, header=0, dtype=str) # 모든 데이터를 문자열로 읽기
            
            required_cols = ['신청자', 'RN번호']
            if all(col in df.columns for col in required_cols):
                # 현재 작업자 이름과 일치하는 행 필터링
                filtered_df = df[df['신청자'] == self.worker_name]
                
                if not filtered_df.empty:
                    # 표시할 칼럼 목록 정의
                    display_columns = [
                        '주문시간', '성명(대표자)', '생년월일(법인번호)', '성별', '신청자종', '출고예정일',
                        '주소1', '주소2', '전화', '휴대폰', '이메일', '신청유형', '우선순위', 'RN번호'
                    ]
                    
                    # 값이 있을 때만 표시할 선택적 칼럼
                    optional_columns = ['사업자번호', '사업자명', '다자녀수', '공동명의자', '공동 생년월일']
                    
                    # 날짜 형식 칼럼 목록
                    date_columns = ['주문시간', '출고예정일', '공동 생년월일']
                    
                    self._overlay_texts = []
                    self._overlay_copy_data = []  # 복사 가능한 칼럼 데이터 리스트
                    
                    for index, row in filtered_df.iterrows():
                        lines = []
                        
                        # 필수 표시 칼럼 처리
                        for col in display_columns:
                            if col in df.columns:
                                value = str(row[col]).strip()
                                if value and value != 'nan':  # 빈 값이나 NaN이 아닌 경우만
                                    # 날짜 칼럼인 경우 날짜 부분만 추출
                                    if col in date_columns:
                                        value = self._format_date_value(value)
                                    lines.append(f"{col}: {value}")
                        
                        # 선택적 칼럼 처리 (값이 있을 때만)
                        for col in optional_columns:
                            if col in df.columns:
                                value = str(row[col]).strip()
                                if value and value != 'nan' and value != '':  # 빈 값이 아닌 경우만
                                    # 날짜 칼럼인 경우 날짜 부분만 추출
                                    if col in date_columns:
                                        value = self._format_date_value(value)
                                    lines.append(f"{col}: {value}")
                        
                        # 줄바꿈으로 연결하여 하나의 문자열로 만듦
                        self._overlay_texts.append('\n'.join(lines))
                        
                        # 복사 가능한 칼럼 데이터 생성
                        copy_columns = ['성명(대표자)', '주소1', '주소2', '전화', '휴대폰', '이메일']
                        copy_values = []
                        
                        for col in copy_columns:
                            if col in df.columns:
                                value = str(row[col]).strip()
                                if value and value != 'nan':
                                    copy_values.append(value)
                                else:
                                    copy_values.append('')  # 빈 값도 추가하여 인덱스 유지
                        
                        # 공동명의자가 있으면 추가 (RN번호 전에)
                        has_joint = False
                        if '공동명의자' in df.columns:
                            joint_value = str(row['공동명의자']).strip()
                            if joint_value and joint_value != 'nan' and joint_value != '':
                                copy_values.append(joint_value)
                                has_joint = True
                        
                        # RN번호 추가 (항상 마지막)
                        if 'RN번호' in df.columns:
                            rn_value = str(row['RN번호']).strip()
                            if rn_value and rn_value != 'nan':
                                copy_values.append(rn_value)
                        
                        self._overlay_copy_data.append(copy_values)
                    
                    QMessageBox.information(self, "정보", f"'{self.worker_name}'님의 신청 건 {len(self._overlay_texts)}개를 찾았습니다.")
                else:
                    self._overlay_texts = []
                    self._overlay_copy_data = []
                    QMessageBox.information(self, "정보", f"'{self.worker_name}'님의 신청 건을 찾을 수 없습니다.")
            else:
                self._overlay_texts = []
                self._overlay_copy_data = []
                missing_cols = [f"'{col}'" for col in required_cols if col not in df.columns]
                QMessageBox.warning(self, "오류", f"엑셀 파일에 필요한 칼럼({', '.join(missing_cols)})이 없습니다.")

        except Exception as e:
            self._overlay_texts = []
            self._overlay_copy_data = []
            QMessageBox.critical(self, "오류", f"엑셀 파일 처리 중 오류가 발생했습니다:\n{e}")

    def open_overlay(self):
        """'열기' 버튼을 누르면 오버레이 창을 생성하고 표시합니다."""
        if not self._overlay_texts:
            QMessageBox.information(self, "데이터 없음", "표시할 데이터가 없습니다.\n엑셀 파일을 먼저 로드하고, 본인에게 할당된 신청 건이 있는지 확인해주세요.")
            return
            
        if self.overlay is None or not self.overlay.isVisible():
            self.overlay = OverlayWindow(texts=self._overlay_texts, copy_data=self._overlay_copy_data)
            self.overlay.show()

    def close_overlay(self):
        """'닫기' 버튼을 누르면 오버레이 창을 닫습니다."""
        if self.overlay and self.overlay.isVisible():
            self.overlay.close()
            self.overlay = None
            
    def closeEvent(self, event):
        """다이얼로그가 닫힐 때 오버레이 창도 함께 닫히도록 합니다."""
        self.close_overlay()
        super().closeEvent(event)
