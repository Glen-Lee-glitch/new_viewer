from PyQt6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QLabel, QWidget, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal, QRectF
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen
from PyQt6 import uic
from pathlib import Path
import math
from core.sql_manager import (
    get_daily_worker_progress, 
    get_daily_worker_payment_progress,
    fetch_daily_status_counts,
    fetch_today_completed_worker_stats
)

class ClickableCard(QWidget):
    """클릭 가능한 카드 위젯"""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

class PieChartWidget(QWidget):
    """파이 차트 위젯"""
    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.data = data  # {'label': value, ...}
        self.colors = [
            QColor("#3498db"), QColor("#e74c3c"), QColor("#2ecc71"), 
            QColor("#f1c40f"), QColor("#9b59b6"), QColor("#e67e22"), 
            QColor("#1abc9c"), QColor("#34495e")
        ]
        self.setMinimumSize(300, 200)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        side = min(rect.width(), rect.height())
        pie_rect = QRectF(10, 10, side - 20, side - 20)
        
        # 데이터 총합 계산
        total = sum(self.data.values())
        if total == 0:
            painter.setPen(QColor("white"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "데이터 없음")
            return

        # 파이 차트 그리기
        start_angle = 90 * 16
        color_index = 0
        
        # 범례 시작 위치 (오른쪽 여백)
        legend_x = side + 20
        legend_y = 20
        legend_available = rect.width() > side + 50

        for label, value in self.data.items():
            if value == 0: continue

            span_angle = int(-(value / total) * 360 * 16)
            
            color = self.colors[color_index % len(self.colors)]
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            
            painter.drawPie(pie_rect, start_angle, span_angle)
            
            # 범례 그리기 (공간이 있을 때만)
            if legend_available and legend_y + 20 < rect.height():
                painter.setBrush(QBrush(color))
                painter.drawRect(int(legend_x), int(legend_y), 15, 15)
                
                painter.setPen(QColor("white"))
                percentage = (value / total) * 100
                text = f"{label}: {value}건 ({percentage:.1f}%)"
                painter.drawText(int(legend_x + 25), int(legend_y + 12), text)
                
                legend_y += 25

            start_angle += span_angle
            color_index += 1

class WorkerProgressDialog(QDialog):
    """전체 업무 현황판 다이얼로그"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # UI 파일 로드
        ui_path = Path(__file__).parent.parent / "ui" / "worker_progress.ui"
        uic.loadUi(str(ui_path), self)
        
        # 다이얼로그 설정
        self.setWindowTitle("전체 업무 현황판")
        self.setModal(True)
        
        # 초기화
        self._setup_ui()
        # 데이터 로드는 창이 보일 때(showEvent) 혹은 명시적으로 호출
    
    def showEvent(self, event):
        """다이얼로그가 표시될 때 데이터를 로드한다."""
        super().showEvent(event)
        self._load_overall_status()

    def _setup_ui(self):
        """UI 컴포넌트를 설정한다."""
        # 버튼 연결
        self.close_button.clicked.connect(self.accept)
        self.refresh_button.clicked.connect(self._load_overall_status)
        
        # 요약 정보 위젯 참조 저장소
        self.summary_widgets = {}
        self.current_chart_type = None  # 현재 표시 중인 차트 타입 (toggle 기능용)
        
        # 요약 정보 레이아웃 초기화 (Placeholders)
        self._init_summary_ui()
    
    def _init_summary_ui(self):
        """요약 UI 구조를 초기화한다."""
        self._clear_layout(self.summary_layout)
        self.summary_widgets.clear()
        
        # 초기 카드 생성 및 참조 저장
        self._create_summary_card("pipeline", "파이프라인", "#3498db")
        self._create_summary_card("processing", "처리중", "#f1c40f")
        self._create_summary_card("completed", "완료", "#2ecc71", clickable=True, onClick=self._show_completed_stats)
        self._create_summary_card("deferred", "미비/보류", "#e74c3c")
        self._create_summary_card("impossible", "신청불가", "#95a5a6")
        
    def _create_summary_card(self, key: str, label: str, color: str, clickable=False, onClick=None):
        """요약 카드를 생성하고 레이아웃에 추가한다."""
        if clickable:
            card = ClickableCard()
            if onClick:
                card.clicked.connect(onClick)
        else:
            card = QWidget()
            
        card.setStyleSheet(f"""
            QWidget {{
                background-color: #2c3e50;
                border-radius: 10px;
                border: 1px solid #3e5871;
            }}
            QWidget:hover {{
                border: {'2px solid ' + color if clickable else '1px solid #3e5871'};
                background-color: {'#34495e' if clickable else '#2c3e50'};
            }}
        """)
        card.setMinimumHeight(100)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(15, 15, 15, 15)
        card_layout.setSpacing(5)
        
        val_label = QLabel("0")
        val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_label.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {color}; border: none; background: transparent;")
        
        txt_label = QLabel(label)
        txt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        txt_label.setStyleSheet("font-size: 14px; color: #bdc3c7; border: none; background: transparent;")
        
        card_layout.addWidget(val_label)
        card_layout.addWidget(txt_label)
        
        self.summary_layout.addWidget(card)
        
        # 값 라벨에 대한 참조 저장
        self.summary_widgets[key] = val_label

    def _refresh_summary_ui(self, pipeline="0", processing="0", completed="0", deferred="0", impossible="0"):
        """요약 영역의 값을 갱신한다."""
        if "pipeline" in self.summary_widgets:
            self.summary_widgets["pipeline"].setText(str(pipeline))
        if "processing" in self.summary_widgets:
            self.summary_widgets["processing"].setText(str(processing))
        if "completed" in self.summary_widgets:
            self.summary_widgets["completed"].setText(str(completed))
        if "deferred" in self.summary_widgets:
            self.summary_widgets["deferred"].setText(str(deferred))
        if "impossible" in self.summary_widgets:
            self.summary_widgets["impossible"].setText(str(impossible))
    
    def _clear_layout(self, layout):
        """레이아웃 내의 모든 위젯을 제거한다."""
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                elif child.layout():
                    self._clear_layout(child.layout())

    def _load_overall_status(self):
        """전체 업무 현황 데이터를 로드한다."""
        try:
            # 통합 쿼리 함수 호출
            counts = fetch_daily_status_counts()
            
            self._refresh_summary_ui(
                pipeline=counts.get('pipeline', 0),
                processing=counts.get('processing', 0),
                completed=counts.get('completed', 0),
                deferred=counts.get('deferred', 0),
                impossible=counts.get('impossible', 0)
            )
            
            # 하단 타이틀 업데이트
            self.title_label.setText(f"실시간 업무 현황 (금일 접수: {counts.get('pipeline', 0)}건)")
            
            # 차트 컨테이너 초기화 (기본 메시지)
            self._show_message_in_chart("상단의 '완료' 카드를 클릭하면 상세 통계를 볼 수 있습니다.")
            self.current_chart_type = None
            
        except Exception as e:
            print(f"Error loading status: {e}")
            self.title_label.setText("데이터 로드 실패")

    def _show_completed_stats(self):
        """완료 건에 대한 상세 통계(파이 차트)를 보여준다 (토글 방식)."""
        # 토글 로직: 이미 보고 있다면 닫기
        if self.current_chart_type == 'completed':
            self._show_message_in_chart("상단의 '완료' 카드를 클릭하면 상세 통계를 볼 수 있습니다.")
            self.current_chart_type = None
            return

        try:
            stats = fetch_today_completed_worker_stats()
            
            # 차트 컨테이너 비우기
            self._clear_layout(self.chart_container.layout())
            
            # 레이아웃 생성 및 설정
            if self.chart_container.layout() is None:
                layout = QVBoxLayout()
                self.chart_container.setLayout(layout)
            
            if not stats:
                self._show_message_in_chart("완료된 작업 데이터가 없습니다.")
                self.current_chart_type = 'completed' # 데이터 없어도 상태는 변경
                return

            # 파이 차트 위젯 생성 및 추가
            chart = PieChartWidget(stats)
            self.chart_container.layout().addWidget(chart)
            
            self.current_chart_type = 'completed'
            
        except Exception as e:
            self._show_message_in_chart(f"차트 로드 실패: {str(e)}")
            self.current_chart_type = None

    def _show_message_in_chart(self, message: str):
        """차트 영역에 메시지를 표시한다."""
        # 차트 컨테이너 비우기
        if self.chart_container.layout():
            self._clear_layout(self.chart_container.layout())
        
        # 레이아웃 생성 및 설정
        if self.chart_container.layout() is None:
            layout = QVBoxLayout()
            self.chart_container.setLayout(layout)
            
        label = QLabel(message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #bdc3c7; font-size: 14px;")
        self.chart_container.layout().addWidget(label)
    
    def _load_worker_progress(self):
        """이전 작업자 현황 로드 로직 (필요 시 현황판 하단 차트용으로 재구성 가능)"""
        pass
    
    def _show_no_data_message(self):
        pass
    
    def _show_error_message(self, message: str):
        pass
    
    def _create_chart(self, workers: list[str], counts: list[int]):
        pass

    def _create_dual_chart(self, workers: list[str], existing_counts: list[int], new_counts: list[int]):
        pass