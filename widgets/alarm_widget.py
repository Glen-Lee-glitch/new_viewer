from pathlib import Path
from PyQt6.QtWidgets import QWidget, QListWidget, QVBoxLayout, QLabel, QPushButton, QGridLayout, QScrollArea, QDialog
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6 import uic

from core.sql_manager import get_today_completed_subsidies
from widgets.special_note_dialog import SpecialNoteDialog


class AlarmWidget(QWidget):
    """알림 위젯 - PDF 불러오기 전 표시되는 위젯"""
    
    # RN 작업 요청 시그널
    rn_work_requested = pyqtSignal(str)  # RN 번호를 인자로 전달
    
    def __init__(self, worker_name: str = None, parent=None):
        super().__init__(parent)
        
        # 현재 로그인한 작업자 이름 저장
        self._worker_name = worker_name
        
        # UI 파일 로드
        ui_path = Path(__file__).parent.parent / "ui" / "alarm_widget.ui"
        uic.loadUi(str(ui_path), self)
        
        # 처리완료 리스트 위젯 설정
        self._setup_finished_list()
        
        # 서류미비 및 확인필요 리스트 설정
        self._setup_ev_required_list()
        
        # DA 추가요청(수신) 리스트 설정
        self._setup_da_request_list()
        
        # 데이터 로드 (worker_name이 있을 때만)
        if self._worker_name:
            self._load_completed_regions()
            self._update_ev_required_list()
            self._update_da_request_list()
        
        # 특이사항 입력 버튼 연결
        if hasattr(self, 'open_maildialog'):
            self.open_maildialog.clicked.connect(self._open_special_note_dialog)
    
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
    
    def _setup_ev_required_list(self):
        """서류미비 및 확인필요 그룹박스에 리스트 위젯을 설정한다."""
        if hasattr(self, 'groupBox_2'):
            # 기존 레이아웃 가져오기
            layout = self.groupBox_2.layout()
            if layout is None:
                layout = QVBoxLayout(self.groupBox_2)
            
            # 레이아웃 마진 및 간격 조정
            layout.setContentsMargins(2, 15, 2, 2)
            layout.setSpacing(0)
            
            # 스타일 시트 제거
            self.groupBox_2.setStyleSheet("")
            
            # 리스트 위젯 생성
            self._ev_required_list = QListWidget()
            self._ev_required_list.setMaximumHeight(80)
            
            # 폰트 크기 조정
            font = self._ev_required_list.font()
            font.setPointSize(font.pointSize() - 2)
            self._ev_required_list.setFont(font)
            
            layout.addWidget(self._ev_required_list)
            
            # 더블 클릭 시그널 연결
            self._ev_required_list.itemDoubleClicked.connect(self._on_ev_required_item_double_clicked)
    
    def _update_ev_required_list(self):
        """ev_required 정보를 리스트 형태로 갱신한다."""
        if not self._worker_name or not hasattr(self, '_ev_required_list'):
            return
            
        from core.sql_manager import fetch_all_ev_required_rns
        try:
            rn_data_list = fetch_all_ev_required_rns(self._worker_name)
            self._ev_required_list.clear()
            
            if rn_data_list:
                for rn, source_type in rn_data_list:
                    prefix = ""
                    if source_type == 'ev_complement':
                        prefix = "(EV) "
                    elif source_type == 'chained_emails':
                        prefix = "(요청) "
                    
                    self._ev_required_list.addItem(f"{prefix}{rn}")
            else:
                self._ev_required_list.addItem("내역 없음")
                
        except Exception as e:
            print(f"서류미비 목록 로드 중 오류: {e}")
            self._ev_required_list.clear()
            self._ev_required_list.addItem("로드 실패")

    def _on_ev_required_item_double_clicked(self, item):
        """서류미비 리스트 아이템 더블 클릭 시 작업 요청 시그널을 발생시킨다."""
        text = item.text()
        if text in ["내역 없음", "로드 실패"]:
            return
            
        # 접두어 제거하고 RN만 추출
        rn = text.replace("(EV) ", "").replace("(요청) ", "").strip()
        if rn:
            self.rn_work_requested.emit(rn)
    
    def _load_completed_regions(self):
        """
        TODO: MySQL 데이터베이스 미사용으로 인해 임시 비활성화
        오늘 완료된 지역 목록을 로드한다.
        """
        if not hasattr(self, '_finished_list'):
            return
        
        # TODO: MySQL 데이터베이스 미사용으로 인해 임시 비활성화
        # 아무것도 표시하지 않도록 리스트만 클리어
        self._finished_list.clear()
    
    def _handle_ev_complement_click(self):
        """
        ev_complement 타입 버튼 클릭 시 호출되는 함수.
        현재는 아무 작동도 하지 않으며, 추후 구현 예정.
        """
        pass
    
    def refresh_data(self):
        """데이터를 수동으로 새로고침한다."""
        self._load_completed_regions()
        self._update_ev_required_list()
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
            
            # 다이얼로그 결과 처리
            result = dialog.exec()
            if result == QDialog.DialogCode.Accepted:
                # 처리완료 시 목록 갱신
                self.refresh_data()
                # 메인 윈도우 새로고침 (데이터 갱신을 위해)
                if hasattr(self.window(), 'refresh_data'):
                    self.window().refresh_data()
            elif result == 3:
                # 처리시작 시 작업 요청 시그널 발생
                self.rn_work_requested.emit(rn)
            
        except Exception as e:
            print(f"이메일 확인 중 오류 발생: {e}")
            QMessageBox.critical(self, "오류", f"이메일 확인 중 오류가 발생했습니다.\n{e}")

    def _open_special_note_dialog(self):
        """특이사항 입력 다이얼로그를 연다."""
        dialog = SpecialNoteDialog(parent=self)
        
        # MainWindow의 PdfLoadWidget에서 선택된 RN 가져오기
        try:
            main_window = self.window()
            if hasattr(main_window, 'pdf_load_widget'):
                selected_rn = main_window.pdf_load_widget.get_selected_rn()
                if selected_rn and hasattr(dialog, 'RN_lineEdit'):
                    dialog.RN_lineEdit.setText(selected_rn)
        except Exception as e:
            print(f"RN 자동 입력 실패: {e}")
            
        dialog.exec()

