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
        refresh_interval = self._settings.value("general/refresh_interval", 30, type=int)
        self.spinBox_refresh_time.setValue(refresh_interval)
        
        # 지급신청 로드 체크박스는 항상 체크된 상태로 시작 (설정 저장 안 함)
        self.checkBox_payment_request_load.setChecked(True)
        
        # AI 결과 자동 띄우기 체크박스 설정 로드 (기본값: True)
        auto_show_ai = self._settings.value("general/auto_show_ai_results", True, type=bool)
        self.checkBox_auto_show_ai_results.setChecked(auto_show_ai)
    
    def _save_settings(self):
        """UI에 설정된 값을 저장합니다."""
        self._settings.setValue("general/refresh_interval", self.spinBox_refresh_time.value())
        # 지급신청 로드 체크박스는 저장하지 않음 (프로그램 시작 시 항상 체크된 상태)
        
        # AI 결과 자동 띄우기 설정 저장
        self._settings.setValue("general/auto_show_ai_results", self.checkBox_auto_show_ai_results.isChecked())
        
        self.accept()
    
    @property
    def settings(self):
        """QSettings 인스턴스를 반환합니다."""
        return self._settings
    
    @property
    def payment_request_load_enabled(self):
        """지급신청 로드 체크박스 상태를 반환합니다."""
        return self.checkBox_payment_request_load.isChecked()
    
    @property
    def auto_show_ai_results(self):
        """AI 결과 자동 띄우기 체크박스 상태를 반환합니다."""
        return self.checkBox_auto_show_ai_results.isChecked()

