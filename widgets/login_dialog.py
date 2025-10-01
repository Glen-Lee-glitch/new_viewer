from PyQt6.QtWidgets import QDialog
from PyQt6 import uic
from pathlib import Path

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # UI 파일 로드
        ui_path = Path(__file__).parent.parent / "ui" / "login_dialog.ui"
        uic.loadUi(str(ui_path), self)
        
        # 다이얼로그 설정
        self.setWindowTitle("로그인")
        self.setModal(True)
    
    def get_worker_name(self) -> str:
        """입력된 작업자 이름을 반환한다."""
        return self.lineEdit_worker.text().strip()