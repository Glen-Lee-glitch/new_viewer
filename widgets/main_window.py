import sys
import os
from pathlib import Path
from datetime import datetime, timedelta, date
import pytz
import pymupdf
import traceback
import pandas as pd

from PyQt6.QtCore import Qt, QThreadPool, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QMainWindow,
                             QMessageBox, QSplitter, QStackedWidget, QWidget, QFileDialog, QStatusBar,
                             QPushButton, QLabel, QDialog)
from PyQt6 import uic
from qt_material import apply_stylesheet

from core.pdf_render import PdfRender
from core.pdf_saved import compress_pdf_with_multiple_stages
from core.sql_manager import claim_subsidy_work, get_original_pdf_path_by_rn
from core.workers import BatchTestSignals, PdfBatchTestWorker
from core.utility import normalize_basic_info, get_converted_path
from core.data_manage import is_sample_data_mode
from widgets.pdf_load_widget import PdfLoadWidget
from widgets.pdf_view_widget import PdfViewWidget
from widgets.thumbnail_view_widget import ThumbnailViewWidget
from widgets.info_panel_widget import InfoPanelWidget
from widgets.todo_widget import ToDoWidget
from widgets.settings_dialog import SettingsDialog
from widgets.login_dialog import LoginDialog
from widgets.special_note_dialog import SpecialNoteDialog
from widgets.worker_progress_dialog import WorkerProgressDialog
from widgets.alarm_widget import AlarmWidget
from widgets.detail_form_dialog import DetailFormDialog
from widgets.config_dialog import ConfigDialog
from widgets.necessary_widget import NecessaryWidget
from widgets.multi_child_check_dialog import MultiChildCheckDialog
from widgets.help_dialog import HelpDialog
from widgets.region_manager_dialog import RegionManagerDialog


