from PyQt6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QLabel, QWidget
from PyQt6.QtCore import Qt
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
        # 닫기 버튼 연결
        self.close_button.clicked.connect(self.accept)
    
    def _load_worker_progress(self):
        """작업자 현황 데이터를 로드하고 차트를 생성한다."""
        # 테스트 데이터
        workers = ['테스트1', '테스트2', '테스트3']
        counts = [10, 5, 8]
        
        # 차트 생성
        self._create_chart(workers, counts)
    
    def _create_chart(self, workers: list[str], counts: list[int]):
        """간단한 수직 막대그래프를 생성한다."""
        # 기존 레이아웃 정리
        if self.chart_container.layout():
            while self.chart_container.layout().count():
                child = self.chart_container.layout().takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        
        # 메인 레이아웃 설정
        main_layout = QHBoxLayout(self.chart_container)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 최대값 구하기 (차트 스케일용)
        max_count = max(counts) if counts else 1
        chart_height = 200  # 차트 전체 높이
        
        # 각 작업자별 막대 생성
        colors = ['#3498db', '#e74c3c', '#2ecc71']  # 파랑, 빨강, 초록
        
        for i, (worker, count) in enumerate(zip(workers, counts)):
            # 각 막대를 담을 컨테이너
            bar_container = QVBoxLayout()
            bar_container.setAlignment(Qt.AlignmentFlag.AlignBottom)
            bar_container.setSpacing(5)
            
            # 건수 라벨 (막대 위)
            count_label = QLabel(str(count))
            count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            count_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
            
            # 막대 (QWidget으로 구현)
            bar = QWidget()
            bar_height = int((count / max_count) * chart_height) if max_count > 0 else 0
            bar.setFixedSize(60, bar_height)
            
            # 막대 색상 설정 (인덱스로 색상 선택)
            color = colors[i % len(colors)]
            bar.setStyleSheet(f"""
                background-color: {color};
                border: 2px solid #2c3e50;
                border-radius: 4px;
            """)
            
            # 작업자 이름 라벨 (막대 아래)
            worker_label = QLabel(worker)
            worker_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            worker_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #2c3e50;")
            
            # 빈 공간 (막대를 아래쪽에 정렬하기 위함)
            spacer_height = chart_height - bar_height
            if spacer_height > 0:
                spacer = QWidget()
                spacer.setFixedHeight(spacer_height)
                bar_container.addWidget(spacer)
            
            # 컨테이너에 위젯들 추가
            bar_container.addWidget(count_label)
            bar_container.addWidget(bar)
            bar_container.addWidget(worker_label)
            
            # 메인 레이아웃에 추가
            bar_widget = QWidget()
            bar_widget.setLayout(bar_container)
            bar_widget.setFixedWidth(80)
            main_layout.addWidget(bar_widget)
        
        # 여백 추가
        main_layout.addStretch()
