from pathlib import Path

from PyQt6 import uic
from PyQt6.QtWidgets import QDialog


class HelpDialog(QDialog):
    """도움말 다이얼로그"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # UI 파일 로드
        ui_path = Path(__file__).parent.parent / "ui" / "help_dialog.ui"
        uic.loadUi(str(ui_path), self)
        
        # 다이얼로그 설정
        self.setWindowTitle("도움말")
        self.setModal(True)
        
        # 리스트 위젯에 임시 아이템 추가
        self.listWidget.addItem("임시1")
        self.listWidget.addItem("임시2")
        self.listWidget.addItem("임시3")

