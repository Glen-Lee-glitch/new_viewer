from pathlib import Path
from PyQt6.QtWidgets import QWidget, QListWidget, QVBoxLayout, QLabel, QPushButton, QGridLayout, QScrollArea, QDialog
from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QSettings
from PyQt6 import uic

from core.sql_manager import get_today_completed_subsidies
from widgets.special_note_dialog import SpecialNoteDialog


class AlarmWidget(QWidget):
    """알림 위젯 - PDF 불러오기 전 표시되는 위젯"""
    
    # RN 작업 요청 시그널: (RN 번호, EV 보완 여부, CE 요청 여부)
    rn_work_requested = pyqtSignal(str, bool, bool)  # RN 번호, EV 보완 여부, CE 요청 여부를 인자로 전달
    
    def __init__(self, worker_name: str = None, parent=None):
        super().__init__(parent)
        
        # 현재 로그인한 작업자 이름 저장
        self._worker_name = worker_name
        self._special_note_dialog = None  # 비모달 다이얼로그 인스턴스 유지용
        self._notified_chained_rns = set()  # 이미 알림을 띄운 (요청) RN 목록
        
        # UI 파일 로드
        ui_path = Path(__file__).parent.parent / "ui" / "alarm_widget.ui"
        uic.loadUi(str(ui_path), self)
        
        # 위젯 매핑 (순서 변경용)
        self._widget_map = {
            "email": self.groupBox_email,
            "memo": self.groupBox_memo_management,
            "ev_check": self.groupBox_2,
            "da_request": self.groupBox_3
        }

        # 메모 리스트 위젯 및 레이아웃 설정
        self._setup_memo_list()
        
        # 서류미비 및 확인필요 리스트 설정
        self._setup_ev_required_list()
        
        # DA 추가요청(수신) 리스트 설정
        self._setup_da_request_list()
        
        # 데이터 로드 (worker_name이 있을 때만)
        if self._worker_name:
            self._update_ev_required_list()
            self._update_da_request_list()
        
        # 특이사항 입력 버튼 연결
        if hasattr(self, 'open_maildialog'):
            self.open_maildialog.clicked.connect(self._open_special_note_dialog)
            
        # 메모 작성 버튼 연결
        if hasattr(self, 'pushButton_write_memo'):
            self.pushButton_write_memo.clicked.connect(self._on_write_memo_clicked)
            
        # 레이아웃 순서 적용
        self._apply_layout_order()

    def _apply_layout_order(self):
        """저장된 설정에 따라 레이아웃 순서를 적용합니다."""
        settings = QSettings("GyeonggooLee", "NewViewer")
        default_order = ["email", "memo", "ev_check", "da_request"]
        order = settings.value("layout/info_panel_order", default_order)
        
        if isinstance(order, list):
            self.set_layout_order(order)

    def set_layout_order(self, order_list):
        """주어진 키 순서대로 위젯을 재배치합니다."""
        layout = self.layout()
        if not layout:
            return
            
        # 순서대로 다시 추가 (기존 레이아웃에서 자동으로 이동됨)
        for key in order_list:
            widget = self._widget_map.get(key)
            if widget:
                layout.addWidget(widget)
                widget.show()

    def _setup_memo_list(self):
        """메모관리 그룹박스의 리스트 위젯 스타일 및 레이아웃 설정"""
        if hasattr(self, 'listWidget_memos'):
            # 폰트 크기 조정
            font = self.listWidget_memos.font()
            font.setPointSize(font.pointSize() - 2)
            self.listWidget_memos.setFont(font)
            
            # 레이아웃 여백 조정
            if hasattr(self, 'groupBox_memo_management'):
                layout = self.groupBox_memo_management.layout()
                if layout:
                    layout.setContentsMargins(4, 15, 4, 4)
                    layout.setSpacing(2)

    def _refresh_memo_list(self, rn: str):
        """특정 RN의 메모 목록을 DB에서 가져와 리스트 위젯에 표시한다."""
        if not hasattr(self, 'listWidget_memos') or not rn:
            return
            
        self.listWidget_memos.clear()

        from core.sql_manager import fetch_user_memos
        try:
            memos = fetch_user_memos(rn)
            for memo in memos:
                from datetime import datetime
                created_at = memo['created_at']
                time_str = created_at.strftime("%m/%d %H:%M") if isinstance(created_at, datetime) else str(created_at)
                worker_name = memo.get('worker_name') or "알 수 없음"
                content = memo['comment']
                
                self.listWidget_memos.addItem(f"[{time_str}] {worker_name}: {content}")
            
            self.listWidget_memos.scrollToTop()
        except Exception as e:
            print(f"메모 목록 로드 오류 (RN: {rn}): {e}")

    def _on_write_memo_clicked(self):
        """메모 작성 버튼 클릭 시 처리"""
        # 현재 선택된 RN 확인
        rn = ""
        try:
            main_window = self.window()
            if hasattr(main_window, 'pdf_load_widget'):
                rn = main_window.pdf_load_widget.get_selected_rn() or ""
        except Exception:
            pass
            
        if not rn:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "경고", "선택된 RN이 없습니다.")
            return

        # 입력 내용 확인
        if not hasattr(self, 'textEdit_memo_input'):
            return
            
        comment = self.textEdit_memo_input.toPlainText().strip()
        if not comment:
            return

        # 작업자 ID 확인 (MainWindow에서 가져옴)
        worker_id = None
        try:
            worker_id = getattr(self.window(), '_worker_id', None)
        except Exception:
            pass
            
        if worker_id is None:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "경고", "작업자 정보를 확인할 수 없습니다. 다시 로그인해주세요.")
            return

        # DB 저장
        from core.sql_manager import insert_user_memo
        if insert_user_memo(rn, worker_id, comment):
            self.textEdit_memo_input.clear()
            self._refresh_memo_list(rn)
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "오류", "메모 저장에 실패했습니다.")

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
            
            # 강조 스타일 시트 적용 (카드 형태 디자인)
            self._ev_required_list.setStyleSheet("""
                QListWidget {
                    background-color: transparent;
                    border: none;
                }
                QListWidget::item {
                    background-color: rgba(29, 233, 182, 0.15); /* 틴트된 배경색 */
                    border: 1px solid #1de9b6;                   /* 밝은 틸 색상 테두리 */
                    border-radius: 6px;                          /* 둥근 모서리 */
                    margin: 4px 2px;                             /* 아이템 간격 */
                    padding: 8px;                                /* 내부 여백 */
                    color: #1de9b6;                              /* 텍스트 색상도 강조색으로 */
                    font-weight: bold;
                    font-size: 13px;                             /* 폰트 크기 명시 */
                }
                QListWidget::item:hover {
                    background-color: rgba(29, 233, 182, 0.3);  /* 호버 시 더 밝게 */
                    cursor: pointer;
                }
                QListWidget::item:selected {
                    background-color: #1de9b6;                  /* 선택 시 반전 */
                    color: #263238;                             /* 텍스트 어둡게 및 진하게 */
                    border: 1px solid #1de9b6;
                }
            """)
            
            layout.addWidget(self._ev_required_list)
            
            # 더블 클릭 시그널 연결
            self._ev_required_list.itemDoubleClicked.connect(self._on_ev_required_item_double_clicked)
    
    def _update_ev_required_list(self):
        """ev_required 정보를 리스트 형태로 갱신한다."""
        if not self._worker_name or not hasattr(self, '_ev_required_list'):
            return
            
        from core.sql_manager import fetch_all_ev_required_rns
        from widgets.alert_dialog import show_toast

        try:
            rn_data_list = fetch_all_ev_required_rns(self._worker_name)
            self._ev_required_list.clear()
            
            current_chained_rns = set()

            if rn_data_list:
                for rn, source_type in rn_data_list:
                    prefix = ""
                    if source_type == 'ev_complement':
                        prefix = "(EV) "
                    elif source_type == 'chained_emails':
                        prefix = "(요청) "
                        current_chained_rns.add(rn)
                        
                        # 새로운 (요청) 건인 경우 알림 띄우기
                        if rn not in self._notified_chained_rns:
                            show_toast(
                                title="[확인 요청] 추가 메일 수신",
                                message=f"RN: {rn}\n추가 서류 또는 문의 메일이 도착했습니다.",
                                sticky=True
                            )
                            self._notified_chained_rns.add(rn)
                    elif source_type == 'checked':
                        prefix = "(확인필요) "
                    
                    self._ev_required_list.addItem(f"{prefix}{rn}")
            else:
                self._ev_required_list.addItem("내역 없음")
            
            # 리스트에 없는(처리된) RN은 알림 기록에서 제거 (나중에 다시 올 경우 알림을 위해)
            # 단, 이 방식은 리스트에 있는 동안만 유지하길 원한다면 사용
            # self._notified_chained_rns = self._notified_chained_rns.intersection(current_chained_rns)
                
        except Exception as e:
            print(f"서류미비 목록 로드 중 오류: {e}")
            self._ev_required_list.clear()
            self._ev_required_list.addItem("로드 실패")
    
    def _on_ev_required_item_double_clicked(self, item):
        """서류미비 리스트 아이템 더블 클릭 시 작업 요청 시그널을 발생시킨다."""
        text = item.text()
        if text in ["내역 없음", "로드 실패"]:
            return

        # (EV), (요청), (확인필요) 항목인지 확인
        is_ev = text.startswith("(EV) ")
        is_ce = text.startswith("(요청) ")
        is_checked = text.startswith("(확인필요) ")
        
        if is_ev:
            print(f"[DEBUG] EV Complement 작업 플래그 활성화 (항목: {text})")
        elif is_ce:
            print(f"[DEBUG] CE(Chained Emails) 작업 플래그 활성화 (항목: {text})")
        elif is_checked:
            print(f"[DEBUG] 확인필요 항목 작업 (항목: {text})")
            
        # 접두어 제거하고 RN만 추출
        rn = text.replace("(EV) ", "").replace("(요청) ", "").replace("(확인필요) ", "").strip()
        if rn:
            self.rn_work_requested.emit(rn, is_ev, is_ce)
    
    def _handle_ev_complement_click(self):
        """
        ev_complement 타입 버튼 클릭 시 호출되는 함수.
        현재는 아무 작동도 하지 않으며, 추후 구현 예정.
        """
        pass
    
    def refresh_data(self):
        """데이터를 수동으로 새로고침한다."""
        self._update_ev_required_list()
        self._update_da_request_list()
        self.update_selected_rn_display()

    def update_selected_rn_display(self):
        """PdfLoadWidget에서 선택된 RN을 가져와 라벨에 표시하고 메모 리스트를 갱신한다."""
        if not hasattr(self, 'label_selected_rn'):
            return
            
        try:
            main_window = self.window()
            if hasattr(main_window, 'pdf_load_widget'):
                selected_rn = main_window.pdf_load_widget.get_selected_rn()
                if selected_rn:
                    self.label_selected_rn.setText(selected_rn)
                    self._refresh_memo_list(selected_rn)
                else:
                    self.label_selected_rn.setText("선택된 RN 없음")
                    if hasattr(self, 'listWidget_memos'):
                        self.listWidget_memos.clear()
        except Exception as e:
            print(f"RN 표시 업데이트 실패: {e}")

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
                # 처리시작 시 작업 요청 시그널 발생 (rn, is_ev=False, is_ce=False)
                self.rn_work_requested.emit(rn, False, False)
            
        except Exception as e:
            print(f"이메일 확인 중 오류 발생: {e}")
            QMessageBox.critical(self, "오류", f"이메일 확인 중 오류가 발생했습니다.\n{e}")

    def _open_special_note_dialog(self):
        """특이사항 입력 다이얼로그를 비모달로 연다."""
        if self._special_note_dialog is None or not self._special_note_dialog.isVisible():
            self._special_note_dialog = SpecialNoteDialog(parent=self)
        
        # MainWindow의 PdfLoadWidget에서 선택된 RN 가져오기
        try:
            main_window = self.window()
            if hasattr(main_window, 'pdf_load_widget'):
                selected_rn = main_window.pdf_load_widget.get_selected_rn()
                if selected_rn and hasattr(self._special_note_dialog, 'RN_lineEdit'):
                    self._special_note_dialog.RN_lineEdit.setText(selected_rn)
        except Exception as e:
            print(f"RN 자동 입력 실패: {e}")
            
        self._special_note_dialog.show()
        self._special_note_dialog.raise_()
        self._special_note_dialog.activateWindow()