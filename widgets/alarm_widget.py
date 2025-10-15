from pathlib import Path
from PyQt6.QtWidgets import QWidget, QListWidget, QVBoxLayout
from PyQt6.QtCore import QTimer
from PyQt6 import uic

from core.sql_manager import get_today_completed_subsidies


class AlarmWidget(QWidget):
    """알림 위젯 - PDF 불러오기 전 표시되는 위젯"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # UI 파일 로드
        ui_path = Path(__file__).parent.parent / "ui" / "alarm_widget.ui"
        uic.loadUi(str(ui_path), self)
        
        # 처리완료 리스트 위젯 설정
        self._setup_finished_list()
        
        # 데이터 로드
        self._load_completed_regions()
        
        # 주기적 업데이트 타이머 (5분마다)
        self._timer = QTimer()
        self._timer.timeout.connect(self._load_completed_regions)
        self._timer.start(300000)  # 5분 = 300,000ms
    
    def _setup_finished_list(self):
        """처리완료 그룹박스에 리스트 위젯을 추가한다."""
        if hasattr(self, 'groupBox_finished'):
            # 기존 레이아웃 가져오기
            layout = self.groupBox_finished.layout()
            if layout is None:
                layout = QVBoxLayout(self.groupBox_finished)
            
            # 리스트 위젯 생성 및 추가
            self._finished_list = QListWidget()
            self._finished_list.setMaximumHeight(100)  # 높이 제한
            layout.addWidget(self._finished_list)
    
    def _load_completed_regions(self):
        """오늘 완료된 지역 목록을 로드한다."""
        if not hasattr(self, '_finished_list'):
            return
        
        try:
            completed_regions = get_today_completed_subsidies()
            
            # 리스트 클리어 후 새 데이터 추가
            self._finished_list.clear()
            
            if completed_regions:
                for region in completed_regions:
                    self._finished_list.addItem(f"✅ {region}")
            else:
                self._finished_list.addItem("오늘 완료된 지원 건이 없습니다.")
                
        except Exception as e:
            print(f"완료된 지역 로드 중 오류: {e}")
            if hasattr(self, '_finished_list'):
                self._finished_list.clear()
                self._finished_list.addItem("데이터 로드 실패")
    
    def refresh_data(self):
        """데이터를 수동으로 새로고침한다."""
        self._load_completed_regions()

