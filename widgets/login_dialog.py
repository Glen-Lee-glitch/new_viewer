from PyQt6.QtWidgets import QDialog, QMessageBox
from PyQt6 import uic
from pathlib import Path
from core.sql_manager import get_worker_names

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # UI 파일 로드
        ui_path = Path(__file__).parent.parent / "ui" / "login_dialog.ui"
        uic.loadUi(str(ui_path), self)
        
        # 다이얼로그 설정
        self.setWindowTitle("로그인")
        self.setModal(True)
        
        # 버튼 연결
        self.buttonBox.accepted.connect(self._validate_and_accept)
        self.buttonBox.rejected.connect(self.reject)
        
        # 입력 필드 포커스
        self.lineEdit_worker.setFocus()
    
    def _validate_and_accept(self):
        """작업자 이름을 검증하고 유효하면 다이얼로그를 승인한다."""
        worker_name = self.lineEdit_worker.text().strip()
        
        # 빈 입력 체크
        if not worker_name:
            QMessageBox.warning(self, "입력 오류", "작업자 이름을 입력해주세요.")
            self.lineEdit_worker.setFocus()
            return
        
        # 유효한 작업자 목록 가져오기
        valid_workers = get_worker_names()
        
        # 작업자 이름 유효성 검사
        if worker_name not in valid_workers:
            error_msg = f"'{worker_name}'은(는) 등록되지 않은 작업자입니다.\n\n등록된 작업자 목록:\n"
            error_msg += "\n".join(f"• {worker}" for worker in valid_workers)
            QMessageBox.warning(self, "등록되지 않은 작업자", error_msg)
            self.lineEdit_worker.setFocus()
            return
        
        # 유효한 경우 다이얼로그 승인
        self.accept()
    
    def get_worker_name(self) -> str:
        """입력된 작업자 이름을 반환한다."""
        return self.lineEdit_worker.text().strip()