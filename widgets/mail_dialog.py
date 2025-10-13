from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog


class MailDialog(QDialog):
    """이메일 전송 다이얼로그"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "mail_dialog.ui"
        uic.loadUi(str(ui_path), self)
        
        self._setup_connections()
        
    def _setup_connections(self):
        """시그널-슬롯 연결을 설정한다."""
        # 자동완성 버튼들 연결
        if hasattr(self, 'pushButton'):
            self.pushButton.clicked.connect(self._insert_completion_text_1)
        if hasattr(self, 'pushButton_2'):
            self.pushButton_2.clicked.connect(self._insert_completion_text_2)
        if hasattr(self, 'pushButton_3'):
            self.pushButton_3.clicked.connect(self._insert_completion_text_3)
    
    def _insert_completion_text_1(self):
        """신청완료 텍스트 삽입"""
        if hasattr(self, 'textEdit'):
            self.textEdit.append("신청이 완료되었습니다.")
    
    def _insert_completion_text_2(self):
        """서류미비 텍스트 삽입"""
        if hasattr(self, 'textEdit'):
            self.textEdit.append("서류가 미비하여 추가 제출이 필요합니다.")
    
    def _insert_completion_text_3(self):
        """기타 텍스트 삽입"""
        if hasattr(self, 'textEdit'):
            self.textEdit.append("기타 사항: ")
    
    def get_rn_value(self) -> str:
        """RN 값을 반환한다."""
        if hasattr(self, 'RN_lineEdit'):
            return self.RN_lineEdit.text().strip()
        return ""
    
    def get_content(self) -> str:
        """내용을 반환한다."""
        if hasattr(self, 'textEdit'):
            return self.textEdit.toPlainText().strip()
        return ""
    
    def set_rn_value(self, rn_value: str):
        """RN 값을 설정한다."""
        if hasattr(self, 'RN_lineEdit'):
            self.RN_lineEdit.setText(rn_value)
    
    def set_content(self, content: str):
        """내용을 설정한다."""
        if hasattr(self, 'textEdit'):
            self.textEdit.setPlainText(content)
