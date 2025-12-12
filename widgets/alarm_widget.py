from pathlib import Path
from PyQt6.QtWidgets import QWidget, QListWidget, QVBoxLayout, QLabel, QPushButton, QGridLayout, QScrollArea, QDialog
from PyQt6.QtCore import QTimer, Qt
from PyQt6 import uic

from core.sql_manager import get_today_completed_subsidies
from widgets.special_note_dialog import SpecialNoteDialog


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
        
        # DA 추가요청(수신) 리스트 설정
        self._setup_da_request_list()
        
        # 데이터 로드 (worker_name이 있을 때만)
        if self._worker_name:
            self._load_completed_regions()
            self._update_ev_required_buttons()
            self._update_da_request_list()
        
        # 특이사항 입력 버튼 연결
        if hasattr(self, 'open_maildialog'):
            self.open_maildialog.clicked.connect(self._open_special_note_dialog)

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
            
            # 레이아웃 마진 및 간격 조정 (타이틀 공간 확보를 위해 상단 마진 추가)
            layout.setContentsMargins(2, 15, 2, 2)
            layout.setSpacing(0)
            
            # 스타일 시트 제거 (기본 테마 스타일 사용)
            self.groupBox_finished.setStyleSheet("")
            
            # 리스트 위젯 생성 및 추가
            self._finished_list = QListWidget()
            # 높이 조정 (항목당 약 24px로 계산, 3~4개 보이도록 축소)
            self._finished_list.setMinimumHeight(60)  
            self._finished_list.setMaximumHeight(80)

            # 폰트 크기 조정 (1pt 줄이기)
            font = self._finished_list.font()
            font.setPointSize(font.pointSize() - 2)
            self._finished_list.setFont(font)

            layout.addWidget(self._finished_list)
    
    def _setup_ev_required_buttons(self):
        """서류미비 및 확인필요 그룹박스에 버튼 컨테이너를 설정한다."""
        if hasattr(self, 'groupBox_2'):
            # 기존 레이아웃 가져오기
            layout = self.groupBox_2.layout()
            if layout is None:
                layout = QVBoxLayout(self.groupBox_2)
            
            # 레이아웃 마진 및 간격 조정 (타이틀 공간 확보를 위해 상단 마진 추가)
            layout.setContentsMargins(2, 15, 2, 2)
            layout.setSpacing(0)
            
            # 스타일 시트 제거 (기본 테마 스타일 사용)
            self.groupBox_2.setStyleSheet("")
            
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
        
        # 기존 컨테이너 제거 (QScrollArea 포함)
        if hasattr(self, '_ev_buttons_scroll_area') and self._ev_buttons_scroll_area:
            parent_layout.removeWidget(self._ev_buttons_scroll_area)
            self._ev_buttons_scroll_area.deleteLater()
            self._ev_buttons_scroll_area = None
        elif hasattr(self, '_ev_buttons_container') and self._ev_buttons_container:
            # 혹시 이전 버전의 컨테이너가 남아있다면 제거
            parent_layout.removeWidget(self._ev_buttons_container)
            self._ev_buttons_container.deleteLater()
            self._ev_buttons_container = None
        
        if not rn_list:
            return
        
        # 스크롤 영역 생성
        self._ev_buttons_scroll_area = QScrollArea()
        self._ev_buttons_scroll_area.setWidgetResizable(True)
        self._ev_buttons_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._ev_buttons_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # 스크롤 영역 내부 컨테이너 위젯
        scroll_content = QWidget()
        self._ev_buttons_scroll_area.setWidget(scroll_content)
        
        # 세로 정렬 레이아웃 (VBoxLayout)
        container_layout = QVBoxLayout(scroll_content)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(3)
        # 위쪽 정렬 (버튼이 위에서부터 쌓이도록)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # QSizePolicy 임포트 확인
        from PyQt6.QtWidgets import QSizePolicy
        
        for i, rn in enumerate(rn_list):
            btn = QPushButton(rn)
            
            # 사이즈 정책 및 높이 강제 고정
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setFixedHeight(22)  # 높이를 강제로 22px로 고정
            
            # 스타일 설정
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 11px;
                    padding: 0px;
                    margin: 0px;
                    border: 1px solid #555;
                    border-radius: 2px;
                    background-color: rgba(255, 255, 255, 0.05);
                    text-align: center;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.15);
                    border: 1px solid #777;
                }
                QPushButton:pressed {
                    background-color: rgba(255, 255, 255, 0.25);
                }
            """)
            
            container_layout.addWidget(btn)
        
        # 높이 설정: 버튼 하나당 높이(22) + 간격(3) = 25
        item_height = 25
        
        # 5개 이하일 때는 스크롤 없이 모두 표시
        if len(rn_list) <= 5:
            # 내용물 크기에 맞춤 (스크롤 필요 없음)
            # 여유분 10px 추가 (테마 패딩 등 고려하여 넉넉하게)
            needed_h = len(rn_list) * item_height + 10
            self._ev_buttons_scroll_area.setFixedHeight(needed_h)
            self._ev_buttons_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        else:
            # 5개 초과 시 최대 5개 높이로 제한하고 스크롤 활성화
            max_h = 5 * item_height + 10
            self._ev_buttons_scroll_area.setFixedHeight(max_h)
            self._ev_buttons_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # 5개 이하일 때는 스크롤 없이 모두 표시
        if len(rn_list) <= 5:
            # 내용물 크기에 맞춤 (스크롤 필요 없음)
            # 여유분 5px 추가
            needed_h = len(rn_list) * item_height + 5
            self._ev_buttons_scroll_area.setFixedHeight(needed_h)
            self._ev_buttons_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        else:
            # 5개 초과 시 최대 5개 높이로 제한하고 스크롤 활성화
            max_h = 5 * item_height + 5
            self._ev_buttons_scroll_area.setFixedHeight(max_h)
            self._ev_buttons_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # 스크롤 영역 테두리 제거 (깔끔하게 보이도록)
        self._ev_buttons_scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        
        # 새 스크롤 영역을 groupBox_2에 추가
        parent_layout.addWidget(self._ev_buttons_scroll_area)
    
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
        self._update_da_request_list()

    def _setup_da_request_list(self):
        """DA 추가요청(수신) 그룹박스에 리스트 위젯을 설정한다."""
        if hasattr(self, 'groupBox_3'):
            # 기존 레이아웃 가져오기
            layout = self.groupBox_3.layout()
            if layout is None:
                layout = QVBoxLayout(self.groupBox_3)
            
            # 레이아웃 마진 및 간격 조정
            layout.setContentsMargins(2, 15, 2, 2)
            layout.setSpacing(0)
            
            # 스타일 시트 제거
            self.groupBox_3.setStyleSheet("")
            
            # 리스트 위젯 생성
            self._da_request_list = QListWidget()
            # 높이 조정 (적절히 조절)
            self._da_request_list.setMaximumHeight(80) 
            
            # 폰트 크기 조정
            font = self._da_request_list.font()
            font.setPointSize(font.pointSize() - 2)
            self._da_request_list.setFont(font)

            layout.addWidget(self._da_request_list)
            
            # 더블 클릭 시그널 연결
            self._da_request_list.itemDoubleClicked.connect(self._on_da_request_item_double_clicked)

    def _update_da_request_list(self):
        """중복메일(DA 추가요청) 목록을 업데이트한다."""
        if not self._worker_name or not hasattr(self, '_da_request_list'):
            return
            
        from core.sql_manager import fetch_duplicate_mail_rns
        
        try:
            rn_list = fetch_duplicate_mail_rns(self._worker_name)
            
            self._da_request_list.clear()
            
            if rn_list:
                for rn in rn_list:
                    self._da_request_list.addItem(f"🔔 {rn}")
            else:
                self._da_request_list.addItem("요청 내역 없음")
                
        except Exception as e:
            print(f"DA 추가요청 로드 중 오류: {e}")
            self._da_request_list.clear()
            self._da_request_list.addItem("로드 실패")

    def _on_da_request_item_double_clicked(self, item):
        """DA 추가요청 리스트 아이템 더블 클릭 시 이메일 내용을 확인한다."""
        text = item.text()
        if not text.startswith("🔔 "):
            return
            
        # "🔔 RN..." 형식에서 RN 추출
        rn = text.replace("🔔 ", "").strip()
        if not rn:
            return
            
        from core.sql_manager import get_recent_thread_id_by_rn, get_email_by_thread_id, get_original_worker_by_rn
        from widgets.email_view_dialog import EmailViewDialog
        from PyQt6.QtWidgets import QMessageBox
        
        try:
            # 1. RN으로 thread_id 조회
            thread_id = get_recent_thread_id_by_rn(rn)
            if not thread_id:
                QMessageBox.warning(self, "알림", "연결된 메일 정보를 찾을 수 없습니다.")
                return
                
            # 2. thread_id로 이메일 내용 조회
            email_data = get_email_by_thread_id(thread_id)
            if not email_data:
                QMessageBox.warning(self, "알림", "메일 내용을 불러올 수 없습니다.")
                return
            
            # 3. 기존 작업자 정보 조회
            original_worker = get_original_worker_by_rn(rn)
                
            # 4. 다이얼로그 표시
            title = email_data.get('title', '제목 없음')
            content = email_data.get('content', '내용 없음')
            
            dialog = EmailViewDialog(title=title, content=content, original_worker=original_worker, rn=rn, parent=self)
            
            # 다이얼로그가 '처리완료'로 닫혔을 때(Accepted) 목록 갱신
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.refresh_data()
                # 메인 윈도우 새로고침 (데이터 갱신을 위해)
                if hasattr(self.window(), 'refresh_data'):
                    self.window().refresh_data()
            
        except Exception as e:
            print(f"이메일 확인 중 오류 발생: {e}")
            QMessageBox.critical(self, "오류", f"이메일 확인 중 오류가 발생했습니다.\n{e}")

    def _open_special_note_dialog(self):
        """특이사항 입력 다이얼로그를 연다."""
        dialog = SpecialNoteDialog(parent=self)
        dialog.exec()

