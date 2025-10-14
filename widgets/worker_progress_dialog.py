from PyQt6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QLabel, QWidget, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6 import uic
from pathlib import Path
import pandas as pd
from datetime import datetime
from core.sql_manager import get_daily_worker_progress

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
        try:
            # 데이터베이스에서 작업자별 현황 조회
            df = get_daily_worker_progress()
            
            if not df.empty:
                # 데이터프레임에서 작업자와 건수 추출
                workers = df['worker'].tolist()
                counts = df['count'].tolist()
                
                # 총 건수 계산 및 표시
                total_count = sum(counts)
                self.title_label.setText(f"금일 총 신청 건수: {total_count}건")
                
                # 차트 생성
                if workers and counts:
                    self._create_chart(workers, counts)
                else:
                    self._show_no_data_message()
            else:
                # 데이터가 없는 경우
                self.title_label.setText("금일 총 신청 건수: 0건")
                self._show_no_data_message()
                
        except Exception as e:
            self._show_error_message(f"데이터 로드 중 오류가 발생했습니다: {str(e)}")
    
    def _show_no_data_message(self):
        """데이터가 없을 때 메시지를 표시한다."""
        # 빈 차트 대신 메시지 표시
        if self.chart_container.layout():
            while self.chart_container.layout().count():
                child = self.chart_container.layout().takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        
        layout = QVBoxLayout(self.chart_container)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        message_label = QLabel("오늘 처리된 신청 건이 없습니다.")
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message_label.setStyleSheet("font-size: 16px; color: #ffffff; margin: 50px;")
        layout.addWidget(message_label)
    
    def _show_error_message(self, message: str):
        """오류 메시지를 표시한다."""
        QMessageBox.critical(self, "데이터 로드 오류", message)
        self.title_label.setText("데이터 로드 실패")
        self._show_no_data_message()
    
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
            count_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff;")
            
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
            worker_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #ffffff;")
            
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
