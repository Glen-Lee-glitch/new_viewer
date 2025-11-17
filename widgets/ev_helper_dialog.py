from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import QDialog, QApplication, QLineEdit, QFileDialog, QMessageBox
from PyQt6.QtCore import QTimer, Qt
from core.etc_tools import reverse_text
from core.sql_manager import is_admin_user
import pandas as pd

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

    def _process_excel_file(self, file_path: str):
        """엑셀 파일을 읽고 현재 작업자와 일치하는 신청 건의 순서와 RN을 추출합니다."""
        try:
            df = pd.read_excel(file_path, header=0, dtype=str) # 모든 데이터를 문자열로 읽기
            
            required_cols = ['신청자', '순서', 'RN번호']
            if all(col in df.columns for col in required_cols):
                # 현재 작업자 이름과 일치하는 행 필터링
                filtered_df = df[df['신청자'] == self.worker_name]
                
                if not filtered_df.empty:
                    # '순서'와 'RN번호'를 "순서\nRN번호" 형태의 문자열로 만들어 리스트에 저장
                    self._overlay_texts = [
                        f"{row['순서']}\n{row['RN번호']}" for index, row in filtered_df.iterrows()
                    ]
                    QMessageBox.information(self, "정보", f"'{self.worker_name}'님의 신청 건 {len(self._overlay_texts)}개를 찾았습니다.")
                else:
                    self._overlay_texts = []
                    QMessageBox.information(self, "정보", f"'{self.worker_name}'님의 신청 건을 찾을 수 없습니다.")
            else:
                self._overlay_texts = []
                missing_cols = [f"'{col}'" for col in required_cols if col not in df.columns]
                QMessageBox.warning(self, "오류", f"엑셀 파일에 필요한 칼럼({', '.join(missing_cols)})이 없습니다.")

        except Exception as e:
            self._overlay_texts = []
            QMessageBox.critical(self, "오류", f"엑셀 파일 처리 중 오류가 발생했습니다:\n{e}")

    def open_overlay(self):
        """'열기' 버튼을 누르면 오버레이 창을 생성하고 표시합니다."""
        if not self._overlay_texts:
            QMessageBox.information(self, "데이터 없음", "표시할 데이터가 없습니다.\n엑셀 파일을 먼저 로드하고, 본인에게 할당된 신청 건이 있는지 확인해주세요.")
            return
            
        if self.overlay is None or not self.overlay.isVisible():
            self.overlay = OverlayWindow(texts=self._overlay_texts)
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
