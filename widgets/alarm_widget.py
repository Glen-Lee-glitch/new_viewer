from pathlib import Path
from PyQt6.QtWidgets import QWidget, QListWidget, QVBoxLayout, QLabel, QPushButton, QGridLayout
from PyQt6.QtCore import QTimer, Qt
from PyQt6 import uic

from core.sql_manager import get_today_completed_subsidies
from widgets.mail_dialog import MailDialog


class AlarmWidget(QWidget):
    """알림 위젯 - PDF 불러오기 전 표시되는 위젯"""
    
    def __init__(self, worker_name: str = None, parent=None):
        super().__init__(parent)
        
        # 현재 로그인한 작업자 이름 저장
        self._worker_name = worker_name
        
        # UI 파일 로드
        ui_path = Path(__file__).parent.parent / "ui" / "alarm_widget.ui"
        uic.loadUi(str(ui_path), self)
        
        # 처리완료 리스트 위젯 설정
        self._setup_finished_list()
        
        # ev_required 버튼 설정 (초기화만, 데이터 로드는 로그인 후)
        self._setup_ev_required_buttons()
        
        # 데이터 로드 (worker_name이 있을 때만)
        if self._worker_name:
            self._load_completed_regions()
            self._update_ev_required_buttons()
        
        # 이메일 전송 버튼 연결
        if hasattr(self, 'open_maildialog'):
            self.open_maildialog.clicked.connect(self._open_mail_dialog)

        # # 주기적 업데이트 타이머 (5분마다)
        # self._timer = QTimer()
        # self._timer.timeout.connect(self._load_completed_regions)
        # self._timer.start(300000)  # 5분 = 300,000ms
    
    def _setup_finished_list(self):
        """처리완료 그룹박스에 리스트 위젯을 추가한다."""
        if hasattr(self, 'groupBox_finished'):
            # 기존 레이아웃 가져오기
            layout = self.groupBox_finished.layout()
            if layout is None:
                layout = QVBoxLayout(self.groupBox_finished)
            
            # 제목 라벨 추가
            title_label = QLabel("금일 처리완료 건")
            title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_label.setStyleSheet("font-weight: bold; color: #333; margin-bottom: 5px;")
            layout.addWidget(title_label)
            
            # 리스트 위젯 생성 및 추가
            self._finished_list = QListWidget()
            # 최소 5개 row가 보이도록 높이 조정 (항목당 약 28px로 계산)
            self._finished_list.setMinimumHeight(120)  # 5 * 28 = 140px
            self._finished_list.setMaximumHeight(140)  # 최대 높이도 약간 증가

            # 폰트 크기 조정 (1pt 줄이기)
            font = self._finished_list.font()
            font.setPointSize(font.pointSize() - 2)
            self._finished_list.setFont(    font)

            layout.addWidget(self._finished_list)
    
    def _setup_ev_required_buttons(self):
        """서류미비 및 확인필요 그룹박스에 버튼 컨테이너를 설정한다."""
        if hasattr(self, 'groupBox_2'):
            # 기존 레이아웃 가져오기
            layout = self.groupBox_2.layout()
            if layout is None:
                layout = QVBoxLayout(self.groupBox_2)
            
            # 버튼 컨테이너 생성 (나중에 업데이트할 때 사용)
            self._ev_buttons_container = QWidget()
            layout.addWidget(self._ev_buttons_container)
    
    def _update_ev_required_buttons(self):
        """ev_required 테이블 정보를 바탕으로 버튼을 갱신한다."""
        if not self._worker_name:
            return
        
        if not hasattr(self, 'groupBox_2'):
            return
        
        from core.sql_manager import fetch_ev_required_rns
        rn_list = fetch_ev_required_rns(self._worker_name)
        
        # groupBox_2의 레이아웃 가져오기
        parent_layout = self.groupBox_2.layout()
        if not parent_layout:
            return
        
        # 기존 컨테이너 제거
        if hasattr(self, '_ev_buttons_container') and self._ev_buttons_container:
            parent_layout.removeWidget(self._ev_buttons_container)
            self._ev_buttons_container.deleteLater()
            self._ev_buttons_container = None
        
        if not rn_list:
            return
        
        # 새 컨테이너 생성
        self._ev_buttons_container = QWidget()
        container_layout = QGridLayout(self._ev_buttons_container)
        container_layout.setContentsMargins(0, 5, 0, 0)
        container_layout.setSpacing(5)
        
        # 버튼 생성 및 배치 (2열로 배치)
        cols = 2
        for i, rn in enumerate(rn_list):
            btn = QPushButton(rn)
            # 스타일 설정: 글자 크기 조정, 패딩 최소화, 높이 조정
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 11px;
                    padding: 3px;
                    min-height: 20px;
                }
            """)
            
            row = i // cols
            col = i % cols
            container_layout.addWidget(btn, row, col)
        
        # 새 컨테이너를 groupBox_2에 추가
        parent_layout.addWidget(self._ev_buttons_container)
    
    def _load_completed_regions(self):
        """오늘 완료된 지역 목록을 로드한다."""
        if not hasattr(self, '_finished_list'):
            return
        
        try:
            # 현재 로그인한 작업자 정보와 함께 완료된 지역 및 시간 목록 조회
            completed_items = get_today_completed_subsidies(self._worker_name)
            
            # 리스트 클리어 후 새 데이터 추가
            self._finished_list.clear()
            
            if completed_items:
                for region, completed_at in completed_items:
                    # 시간 포맷팅: HH_MM (예: 15_57)
                    time_str = completed_at.strftime('%H_%M')
                    item_text = f"✅ {region}_{time_str}"
                    self._finished_list.addItem(item_text)
            else:
                if self._worker_name:
                    self._finished_list.addItem(f"오늘 {self._worker_name}님이 완료한 지원 건이 없습니다.")
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
        self._update_ev_required_buttons()

    def _open_mail_dialog(self):
        """메일 전송 다이얼로그를 연다."""
        dialog = MailDialog(parent=self)
        dialog.set_worker_name(self._worker_name)
        dialog.exec()

