from PyQt6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QLabel, QWidget, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6 import uic
from pathlib import Path
import pandas as pd
from datetime import datetime
import random
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
                existing_counts = df['count'].tolist()
                
                # 각 작업자마다 새로운 데이터(테스트용 랜덤 값) 생성
                new_counts = [random.randint(0, 5) for _ in workers]
                
                # 총 건수 계산 및 표시 (지원 + 지급)
                total_existing = sum(existing_counts)
                total_new = sum(new_counts)
                self.title_label.setText(f"금일 총 신청 건수: {total_existing}건 (지원) + {total_new}건 (지급)")
                
                # 이중 막대 차트 생성
                if workers and existing_counts:
                    self._create_dual_chart(workers, existing_counts, new_counts)
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

    def _create_dual_chart(self, workers: list[str], existing_counts: list[int], new_counts: list[int]):
        """이중 막대그래프를 생성한다 (기존 + 새로운 데이터)."""
        # 기존 레이아웃 정리
        if self.chart_container.layout():
            while self.chart_container.layout().count():
                child = self.chart_container.layout().takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        
        # 메인 레이아웃 설정
        main_layout = QHBoxLayout(self.chart_container)
        main_layout.setSpacing(25)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 최대값 구하기 (차트 스케일용)
        all_counts = existing_counts + new_counts
        max_count = max(all_counts) if all_counts else 1
        chart_height = 200  # 차트 전체 높이
        
        # 막대 색상 설정
        existing_color = '#3498db'  # 파란색 (지원 데이터)
        new_color = '#e74c3c'      # 빨간색 (지급 데이터)
        
        for i, (worker, existing_count, new_count) in enumerate(zip(workers, existing_counts, new_counts)):
            # 각 작업자별 컨테이너
            worker_container = QVBoxLayout()
            worker_container.setAlignment(Qt.AlignmentFlag.AlignBottom)
            worker_container.setSpacing(5)
            
            # 막대들을 담을 수평 레이아웃
            bars_layout = QHBoxLayout()
            bars_layout.setSpacing(3)
            bars_layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
            
            # 기존 데이터 막대
            existing_bar_container = QVBoxLayout()
            existing_bar_container.setAlignment(Qt.AlignmentFlag.AlignBottom)
            existing_bar_container.setSpacing(2)
            
            # 기존 데이터 건수 라벨
            existing_label = QLabel(str(existing_count))
            existing_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            existing_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #ffffff;")
            
            # 기존 데이터 막대
            existing_bar = QWidget()
            existing_bar_height = int((existing_count / max_count) * chart_height) if max_count > 0 else 0
            existing_bar.setFixedSize(25, existing_bar_height)  # 막대를 가늘게
            existing_bar.setStyleSheet(f"""
                background-color: {existing_color};
                border: 1px solid #2c3e50;
                border-radius: 3px;
            """)
            
            # 기존 막대 컨테이너에 추가
            existing_spacer_height = chart_height - existing_bar_height
            if existing_spacer_height > 0:
                existing_spacer = QWidget()
                existing_spacer.setFixedHeight(existing_spacer_height)
                existing_bar_container.addWidget(existing_spacer)
            
            existing_bar_container.addWidget(existing_label)
            existing_bar_container.addWidget(existing_bar)
            
            # 새로운 데이터 막대
            new_bar_container = QVBoxLayout()
            new_bar_container.setAlignment(Qt.AlignmentFlag.AlignBottom)
            new_bar_container.setSpacing(2)
            
            # 새로운 데이터 건수 라벨
            new_label = QLabel(str(new_count))
            new_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            new_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #ffffff;")
            
            # 새로운 데이터 막대
            new_bar = QWidget()
            new_bar_height = int((new_count / max_count) * chart_height) if max_count > 0 else 0
            new_bar.setFixedSize(25, new_bar_height)  # 막대를 가늘게
            new_bar.setStyleSheet(f"""
                background-color: {new_color};
                border: 1px solid #2c3e50;
                border-radius: 3px;
            """)
            
            # 새로운 막대 컨테이너에 추가
            new_spacer_height = chart_height - new_bar_height
            if new_spacer_height > 0:
                new_spacer = QWidget()
                new_spacer.setFixedHeight(new_spacer_height)
                new_bar_container.addWidget(new_spacer)
            
            new_bar_container.addWidget(new_label)
            new_bar_container.addWidget(new_bar)
            
            # 막대들을 수평으로 배치
            existing_bar_widget = QWidget()
            existing_bar_widget.setLayout(existing_bar_container)
            existing_bar_widget.setFixedWidth(30)
            
            new_bar_widget = QWidget()
            new_bar_widget.setLayout(new_bar_container)
            new_bar_widget.setFixedWidth(30)
            
            bars_layout.addWidget(existing_bar_widget)
            bars_layout.addWidget(new_bar_widget)
            
            # 작업자 이름 라벨 (막대들 아래)
            worker_label = QLabel(worker)
            worker_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            worker_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #ffffff;")
            
            # 막대들 위젯
            bars_widget = QWidget()
            bars_widget.setLayout(bars_layout)
            
            # 작업자 컨테이너에 추가
            worker_container.addWidget(bars_widget)
            worker_container.addWidget(worker_label)
            
            # 메인 레이아웃에 추가
            worker_widget = QWidget()
            worker_widget.setLayout(worker_container)
            worker_widget.setFixedWidth(70)
            main_layout.addWidget(worker_widget)
        
        # 범례 추가
        legend_layout = QVBoxLayout()
        legend_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        legend_layout.setSpacing(10)
        
        # 지원 데이터 범례
        existing_legend = QHBoxLayout()
        existing_legend_color = QWidget()
        existing_legend_color.setFixedSize(15, 15)
        existing_legend_color.setStyleSheet(f"background-color: {existing_color}; border: 1px solid #2c3e50;")
        existing_legend_label = QLabel("지원")
        existing_legend_label.setStyleSheet("font-size: 12px; color: #ffffff;")
        existing_legend.addWidget(existing_legend_color)
        existing_legend.addWidget(existing_legend_label)
        existing_legend.addStretch()
        
        # 지급 데이터 범례
        new_legend = QHBoxLayout()
        new_legend_color = QWidget()
        new_legend_color.setFixedSize(15, 15)
        new_legend_color.setStyleSheet(f"background-color: {new_color}; border: 1px solid #2c3e50;")
        new_legend_label = QLabel("지급")
        new_legend_label.setStyleSheet("font-size: 12px; color: #ffffff;")
        new_legend.addWidget(new_legend_color)
        new_legend.addWidget(new_legend_label)
        new_legend.addStretch()
        
        existing_legend_widget = QWidget()
        existing_legend_widget.setLayout(existing_legend)
        new_legend_widget = QWidget()
        new_legend_widget.setLayout(new_legend)
        
        legend_layout.addWidget(existing_legend_widget)
        legend_layout.addWidget(new_legend_widget)
        legend_layout.addStretch()
        
        legend_widget = QWidget()
        legend_widget.setLayout(legend_layout)
        legend_widget.setFixedWidth(60)
        
        # 여백 추가
        main_layout.addStretch()
        main_layout.addWidget(legend_widget)
