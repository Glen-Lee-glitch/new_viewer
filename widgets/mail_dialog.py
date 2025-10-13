from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QMessageBox


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
        if hasattr(self, 'pushButton_complement'):
            self.pushButton_complement.clicked.connect(self._insert_completion_text)
        if hasattr(self, 'pushButton_unqualified'):
            self.pushButton_unqualified.clicked.connect(self._insert_unqualified_text)
        if hasattr(self, 'pushButton_etc'):
            self.pushButton_etc.clicked.connect(self._insert_etc_text)
    
    def _insert_completion_text(self):
        """신청완료 텍스트 삽입 (apply_number 검증 후)"""
        # apply_number 검증
        if not self._validate_apply_number():
            return
        
        apply_number = self._get_apply_number()
        if hasattr(self, 'textEdit'):
            completion_text = f"안녕하세요.\n{apply_number} 신청이 완료되었습니다."
            self.textEdit.append(completion_text)
    
    def _insert_unqualified_text(self):
        """서류미비 텍스트 삽입"""
        if hasattr(self, 'textEdit'):
            self.textEdit.append("서류가 미비하여 추가 제출이 필요합니다.")
    
    def _insert_etc_text(self):
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
    
    def _validate_apply_number(self) -> bool:
        """apply_number 값이 유효한 정수인지 검증한다."""
        if not hasattr(self, 'apply_number'):
            QMessageBox.warning(self, "입력 오류", "신청번호를 입력하세요.")
            return False
        
        apply_number_text = self.apply_number.text().strip()
        
        # 빈 값 체크
        if not apply_number_text:
            QMessageBox.warning(self, "입력 오류", "신청번호를 입력하세요.")
            return False
        
        # 정수 변환 가능성 체크
        try:
            int(apply_number_text)
            return True
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "신청번호는 숫자로 입력하세요.")
            return False
    
    def _get_apply_number(self) -> str:
        """apply_number 값을 반환한다."""
        if hasattr(self, 'apply_number'):
            return self.apply_number.text().strip()
        return ""
