from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import QDialog, QApplication, QLineEdit, QFileDialog
from PyQt6.QtCore import QTimer, Qt
from core.etc_tools import reverse_text
from core.sql_manager import is_admin_user


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