class MainWindow(QMainWindow):
    """메인 윈도우"""

    # --- 초기화 및 설정 ---
    
    def __init__(self):
        super().__init__()
        
        # 1. UI 로드 및 변수 초기화
        self._load_ui_file()
        self._init_variables()
        
        # 2. 위젯 생성 및 타이머 설정
        self._create_widgets()
        self._setup_timers()

        # 3. UI 배치 및 초기 상태 설정
        self._setup_ui_containers()
        self._set_initial_ui_state()

        # 4. 시스템 설정 (메뉴, 시그널, 단축키)
        self._setup_menus()
        self._setup_connections()
        self._setup_global_shortcuts()

        # 5. 로그인 다이얼로그 초기화 및 실행
        self._init_login_dialog()
        self._show_login_dialog()

    def _load_ui_file(self):
        """UI 파일을 로드한다."""
        ui_path = Path(__file__).parent.parent / "ui" / "main_window.ui"
        uic.loadUi(str(ui_path), self)

    def _init_variables(self):
        """클래스 멤버 변수들을 초기화한다."""
        self.renderer: PdfRender | None = None
        self.current_page = -1
        self.thread_pool = QThreadPool()
        self._initial_resize_done = False
        self._auto_return_to_main_after_save = False
        self._worker_name = ""
        self._worker_id = None
        self._original_filepath: str | None = None
        self._is_current_file_processed: bool = False
        self._is_give_works_started: bool = False
        self._give_works_rn: str = ""
        self._is_alarm_rn_work: bool = False
        self._is_ev_complement_work: bool = False
        self._page_order: list[int] = []
        self._pending_basic_info: dict | None = None
        
        # 이상치 및 작업 관련 변수
        self._current_rn = ""
        self._is_context_menu_work = False
        self._special_note_dialog = None  # 비모달 다이얼로그 인스턴스 유지용
        self._pending_outlier_check = False
        self._pending_outlier_metadata = None
        self._pending_outlier_metadata_copy = None
        self._outlier_queue = []
        self._original_outlier_types = []
        self._pending_open_file_after_save = False

    def _create_widgets(self):
        """자식 위젯들을 생성한다."""
        self._thumbnail_viewer = ThumbnailViewWidget()
        self._pdf_view_widget = PdfViewWidget()
        self._pdf_load_widget = PdfLoadWidget()
        self._info_panel = InfoPanelWidget()
        self._alarm_widget = AlarmWidget(self._worker_name)
        self._todo_widget = ToDoWidget(self)
        self._settings_dialog = SettingsDialog(self)
        self._detail_form_dialog = DetailFormDialog(self)
        self._config_dialog = ConfigDialog(self)
        self._necessary_widget = NecessaryWidget()

    def _setup_timers(self):
        """타이머를 설정한다."""
        # 새로고침 타이머
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_all_data)
        
        # PDF 편집 모드 3분 경과 체크 타이머
        self._edit_mode_timer = QTimer(self)
        self._edit_mode_timer.setInterval(180000)  # 3분
        self._edit_mode_timer.setSingleShot(True)
        self._edit_mode_timer.timeout.connect(self._handle_edit_mode_timeout)

    def _set_initial_ui_state(self):
        """위젯들의 초기 표시/숨김 상태와 스타일을 설정한다."""
        self._pdf_view_widget.hide()
        self._thumbnail_viewer.hide()
        self._info_panel.hide()
        self._necessary_widget.show()
        self._alarm_widget.show()
        self._todo_widget.hide()

        # 상태바에 네비게이션 위젯 추가
        self.ui_status_bar.addPermanentWidget(self.ui_nav_widget)
        
        # 라벨 포맷 설정
        if hasattr(self, 'database_updated_time_label'):
            self.database_updated_time_label.setTextFormat(Qt.TextFormat.RichText)
            
        # 초기 상태에서 작업자 현황 버튼 숨김
        if hasattr(self, 'pushButton_worker_progress'):
            self.pushButton_worker_progress.hide()

    def _init_login_dialog(self):
        """로그인 다이얼로그를 초기화한다."""
        # parent를 None으로 설정하여 독립적인 윈도우로 생성
        self._login_dialog = LoginDialog()

    def _setup_ui_containers(self):
        """UI 컨테이너에 위젯들을 배치한다."""
        # 레이아웃 객체 이름으로 직접 접근하여 위젯 추가
        
        # 썸네일 영역 (thumbnail_layout)
        if hasattr(self, 'thumbnail_layout'):
            self.thumbnail_layout.addWidget(self._necessary_widget)
            self.thumbnail_layout.addWidget(self._thumbnail_viewer)
        
        # 콘텐츠 영역 (content_layout)
        if hasattr(self, 'content_layout'):
            self.content_layout.addWidget(self._pdf_load_widget)
            self.content_layout.addWidget(self._pdf_view_widget)
        
        # 정보 패널 영역 (info_panel_layout)
        if hasattr(self, 'info_panel_layout'):
            self.info_panel_layout.addWidget(self._alarm_widget)
            self.info_panel_layout.addWidget(self._info_panel)

    def _setup_menus(self):
        """메뉴바를 설정합니다."""
        # 파일 메뉴
        open_action = QAction("PDF 열기", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._prompt_save_before_open_file)
        self.menu_file.addAction(open_action)
        
        self.menu_file.addSeparator()
        
        # 원본 불러오기 액션 추가 (초기에는 비활성화)
        self.load_original_action = QAction("원본으로 바꾸기", self)
        self.load_original_action.setEnabled(False)
        self.load_original_action.triggered.connect(self._load_original_document)
        self.menu_file.addAction(self.load_original_action)

        # 원본 불러오기 액션 추가 (초기에는 비활성화)
        self.outbound_allocation_action = QAction("출고배정표 불러오기", self)
        self.outbound_allocation_action.setEnabled(False)
        self.outbound_allocation_action.triggered.connect(self._load_outbound_allocation_document)
        self.menu_file.addAction(self.outbound_allocation_action)
        
        self.menu_file.addSeparator()
        
        save_action = QAction("저장", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._save_document)
        self.menu_file.addAction(save_action)
        
        self.menu_file.addSeparator()
        
        exit_action = QAction("종료", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        self.menu_file.addAction(exit_action)
        
        # 편집 메뉴
        undo_action = QAction("실행 취소", self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self._pdf_view_widget.undo_last_action)
        self.menu_edit.addAction(undo_action)

        self.menu_edit.addSeparator()

        # 지역 관리 액션 (UI 파일에 정의됨)
        if hasattr(self, 'action_region_manager'):
            self.action_region_manager.triggered.connect(self._open_region_manager_dialog)
        
        self.menu_edit.addSeparator()
        
        # 보기 메뉴
        todo_action = QAction("할일 목록", self)
        todo_action.setCheckable(True)
        todo_action.triggered.connect(self._todo_widget.toggle_overlay)
        self.menu_view.addAction(todo_action)
        
        self.menu_view.addSeparator()
        
        self.worker_progress_action = QAction("현황판", self)
        self.worker_progress_action.triggered.connect(self._open_worker_progress_dialog)
        self.menu_view.addAction(self.worker_progress_action)

        self.view_saved_pdfs_action = QAction("저장된 PDF 보기", self)
        self.view_saved_pdfs_action.triggered.connect(self._necessary_widget._open_folder_in_explorer)
        self.menu_view.addAction(self.view_saved_pdfs_action)

        self.view_ev_work_action = QAction("EV 신청 작업", self)
        self.menu_view.addAction(self.view_ev_work_action)
        
        self.menu_view.addSeparator()
        
        # AI 결과 보기 액션 추가 (초기에는 비활성화)
        self.view_ai_results_action = QAction("AI 결과 보기", self)
        self.view_ai_results_action.setEnabled(False)
        self.view_ai_results_action.triggered.connect(self._open_ai_results_dialog)
        self.menu_view.addAction(self.view_ai_results_action)

        # 설정 메뉴
        settings_action = QAction("설정", self)
        settings_action.triggered.connect(self._open_settings_dialog)
        self.menu_edit.addAction(settings_action)

        preferences_action = QAction("환경설정", self)
        preferences_action.triggered.connect(self._open_config_dialog)
        self.menu_settings.addAction(preferences_action)

        # 도움말 메뉴
        help_action = QAction("도움말", self)
        help_action.triggered.connect(self._open_help_dialog)
        self.menu_help.addAction(help_action)
        
        # '파일' 메뉴 안의 '추가서류' 서브메뉴는 UI 파일에서 정의되어 있으며, hover 시 자동으로 서브메뉴가 표시됩니다.
        # 초기에는 비활성화 (컨텍스트 메뉴 작업일 때만 활성화)
        if hasattr(self, 'menu_additional_documents'):
            self.menu_additional_documents.menuAction().setEnabled(False)

    def _setup_connections(self):
        """애플리케이션의 모든 시그널-슬롯 연결을 설정한다."""
        self._pdf_load_widget.pdf_selected.connect(self._handle_pdf_selected)
        self._pdf_load_widget.work_started.connect(self._handle_work_started)
        self._thumbnail_viewer.page_selected.connect(self.go_to_page)
        self._thumbnail_viewer.page_change_requested.connect(self.change_page)
        self._thumbnail_viewer.page_order_changed.connect(self._update_page_order)
        self._pdf_view_widget.page_change_requested.connect(self.change_page)
        self._thumbnail_viewer.undo_requested.connect(self._handle_undo_request)
        self._thumbnail_viewer.page_delete_requested.connect(self._handle_page_delete_request)
        self._thumbnail_viewer.page_replace_with_original_requested.connect(self._handle_page_replace_with_original)
        # self._pdf_view_widget.page_aspect_ratio_changed.connect(self.set_splitter_sizes)
        self._pdf_view_widget.save_completed.connect(self._handle_save_completed) # 저장 완료 시그널 연결
        self._pdf_view_widget.toolbar.save_pdf_requested.connect(self._save_document)
        self._pdf_view_widget.toolbar.setting_requested.connect(self._open_settings_dialog)
        self._pdf_view_widget.toolbar.email_requested.connect(self._open_special_note_dialog)
        self._pdf_view_widget.page_delete_requested.connect(self._handle_page_delete_request)
        self._pdf_load_widget.ai_review_requested.connect(self._handle_ai_review_requested)
        # 데이터 새로고침 시 시간 업데이트 및 알람 위젯 갱신
        self._pdf_load_widget.data_refreshed.connect(self._on_data_refreshed)
        
        # 알람 위젯 RN 작업 요청 시그널 연결
        self._alarm_widget.rn_work_requested.connect(self._handle_alarm_rn_clicked)
        
        # 정보 패널 업데이트 연결
        self._pdf_view_widget.pdf_loaded.connect(self._info_panel.update_file_info)
        self._pdf_view_widget.page_info_updated.connect(self._info_panel.update_page_info)
        self._info_panel.text_stamp_requested.connect(self._pdf_view_widget.activate_text_stamp_mode)
        self._pdf_view_widget.page_rotation_changed.connect(self._thumbnail_viewer.update_page_rotation)
        self._pdf_view_widget.thumbnail_updated.connect(self._thumbnail_viewer.update_page_thumbnail)

        # 페이지 네비게이션 버튼 클릭 시그널 연결
        self.ui_push_button_prev.clicked.connect(lambda: self.change_page(-1))
        self.ui_push_button_next.clicked.connect(lambda: self.change_page(1))
        self.ui_push_button_reset.clicked.connect(self._prompt_save_before_reset)
        
        # 테스트 버튼 시그널 연결
        self.ui_test_button.clicked.connect(self.start_batch_test)
        
        # 작업자 현황 버튼 시그널 연결
        self.pushButton_worker_progress.clicked.connect(self._open_worker_progress_dialog)
        
        # --- 전역 단축키 설정 ---
        # _setup_global_shortcuts() 메서드에서 처리하므로 기존 코드는 제거
        # toggle_todo_action = QAction(self)
        # toggle_todo_action.setShortcut(Qt.Key.Key_QuoteLeft) # '~' 키
        # toggle_todo_action.triggered.connect(self.todo_widget.toggle_overlay)
        # self.addAction(toggle_todo_action)

    def _setup_global_shortcuts(self):
        """전역 단축키를 설정하고 액션에 연결한다."""
        # ToDo 리스트 토글 액션
        self.toggle_todo_action = QAction(self)
        self.addAction(self.toggle_todo_action)
        self.toggle_todo_action.triggered.connect(self._todo_widget.toggle_overlay)
        
        # 스탬프 오버레이 토글 액션
        self.toggle_stamp_overlay_action = QAction(self)
        self.addAction(self.toggle_stamp_overlay_action)
        self.toggle_stamp_overlay_action.triggered.connect(self._pdf_view_widget.toggle_stamp_overlay)
        
        # 메일 오버레이 토글 액션
        self.toggle_mail_overlay_action = QAction(self)
        self.addAction(self.toggle_mail_overlay_action)
        self.toggle_mail_overlay_action.triggered.connect(self._pdf_view_widget.toggle_mail_overlay)
        
        # 자르기 액션
        self.crop_action = QAction(self)
        self.addAction(self.crop_action)
        self.crop_action.triggered.connect(self._pdf_view_widget._open_crop_dialog)

        # AI 결과 보기 단축키 액션 (메뉴와 별개로 동작)
        self.view_ai_results_shortcut_action = QAction(self)
        self.addAction(self.view_ai_results_shortcut_action)
        self.view_ai_results_shortcut_action.triggered.connect(self._open_ai_results_dialog)

        self._apply_shortcuts()

    def _apply_shortcuts(self):
        """QSettings에서 단축키를 불러와 액션에 적용한다."""
        settings = self._settings_dialog.settings
        
        # TODO: settings.ui 위젯 이름이 확정되면 키 값을 맞춰야 함
        todo_shortcut = settings.value("shortcuts/toggle_todo", "grave") # '`' 키
        self.toggle_todo_action.setShortcut(QKeySequence.fromString(todo_shortcut, QKeySequence.SequenceFormat.PortableText))

        # 스탬프 오버레이 단축키 적용
        stamp_overlay_shortcut = settings.value("shortcuts/toggle_stamp_overlay", "Ctrl+T")
        self.toggle_stamp_overlay_action.setShortcut(QKeySequence.fromString(stamp_overlay_shortcut, QKeySequence.SequenceFormat.PortableText))
        
        # 메일 오버레이 단축키 적용
        mail_overlay_shortcut = settings.value("shortcuts/toggle_mail_overlay", "M")
        self.toggle_mail_overlay_action.setShortcut(QKeySequence.fromString(mail_overlay_shortcut, QKeySequence.SequenceFormat.PortableText))
        
        # 자르기 단축키 적용
        crop_shortcut = settings.value("shortcuts/crop", "Y")
        self.crop_action.setShortcut(QKeySequence.fromString(crop_shortcut, QKeySequence.SequenceFormat.PortableText))

        # AI 결과 보기 단축키 적용
        view_ai_results_shortcut = settings.value("shortcuts/view_ai_results", "A")
        self.view_ai_results_shortcut_action.setShortcut(QKeySequence.fromString(view_ai_results_shortcut, QKeySequence.SequenceFormat.PortableText))

    # === 프로퍼티 정의(선택 범위 숨김 권장) ===

    # 속성 접근을 위한 프로퍼티들 (기존 코드와의 호환성을 위해)
    @property
    def thumbnail_viewer(self):
        return self._thumbnail_viewer
    
    @property
    def pdf_view_widget(self):
        return self._pdf_view_widget
    
    @property
    def pdf_load_widget(self):
        return self._pdf_load_widget
    
    @property
    def info_panel(self):
        return self._info_panel
    
    @property
    def alarm_widget(self):
        return self._alarm_widget
    
    @property
    def todo_widget(self):
        return self._todo_widget
    
    @property
    def settings_dialog(self):
        return self._settings_dialog
  
    @property
    def statusBar(self):
        return self.ui_status_bar
    
    @property
    def test_button(self):
        return self.ui_test_button
    
    @property
    def pushButton_prev(self):
        return self.ui_push_button_prev
    
    @property
    def pushButton_next(self):
        return self.ui_push_button_next
    
    @property
    def label_page_nav(self):
        return self.ui_label_page_nav
    
    @property
    def pushButton_reset(self):
        return self.ui_push_button_reset

    # === 다이얼로그(창) 관리 ===

    def _show_login_dialog(self):
        """로그인 다이얼로그를 표시하고 작업자 이름을 설정한다."""
        if self._login_dialog.exec() == QDialog.DialogCode.Accepted:
            # 로그인 창이 있던 모니터(스크린)를 감지하여 메인 윈도우를 해당 모니터로 이동하고 포지션 조정
            target_screen = self._login_dialog.screen()
            self.setScreen(target_screen)
            self.move(target_screen.geometry().topLeft())

            self._worker_name = self._login_dialog.get_worker_name() # 작업자 이름 설정
            self._worker_id = self._login_dialog.get_worker_id() # 작업자 ID 설정
            self._update_worker_label()
            
            # 로그인 후 알람 위젯 업데이트
            if hasattr(self, '_alarm_widget'):
                self._alarm_widget._worker_name = self._worker_name
                self._alarm_widget.refresh_data()
            
            # 로그인 후 정보 패널에 작업자 정보 설정
            if hasattr(self, '_info_panel'):
                self._info_panel.set_worker_info(self._worker_id)
                
            # 로그인 후 PDF 로드 위젯에 작업자 이름 및 ID 설정
            if hasattr(self, '_pdf_load_widget'):
                self._pdf_load_widget.set_worker_name(self._worker_name)
                self._pdf_load_widget.set_worker_id(self._worker_id)
                # 프로그램 시작 시 체크박스 상태 초기화 (기본값: True)
                self._pdf_load_widget.set_payment_request_load_enabled(True)
            
            # 초기 새로고침 타이머 시작 (샘플 모드가 아닐 때만)
            if not is_sample_data_mode():
                refresh_interval = self._config_dialog.settings.value("general/refresh_interval", 30, type=int)
                self._refresh_timer.start(refresh_interval * 1000)  # 초 단위이므로 1000을 곱함
            else:
                print("[INFO] 샘플 데이터 모드이므로 자동 새로고침 타이머를 시작하지 않습니다.")
            
            # 로그인 직후 초기 시간 표시
            self._refresh_all_data()
        else:
            # 취소 시 앱 완전 종료
            # QApplication.instance().quit()은 이벤트 루프 시작 전에는 즉시 종료되지 않아 window.show()가 실행될 수 있음
            sys.exit(0)

    def _open_settings_dialog(self):
        """설정 다이얼로그를 연다."""
        if self._settings_dialog.exec():
            # 사용자가 OK를 누르면 변경된 단축키를 다시 적용
            self._apply_shortcuts()
    
    def _open_config_dialog(self):
        """환경설정 다이얼로그를 연다."""
        if self._config_dialog.exec():
            # 사용자가 OK를 누르면 변경된 새로고침 주기를 적용 (샘플 모드가 아닐 때만)
            if not is_sample_data_mode():
                refresh_interval = self._config_dialog.settings.value("general/refresh_interval", 30, type=int)
                self._refresh_timer.stop()  # 기존 타이머 중지
                self._refresh_timer.start(refresh_interval * 1000)  # 새 주기로 시작 (초 단위이므로 1000을 곱함)
            
            # 지급신청 로드 체크박스 상태를 PdfLoadWidget에 설정
            payment_request_load_enabled = self._config_dialog.payment_request_load_enabled
            self._pdf_load_widget.set_payment_request_load_enabled(payment_request_load_enabled)
    
    def _open_region_manager_dialog(self):
        """지역 관리 다이얼로그를 연다."""
        dialog = RegionManagerDialog(self)
        dialog.exec()

    def _open_special_note_dialog(self):
        """특이사항 입력 다이얼로그를 비모달로 연다."""
        if self._special_note_dialog is None or not self._special_note_dialog.isVisible():
            self._special_note_dialog = SpecialNoteDialog(parent=self)
        
        # 현재 작업 중인 RN 값을 다이얼로그에 자동 설정
        if self._current_rn and hasattr(self._special_note_dialog, 'RN_lineEdit'):
            self._special_note_dialog.RN_lineEdit.setText(self._current_rn)

        self._special_note_dialog.show()
        self._special_note_dialog.raise_()
        self._special_note_dialog.activateWindow()

    def _open_worker_progress_dialog(self):
        """작업자 현황 다이얼로그를 연다."""
        worker_progress_dialog = WorkerProgressDialog(self)
        worker_progress_dialog.exec()
        
    def _handle_ai_review_requested(self, rn: str):
        """AI 검토 요청을 처리한다. 설정에 따라 자동으로 열지 말지 결정한다."""
        # 설정 확인: AI 결과 자동 띄우기가 체크되어 있는지 확인
        auto_show_ai = self._config_dialog.settings.value("general/auto_show_ai_results", True, type=bool)
        
        if auto_show_ai:
            self._show_gemini_results_dialog(rn)
    
    def _show_gemini_results_dialog(self, rn: str):
        """상세 정보 다이얼로그를 표시한다."""
        self._detail_form_dialog.load_data(rn)
        self._detail_form_dialog.show()
        self._detail_form_dialog.raise_()
        self._detail_form_dialog.activateWindow()
    
    def _open_help_dialog(self):
        """도움말 다이얼로그를 연다."""
        dialog = HelpDialog(parent=self)
        dialog.show()
    
    def _open_ai_results_dialog(self):
        """현재 작업 중인 RN으로 AI 결과 다이얼로그를 연다."""
        if not self._current_rn:
            QMessageBox.warning(self, "오류", "현재 작업 중인 RN이 없습니다.")
            return

        # AI 결과 데이터 존재 여부 확인
        from core.sql_manager import check_gemini_flags
        flags = check_gemini_flags(self._current_rn)
        
        # 플래그 중 하나라도 True면 데이터가 있는 것으로 간주
        has_ai_results = any(flags.values()) if flags else False

        if has_ai_results:
            self._show_gemini_results_dialog(self._current_rn)
        else:
            QMessageBox.warning(self, "알림", "AI 결과 데이터가 없습니다.")

    # === 문서 생명주기 관리 ===
    def load_document(self, pdf_paths: list, is_preprocessed: bool = False, metadata: dict = None):
        """PDF 및 이미지 문서를 로드하고 뷰를 전환한다."""
        if not pdf_paths:
            return

        # metadata 처리
        if metadata and metadata.get('is_from_rns_filepath'):
            is_preprocessed = True
            self._is_current_file_processed = True

        # 새 파일 로드 시 RN 초기화
        self._pdf_view_widget.set_current_rn("")

        if self.renderer:
            self.renderer.close()

        try:
            self.renderer = PdfRender()
            # 고속 로딩: 전처리된 단일 파일
            if is_preprocessed and len(pdf_paths) == 1:
                self.renderer.load_preprocessed_pdf(pdf_paths[0])
            # 일반 로딩: A4 변환 및 병합 필요한 파일들
            else:
                # 첫 번째 파일이든 여러 파일이든 append_file을 통해 순차적으로 처리
                # (append_file 내부에 초기 로드 로직이 포함되어 있거나, 첫 호출 시 처리됨)
                for path in pdf_paths:
                    self.renderer.append_file(path)
                
        except Exception as e:
            QMessageBox.critical(self, "오류", f"문서를 여는 데 실패했습니다: {e}")
            self.renderer = None
            return

        # 페이지 순서 초기화
        self._page_order = list(range(self.renderer.get_page_count()))

        # 첫 번째 파일 이름을 기준으로 창 제목 설정
        self.setWindowTitle(f"PDF Viewer - {Path(pdf_paths[0]).name}")
        
        # 썸네일 생성 시 회전 정보 전달
        self._thumbnail_viewer.set_renderer(self.renderer, self._page_order, rotations=self._pdf_view_widget.get_page_rotations()) 
        self._pdf_view_widget.set_renderer(self.renderer) # PDF 뷰어 사전 작업(준비 작업, 밑에서 펼침)

        # PDF 편집 모드를 위한 필요한 영역 활성화/필요 없는 영역 숨기기
        self._pdf_load_widget.hide()
        self._pdf_view_widget.show()
        self._necessary_widget.hide()
        self._thumbnail_viewer.show()
        self._alarm_widget.hide()
        self._info_panel.show()
        # alarm_widget에서 info_panel_widget으로 전환될 때 체크박스 초기화
        self._info_panel.reset_task_checkboxes()

        # 기본 스플리터 사이즈를 즉시 한 번 강제하여 초기 힌트를 통일
        self.set_splitter_sizes(False)

        name, region, special_note, rn = self._collect_pending_basic_info()
        self._info_panel.update_basic_info(name, region, special_note, rn)

        # 텍스트 삽입 라디오 버튼을 '일반'으로 초기화
        self._info_panel.reset_text_radio_buttons()
        if hasattr(self._info_panel, 'text_edit'):
            self._info_panel.text_edit.clear()

        # day_gap 조회 및 설정
        if region:
            from core.sql_manager import fetch_delivery_day_gap
            day_gap = fetch_delivery_day_gap(region)
            self._info_panel.set_delivery_day_gap(day_gap)
        else:
            self._info_panel.set_delivery_day_gap(None)

        # PDF 열면 맨 처음 페이지 포커스
        if self.renderer.get_page_count() > 0:
            QTimer.singleShot(0, lambda: self.go_to_page(0))
            # PDF 렌더 완료 후 이상치 체크 (약간의 지연을 두어 렌더링 완료 보장)
            if self._pending_outlier_check:
                QTimer.singleShot(500, self._check_and_show_outlier_reminder)

        # PDF 편집 모드 진입 시 3분 타이머 시작
        self._edit_mode_timer.start()
        
        # 컨텍스트 메뉴를 통한 작업인 경우 '원본 불러오기' 및 '추가서류' 액션 활성화
        if self._is_context_menu_work:
            if hasattr(self, 'load_original_action'):
                self.load_original_action.setEnabled(True)
            if hasattr(self, 'menu_additional_documents'):
                self.menu_additional_documents.menuAction().setEnabled(True)

        # 성남시인 경우 전용 액션 활성화
        if hasattr(self, 'outbound_allocation_action') and region == '성남시':
            self.outbound_allocation_action.setEnabled(True)
        
        # AI 결과 보기 액션 활성화/비활성화
        self._update_ai_results_action_state(rn)

    def _handle_pdf_selected(self, pdf_paths: list, metadata: dict = None):
        if metadata is None:
            metadata = {}
            
        self._pending_basic_info = None
        self._current_rn = ""  # 로컬 파일 열기 시 RN 초기화
        self._is_context_menu_work = False  # 로컬 파일 열기 시 컨텍스트 메뉴 작업 플래그 리셋
        self._pending_outlier_check = False  # 로컬 파일 열기 시 이상치 체크 플래그 리셋
        self._pending_outlier_metadata = None  # 이상치 메타데이터 리셋
        
        # 지급 테이블 시작 여부 확인
        self._is_give_works_started = metadata.get('is_give_works', False)
        self._give_works_rn = metadata.get('rn', "") if self._is_give_works_started else ""
        
        if self._is_give_works_started:
            print(f"[지급 테이블 작업 시작] RN: {self._give_works_rn}")
            # RN이 있으면 현재 RN 설정 (저장 시 사용 등)
            self._current_rn = self._give_works_rn
        
        self._info_panel.update_basic_info("", "", "", "")
        # 로컬 파일 열기 시 '원본 불러오기' 및 '추가서류' 액션 비활성화
        if hasattr(self, 'load_original_action'):
            self.load_original_action.setEnabled(False)
        if hasattr(self, 'menu_additional_documents'):
            self.menu_additional_documents.menuAction().setEnabled(False)
        self.load_document(pdf_paths)

    def _handle_alarm_rn_clicked(self, rn: str, is_ev: bool = False, is_ce: bool = False):
        """알람 위젯에서 RN 버튼 클릭 시 호출되는 핸들러.
        
        RN의 rns.file_path와 chained_emails.chained_file_path를 병합하여 작업을 시작한다.
        중복 메일(duplicated_rn)이 있는 경우 해당 파일들과 rns 파일을 병합한다.
        """
        if not rn:
            return
        
        # EV 보완 작업 플래그 설정
        self._is_ev_complement_work = is_ev
        self._is_ce_work = is_ce
        
        if is_ev:
            print(f"[MainWindow] EV 보완 작업 모드로 시작 (RN: {rn})")
        if is_ce:
            print(f"[MainWindow] CE(Chained Emails) 작업 모드로 시작 (RN: {rn})")
        
        from core.sql_manager import (
            get_recent_thread_id_by_rn, 
            get_chained_emails_file_path_by_thread_id,
            get_rns_file_path_by_rn,
            claim_subsidy_work,
            get_duplicate_rn_file_paths
        )
        from core.utility import get_converted_path, normalize_basic_info
        from pathlib import Path
        
        try:
            # 1. RN으로부터 recent_thread_id 조회
            thread_id = get_recent_thread_id_by_rn(rn)
            
            # 2. thread_id로 chained_file_path 조회
            chained_file_path = None
            if thread_id:
                chained_file_path = get_chained_emails_file_path_by_thread_id(thread_id)
                if chained_file_path:
                    chained_file_path = get_converted_path(chained_file_path)
                    # 파일 존재 여부 확인
                    if not Path(chained_file_path).exists():
                        chained_file_path = None
            
            # 3. RN으로부터 rns 테이블의 file_path 조회
            rns_file_path = get_rns_file_path_by_rn(rn)
            if rns_file_path:
                rns_file_path = get_converted_path(rns_file_path)
                # 파일 존재 여부 확인
                if not Path(rns_file_path).exists():
                    rns_file_path = None
            
            # 4. duplicated_rn 테이블에서 중복 파일 경로 조회
            duplicate_file_paths = get_duplicate_rn_file_paths(rn)
            valid_duplicate_paths = []
            for path in duplicate_file_paths:
                conv_path = get_converted_path(path)
                if Path(conv_path).exists():
                    valid_duplicate_paths.append(conv_path)
            
            # 5. 파일 경로 리스트 구성
            pdf_paths = []
            
            if valid_duplicate_paths:
                # 중복 메일이 있는 경우: 중복 파일들 + RNS 파일
                # "duplicated_rn['file_path']에 rns['file_path']가 병합" -> Duplicates + RNS
                pdf_paths.extend(valid_duplicate_paths)
                if rns_file_path:
                    pdf_paths.append(rns_file_path)
            else:
                # 일반적인 경우: RNS 파일 + Chained 파일
                if rns_file_path:
                    pdf_paths.append(rns_file_path)
                if chained_file_path:
                    pdf_paths.append(chained_file_path)
            
            if not pdf_paths:
                QMessageBox.warning(
                    self, 
                    "파일 없음", 
                    f"RN {rn}에 연결된 PDF 파일을 찾을 수 없습니다."
                )
                return
            
            # 6. RN으로부터 메타데이터 조회 (PostgreSQL 쿼리)
            from contextlib import closing
            import psycopg2
            import psycopg2.extras
            from core.sql_manager import DB_CONFIG
            
            metadata = {
                'rn': rn,
                'name': "",
                'region': "",
                'worker': "",
                'special_note': "",
                'recent_thread_id': thread_id or "",
                'file_rendered': 0,
                'urgent': 0,
                'mail_count': 0,
                'outlier': "",
                'original_filepath': rns_file_path or "",
                'finished_file_path': rns_file_path or "",
                'is_from_rns_filepath': True,
                'is_context_menu_work': False,
                '구매계약서': 0,
                '초본': 0,
                '공동명의': 0,
                '다자녀': 0,
                'ai_계약일자': None,
                'ai_이름': None,
                '전화번호': None,
                '이메일': None,
                '차종': None,
                'page_number': None,
                'chobon_name': None,
                'chobon_birth_date': None,
                'chobon_address_1': None,
                'chobon': 0,
                'is_법인': 0,
                'child_birth_date': None,
                'issue_date': None,
                'birth_date': None,
                'address_1': None
            }
            
            # DB에서 메타데이터 조회
            try:
                with closing(psycopg2.connect(**DB_CONFIG)) as connection:
                    with connection.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                        query = """
                            SELECT 
                                r."RN",
                                r.region,
                                w.worker_name AS worker,
                                r.customer AS name,
                                array_to_string(r.special, ', ') AS special_note,
                                r.file_path AS finished_file_path,
                                e.original_pdf_path AS original_filepath,
                                r.recent_thread_id,
                                CASE WHEN r.is_urgent THEN 1 ELSE 0 END AS urgent,
                                r.mail_count,
                                r.model AS 차종
                            FROM rns r
                            LEFT JOIN emails e ON r.recent_thread_id = e.thread_id
                            LEFT JOIN workers w ON r.worker_id = w.worker_id
                            WHERE r."RN" = %s
                        """
                        cursor.execute(query, (rn,))
                        row = cursor.fetchone()
                        
                        if row:
                            metadata.update({
                                'rn': row.get('RN', rn),
                                'region': row.get('region', '') or '',
                                'worker': row.get('worker', '') or '',
                                'name': row.get('name', '') or '',
                                'special_note': row.get('special_note', '') or '',
                                'recent_thread_id': row.get('recent_thread_id', '') or '',
                                'urgent': row.get('urgent', 0) or 0,
                                'mail_count': row.get('mail_count', 0) or 0,
                                '차종': row.get('차종', None),
                                'original_filepath': row.get('original_filepath', '') or (rns_file_path or ''),
                                'finished_file_path': row.get('finished_file_path', '') or (rns_file_path or '')
                            })
            except Exception as e:
                print(f"메타데이터 조회 중 오류: {e}")
                import traceback
                traceback.print_exc()
            
            # 7. 알람 위젯에서 시작한 작업임을 표시하는 플래그 설정
            self._is_alarm_rn_work = True
            
            # 8. 작업 시작
            self._handle_work_started(pdf_paths, metadata)
            
        except Exception as e:
            print(f"알람 RN 클릭 처리 중 오류: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(
                self,
                "오류",
                f"작업을 시작하는 중 오류가 발생했습니다.\n{e}"
            )

    def _handle_work_started(self, pdf_paths: list, metadata: dict):
        # 컨텍스트 메뉴를 통한 작업 시작 여부 확인 및 저장
        self._is_context_menu_work = metadata.get('is_context_menu_work', False)
        
        self._original_filepath = metadata.get('original_filepath') # 원본 파일 경로 저장
        
        # 'rns' 테이블의 file_path에서 시작된 경우 is_preprocessed를 True로 설정
        is_from_rns_filepath = metadata.get('is_from_rns_filepath', False)
        # finished_file_path(처리된 파일 경로)가 존재하는 경우
        has_finished_file = bool(metadata.get('finished_file_path'))
        
        if is_from_rns_filepath or has_finished_file:
            is_preprocessed = True
            self._is_current_file_processed = True
        else:
            # 그 외의 경우 기존 로직 유지
            is_preprocessed = metadata.get('file_rendered', 0) == 1
            self._is_current_file_processed = is_preprocessed
        
        if self._is_context_menu_work:
            # print(f"[컨텍스트 메뉴를 통한 작업 시작] RN: {metadata.get('rn', 'N/A')}")
            pass

        # 메일 content 조회
        thread_id = metadata.get('recent_thread_id')
        mail_content = ""
        if thread_id:
            from core.sql_manager import get_mail_content_by_thread_id
            mail_content = get_mail_content_by_thread_id(thread_id)
        
        # 방어 코드: metadata가 없는 경우 초기화
        if not metadata:
            self._current_rn = ""  # metadata가 없는 경우 RN 초기화
            self._pending_basic_info = normalize_basic_info(metadata)
            self.load_document(pdf_paths)
            return

        worker_name = self._worker_name or metadata.get('worker') or ''
        rn_value = metadata.get('rn') # RN 값 저장
        existing_worker = (metadata.get('worker') or '').strip()  # 이미 배정된 작업자
        # 현재 작업 중인 RN 저장
        self._current_rn = rn_value or ""

        # 방어 코드: worker_name(프로그램 작업자) 또는 rn_value(시작건 RN번호)가 없는 경우 초기화
        if not worker_name or not rn_value:
            self._pending_basic_info = normalize_basic_info(metadata)
            self.load_document(pdf_paths)
            return

        # 관리자 권한 확인
        admin_workers = ['이경구', '이호형']
        is_admin = self._worker_name in admin_workers
        
        # 이미 작업자가 배정되어 있고, 현재 로그인 사용자가 관리자인 경우 조회 모드로 진행
        if existing_worker and is_admin:
            print(f"[관리자 조회 모드] 작업자: {existing_worker}, 관리자: {self._worker_name}")
            self._initialize_work_session(pdf_paths, metadata, is_preprocessed, rn_value, mail_content)
            return

        # 일반 사용자가 이미 할당된 RN번호를 시작하려고 하는 경우 오류 메시지 표시 및 진행 불가
        # worker_id를 사용하여 작업 할당 시도
        if not self._worker_id or not claim_subsidy_work(rn_value, self._worker_id):
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle("이미 작업 중")
            msg_box.setText("해당 신청 건은 다른 작업자가 진행 중입니다.")
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            
            # 메시지박스가 닫힐 때 자동으로 데이터 새로고침 실행
            msg_box.finished.connect(self._refresh_all_data)
            msg_box.exec()
            return

        # 작업 시작 (공통 로직 호출)
        self._initialize_work_session(pdf_paths, metadata, is_preprocessed, rn_value, mail_content)

    def _initialize_work_session(self, pdf_paths: list, metadata: dict, is_preprocessed: bool, rn_value: str, mail_content: str):
        """작업 세션을 초기화하고 문서를 로드하는 공통 로직을 수행한다."""
        from core.sql_manager import fetch_ev_complement_memo

        self._pending_basic_info = normalize_basic_info(metadata)
        
        # 이상치 정보 저장 (컨텍스트 메뉴 작업인 경우에만)
        outlier_value = metadata.get('outlier', '')
        if outlier_value == 'O': # outlier 값이 'O'이면 이상치 체크 플래그 설정
            self._pending_outlier_check = True
            self._pending_outlier_metadata = metadata  # 이상치 메타데이터 저장
        else:
            self._pending_outlier_check = False # outlier가 'O'가 아니면 플래그 리셋
            self._pending_outlier_metadata = None
        
        self.load_document(pdf_paths, is_preprocessed=is_preprocessed)
        
        # ev_complement 모드 체크 및 설정
        if rn_value:
            ev_memo = fetch_ev_complement_memo(rn_value)
            # 알람 위젯 플래그 또는 DB 메모 존재 여부로 판단
            is_ev = self._is_ev_complement_work or (ev_memo is not None)
            self._info_panel.set_ev_complement_mode(is_ev, ev_memo if ev_memo else "")
            self._pdf_view_widget.set_ev_complement_mode(is_ev)
        else:
            self._info_panel.set_ev_complement_mode(False)
            self._pdf_view_widget.set_ev_complement_mode(False)
        
        # PDF 로드 후 RN을 PdfViewWidget에 전달
        if rn_value:
            self._pdf_view_widget.set_current_rn(rn_value)
        
        # PDF 로드 후 메일 content 표시
        if mail_content:
            self._pdf_view_widget.set_mail_content(mail_content)

    def check_chained_emails(self):
        """현재 작업 중인 작업건의 thread_id를 조회하고 chained_emails 테이블에서 존재 여부를 확인한다.
        
        Returns:
            bool: True이면 저장 프로세스를 계속 진행, False이면 중단(병합 로직 수행 등)
        """
        from core.sql_manager import (get_recent_thread_id_by_rn, check_thread_id_in_chained_emails, 
                                     get_chained_emails_content_by_thread_id, get_chained_emails_file_path_by_thread_id)
        from widgets.email_view_dialog import EmailViewDialog
        
        current_rn = self._current_rn or self._give_works_rn
        thread_id = None
        if current_rn:
            thread_id = get_recent_thread_id_by_rn(current_rn)
        print(f"[_save_document 호출] 현재 작업건 thread_id: {thread_id}")
        
        # chained_emails 테이블에서 thread_id 존재 여부 확인
        if thread_id and check_thread_id_in_chained_emails(thread_id):
            print(f"[_save_document 호출] chained_emails 테이블에 thread_id 존재: {thread_id}")
            
            # content 조회
            try:
                content = get_chained_emails_content_by_thread_id(thread_id)
                
                # 이메일 확인 창 띄우기 (title은 비우고 content만 표시)
                if content:
                    dialog = EmailViewDialog(title="", content=content, thread_id=thread_id, parent=self)
                    result = dialog.exec()
                    
                    # '첨부 후 재확인' 버튼을 누른 경우 (result == 2)
                    if result == 2:
                        print("[check_chained_emails] '첨부 후 재확인' 선택됨. 서류 병합 시도.")
                        file_path = get_chained_emails_file_path_by_thread_id(thread_id)
                        if file_path:
                            if self._merge_chained_file(file_path):
                                return False # 병합 성공 시 저장 중단 (재확인을 위해)
                        else:
                            print(f"[check_chained_emails] 병합할 파일 경로가 없습니다. thread_id: {thread_id}")
                            QMessageBox.warning(self, "알림", "병합할 파일 경로를 찾을 수 없습니다.")
                    
            except Exception as e:
                print(f"[check_chained_emails] content 조회 중 오류: {e}")
                traceback.print_exc()
        
        return True # 기본적으로는 저장 프로세스 계속 진행

    def _merge_chained_file(self, file_path: str):
        """chained_emails의 PDF 파일을 현재 PDF에 병합한다."""
        if not file_path or not os.path.exists(file_path):
            print(f"[서류 병합 실패] 파일이 존재하지 않음: {file_path}")
            QMessageBox.warning(self, "오류", f"병합할 파일을 찾을 수 없습니다:\n{file_path}")
            return False

        try:
            if not self.renderer:
                from core.pdf_render import PdfRender
                self.renderer = PdfRender()

            old_page_count = self.renderer.get_page_count()
            
            # 파일 병합
            self.renderer.append_file(file_path)
            
            # 페이지 순서 업데이트 (기존 순서 유지 + 새 페이지 추가)
            self._page_order.extend(range(old_page_count, self.renderer.get_page_count()))
            
            # 썸네일 뷰 갱신 (기존 회전 정보 유지)
            self._thumbnail_viewer.set_renderer(self.renderer, self._page_order, rotations=self._pdf_view_widget.get_page_rotations())
            
            # PDF 뷰어 갱신 (렌더러 재설정 및 화면 갱신, 오버레이 보존)
            self._pdf_view_widget.set_renderer(self.renderer, clear_overlay=False)
            
            # 마지막 페이지로 이동
            last_page_index = self.renderer.get_page_count() - 1
            if last_page_index >= 0:
                QTimer.singleShot(100, lambda: self.go_to_page(last_page_index))
            
            print(f"[서류 병합 완료] {os.path.basename(file_path)}")
            return True

        except Exception as e:
            print(f"[서류 병합 중 오류] {e}")
            traceback.print_exc()
            QMessageBox.critical(self, "오류", f"서류 병합 중 오류가 발생했습니다:\n{e}")
            return False

    def _save_document(self, skip_confirmation: bool = False):
        """현재 상태(페이지 순서 포함)로 문서를 저장한다."""
        # 알람 위젯에서 시작한 작업인 경우 chained_emails 검토 건너뛰기
        if self._is_alarm_rn_work:
            print("[_save_document] 알람 위젯에서 시작한 작업이므로 chained_emails 검토를 건너뜁니다.")
        else:
            # 현재 작업 중인 작업건의 thread_id 조회 및 chained_emails 확인
            if not self.check_chained_emails():
                print("[_save_document] check_chained_emails 결과에 따라 저장 프로세스를 중단합니다.")
                return
        
        if self.renderer:
            print(f"저장할 페이지 순서: {self._page_order}")  # 디버그 출력
            print(f"[_save_document 호출] is_give_works={self._is_give_works_started}, rn={self._give_works_rn}, skip_confirmation={skip_confirmation}")
            
            # 저장 완료 후 자동으로 메인화면으로 돌아가도록 플래그 설정
            self._auto_return_to_main_after_save = True
            
            # 저장 시 사용할 RN 결정 (지급 작업이 아니면 현재 RN 사용)
            target_rn = self._give_works_rn if self._is_give_works_started else self._current_rn
            
            try:
                self._pdf_view_widget.save_pdf(
                    page_order=self._page_order, 
                    worker_name=self._worker_name,
                    is_give_works=self._is_give_works_started,
                    rn=target_rn,
                    skip_confirmation=skip_confirmation
                )
            except Exception as e:
                # 저장 호출 중 예외 발생 시 안전장치
                print(f"[저장 호출 중 예외] {e}")
                self._auto_return_to_main_after_save = False
                # 컨텍스트 메뉴 작업이었다면 플래그 리셋
                if self._is_context_menu_work:
                    self._is_context_menu_work = False
                    print("[컨텍스트 메뉴 작업 플래그] 저장 호출 예외로 인해 False로 리셋됨")
                QMessageBox.critical(self, "오류", f"저장 호출 중 오류가 발생했습니다:\n\n{str(e)}")
        
    def _handle_save_completed(self):
        """PDF 저장이 완료되었을 때 호출된다."""
        
        # RN이 존재하고 지급 작업이 아닌 경우 status 업데이트 (알람, 컨텍스트 메뉴 등)
        if self._current_rn and not self._is_give_works_started:
            from core.sql_manager import update_subsidy_status
            target_status = '보완 전처리' if self._is_ev_complement_work else 'pdf 전처리'
            success = update_subsidy_status(self._current_rn, target_status)
            if success:
                print(f"[저장 완료] RN {self._current_rn}의 status를 '{target_status}'로 업데이트 완료")
            else:
                print(f"[저장 완료] RN {self._current_rn}의 status 업데이트 실패")

        # 알람 위젯 작업 플래그 리셋
        if self._is_alarm_rn_work:
            self._is_alarm_rn_work = False
            self._is_ev_complement_work = False # EV 플래그 리셋
            print("[알람 위젯 작업 플래그] 저장 완료 후 초기화됨")
        
        # 지급 테이블 작업이었다면 플래그 리셋
        if self._is_give_works_started:
            self._is_give_works_started = False
            self._give_works_rn = ""
            print("[지급 테이블 작업 플래그] 저장 완료 후 초기화됨")
            
        if hasattr(self, '_auto_return_to_main_after_save') and self._auto_return_to_main_after_save:
            self._auto_return_to_main_after_save = False
            
            # 컨텍스트 메뉴 작업 플래그 리셋
            if self._is_context_menu_work:
                self._is_context_menu_work = False

            # 바로 메인화면으로 돌아가기
            self.show_load_view()
            # 메인화면으로 돌아갈 때 데이터 새로고침
            self._refresh_all_data()

            # 저장 후 파일 열기 대기 중이었다면 파일 선택창 띄우기
            if hasattr(self, '_pending_open_file_after_save') and self._pending_open_file_after_save:
                self._pending_open_file_after_save = False
                # 메인 화면으로 돌아간 직후 파일 선택창 띄우기
                QTimer.singleShot(100, self._pdf_load_widget.open_pdf_file)

    def show_load_view(self):
        """PDF 뷰어를 닫고 초기 로드 화면으로 전환하며 모든 관련 리소스를 정리한다."""
        # PDF 편집 모드 타이머 중지
        if self._edit_mode_timer.isActive():
            self._edit_mode_timer.stop()

        self.setWindowTitle("PDF Viewer")
        if self.renderer:
            self.renderer.close()
        
        self.renderer = None
        self.current_page = -1
        self._current_rn = ""  # 현재 RN 초기화
        self._is_context_menu_work = False  # 컨텍스트 메뉴 작업 플래그 리셋
        self._is_alarm_rn_work = False  # 알람 위젯 작업 플래그 리셋
        self._pending_outlier_check = False  # 이상치 체크 플래그 리셋
        self._pending_outlier_metadata = None  # 이상치 메타데이터 리셋
        self._pdf_view_widget.set_current_rn("") # PdfViewWidget의 RN도 초기화

        # 메인화면으로 돌아갈 때 '원본 불러오기' 및 '추가서류' 액션 비활성화
        if hasattr(self, 'load_original_action'):
            self.load_original_action.setEnabled(False)
        if hasattr(self, 'menu_additional_documents'):
            self.menu_additional_documents.menuAction().setEnabled(False)
        
        # AI 결과 보기 액션 비활성화
        if hasattr(self, 'view_ai_results_action'):
            self.view_ai_results_action.setEnabled(False)

        self._pdf_load_widget.show()
        
        # 뷰어 관련 위젯들 숨기기 및 초기화
        self._pdf_view_widget.hide()
        self._pdf_view_widget.set_renderer(None) # 뷰어 내부 상태 초기화
        self._necessary_widget.show()
        self._thumbnail_viewer.hide()
        self._thumbnail_viewer.clear_thumbnails()
        self._info_panel.hide()
        self._info_panel.clear_info()
        self._alarm_widget.show()  # 메인화면으로 돌아갈 때 alarm_widget 표시

        self._update_page_navigation()

    # === 페이지 네비게이션 ===
    def go_to_page(self, visual_page_num: int):
        """'보이는' 페이지 번호로 뷰를 이동시킨다."""
        if self.renderer and 0 <= visual_page_num < len(self._page_order):
            self.current_page = visual_page_num
            
            # '보이는' 순서를 '실제' 페이지 번호로 변환
            actual_page_num = self._page_order[visual_page_num]
            
            self._pdf_view_widget.show_page(actual_page_num)
            self._thumbnail_viewer.set_current_page(visual_page_num)
            self._update_page_navigation()
    
    def change_page(self, delta: int):
        """현재 페이지에서 delta만큼 페이지를 이동시킨다."""
        if self.renderer and self.current_page != -1:
            new_page = self.current_page + delta
            self.go_to_page(new_page)

    def _update_page_order(self, new_order: list[int]):
        """페이지 순서가 변경되면 호출되는 슬롯"""
        self._page_order = new_order
        print(f"MainWindow가 새 페이지 순서를 받음: {self._page_order}")

    def _update_page_navigation(self):
        """페이지 네비게이션 상태(라벨, 버튼 활성화)를 업데이트한다."""
        total_pages = len(self._page_order)
        current_visual_page = self.current_page
        
        if total_pages > 0:
            self.ui_label_page_nav.setText(f"{current_visual_page + 1} / {total_pages}")
        else:
            self.ui_label_page_nav.setText("N/A")

        self.ui_push_button_prev.setEnabled(total_pages > 0 and current_visual_page > 0)
        self.ui_push_button_next.setEnabled(total_pages > 0 and current_visual_page < total_pages - 1)

    def _handle_page_delete_request(self, visual_page_num, delete_info: dict):
        """페이지 삭제 요청을 처리하는 중앙 슬롯
        
        Args:
            visual_page_num: 단일 int 또는 int 리스트. '보이는' 페이지 번호(0부터 시작)
            delete_info: 삭제 정보 딕셔너리
        """
        if not self.renderer:
            return
        
        # 단일 페이지인지 여러 페이지인지 확인
        if isinstance(visual_page_num, int):
            visual_pages_to_delete = [visual_page_num]
        else:
            visual_pages_to_delete = list(visual_page_num)
        
        # 유효성 검사
        if not visual_pages_to_delete:
            return
        for vp in visual_pages_to_delete:
            if not (0 <= vp < len(self._page_order)):
                return
        
        # 1. '보이는' 순서를 '실제' 페이지 번호로 변환
        actual_pages_to_delete = [self._page_order[vp] for vp in visual_pages_to_delete]
        
        # 2. 실제 페이지 번호를 내림차순으로 정렬 (뒤에서부터 삭제하여 인덱스 변동 최소화)
        actual_pages_to_delete.sort(reverse=True)
        
        # 3. PdfViewWidget에 실제 페이지 번호 리스트를 전달하여 삭제 실행
        self._pdf_view_widget.delete_pages(actual_pages_to_delete, worker_name=self._worker_name, delete_info=delete_info)
        
        # 4. 페이지 순서 목록 업데이트
        # visual_pages_to_delete도 내림차순으로 정렬하여 뒤에서부터 제거
        visual_pages_to_delete_sorted = sorted(visual_pages_to_delete, reverse=True)
        for vp in visual_pages_to_delete_sorted:
            self._page_order.pop(vp)
        
        # 5. 삭제된 페이지 뒤의 페이지들의 순서 값 갱신 (실제 파일 인덱스가 바뀌었으므로)
        # 각 실제 페이지가 삭제될 때마다 그보다 큰 인덱스를 가진 페이지들의 값을 1씩 감소
        for actual_page in actual_pages_to_delete:
            for i in range(len(self._page_order)):
                if self._page_order[i] > actual_page:
                    self._page_order[i] -= 1
        
        # 6. 썸네일 뷰 갱신
        self._thumbnail_viewer.set_renderer(self.renderer, self._page_order, rotations=self._pdf_view_widget.get_page_rotations())

        # 7. 뷰어 및 네비게이션 갱신
        new_total_pages = len(self._page_order)
        if new_total_pages == 0:
            self.show_load_view() # 모든 페이지 삭제 시 로드 화면으로
            return                # 로드 화면으로 전환했으므로 여기서 함수 종료
        else:
            # 삭제 후 적절한 페이지로 포커스 이동
            # 삭제된 페이지들 중 가장 작은 위치 또는 그 앞
            first_deleted_visual = min(visual_pages_to_delete) if visual_pages_to_delete else 0
            next_visual_page = min(first_deleted_visual, new_total_pages - 1)
            self.go_to_page(next_visual_page)
        
        # 파일 정보 패널 업데이트
        self._info_panel.update_total_pages(new_total_pages)

    # === UI 및 레이아웃 업데이트 ===

    def set_splitter_sizes(self, is_landscape: bool):
        # QSplitter를 사용하여 영역 너비 설정
        try:
            if hasattr(self, 'ui_main_splitter'):
                # 썸네일(왼쪽), 콘텐츠(중앙), 정보패널(오른쪽)
                left_width = 220
                right_width = 450
                
                # 현재 스플리터의 전체 너비
                total_width = self.ui_main_splitter.width()
                if total_width <= 0:
                    total_width = 1350 # 기본 예상 너비
                
                center_width = max(600, total_width - left_width - right_width)
                
                # 스플리터 크기 설정
                self.ui_main_splitter.setSizes([left_width, center_width, right_width])
                
        except Exception:
            # 안전 장치: 실패해도 크래시 방지
            pass

    def _check_and_show_outlier_reminder(self):
        """PDF 렌더 완료 후 이상치가 있는 경우 리마인더 메시지를 표시한다."""
        if self._pending_outlier_check:
            self._pending_outlier_check = False  # 플래그 리셋
            
            # print(f"[디버그 main_window] _check_and_show_outlier_reminder - 호출 전 _pending_outlier_metadata: {self._pending_outlier_metadata}")
            # 이상치 종류 판단
            self._original_outlier_types = self._determine_outlier_type(self._pending_outlier_metadata)
            self._outlier_queue = self._original_outlier_types[:] # 처리할 큐 복사
            
            # 메타데이터 복사본 저장
            self._pending_outlier_metadata_copy = self._pending_outlier_metadata
            self._pending_outlier_metadata = None  # 원본 메타데이터 리셋
            
            # 순차적으로 이상치 처리 시작
            self._process_outlier_queue()

    def _process_outlier_queue(self):
        """이상치 큐를 순차적으로 처리하여 다이얼로그를 표시한다."""
        if not self._outlier_queue:
            # 큐가 비었으면 페이지 이동 로직 처리 후 종료
            if 'contract' in self._original_outlier_types:
                try:
                    page_number_raw = self._pending_outlier_metadata_copy.get('page_number')
                    if page_number_raw:
                        page_number = int(page_number_raw) - 1
                        total_pages = self.renderer.get_page_count()
                        if 0 <= page_number < total_pages:
                            self.go_to_page(page_number)
                except (ValueError, TypeError):
                    pass
            
            # 정리
            self._original_outlier_types = []
            self._pending_outlier_metadata_copy = None
            return

        outlier_type = self._outlier_queue.pop(0)

        # 타입에 따라 다이얼로그 표시
        if outlier_type == 'multichild':
            child_birth_date_str = self._pending_outlier_metadata_copy.get('child_birth_date')
            dates = []
            try:
                import json
                dates = json.loads(child_birth_date_str) if isinstance(child_birth_date_str, str) else child_birth_date_str
                if not isinstance(dates, list): dates = []
            except Exception:
                dates = []
            
            dialog = MultiChildCheckDialog(dates, self)
            dialog.exec()

        elif outlier_type == 'contract':
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle("구매계약서 이상")
            msg_box.setText("구매계약서 이상!")
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()

        elif outlier_type == 'contract_missing':
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle("구매계약서 확인 불가")
            msg_box.setText("구매계약서 확인 불가!")
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()

        elif outlier_type == 'chobon':
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle("초본 이상")
            msg_box.setText("초본 이상!")
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()

        elif outlier_type == 'chobon_data_missing':
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle("초본 데이터 누락")
            msg_box.setText("초본 필수 데이터가 누락되었습니다!")
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()

        elif outlier_type == 'chobon_address_mismatch':
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle("초본 주소 불일치")
            msg_box.setText("초본 주소와 지역이 일치하지 않습니다!")
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()

        # elif outlier_type == 'chobon_issue_date_outlier':
        #     msg_box = QMessageBox(self)
        #     msg_box.setIcon(QMessageBox.Icon.Warning)
        #     msg_box.setWindowTitle("초본 발행일 이상")
        #     msg_box.setText("초본 발행일이 31일 이상 경과했습니다!")
        #     msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        #     msg_box.exec()

        elif outlier_type == 'chobon_missing':
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle("초본 없음")
            msg_box.setText("초본 없음!")
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()

        # 현재 다이얼로그가 닫힌 후, 다음 큐 아이템을 처리하도록 스케줄링
        QTimer.singleShot(0, self._process_outlier_queue)
    
    def _determine_outlier_type(self, metadata: dict | None) -> list[str]:
        """
        메타데이터를 기반으로 이상치 종류를 판단하여 리스트로 반환한다.
        """
        if not metadata:
            return []
        
        import pandas as pd  # 함수 내부에서 pd.Timestamp 사용을 위해 필요
        
        outlier_types = []
        
        구매계약서 = metadata.get('구매계약서', 0) == 1
        초본 = metadata.get('초본', 0) == 1
        공동명의 = metadata.get('공동명의', 0) == 1
        
        # 필수 서류 확인: 구매계약서 또는 초본 중 하나라도 없으면 체크
        구매계약서값 = metadata.get('구매계약서', 0)
        초본값 = metadata.get('초본', 0)
        
        # 구매계약서가 0이고 초본이 1인 경우
        if 구매계약서값 == 0 and 초본값 == 1:
            outlier_types.append('contract_missing')
        
        # 초본이 0이고 구매계약서가 1인 경우 (초본 없음은 이미 chobon_missing으로 처리됨)
        
        # 다자녀 이상치 체크
        다자녀값 = metadata.get('다자녀', 0)
        if 다자녀값 == 1:
            child_birth_date_str = metadata.get('child_birth_date')
            if child_birth_date_str:
                try:
                    import json
                    
                    dates = json.loads(child_birth_date_str) if isinstance(child_birth_date_str, str) else child_birth_date_str
                    # 리스트가 아니면 빈 리스트 처리
                    if not isinstance(dates, list):
                        dates = []
                        
                    today = datetime.now().date()
                    for d_str in dates:
                        try:
                            # 문자열 형식에 따라 파싱
                            if len(d_str) > 10: # YYYY-MM-DD HH:MM:SS 등
                                d_str = d_str.split()[0]
                            
                            birth_date = datetime.strptime(d_str, "%Y-%m-%d").date()
                            
                            # 만나이 19세 이상 체크 (만 18세 초과)
                            age = today.year - birth_date.year
                            is_over_18 = False
                            
                            if age > 19:
                                is_over_18 = True
                            elif age == 19:
                                # 생일이 지났거나 같으면 만 19세
                                if (today.month, today.day) >= (birth_date.month, birth_date.day):
                                    is_over_18 = True
                            
                            if is_over_18:
                                outlier_types.append('multichild')
                                break # 한 명이라도 발견되면 중단
                        except (ValueError, TypeError):
                            pass
                except Exception:
                    pass

        # 구매계약서 이상치 체크
        if 구매계약서 and (초본 or 공동명의):
            ai_계약일자 = metadata.get('ai_계약일자')
            ai_이름 = metadata.get('ai_이름')
            전화번호 = metadata.get('전화번호')
            이메일 = metadata.get('이메일')
            차종 = metadata.get('차종')
            
            # 차종이 None인 경우 구매계약서 이상으로 처리
            if 차종 is None or (isinstance(차종, str) and 차종.strip() == ''):
                if 'contract' not in outlier_types: outlier_types.append('contract')
            
            # NULL 체크
            if ai_계약일자 is None or ai_이름 is None or 전화번호 is None or 이메일 is None:
                if 'contract' not in outlier_types: outlier_types.append('contract')
            
            # 계약일자 > 오늘-4일 체크
            try:
                import pandas as pd
                
                contract_date = None
                if isinstance(ai_계약일자, str):
                    try:
                        contract_date = datetime.strptime(ai_계약일자.split()[0], "%Y-%m-%d").date()
                    except (ValueError, AttributeError):
                        pass
                elif isinstance(ai_계약일자, (datetime, date)):
                    contract_date = ai_계약일자 if isinstance(ai_계약일자, date) else ai_계약일자.date()
                elif isinstance(ai_계약일자, pd.Timestamp):
                    contract_date = ai_계약일자.date()
                
                if contract_date:
                    today = datetime.now().date()
                    four_days_ago = today - timedelta(days=4)
                    if contract_date > four_days_ago:
                        if 'contract' not in outlier_types: outlier_types.append('contract')
            except Exception:
                pass
            
            # 2025년 이전 체크
            try:
                import pandas as pd
                
                if isinstance(ai_계약일자, str):
                    try:
                        contract_date = datetime.strptime(ai_계약일자.split()[0], "%Y-%m-%d").date()
                        if contract_date < date(2025, 1, 1):
                            if 'contract' not in outlier_types: outlier_types.append('contract')
                    except (ValueError, AttributeError):
                        pass
                elif isinstance(ai_계약일자, (datetime, date)):
                    contract_date = ai_계약일자 if isinstance(ai_계약일자, date) else ai_계약일자.date()
                    if contract_date < date(2025, 1, 1):
                        if 'contract' not in outlier_types: outlier_types.append('contract')
                elif isinstance(ai_계약일자, pd.Timestamp):
                    if ai_계약일자.date() < date(2025, 1, 1):
                        if 'contract' not in outlier_types: outlier_types.append('contract')
            except Exception:
                pass
        
        # 초본 이상치 체크
        if 초본:
            chobon_name = metadata.get('name') # 'name'으로 수정
            chobon_birth_date = metadata.get('birth_date') # 'birth_date'로 수정
            chobon_address_1 = metadata.get('address_1') # 'address_1'으로 수정
            chobon = metadata.get('chobon', 1)  # 기본값은 1 (정상)
            
            # chobon == 0이면 "초본 없음"으로 처리
            if chobon == 0:
                outlier_types.append('chobon_missing')
            
            # 초본 기본 정보 누락 (name, birth_date, address_1) 이상치 체크
            if chobon_name is None or chobon_birth_date is None or chobon_address_1 is None:
                if 'chobon_data_missing' not in outlier_types: outlier_types.append('chobon_data_missing')
            
            # 초본 address_1 지역 불일치 체크
            region_val = metadata.get('region')
            address_1_val = metadata.get('chobon_address_1') # 여기를 수정
            if region_val and address_1_val and region_val not in address_1_val:
                if 'chobon_address_mismatch' not in outlier_types: outlier_types.append('chobon_address_mismatch')
            
            # 초본 issue_date 이상치 체크 (31일 이상) - 이전에 sql_manager.py에서 계산된 값 활용
            issue_date = metadata.get('issue_date')
            # print(f"[디버그 main_window] _determine_outlier_type - issue_date raw: {issue_date}, type: {type(issue_date)}")
            if issue_date and isinstance(issue_date, (str, datetime, date, pd.Timestamp)):
                try:
                    import pytz

                    issue_date_obj = None
                    if isinstance(issue_date, str):
                        # print(f"[디버그 main_window] issue_date (str) 파싱 시도: {issue_date}")
                        try:
                            # ISO 8601 형식 처리 (예: "2025-04-28T15:00:00.000Z")
                            issue_date_obj = datetime.strptime(issue_date.split('T')[0], "%Y-%m-%d").date()
                            # print(f"[디버그 main_window] ISO 8601 파싱 성공: {issue_date_obj}")
                        except ValueError:
                            try:
                                # 다른 문자열 형식 처리 (예: "2025-04-28 00:00:00")
                                issue_date_obj = datetime.strptime(issue_date.split()[0], "%Y-%m-%d").date()
                                # print(f"[디버그 main_window] 일반 문자열 파싱 성공: {issue_date_obj}")
                            except ValueError:
                                pass # 파싱 실패 시 issue_date_obj는 None 유지
                                # print(f"[디버그 main_window] 문자열 파싱 실패")
                    elif isinstance(issue_date, (datetime, date)):
                        issue_date_obj = issue_date if isinstance(issue_date, date) else issue_date.date()
                        # print(f"[디버그 main_window] datetime/date 타입: {issue_date_obj}")
                    elif isinstance(issue_date, pd.Timestamp):
                        issue_date_obj = issue_date.date()
                        # print(f"[디버그 main_window] pd.Timestamp 타입: {issue_date_obj}")

                    # print(f"[디버그 main_window] 최종 issue_date_obj: {issue_date_obj}")

                    if issue_date_obj:
                        kst = pytz.timezone('Asia/Seoul')
                        today = datetime.now(kst).date()
                        # print(f"[디버그 main_window] 오늘 날짜: {today}")
                        days_diff = (today - issue_date_obj).days
                        # print(f"[디버그 main_window] 날짜 차이 (일): {days_diff}")
                        if days_diff >= 31:
                            if 'chobon_issue_date_outlier' not in outlier_types: outlier_types.append('chobon_issue_date_outlier')
                            # print(f"[디버그 main_window] 'chobon_issue_date_outlier' 추가됨")
                except Exception:
                    traceback.print_exc()
                    # print(f"[디버그 main_window] 초본 발행일 이상치 체크 중 예외 발생")
        # print(f"[디버그] _determine_outlier_type - region_val: {region_val}")
        # print(f"[디버그] _determine_outlier_type - address_1_val: {address_1_val}")
        print(f"[디버그] _determine_outlier_type - 최종 outlier_types: {outlier_types}")
        return outlier_types
    
    def _on_data_refreshed(self):
        """데이터 새로고침 완료 시 호출되는 슬롯"""
        self._update_refresh_time()
        # 알람 위젯도 함께 새로고침
        if hasattr(self, '_alarm_widget'):
            self._alarm_widget.refresh_data()

    def _update_refresh_time(self):
        """한국 시간으로 새로고침 시간을 업데이트한다."""
        korea_tz = pytz.timezone('Asia/Seoul')
        korea_time = datetime.now(korea_tz)
        time_str = korea_time.strftime('%Y-%m-%d %H:%M:%S')
        if hasattr(self, 'database_updated_time_label'):
            # 시간 부분을 빨간색 bold로 표시
            html_text = f"새로고침: <span style='color: red; font-weight: bold;'>{time_str}</span>"
            self.database_updated_time_label.setText(html_text)
    
    def _refresh_all_data(self):
        """모든 데이터를 새로고침한다 (메인화면일 때만)."""
        # 한국 시간으로 새로고침 시간 업데이트
        self._update_refresh_time()
        
        # PDF가 렌더된 상태가 아닐 때만 새로고침
        if self.renderer is None:
            self._pdf_load_widget.refresh_data()
            if hasattr(self, '_alarm_widget'):
                self._alarm_widget.refresh_data()

    def _update_worker_label(self):
        """worker_label_2에 작업자 이름을 표시하고, 관리자 권한에 따라 버튼 가시성을 설정한다."""
        # 관리자 작업자 목록
        admin_workers = ['이경구', '이호형']
        is_admin = self._worker_name in admin_workers
        
        # 작업자 현황 버튼 가시성 설정
        if hasattr(self, 'pushButton_worker_progress'):
            self.pushButton_worker_progress.setVisible(is_admin)
        
        # 작업자 현황 메뉴 항목 가시성 설정
        if hasattr(self, 'worker_progress_action'):
            self.worker_progress_action.setVisible(is_admin)
        
        # 작업자 라벨 업데이트
        if hasattr(self, 'worker_label_2'):
            if self._worker_name:
                self.worker_label_2.setText(f"작업자: {self._worker_name}")
            else:
                self.worker_label_2.setText("작업자: 미로그인")
    
    def _update_ai_results_action_state(self, rn: str):
        """AI 결과 보기 액션의 활성화 상태를 업데이트한다."""
        if not hasattr(self, 'view_ai_results_action'):
            return
        
        if not rn:
            self.view_ai_results_action.setEnabled(False)
            return
        
        # AI 결과 플래그 확인
        from core.sql_manager import check_gemini_flags
        flags = check_gemini_flags(rn)
        
        # 플래그 중 하나라도 True면 활성화
        has_ai_results = any(flags.values()) if flags else False
        self.view_ai_results_action.setEnabled(has_ai_results)

    # === 이벤트 처리 ===
    
    def showEvent(self, event):
        """창이 처음 표시될 때 제목 표시줄을 포함한 전체 높이를 화면에 맞게 조정한다."""
        super().showEvent(event)
        if not self._initial_resize_done:
            # 최대화 상태로 전환하여 최대 크기 정보 획득
            self.showMaximized()
            max_geometry = self.geometry()
            
            # 즉시 일반 상태로 복원
            self.showNormal()
            
            # 너비는 1350으로 고정, 높이는 최대화 상태의 높이 사용
            target_width = 1350
            target_height = max_geometry.height()
            
            # 화면 중앙에 배치 (전체 창 높이가 화면 높이와 일치하도록)
            screen = self.screen()
            if screen:
                available_geometry = screen.availableGeometry()
                x = (available_geometry.width() - target_width) // 2
                # 제목 표시줄 높이 계산
                title_bar_height = self.frameGeometry().height() - self.geometry().height()
                
                # 제목 표시줄이 화면 맨 위에 오도록 클라이언트 영역을 제목 표시줄 높이만큼 아래로 배치
                y = title_bar_height
                
                # 클라이언트 영역 높이 = 화면 높이 - 제목 표시줄 높이
                client_height = available_geometry.height() - title_bar_height
                
                self.setGeometry(x, y, target_width, client_height)
            
            # 초기 스플리터 크기 설정 (화면에 표시된 후 정확한 너비 기반으로 설정)
            QTimer.singleShot(0, lambda: self.set_splitter_sizes(False))
            
            self._initial_resize_done = True
        
    def closeEvent(self, event):
        """애플리케이션 종료 시 PDF 문서 자원을 해제한다."""
        if self.renderer:
            self.renderer.close()
        event.accept()

    # === 사용자 상호작용 핸들러 ===
    
    def _prompt_save_before_reset(self):
        """'메인 화면' 버튼 클릭 시 저장 여부를 묻는 대화상자를 표시한다."""
        if not self.renderer:
            self.show_load_view()
            return

        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setWindowTitle("메인화면으로 돌아가기")
        msg_box.setText("변경사항을 저장하시겠습니까?")
        msg_box.setInformativeText("저장하지 않으면 변경사항이 모두 사라집니다.")

        # 사용자 요청에 따른 버튼 생성
        no_save_button = msg_box.addButton("저장X", QMessageBox.ButtonRole.DestructiveRole)
        save_button = msg_box.addButton("저장O", QMessageBox.ButtonRole.AcceptRole)
        cancel_button = msg_box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        
        msg_box.setDefaultButton(cancel_button)
        msg_box.exec()
        
        clicked_button = msg_box.clickedButton()
        
        if clicked_button == no_save_button:
            self.show_load_view()
            # 메인화면으로 돌아갈 때 데이터 새로고침
            self._refresh_all_data()
        elif clicked_button == save_button:
            self._save_document()
            # 저장 후 메인화면으로 돌아갈 때도 데이터 새로고침
            self._refresh_all_data()
        # 취소 버튼을 누르면 아무것도 하지 않고 대화상자만 닫힘

    def _prompt_save_before_open_file(self):
        """새 PDF 파일을 열기 전 저장 여부를 묻는다."""
        if not self.renderer:
            # 렌더러가 없으면(편집 중이 아니면) 바로 파일 열기
            self._pdf_load_widget.open_pdf_file()
            return

        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setWindowTitle("새 파일 열기")
        msg_box.setText("현재 문서를 저장하시겠습니까?")
        msg_box.setInformativeText("저장하지 않으면 변경사항이 사라집니다.")

        # 사용자 요청에 따른 버튼 생성
        no_save_button = msg_box.addButton("저장 안함", QMessageBox.ButtonRole.DestructiveRole)
        save_button = msg_box.addButton("저장", QMessageBox.ButtonRole.AcceptRole)
        cancel_button = msg_box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        
        msg_box.setDefaultButton(save_button)
        msg_box.exec()
        
        clicked_button = msg_box.clickedButton()
        
        if clicked_button == cancel_button:
            return # 취소 시 아무것도 하지 않음
            
        if clicked_button == save_button:
            # 저장 후 파일 열기 플래그 설정
            self._pending_open_file_after_save = True
            self._save_document()
            
        elif clicked_button == no_save_button:
            # 저장 안 함: 바로 파일 열기 창 호출
            # (사용자가 파일을 선택하고 로드하면 기존 렌더러가 닫힘)
            self._pdf_load_widget.open_pdf_file()

    def _handle_undo_request(self):
        """썸네일에서 Undo 요청이 왔을 때 PDF 뷰어의 되돌리기를 실행한다."""
        if self._pdf_view_widget and self.renderer:
            self._pdf_view_widget.undo_last_action()

    def _handle_edit_mode_timeout(self):
        """PDF 편집 모드 3분 경과 시 호출되는 핸들러"""
        # 1분 후 자동 저장 및 종료를 위한 타이머 설정
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setInterval(60000)  # 1분
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_triggered = False  # 자동 저장 트리거 플래그

        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("경고")
        msg_box.setText("PDF 편집 모드에서 3분이 경과했습니다.")
        msg_box.setInformativeText("1분 내에 확인을 누르지 않으면 변경사항이 저장되고 메인화면으로 이동합니다.")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        
        def on_auto_save_timeout():
            self._auto_save_triggered = True
            if msg_box.isVisible():
                msg_box.close()

        self._auto_save_timer.timeout.connect(on_auto_save_timeout)
        self._auto_save_timer.start()
        
        # 메시지 박스 실행 (Blocking)
        msg_box.exec()
        
        # 메시지 박스가 닫히면 타이머 중지
        if self._auto_save_timer.isActive():
            self._auto_save_timer.stop()
            
        # 자동 저장이 트리거된 경우 저장 로직 실행
        if self._auto_save_triggered:
            print("[3분 경과] 1분 추가 대기 시간 초과. 자동 저장 프로세스 시작.")
            self._save_document(skip_confirmation=True)

    # === 유틸리티 및 헬퍼 ===

    def _collect_pending_basic_info(self) -> tuple[str, str, str, str]:
        """대기 중인 기본 정보를 추출하여 튜플로 반환한다."""
        info = self._pending_basic_info or {'name': "", 'region': "", 'special_note': "", 'rn': ""}
        name = info.get('name', "")
        region = info.get('region', "")
        special_note = info.get('special_note', "")
        rn = info.get('rn', "")
        self._pending_basic_info = info
        return name, region, special_note, rn

    
    # === 테스트 관련 함수 ===

    def start_batch_test(self):
        """PDF 일괄 테스트를 시작한다 (test.py의 로직 사용)."""
        self.ui_status_bar.showMessage("PDF 일괄 테스트를 시작합니다...", 0)
        
        # test.py의 batch_process_pdfs 함수를 백그라운드에서 실행
        import sys
        from pathlib import Path as TestPath
        
        # test.py 모듈 임포트
        test_dir = TestPath(__file__).parent.parent / "test"
        if str(test_dir) not in sys.path:
            sys.path.insert(0, str(test_dir))
        
        try:
            from test import batch_process_pdfs
            
            input_dir = r'C:\Users\HP\Desktop\files\테스트PDF'
            output_dir = r'C:\Users\HP\Desktop\files\결과'
            
            # 백그라운드 스레드에서 실행
            import threading
            def run_test():
                try:
                    batch_process_pdfs(input_dir, output_dir)
                    self.ui_status_bar.showMessage("모든 PDF 파일 테스트를 성공적으로 완료했습니다.", 8000)
                except Exception as e:
                    self.ui_status_bar.showMessage(f"테스트 중 오류 발생: {e}", 10000)
            
            thread = threading.Thread(target=run_test, daemon=True)
            thread.start()
            
        except ImportError as e:
            QMessageBox.critical(self, "오류", f"test.py 모듈을 찾을 수 없습니다: {e}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"테스트 시작 중 오류: {e}")

    def _rotate_90_maybe_for_test(self):
        """10% 확률로 현재 페이지를 90도 회전(첫 페이지 기준)"""
        try:
            import random
            if self.renderer and self.renderer.get_page_count() > 0:
                if self._pdf_view_widget.current_page != 0:
                    self.go_to_page(0)
                if random.random() < 0.10:
                    self._pdf_view_widget.rotate_current_page_by_90_sync()
        except Exception as e:
            if not self.test_worker._is_stopped and self._pdf_view_widget.get_current_pdf_path():
                filename = Path(self._pdf_view_widget.get_current_pdf_path()).name
                self.test_worker.signals.error.emit(filename, f"회전 처리 중 오류: {e}")

    def _focus_page2_maybe_for_test(self):
        """50% 확률로 2페이지로 포커스를 이동 (존재 시)"""
        try:
            import random
            if self.renderer and self.renderer.get_page_count() >= 2:
                if random.random() < 0.50:
                    self.go_to_page(1)
        except Exception as e:
            if not self.test_worker._is_stopped and self._pdf_view_widget.get_current_pdf_path():
                filename = Path(self._pdf_view_widget.get_current_pdf_path()).name
                self.test_worker.signals.error.emit(filename, f"포커스 이동 중 오류: {e}")

    def _on_batch_test_error(self, filename: str, error_msg: str):
        """일괄 테스트 중 오류 발생 시 호출될 슬롯"""
        # 워커를 중지시켜 더 이상 진행되지 않도록 함
        if self.test_worker:
            self.test_worker.stop()

        if filename:
            title = f"'{filename}' 처리 중 오류"
            message = f"파일 '{filename}'을 처리하는 중 오류가 발생하여 테스트를 중단합니다.\n\n오류: {error_msg}"
        else:
            title = "테스트 설정 오류"
            message = f"테스트를 시작하는 중 오류가 발생했습니다.\n\n오류: {error_msg}"
        
        self.ui_status_bar.showMessage(f"오류로 테스트가 중단되었습니다: {error_msg}", 10000)
        QMessageBox.critical(self, title, message)

    def _on_batch_test_finished(self):
        """일괄 테스트 완료 시 호출될 슬롯"""
        self.ui_status_bar.showMessage("모든 PDF 파일 테스트를 성공적으로 완료했습니다.", 8000)
        QMessageBox.information(self, "테스트 완료", "지정된 모든 PDF 파일의 열기/저장 테스트를 성공적으로 완료했습니다.")

    def _load_original_document(self):
        """현재 로드된 PDF의 원본 파일을 불러와 다시 렌더링한다."""
        if not self.renderer:
            QMessageBox.warning(self, "오류", "현재 로드된 PDF 문서가 없습니다.")
            return

        if not self._is_current_file_processed:
            QMessageBox.information(self, "정보", "현재 파일은 이미 원본입니다.")
            return
        
        if not self._original_filepath:
            QMessageBox.warning(self, "오류", "원본 파일 경로 정보를 찾을 수 없습니다.")
            return

        try:
            from pathlib import Path
            import re

            # RN 추출 (self._current_rn이 이미 설정되어 있다고 가정)
            if not self._current_rn:
                QMessageBox.warning(self, "오류", "현재 RN 정보를 찾을 수 없습니다.")
                return
            
            rn = self._current_rn

            # DB에서 원본 파일 경로 조회
            original_filepath_from_db = get_original_pdf_path_by_rn(rn)

            if not original_filepath_from_db:
                QMessageBox.warning(self, "오류", f"원본 파일(RN: {rn})을 찾을 수 없습니다.") # 사용자 메시지 통일
                return
            
            # 단일 파일 경로를 리스트로 변환 (load_document가 리스트를 기대할 수 있으므로)
            original_pdf_paths = [original_filepath_from_db]
            
            # 기본 정보 보존 (show_load_view()에서 초기화되기 전에 저장)
            saved_basic_info = self._pending_basic_info.copy() if self._pending_basic_info else None
            saved_current_rn = self._current_rn
            saved_is_context_menu_work = self._is_context_menu_work  # 컨텍스트 메뉴 작업 플래그 보존
            
            # 기존 뷰어 정리 후 원본 파일 로드
            self.show_load_view() # 현재 뷰를 닫고 로드 화면으로 전환
            self.load_document(original_pdf_paths, metadata={'is_from_rns_filepath': True})
            
            # 보존된 기본 정보 복원
            if saved_basic_info:
                self._pending_basic_info = saved_basic_info
                name, region, special_note, rn = self._collect_pending_basic_info()
                self._info_panel.update_basic_info(name, region, special_note, rn)
            
            # RN 복원
            if saved_current_rn:
                self._current_rn = saved_current_rn
                self._pdf_view_widget.set_current_rn(saved_current_rn)
            
            # 컨텍스트 메뉴 작업 플래그 복원 (special_note 다이얼로그를 위해 필요)
            self._is_context_menu_work = saved_is_context_menu_work
            
            QMessageBox.information(self, "정보", "원본 파일을 성공적으로 불러왔습니다.")

        except Exception as e:
            QMessageBox.critical(self, "오류", f"원본 파일을 불러오는 중 오류가 발생했습니다:\n\n{str(e)}")

    def _handle_page_replace_with_original(self, visual_page_num):
        """선택된 페이지를 원본 PDF 파일의 같은 페이지 번호로 교체한다.
        
        Args:
            visual_page_num: 단일 int 또는 int 리스트. '보이는' 페이지 번호(0부터 시작)
        """
        if not self.renderer:
            QMessageBox.warning(self, "오류", "현재 로드된 PDF 문서가 없습니다.")
            return
        
        if not self._is_current_file_processed:
            QMessageBox.information(self, "정보", "현재 파일은 이미 원본입니다.")
            return
        
        if not self._original_filepath:
            QMessageBox.warning(self, "오류", "원본 파일 경로 정보를 찾을 수 없습니다.")
            return
        
        # 단일 페이지인지 여러 페이지인지 확인
        if isinstance(visual_page_num, int):
            visual_pages_to_replace = [visual_page_num]
        else:
            visual_pages_to_replace = list(visual_page_num)
        
        # 유효성 검사
        if not visual_pages_to_replace:
            return
        for vp in visual_pages_to_replace:
            if not (0 <= vp < len(self._page_order)):
                QMessageBox.warning(self, "오류", f"잘못된 페이지 번호입니다: {vp + 1}")
                return
        
        try:
            # RN 확인
            if not self._current_rn:
                QMessageBox.warning(self, "오류", "현재 RN 정보를 찾을 수 없습니다.")
                return
            rn = self._current_rn

            # DB에서 원본 파일 경로 조회
            original_filepath_from_db = get_original_pdf_path_by_rn(rn)
            
            if not original_filepath_from_db:
                QMessageBox.warning(self, "오류", f"원본 파일(RN: {rn})을 찾을 수 없습니다.")
                return

            # 원본 PDF 파일을 메모리에 로드
            with pymupdf.open(original_filepath_from_db) as original_doc:
                original_pdf_bytes = original_doc.tobytes(garbage=4, deflate=True)
            
            # 선택된 각 페이지에 대해 교체 수행
            # '보이는' 순서를 '실제' 페이지 번호로 변환
            actual_pages_to_replace = [self._page_order[vp] for vp in visual_pages_to_replace]
            
            # 각 페이지에 대해 원본 파일의 같은 페이지 번호 확인 및 교체
            for visual_idx, actual_page_num in enumerate(actual_pages_to_replace):
                # 원본 파일에 해당 페이지 번호가 있는지 확인
                original_doc_check = pymupdf.open(stream=original_pdf_bytes, filetype="pdf")
                if actual_page_num >= original_doc_check.page_count:
                    original_doc_check.close()
                    QMessageBox.critical(
                        self, 
                        "오류", 
                        f"원본 파일에 페이지 {actual_page_num + 1}이 없습니다.\n"
                        f"(원본 파일 총 페이지 수: {original_doc_check.page_count})\n\n"
                        f"작업이 취소되었습니다."
                    )
                    return
                original_doc_check.close()
                
                # 페이지 교체 수행
                self.renderer.replace_page(actual_page_num, original_pdf_bytes, actual_page_num)
            
            # 교체 완료 후 썸네일 및 뷰어 갱신
            self._thumbnail_viewer.set_renderer(self.renderer, self._page_order, rotations=self._pdf_view_widget.get_page_rotations())
            self._pdf_view_widget.set_renderer(self.renderer, clear_overlay=False)
            
            # 현재 페이지가 교체된 페이지 중 하나라면 화면 갱신
            if self.current_page in visual_pages_to_replace:
                self.go_to_page(self.current_page)
            
            QMessageBox.information(
                self, 
                "완료", 
                f"페이지 {[vp + 1 for vp in visual_pages_to_replace]}을(를) 원본 페이지로 교체했습니다."
            )
        
        except Exception as e:
            QMessageBox.critical(self, "오류", f"원본 페이지 교체 중 오류가 발생했습니다:\n\n{str(e)}")

    def _load_outbound_allocation_document(self):
        """(성남시 전용) 출고배정표 불러오기 - 서류병합 """
        import os
        # PdfRender는 상단에서 이미 import 됨

        base_path = get_converted_path(r'\\DESKTOP-R4MM6IR\Users\HP\Desktop\Tesla\24q4\지원\출고배정표')
        rn_number = self._current_rn 

        if not rn_number:
            print("디버그: RN 번호가 설정되지 않았습니다.")
            return

        found_file_path = ""
        # 우선순위: .pdf 먼저 찾기
        priority_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
        
        for ext in priority_extensions:
            for root, _, files in os.walk(base_path):
                for file in files:
                    if file.startswith(rn_number) and file.lower().endswith(ext):
                        found_file_path = os.path.join(root, file)
                        print(f"디버그: 서류 발견 ({ext}) - {found_file_path}")
                        break
                if found_file_path:
                    break
            if found_file_path:
                break

        if not found_file_path:
            print(f"디버그: RN 번호 {rn_number}에 해당하는 서류를 찾을 수 없습니다.")
            QMessageBox.information(self, "알림", f"RN 번호 {rn_number}에 해당하는 출고배정표를 찾을 수 없습니다.")
            return

        # 서류 병합 로직 수행
        try:
            if not self.renderer:
                 self.renderer = PdfRender()

            old_page_count = self.renderer.get_page_count()
            
            self.renderer.append_file(found_file_path)
            
            # 페이지 순서 업데이트 (기존 순서 유지 + 새 페이지 추가)
            self._page_order.extend(range(old_page_count, self.renderer.get_page_count()))
            
            # 썸네일 뷰 갱신
            self._thumbnail_viewer.set_renderer(self.renderer, self._page_order, rotations=self._pdf_view_widget.get_page_rotations())
            
            # PDF 뷰어 갱신 (렌더러 재설정 및 화면 갱신, 오버레이 보존)
            self._pdf_view_widget.set_renderer(self.renderer, clear_overlay=False)
            
            # 마지막 페이지로 이동
            last_page_index = self.renderer.get_page_count() - 1
            if last_page_index >= 0:
                # 뷰어 상태가 초기화되었으므로 약간의 지연을 두고 페이지 이동
                QTimer.singleShot(100, lambda: self.go_to_page(last_page_index))
            
            QMessageBox.information(self, "완료", f"출고배정표가 성공적으로 병합되었습니다.\n\n파일: {os.path.basename(found_file_path)}")

        except Exception as e:
            print(f"출고배정표 병합 중 오류 발생: {e}")
            QMessageBox.critical(self, "오류", f"출고배정표 병합 중 오류가 발생했습니다:\n{e}")

# === 모듈 레벨 함수 ===
def create_app():
    """QApplication을 생성하고 메인 윈도우를 반환한다."""
    app = QApplication(sys.argv)
    try:
        apply_stylesheet(app, theme='dark_teal.xml')
    except Exception:
        pass
    window = MainWindow()
    return app, window
