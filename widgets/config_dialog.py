from pathlib import Path

from PyQt6 import uic
from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import QSettings


class ConfigDialog(QDialog):
    """환경설정 다이얼로그"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # UI 파일 로드
        ui_path = Path(__file__).parent.parent / "ui" / "config_dialog.ui"
        uic.loadUi(str(ui_path), self)
        
        # 다이얼로그 설정
        self.setWindowTitle("환경설정")
        self.setModal(True)
        
        # QSettings 초기화
        self._settings = QSettings("GyeonggooLee", "NewViewer")
        
        # 설정 로드
        self._load_settings()
        
        # 버튼 연결
        self.buttonBox.accepted.connect(self._save_settings)
        self.buttonBox.rejected.connect(self.reject)
    
    def _load_settings(self):
        """저장된 설정을 불러와 UI에 적용합니다."""
        # TODO: UI 위젯이 추가되면 여기에 설정 로드 로직 구현
        pass
    
    def _save_settings(self):
        """UI에 설정된 값을 저장합니다."""
        # TODO: UI 위젯이 추가되면 여기에 설정 저장 로직 구현
        pass
    
    @property
    def settings(self):
        """QSettings 인스턴스를 반환합니다."""
        return self._settings

