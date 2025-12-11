from pathlib import Path
from datetime import datetime
import os
import subprocess
from PyQt6 import uic
from PyQt6.QtWidgets import QWidget, QApplication, QLineEdit, QMessageBox
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
        self.pushButton_copy_folder.clicked.connect(self._copy_folder_path)
        self.pushButton_open_folder.clicked.connect(self._open_folder_in_explorer)

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

    def _copy_folder_path(self):
        """현재 작업자와 금일 날짜까지의 폴더 경로를 클립보드에 복사합니다."""
        try:
            folder_path_str, _ = self._get_folder_path()
            
            # 클립보드에 복사
            clipboard = QApplication.clipboard()
            clipboard.setText(folder_path_str)
            
            # 버튼의 원래 스타일시트 저장
            original_style = self.pushButton_copy_folder.styleSheet()
            
            # 하이라이트 스타일 적용
            highlight_style = """
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    font-weight: bold;
                }
            """
            self.pushButton_copy_folder.setStyleSheet(highlight_style)
            
            # 3초 후 원래 스타일로 복원
            self._style_timer = QTimer(self)
            self._style_timer.setSingleShot(True)
            self._style_timer.timeout.connect(
                lambda: self.pushButton_copy_folder.setStyleSheet(original_style)
            )
            self._style_timer.start(3000)
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "복사 오류",
                f"경로 복사 중 오류가 발생했습니다:\n\n{str(e)}"
            )

    def _get_folder_path(self) -> tuple[str, Path]:
        """현재 작업자와 금일 날짜까지의 폴더 경로를 반환합니다."""
        # parent에서 worker_name 가져오기
        worker_name = ""
        parent = self.parent()
        while parent:
            if hasattr(parent, '_worker_name'):
                worker_name = parent._worker_name or ""
                break
            parent = parent.parent()
        
        # 경로 생성 (pdf_view_widget의 save_pdf와 동일한 로직)
        base_dir = r'\\DESKTOP-KMJ\Users\HP\Desktop\greet_db\files\finished'
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 작업자 이름이 없으면 "미지정" 폴더 사용
        worker_folder = worker_name if worker_name else "미지정"
        
        # 최종 폴더 경로 구성
        folder_path = Path(base_dir) / worker_folder / today
        folder_path_str = str(folder_path)
        
        return folder_path_str, folder_path

    def _open_folder_in_explorer(self):
        """윈도우 파일 탐색기로 폴더를 엽니다."""
        try:
            folder_path_str, folder_path = self._get_folder_path()
            
            # 폴더가 없으면 생성
            folder_path.mkdir(parents=True, exist_ok=True)
            
            # 윈도우 파일 탐색기로 폴더 열기
            # 네트워크 경로도 포함하여 explorer 명령어 사용
            subprocess.Popen(['explorer', folder_path_str])
                
        except Exception as e:
            QMessageBox.critical(
                self,
                "열기 오류",
                f"폴더를 여는 중 오류가 발생했습니다:\n\n{str(e)}"
            )
