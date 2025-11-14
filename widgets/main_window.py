import sys
import os
from pathlib import Path

from PyQt6.QtCore import Qt, QThreadPool, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QMainWindow,
                             QMessageBox, QSplitter, QStackedWidget, QWidget, QFileDialog, QStatusBar,
                             QPushButton, QLabel, QDialog)
from PyQt6 import uic
from qt_material import apply_stylesheet

from core.pdf_render import PdfRender
from core.pdf_saved import compress_pdf_with_multiple_stages
from core.sql_manager import claim_subsidy_work
from core.workers import BatchTestSignals, PdfBatchTestWorker
from core.utility import normalize_basic_info
from widgets.pdf_load_widget import PdfLoadWidget
from widgets.pdf_view_widget import PdfViewWidget
from widgets.thumbnail_view_widget import ThumbnailViewWidget
from widgets.info_panel_widget import InfoPanelWidget
from widgets.todo_widget import ToDoWidget
from widgets.settings_dialog import SettingsDialog
from widgets.login_dialog import LoginDialog
from widgets.mail_dialog import MailDialog
from widgets.worker_progress_dialog import WorkerProgressDialog
from widgets.alarm_widget import AlarmWidget
from widgets.gemini_results_dialog import GeminiResultsDialog
from widgets.config_dialog import ConfigDialog


