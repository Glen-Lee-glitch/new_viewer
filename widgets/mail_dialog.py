from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QMessageBox, QStyle

from widgets.unqualified_document_dialog import UnqualifiedDocumentDialog


class MailDialog(QDialog):
    """이메일 전송 다이얼로그"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "mail_dialog.ui"
        uic.loadUi(str(ui_path), self)
        
        self._setup_help_button()
        self._setup_connections()
    
    def _setup_help_button(self):
        """도움말 버튼 설정"""
        if hasattr(self, 'helpButton'):
            # 시스템 표준 도움말 아이콘 설정
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxQuestion)
            self.helpButton.setIcon(icon)
            self.helpButton.setText("")  # 아이콘만 표시
            self.helpButton.clicked.connect(self._show_help_dialog)
        
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
        priority_text = self._get_priority_text()
        
        if hasattr(self, 'textEdit'):
            # 우선순위가 있으면 신청번호 뒤에 추가
            if priority_text:
                completion_text = f"안녕하세요.\n#{apply_number} {priority_text} 신청이 완료되었습니다.\n감사합니다."
            else:
                completion_text = f"안녕하세요.\n#{apply_number} 신청이 완료되었습니다.\n감사합니다."
            self.textEdit.append(completion_text)
    
    def _insert_unqualified_text(self):
        """서류미비 텍스트 삽입 (다이얼로그에서 항목 선택)"""
        dialog = UnqualifiedDocumentDialog(self)
        
        if dialog.exec():
            selected_items = dialog.get_selected_items()
            
            if hasattr(self, 'textEdit'):
                if selected_items:
                    items_text = ", ".join(selected_items)
                    text = f"다음 서류가 미비하여 추가 제출이 필요합니다.\n {items_text}"
                else:
                    text = "서류가 미비하여 추가 제출이 필요합니다."
                
                self.textEdit.append(text)
    
    def _insert_etc_text(self):
        """기타 텍스트 삽입"""
        if hasattr(self, 'textEdit'):
            self.textEdit.append("기타 사항: ")
    
    def _show_help_dialog(self):
        """이메일 형식 도움말 다이얼로그를 표시한다."""
        help_text = """
<h3>📧 이메일 형식 도움말</h3>

<p><b>1. RN 번호:</b><br>
작업 중인 신청서의 RN 번호가 자동으로 입력됩니다.</p>

<p><b>2. 우선순위:</b><br>
해당되는 우선순위를 선택하면 신청번호 뒤에 자동으로 추가됩니다.<br>
예: #123 다자녀2 신청이 완료되었습니다.</p>

<p><b>3. 신청번호:</b><br>
이메일에 포함될 신청번호를 입력하세요. (숫자만 입력)</p>

<p><b>4. 자동완성 버튼:</b></p>
<ul>
<li><b>신청완료:</b> 신청 완료 안내 메시지를 자동 생성</li>
<li><b>서류미비:</b> 미비 서류 항목을 선택하여 안내 메시지 생성</li>
<li><b>기타:</b> 기타 사항 입력 템플릿 추가</li>
</ul>

<p><b>5. 내용 입력:</b><br>
자동완성 버튼으로 기본 템플릿을 추가한 후,<br>
필요에 따라 내용을 수정하거나 추가할 수 있습니다.</p>

<p><b>💡 팁:</b><br>
여러 자동완성 버튼을 순차적으로 클릭하여<br>
내용을 조합할 수 있습니다.</p>
        """
        
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setWindowTitle("이메일 형식 도움말")
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        msg_box.setText(help_text)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()
    
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
    
    def _get_priority_text(self) -> str:
        """priority_comboBox에서 선택된 우선순위 텍스트를 반환한다. '우선순위 없음'이면 빈 문자열 반환."""
        if not hasattr(self, 'priority_comboBox'):
            return ""
        
        current_text = self.priority_comboBox.currentText().strip()
        
        # '우선순위 없음'이면 빈 문자열 반환
        if current_text == "우선순위 없음":
            return ""
        
        return current_text
