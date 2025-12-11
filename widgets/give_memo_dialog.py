from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import QDialog


class GiveMemoDialog(QDialog):
    """지급 메모 다이얼로그"""

    def __init__(self, parent=None):
        super().__init__(parent)
        
        ui_path = Path(__file__).parent.parent / "ui" / "give_memo_dialog.ui"
        uic.loadUi(str(ui_path), self)
        
        # 버튼 연결
        if hasattr(self, 'pushButton'):
            self.pushButton.clicked.connect(self.close)
        
        # TODO: 메모 수정 및 저장 로직은 추후 구현