class MainWindow(QMainWindow):
    """메인 윈도우"""

    # --- 초기화 및 설정 ---
    
    def __init__(self):
        super().__init__()
        
        # UI 파일 로드
        ui_path = Path(__file__).parent.parent / "ui" / "main_window.ui"
        uic.loadUi(str(ui_path), self)

        self.renderer: PdfRender | None = None
        self.current_page = -1
        self.thread_pool = QThreadPool()
        self._initial_resize_done = False  # 초기 크기 조정 완료 플래그
        self._auto_return_to_main_after_save = False
        self._worker_name = ""  # 작업자 이름 저장용 (위젯 생성 전에 초기화)
        self._original_filepath: str | None = None # 현재 로드된 PDF의 원본 파일 경로
        self._is_current_file_processed: bool = False # 현재 파일이 전처리된 파일인지 여부
        
        # --- 위젯 인스턴스 생성 ---
        self._thumbnail_viewer = ThumbnailViewWidget()
        self._pdf_view_widget = PdfViewWidget()
        self._pdf_load_widget = PdfLoadWidget()
        self._info_panel = InfoPanelWidget()
        self._alarm_widget = AlarmWidget(self._worker_name)
        self._todo_widget = ToDoWidget(self)
        self._settings_dialog = SettingsDialog(self)
        self._mail_dialog = MailDialog(worker_name=self._worker_name, parent=self)
        self._pending_basic_info: dict | None = None
        self._gemini_results_dialog = GeminiResultsDialog(self)
        self._config_dialog = ConfigDialog(self)
        
        # 새로고침 타이머
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_all_data)

        # --- 페이지 순서 관리 ---
        self._page_order: list[int] = []

        # --- UI 컨테이너에 위젯 배치 ---
        self._setup_ui_containers()
        
        # --- 초기 위젯 상태 설정 ---
        self._pdf_view_widget.hide()
        self._thumbnail_viewer.hide()
        self._info_panel.hide()
        self._alarm_widget.show()  # alarm_widget은 초기에 표시
        self._todo_widget.hide()

        # --- 메뉴바 및 액션 설정 ---
        self._setup_menus()

        # --- 상태바에 네비게이션 위젯 추가 ---
        self.ui_status_bar.addPermanentWidget(self.ui_nav_widget)

        # --- 시그널 연결 ---
        self._setup_connections()

        # --- 전역 단축키 설정 ---
        self._setup_global_shortcuts()

        # 로그인 다이얼로그 초기화
        self._login_dialog = LoginDialog(self)
        self._current_rn = ""  # 현재 작업 중인 RN 번호 저장용
        self._is_context_menu_work = False  # 컨텍스트 메뉴를 통한 작업 여부
        
        # 초기 상태에서 작업자 현황 버튼 숨김
        if hasattr(self, 'pushButton_worker_progress'):
            self.pushButton_worker_progress.hide()
        
        # 앱 시작 시 로그인 다이얼로그 표시
        self._show_login_dialog()

    def _setup_ui_containers(self):
        """UI 컨테이너에 위젯들을 배치한다."""

        if hasattr(self, 'ui_main_layout'):
            self.ui_main_layout.setSpacing(0)
            self.ui_main_layout.setContentsMargins(0, 0, 0, 0)

        # 썸네일
        thumbnail_layout = QHBoxLayout(self.ui_thumbnail_container)
        thumbnail_layout.setContentsMargins(0, 0, 0, 0)
        thumbnail_layout.setSpacing(0)
        thumbnail_layout.addWidget(self._thumbnail_viewer)
        
        # 콘텐츠 영역 (load와 view를 같은 공간에 배치)
        content_layout = QHBoxLayout(self.ui_content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._pdf_load_widget)
        content_layout.addWidget(self._pdf_view_widget)
        
        # 정보 패널 컨테이너에 배치 (VBoxLayout으로 변경하여 alarm_widget과 info_panel을 수직으로 배치)
        from PyQt6.QtWidgets import QVBoxLayout, QSpacerItem, QSizePolicy
        info_panel_layout = QVBoxLayout(self.ui_info_panel_container)
        info_panel_layout.setContentsMargins(0, 0, 0, 0)
        info_panel_layout.setSpacing(0)
        
        # alarm_widget 추가 (상단)
        info_panel_layout.addWidget(self._alarm_widget)
        
        # info_panel은 나중에 표시될 때 사용 (초기에는 숨김)
        info_panel_layout.addWidget(self._info_panel)
        
        # 스플리터 크기 설정
        # self.ui_main_splitter.setSizes([600, 600])

        # QHBoxLayout 구조에서는 각 컨테이너의 사이즈 정책으로 제어
        # UI 파일에서 horstretch 값으로 기본 비율이 설정되어 있음

    def _setup_menus(self):
        """메뉴바를 설정합니다."""
        # 파일 메뉴
        open_action = QAction("PDF 열기", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._pdf_load_widget.open_pdf_file)
        self.menu_file.addAction(open_action)
        
        self.menu_file.addSeparator()
        
        # 원본 불러오기 액션 추가 (초기에는 비활성화)
        self.load_original_action = QAction("원본 불러오기", self)
        self.load_original_action.setEnabled(False)
        self.load_original_action.triggered.connect(self._load_original_document)
        self.menu_file.addAction(self.load_original_action)
        
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
        
        settings_action = QAction("설정", self)
        settings_action.triggered.connect(self._open_settings_dialog)
        self.menu_edit.addAction(settings_action)
        
        # 보기 메뉴
        todo_action = QAction("할일 목록", self)
        todo_action.setCheckable(True)
        todo_action.triggered.connect(self._todo_widget.toggle_overlay)
        self.menu_view.addAction(todo_action)
        
        self.menu_view.addSeparator()
        
        self.worker_progress_action = QAction("작업자 현황", self)
        self.worker_progress_action.triggered.connect(self._open_worker_progress_dialog)
        self.menu_view.addAction(self.worker_progress_action)

        self.view_saved_pdfs_action = QAction("저장된 PDF 보기", self)
        # self.view_saved_pdfs_action.triggered.connect(self._open_saved_pdfs_dialog)
        self.menu_view.addAction(self.view_saved_pdfs_action)

        # 설정 메뉴
        preferences_action = QAction("환경설정", self)
        preferences_action.triggered.connect(self._open_config_dialog)
        self.menu_settings.addAction(preferences_action)

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
        self._pdf_view_widget.page_aspect_ratio_changed.connect(self.set_splitter_sizes)
        self._pdf_view_widget.save_completed.connect(self._handle_save_completed) # 저장 완료 시그널 연결
        self._pdf_view_widget.toolbar.save_pdf_requested.connect(self._save_document)
        self._pdf_view_widget.toolbar.setting_requested.connect(self._open_settings_dialog)
        self._pdf_view_widget.toolbar.email_requested.connect(self._open_mail_dialog)
        self._pdf_view_widget.page_delete_requested.connect(self._handle_page_delete_request)
        self._pdf_load_widget.ai_review_requested.connect(self._show_gemini_results_dialog)
        
        # 정보 패널 업데이트 연결
        self._pdf_view_widget.pdf_loaded.connect(self._info_panel.update_file_info)
        self._pdf_view_widget.page_info_updated.connect(self._info_panel.update_page_info)
        self._info_panel.text_stamp_requested.connect(self._pdf_view_widget.activate_text_stamp_mode)

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
            self._worker_name = self._login_dialog.get_worker_name()
            self._update_worker_label()
            # 로그인 후 알람 위젯 업데이트
            if hasattr(self, '_alarm_widget'):
                self._alarm_widget._worker_name = self._worker_name
                self._alarm_widget.refresh_data()
            
            # 초기 새로고침 타이머 시작
            refresh_interval = self._config_dialog.settings.value("general/refresh_interval", 30, type=int)
            self._refresh_timer.start(refresh_interval * 1000)  # 초 단위이므로 1000을 곱함
        else:
            # 취소 시 앱 종료
            self.close()

    def _open_settings_dialog(self):
        """설정 다이얼로그를 연다."""
        if self._settings_dialog.exec():
            # 사용자가 OK를 누르면 변경된 단축키를 다시 적용
            self._apply_shortcuts()
    
    def _open_config_dialog(self):
        """환경설정 다이얼로그를 연다."""
        if self._config_dialog.exec():
            # 사용자가 OK를 누르면 변경된 새로고침 주기를 적용
            refresh_interval = self._config_dialog.settings.value("general/refresh_interval", 30, type=int)
            self._refresh_timer.stop()  # 기존 타이머 중지
            self._refresh_timer.start(refresh_interval * 1000)  # 새 주기로 시작 (초 단위이므로 1000을 곱함)
    
    def _open_mail_dialog(self):
        """메일 다이얼로그를 연다."""
        # 현재 작업 중인 RN 값을 다이얼로그에 자동 설정
        if self._current_rn:
            self._mail_dialog.set_rn_value(self._current_rn)
        
        if self._mail_dialog.exec():
            rn_value = self._mail_dialog.get_rn_value()
            content = self._mail_dialog.get_content()
            print(f"메일 전송 요청 - RN: {rn_value}, 내용: {content}")
            # TODO: 실제 메일 전송 로직 구현

    def _open_mail_dialog_then_return_to_main(self):
        """이메일 다이얼로그를 열고, 완료 후 메인화면으로 돌아간다."""
        # 현재 작업 중인 RN 값을 다이얼로그에 자동 설정
        if self._current_rn:
            self._mail_dialog.set_rn_value(self._current_rn)
        
        # 이메일 다이얼로그를 모달로 실행
        dialog_result = self._mail_dialog.exec()
        
        if dialog_result:
            rn_value = self._mail_dialog.get_rn_value()
            content = self._mail_dialog.get_content()
            print(f"[컨텍스트 메뉴 작업 완료 후 메일 전송] RN: {rn_value}, 내용: {content}")
            # TODO: 실제 메일 전송 로직 구현
        
        # 이메일 창 완료 후 즉시 컨텍스트 메뉴 작업 플래그 리셋
        self._is_context_menu_work = False
        print("[컨텍스트 메뉴 작업 플래그] 이메일 창 완료 후 False로 리셋됨")
        
        # 이메일 창이 닫힌 후 메인화면으로 돌아가기
        self.show_load_view()
        # 메인화면으로 돌아갈 때 데이터 새로고침
        self._pdf_load_widget.refresh_data()
        # 알람 위젯도 함께 새로고침
        if hasattr(self, '_alarm_widget'):
            self._alarm_widget.refresh_data()

    def _open_worker_progress_dialog(self):
        """작업자 현황 다이얼로그를 연다."""
        worker_progress_dialog = WorkerProgressDialog(self)
        worker_progress_dialog.exec()
        
    def _show_gemini_results_dialog(self, rn: str):
        """Gemini AI 결과 다이얼로그를 표시한다."""
        self._gemini_results_dialog.load_data(rn)
        self._gemini_results_dialog.show()
        self._gemini_results_dialog.raise_()
        self._gemini_results_dialog.activateWindow()

    # === 문서 생명주기 관리 ===
    
    def load_document(self, pdf_paths: list, is_preprocessed: bool = False):
        """PDF 및 이미지 문서를 로드하고 뷰를 전환한다."""
        if not pdf_paths:
            return

        if self.renderer:
            self.renderer.close()

        try:
            self.renderer = PdfRender()
            if is_preprocessed and len(pdf_paths) == 1:
                # 고속 로딩: 전처리된 단일 파일
                self.renderer.load_preprocessed_pdf(pdf_paths[0])
            else:
                # 일반 로딩: 전처리 안됐거나 여러 파일
                self.renderer.load_pdf(pdf_paths)
                
        except Exception as e:
            QMessageBox.critical(self, "오류", f"문서를 여는 데 실패했습니다: {e}")
            self.renderer = None
            return

        # 페이지 순서 초기화
        self._page_order = list(range(self.renderer.get_page_count()))

        # 첫 번째 파일 이름을 기준으로 창 제목 설정
        self.setWindowTitle(f"PDF Viewer - {Path(pdf_paths[0]).name}")
        
        self._thumbnail_viewer.set_renderer(self.renderer)
        self._pdf_view_widget.set_renderer(self.renderer)

        self._pdf_load_widget.hide()
        self._pdf_view_widget.show()
        self._thumbnail_viewer.show()
        self._alarm_widget.hide()  # PDF 로드 시 alarm_widget 숨김
        self._info_panel.show()  # PDF 로드 시 info_panel 표시

        # 기본 스플리터 사이즈를 즉시 한 번 강제하여 초기 힌트를 통일
        self.set_splitter_sizes(False)

        name, region, special_note = self._collect_pending_basic_info()
        self._info_panel.update_basic_info(name, region, special_note)

        # UI가 표시된 다음 틱에 첫 페이지 렌더를 예약하여 초기 크기 기준을 보장한다.
        if self.renderer.get_page_count() > 0:
            QTimer.singleShot(0, lambda: self.go_to_page(0))
        
        # 컨텍스트 메뉴를 통한 작업인 경우 '원본 불러오기' 액션 활성화
        if hasattr(self, 'load_original_action') and self._is_context_menu_work:
            self.load_original_action.setEnabled(True)

    def _handle_pdf_selected(self, pdf_paths: list):
        self._pending_basic_info = None
        self._current_rn = ""  # 로컬 파일 열기 시 RN 초기화
        self._is_context_menu_work = False  # 로컬 파일 열기 시 컨텍스트 메뉴 작업 플래그 리셋
        self._info_panel.update_basic_info("", "", "")
        # 로컬 파일 열기 시 '원본 불러오기' 액션 비활성화
        if hasattr(self, 'load_original_action'):
            self.load_original_action.setEnabled(False)
        self.load_document(pdf_paths)

    def _handle_work_started(self, pdf_paths: list, metadata: dict):
        # 컨텍스트 메뉴를 통한 작업 시작 여부 확인 및 저장
        self._is_context_menu_work = metadata.get('is_context_menu_work', False)
        is_preprocessed = metadata.get('file_rendered', 0) == 1
        
        # 원본 파일 경로와 전처리 상태 저장
        self._original_filepath = metadata.get('original_filepath')
        self._is_current_file_processed = is_preprocessed
        
        if self._is_context_menu_work:
            print(f"[컨텍스트 메뉴를 통한 작업 시작] RN: {metadata.get('rn', 'N/A')}")
        
        # 메일 content 조회
        thread_id = metadata.get('recent_thread_id')
        mail_content = ""
        if thread_id:
            from core.sql_manager import get_mail_content_by_thread_id
            mail_content = get_mail_content_by_thread_id(thread_id)
            print(f"\n{'='*80}")
            print(f"[메일 Content 조회 - thread_id: {thread_id}]")
            print(f"{'='*80}")  
            print(mail_content)
            print(f"{'='*80}\n")
        
        # 기존 로직
        if not metadata:
            self._current_rn = ""  # metadata가 없는 경우 RN 초기화
            self._pending_basic_info = normalize_basic_info(metadata)
            self.load_document(pdf_paths)
            return

        worker_name = self._worker_name or metadata.get('worker', '')
        rn_value = metadata.get('rn')
        existing_worker = metadata.get('worker', '').strip()  # 이미 배정된 작업자
        
        # 현재 작업 중인 RN 저장
        self._current_rn = rn_value or ""

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
            self._pending_basic_info = normalize_basic_info(metadata)
            self.load_document(pdf_paths, is_preprocessed=is_preprocessed)
            
            # PDF 로드 후 메일 content 표시
            if mail_content:
                self._pdf_view_widget.set_mail_content(mail_content)
            return

        if not claim_subsidy_work(rn_value, worker_name):
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle("이미 작업 중")
            msg_box.setText("해당 신청 건은 다른 작업자가 진행 중입니다.")
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            
            # 메시지박스가 닫힐 때 자동으로 데이터 새로고침 실행
            msg_box.finished.connect(self._refresh_all_data)
            msg_box.exec()
            return

        self._pending_basic_info = normalize_basic_info(metadata)
        self.load_document(pdf_paths, is_preprocessed=is_preprocessed)
        
        # PDF 로드 후 메일 content 표시
        if mail_content:
            self._pdf_view_widget.set_mail_content(mail_content)

    def _save_document(self):
        """현재 상태(페이지 순서 포함)로 문서를 저장한다."""
        if self.renderer:
            print(f"저장할 페이지 순서: {self._page_order}")  # 디버그 출력
            # 저장 완료 후 자동으로 메인화면으로 돌아가도록 플래그 설정
            self._auto_return_to_main_after_save = True
            try:
                self._pdf_view_widget.save_pdf(page_order=self._page_order, worker_name=self._worker_name)
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
        if hasattr(self, '_auto_return_to_main_after_save') and self._auto_return_to_main_after_save:
            self._auto_return_to_main_after_save = False
            
            # 컨텍스트 메뉴를 통한 작업이었다면 이메일 창을 먼저 열기
            if self._is_context_menu_work:
                self._is_context_menu_work = False  # 플래그 리셋
                self._open_mail_dialog_then_return_to_main()
            else:
                # 일반적인 경우 바로 메인화면으로 돌아가기
                self.show_load_view()
                # 메인화면으로 돌아갈 때 데이터 새로고침
                self._refresh_all_data()

    def show_load_view(self):
        """PDF 뷰어를 닫고 초기 로드 화면으로 전환하며 모든 관련 리소스를 정리한다."""
        self.setWindowTitle("PDF Viewer")
        if self.renderer:
            self.renderer.close()
        
        self.renderer = None
        self.current_page = -1
        self._current_rn = ""  # 현재 RN 초기화
        self._is_context_menu_work = False  # 컨텍스트 메뉴 작업 플래그 리셋

        # 메인화면으로 돌아갈 때 '원본 불러오기' 액션 비활성화
        if hasattr(self, 'load_original_action'):
            self.load_original_action.setEnabled(False)

        self._pdf_load_widget.show()
        
        # 뷰어 관련 위젯들 숨기기 및 초기화
        self._pdf_view_widget.hide()
        self._pdf_view_widget.set_renderer(None) # 뷰어 내부 상태 초기화
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

    def _handle_page_delete_request(self, visual_page_num: int, delete_info: dict):
        """페이지 삭제 요청을 처리하는 중앙 슬롯"""
        if not self.renderer or not (0 <= visual_page_num < len(self._page_order)):
            return

        # 1. '보이는' 순서를 '실제' 페이지 번호로 변환
        actual_page_to_delete = self._page_order[visual_page_num]

        # 2. PdfViewWidget에 실제 페이지 번호를 전달하여 삭제 실행
        self._pdf_view_widget.delete_pages([actual_page_to_delete], worker_name=self._worker_name, delete_info=delete_info)
        
        # 3. 페이지 순서 목록 업데이트
        self._page_order.pop(visual_page_num)
        # 삭제된 페이지 뒤의 페이지들의 순서 값도 갱신해야 함 (실제 파일 인덱스가 바뀌었으므로)
        for i in range(len(self._page_order)):
            if self._page_order[i] > actual_page_to_delete:
                self._page_order[i] -= 1
        
        # 4. 썸네일 뷰 갱신
        self._thumbnail_viewer.set_renderer(self.renderer)

        # 5. 뷰어 및 네비게이션 갱신
        new_total_pages = len(self._page_order)
        if new_total_pages == 0:
            self.show_load_view() # 모든 페이지 삭제 시 로드 화면으로
            return                # 로드 화면으로 전환했으므로 여기서 함수 종료
        else:
            # 삭제 후 현재 위치 또는 그 앞으로 포커스 이동
            next_visual_page = min(visual_page_num, new_total_pages - 1)
            self.go_to_page(next_visual_page)
        
        # 파일 정보 패널 업데이트
        self._info_panel.update_total_pages(new_total_pages)

    # === UI 및 레이아웃 업데이트 ===

    def set_splitter_sizes(self, is_landscape: bool):
        # 현재 UI는 QHBoxLayout 구조이므로 각 컨테이너의 고정 크기를 설정한다.
        try:
            # 썸네일 컨테이너 고정 크기 설정
            thumbnail_width = 220
            self.ui_thumbnail_container.setFixedWidth(thumbnail_width)
            
            # 정보 패널 컨테이너 고정 크기 설정
            info_width = 340 if is_landscape else 300
            self.ui_info_panel_container.setFixedWidth(info_width)
            
            # 중앙 컨테이너는 나머지 공간을 차지하도록 설정 (기본 확장 정책 유지)
            self.ui_content_container.setMinimumWidth(400)
            
        except Exception:
            # 안전 장치: 실패해도 크래시 방지
            pass

    def adjust_viewer_layout(self, is_landscape: bool):
        """페이지 비율에 따라 뷰어 레이아웃을 조정한다."""
        self.set_splitter_sizes(is_landscape)

    def _refresh_all_data(self):
        """모든 데이터를 새로고침한다 (PDF 로드 위젯과 알람 위젯)."""
        self._pdf_load_widget.refresh_data()
        if hasattr(self, '_alarm_widget'):
            self._alarm_widget.refresh_data()

    def _update_worker_label(self):
        """worker_label_2에 작업자 이름을 표시하고, 관리자 권한에 따라 버튼 가시성을 설정한다."""
        # 관리자 작업자 목록
        admin_workers = ['이경구', '이호형', '백주현']
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
            
            # 너비는 1200으로 고정, 높이는 최대화 상태의 높이 사용
            target_width = 1200
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

    def _handle_undo_request(self):
        """썸네일에서 Undo 요청이 왔을 때 PDF 뷰어의 되돌리기를 실행한다."""
        if self._pdf_view_widget and self.renderer:
            self._pdf_view_widget.undo_last_action()

    # === 유틸리티 및 헬퍼 ===

    def _collect_pending_basic_info(self) -> tuple[str, str, str]:
        """대기 중인 기본 정보를 추출하여 튜플로 반환한다."""
        info = self._pending_basic_info or {'name': "", 'region': "", 'special_note': ""}
        name = info.get('name', "")
        region = info.get('region', "")
        special_note = info.get('special_note', "")
        self._pending_basic_info = info
        return name, region, special_note

    
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

            # RN 추출
            original_path_obj = Path(self._original_filepath)
            filename_stem = original_path_obj.stem
            
            # RN을 추출하는 정규식: "RN"으로 시작하고 그 뒤에 숫자가 오는 패턴
            # 파일 이름이 "RN12345_이름_지역.pdf", "RN12345_이름_지역_1.pdf" 형식이라고 가정
            rn_match = re.match(r"(RN\d+)", filename_stem)
            if not rn_match:
                QMessageBox.warning(self, "오류", "원본 파일 경로에서 RN을 추출할 수 없습니다.")
                return
            
            rn = rn_match.group(1)
            
            # 원본 파일이 있는 디렉토리
            new_files_dir = Path(r'\\DESKTOP-KMJ\Users\HP\Desktop\greet_db\files\new')
            
            # RN을 포함하는 모든 PDF 파일 찾기 (RN123.pdf, RN123_1.pdf, RN123_2.pdf 등)
            # glob 패턴 사용: RN123*.pdf
            # re.escape를 사용하여 RN 자체에 특수문자가 있을 경우를 대비
            matching_files = sorted(
                new_files_dir.glob(f"{re.escape(rn)}*.pdf"),
                key=lambda p: (
                    p.stem,
                    # 파일명 끝에 _숫자가 붙은 경우를 위한 정렬 키
                    int(re.search(r'_(\d+)$', p.stem).group(1)) if re.search(r'_(\d+)$', p.stem) else 0
                )
            )

            if not matching_files:
                QMessageBox.warning(self, "오류", f"원본 파일(RN: {rn})을 찾을 수 없습니다.")
                return

            original_pdf_paths = [str(f) for f in matching_files]
            
            # 기존 뷰어 정리 후 원본 파일 로드
            self.show_load_view() # 현재 뷰를 닫고 로드 화면으로 전환
            self.load_document(original_pdf_paths)
            
            QMessageBox.information(self, "정보", "원본 파일을 성공적으로 불러왔습니다.")

        except Exception as e:
            QMessageBox.critical(self, "오류", f"원본 파일을 불러오는 중 오류가 발생했습니다:\n\n{str(e)}")

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
