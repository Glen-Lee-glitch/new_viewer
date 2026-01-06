from pathlib import Path

from PyQt6 import uic
from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import QSettings


class ConfigDialog(QDialog):
    """환경설정 다이얼로그"""
    
    # 정보 패널 섹션 매핑 (Key -> Display Text)
    SECTION_MAP = {
        "email": "이메일",
        "memo": "메모관리",
        "ev_check": "서류미비 및 확인필요",
        "da_request": "DA 추가요청(수신)"
    }
    
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

        # 레이아웃 순서 로드
        default_order = ["email", "memo", "ev_check", "da_request"]
        saved_order = self._settings.value("layout/info_panel_order", default_order)
        
        # 저장된 데이터 유효성 검사 및 복구
        if not isinstance(saved_order, list) or not saved_order:
            saved_order = default_order
        
        # 현재 코드에 정의된 키들만 필터링하고 누락된 키 추가
        current_keys = set(self.SECTION_MAP.keys())
        final_order = [k for k in saved_order if k in current_keys]
        for k in default_order:
            if k not in final_order:
                final_order.append(k)
        
        # 리스트 위젯 구성
        self.listWidget_info_order.clear()
        for key in final_order:
            text = self.SECTION_MAP.get(key)
            if text:
                self.listWidget_info_order.addItem(text)
    
    def _save_settings(self):
        """UI에 설정된 값을 저장합니다."""
        self._settings.setValue("general/refresh_interval", self.spinBox_refresh_time.value())
        # 지급신청 로드 체크박스는 저장하지 않음 (프로그램 시작 시 항상 체크된 상태)
        
        # AI 결과 자동 띄우기 설정 저장
        self._settings.setValue("general/auto_show_ai_results", self.checkBox_auto_show_ai_results.isChecked())
        
        # 레이아웃 순서 저장
        order = []
        for i in range(self.listWidget_info_order.count()):
            text = self.listWidget_info_order.item(i).text()
            # 텍스트로 키 찾기
            for key, val in self.SECTION_MAP.items():
                if val == text:
                    order.append(key)
                    break
        self._settings.setValue("layout/info_panel_order", order)
        
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

    @property
    def layout_order(self):
        """설정된 레이아웃 순서 리스트(Key List)를 반환합니다."""
        order = []
        for i in range(self.listWidget_info_order.count()):
            text = self.listWidget_info_order.item(i).text()
            for key, val in self.SECTION_MAP.items():
                if val == text:
                    order.append(key)
                    break
        return order

