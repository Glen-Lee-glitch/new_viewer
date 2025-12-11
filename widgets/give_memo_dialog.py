from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import QDialog, QMessageBox

from core.sql_manager import update_give_works_memo


class GiveMemoDialog(QDialog):
    """지급 메모 다이얼로그"""

    def __init__(self, parent=None):
        super().__init__(parent)
        
        ui_path = Path(__file__).parent.parent / "ui" / "give_memo_dialog.ui"
        uic.loadUi(str(ui_path), self)
        
        self._rn = ""  # RN 번호 저장
        self._is_editable = False  # 편집 가능 여부 플래그
        
        # 초기 상태: textEdit 읽기 전용
        if hasattr(self, 'textEdit'):
            self.textEdit.setReadOnly(True)
        
        # 버튼 연결
        if hasattr(self, 'pushButton_2'):  # 메모 수정 버튼
            self.pushButton_2.clicked.connect(self._enable_edit)
        if hasattr(self, 'pushButton_3'):  # 메모 저장 버튼
            self.pushButton_3.clicked.connect(self._save_memo)
        if hasattr(self, 'pushButton'):  # 닫기 버튼
            self.pushButton.clicked.connect(self.close)
    
    def set_rn(self, rn: str):
        """RN 번호를 설정한다."""
        self._rn = rn
    
    def set_memo(self, memo: str):
        """메모 내용을 설정한다."""
        if hasattr(self, 'textEdit'):
            self.textEdit.setPlainText(memo)
    
    def _enable_edit(self):
        """메모 수정 모드로 전환"""
        if hasattr(self, 'textEdit'):
            self.textEdit.setReadOnly(False)
            self._is_editable = True
    
    def _save_memo(self):
        """메모를 저장하고 읽기 전용 모드로 복귀"""
        if not self._rn:
            QMessageBox.warning(self, "오류", "RN 번호가 설정되지 않았습니다.")
            return
        
        if not hasattr(self, 'textEdit'):
            return
        
        memo_text = self.textEdit.toPlainText()
        
        # DB 업데이트
        success = update_give_works_memo(self._rn, memo_text)
        
        if success:
            # 읽기 전용 모드로 복귀
            self.textEdit.setReadOnly(True)
            self._is_editable = False
            QMessageBox.information(self, "저장 완료", "메모가 성공적으로 저장되었습니다.")
        else:
            QMessageBox.warning(self, "저장 실패", "메모 저장 중 오류가 발생했습니다.")

