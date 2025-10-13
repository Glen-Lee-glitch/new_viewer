from PyQt6.QtWidgets import QDialog
from PyQt6 import uic
from pathlib import Path

class WorkerProgressDialog(QDialog):
    """작업자 현황 다이얼로그"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # UI 파일 로드
        ui_path = Path(__file__).parent.parent / "ui" / "worker_progress.ui"
        uic.loadUi(str(ui_path), self)
        
        # 다이얼로그 설정
        self.setWindowTitle("작업자 현황")
        self.setModal(True)
        
        # 초기화
        self._setup_ui()
        self._load_worker_progress()
    
    def _setup_ui(self):
        """UI 컴포넌트를 설정한다."""
        # TODO: UI 컴포넌트 설정 로직 추가
        pass
    
    def _load_worker_progress(self):
        """작업자 현황 데이터를 로드한다."""
        # TODO: 작업자 현황 데이터 로드 로직 추가
        pass
