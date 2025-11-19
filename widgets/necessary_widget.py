from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import QWidget, QApplication, QLineEdit
from PyQt6.QtCore import QTimer, Qt
from core.etc_tools import reverse_text
from core.ui_helpers import ReverseToolHandler
from widgets.ev_helper_dialog import EVHelperDialog

class NecessaryWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "necessary_widget.ui"
        uic.loadUi(str(ui_path), self)
        
        # 역순 도구 핸들러 초기화
        self.reverse_tool_handler = ReverseToolHandler(self.lineEdit_reverse_tool)

        self.pushButton_open_ev_helper.clicked.connect(self._open_ev_helper_dialog)

    def _open_ev_helper_dialog(self):
        """오픈 EV 입력 도우미 다이얼로그를 엽니다."""
        # parent에서 worker_name 가져오기
        worker_name = ""
        parent = self.parent()
        while parent:
            if hasattr(parent, '_worker_name'):
                worker_name = parent._worker_name or ""
                break
            parent = parent.parent()
        
        dialog = EVHelperDialog(self, worker_name=worker_name)
        dialog.exec()
