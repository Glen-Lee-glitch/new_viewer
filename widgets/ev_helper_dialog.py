from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import QDialog, QApplication, QLineEdit, QFileDialog
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

        self.overlay = None
        
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
        """엑셀 파일을 읽고 처리합니다."""
        try:
            # pandas로 엑셀 파일을 데이터프레임화 (header=0, 디폴트)
            df = pd.read_excel(file_path, header=0)
            
            # '신청자' 칼럼의 value_counts를 디버그로 출력
            if '신청자' in df.columns:
                value_counts = df['신청자'].value_counts()
                print("신청자 칼럼 value_counts:")
                print(value_counts)
            else:
                print(f"경고: '신청자' 칼럼이 엑셀 파일에 없습니다. 사용 가능한 칼럼: {list(df.columns)}")
        except Exception as e:
            print(f"엑셀 파일 처리 중 오류 발생: {e}")

    def open_overlay(self):
        """'열기' 버튼을 누르면 오버레이 창을 생성하고 표시합니다."""
        if self.overlay is None or not self.overlay.isVisible():
            # TODO: 실제 데이터로 교체해야 합니다.
            sample_texts = [
                "이경구",
                "경기도 고양시 뭐뭐로 31-0",
                "101동 201호",
                "010-2888-3555",
                "gyeonggoo.lee@greetlounge.com",
                "RN123456789"
            ]
            self.overlay = OverlayWindow(texts=sample_texts)
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
