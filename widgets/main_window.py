import sys
import time
import os
from pathlib import Path

from PyQt6.QtCore import Qt, QThreadPool, QRunnable, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QMainWindow,
                             QMessageBox, QSplitter, QStackedWidget, QWidget, QFileDialog, QStatusBar,
                             QPushButton, QLabel, QDialog)
from PyQt6 import uic
from qt_material import apply_stylesheet

from core.pdf_render import PdfRender
from core.pdf_saved import compress_pdf_with_multiple_stages
from core.sql_manager import claim_subsidy_work
from widgets.pdf_load_widget import PdfLoadWidget
from widgets.pdf_view_widget import PdfViewWidget
from widgets.thumbnail_view_widget import ThumbnailViewWidget
from widgets.info_panel_widget import InfoPanelWidget
from widgets.todo_widget import ToDoWidget
from widgets.settings_dialog import SettingsDialog
from widgets.login_dialog import LoginDialog
from widgets.mail_dialog import MailDialog


class BatchTestSignals(QObject):
    """PDF 일괄 테스트 Worker의 시그널 정의"""
    progress = pyqtSignal(str)
    error = pyqtSignal(str, str) # file_name, error_message
    finished = pyqtSignal()
    load_pdf = pyqtSignal(str) # UI에 PDF 로드를 요청하는 시그널
    # 도장 삽입 시나리오용 신호
    rotate_90_maybe = pyqtSignal()  # 10% 확률 회전은 슬롯에서 판단
    focus_page2_maybe = pyqtSignal()  # 50% 확률 2페이지 포커스는 슬롯에서 판단
    save_pdf = pyqtSignal(str)   # UI에 PDF 저장을 요청하는 시그널 (저장 경로 전달)

class PdfBatchTestWorker(QRunnable):
    """PDF 일괄 열기/저장 테스트를 수행하는 Worker"""
    def __init__(self):
        super().__init__()
        self.signals = BatchTestSignals()
        self.input_dir = r'C:\Users\HP\Desktop\files\테스트PDF'
        self.output_dir = r'C:\Users\HP\Desktop\files\결과'
        self._is_stopped = False

    def stop(self):
        """Worker를 중지시킨다."""
        self._is_stopped = True

    def run(self):
        input_path = Path(self.input_dir)
        output_path = Path(self.output_dir)

        if not input_path.is_dir():
            self.signals.error.emit("", f"입력 폴더를 찾을 수 없습니다: {self.input_dir}")
            return

        if not output_path.exists():
            try:
                output_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self.signals.error.emit("", f"출력 폴더를 생성하는 데 실패했습니다: {e}")
                return

        pdf_files = sorted(list(input_path.glob("*.pdf")))
        if not pdf_files:
            self.signals.error.emit("", f"테스트할 PDF 파일이 없습니다: {self.input_dir}")
            return
        
        # 파일 경로를 (원본, 저장될 경로) 튜플로 관리
        file_paths_to_process = [
            (str(p), str(output_path / f"{p.stem}_tested.pdf")) for p in pdf_files
        ]

        self.signals.progress.emit(f"총 {len(file_paths_to_process)}개의 PDF 파일 테스트 시작...")
        time.sleep(1)

        for input_file, output_file in file_paths_to_process:
            if self._is_stopped: return

            try:
                # 1. UI에 PDF 로드 요청
                self.signals.progress.emit(f"'{Path(input_file).name}' 로드 중...")
                self.signals.load_pdf.emit(input_file)
                
                # 2. 2초 대기
                time.sleep(2)
                if self._is_stopped: return

                # 3. 10% 확률 회전 요청 (실제 확률 판단은 슬롯에서 수행)
                self.signals.progress.emit("10% 확률로 첫 페이지 90도 회전 시도")
                self.signals.rotate_90_maybe.emit()
                time.sleep(2)
                if self._is_stopped: return

                # 4. 50% 확률로 2페이지 포커스 이동 (없으면 유지)
                self.signals.progress.emit("50% 확률로 2페이지 포커스 이동 시도")
                self.signals.focus_page2_maybe.emit()
                time.sleep(1)
                if self._is_stopped: return

                # 5. UI에 PDF 저장 요청 (저장 경로 전달)
                self.signals.progress.emit(f"'{Path(output_file).name}' 저장 요청...")
                self.signals.save_pdf.emit(output_file)
                
                # 6. 3초 대기
                time.sleep(3)

            except Exception as e:
                if not self._is_stopped:
                    self.signals.error.emit(Path(input_file).name, str(e))
                return # 오류 발생 시 즉시 중단
        
        if not self._is_stopped:
            self.signals.finished.emit()

class MainWindow(QMainWindow):
    """메인 윈도우"""
    
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
        
        # --- 위젯 인스턴스 생성 ---
        self._thumbnail_viewer = ThumbnailViewWidget()
        self._pdf_view_widget = PdfViewWidget()
        self._pdf_load_widget = PdfLoadWidget()
        self._info_panel = InfoPanelWidget()
        self._todo_widget = ToDoWidget(self)
        self._settings_dialog = SettingsDialog(self)
        self._mail_dialog = MailDialog(self)
        self._pending_basic_info: dict | None = None

        # --- 페이지 순서 관리 ---
        self._page_order: list[int] = []

        # --- UI 컨테이너에 위젯 배치 ---
        self._setup_ui_containers()
        
        # --- 초기 위젯 상태 설정 ---
        self._pdf_view_widget.hide()
        self._thumbnail_viewer.hide()
        self._info_panel.hide()
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
        self._worker_name = ""  # 작업자 이름 저장용
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
        
        # 정보 패널 컨테이너에 배치
        info_panel_layout = QHBoxLayout(self.ui_info_panel_container)
        info_panel_layout.setContentsMargins(0, 0, 0, 0)
        info_panel_layout.setSpacing(0)
        info_panel_layout.addWidget(self._info_panel)
        
        # 스플리터 크기 설정
        # self.ui_main_splitter.setSizes([600, 600])

        # QHBoxLayout 구조에서는 각 컨테이너의 사이즈 정책으로 제어
        # UI 파일에서 horstretch 값으로 기본 비율이 설정되어 있음

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

    def _open_settings_dialog(self):
        """설정 다이얼로그를 연다."""
        if self._settings_dialog.exec():
            # 사용자가 OK를 누르면 변경된 단축키를 다시 적용
            self._apply_shortcuts()
    
    def _open_mail_dialog(self):
        """메일 다이얼로그를 연다."""
        # 현재 작업 중인 RN 값이 있다면 미리 설정
        if self._pending_basic_info:
            # 여기에 RN 값을 설정하는 로직을 추가할 수 있음
            pass
        
        if self._mail_dialog.exec():
            rn_value = self._mail_dialog.get_rn_value()
            content = self._mail_dialog.get_content()
            print(f"메일 전송 요청 - RN: {rn_value}, 내용: {content}")
            # TODO: 실제 메일 전송 로직 구현

    def _setup_menus(self):
        """메뉴바를 설정합니다."""
        pass # 메뉴바 설정 로직 추가

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
        
        # --- 전역 단축키 설정 ---
        # _setup_global_shortcuts() 메서드에서 처리하므로 기존 코드는 제거
        # toggle_todo_action = QAction(self)
        # toggle_todo_action.setShortcut(Qt.Key.Key_QuoteLeft) # '~' 키
        # toggle_todo_action.triggered.connect(self.todo_widget.toggle_overlay)
        # self.addAction(toggle_todo_action)

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

    def _handle_page_delete_request(self, visual_page_num: int):
        """페이지 삭제 요청을 처리하는 중앙 슬롯"""
        if not self.renderer or not (0 <= visual_page_num < len(self._page_order)):
            return

        # 1. '보이는' 순서를 '실제' 페이지 번호로 변환
        actual_page_to_delete = self._page_order[visual_page_num]

        # 2. PdfViewWidget에 실제 페이지 번호를 전달하여 삭제 실행
        self._pdf_view_widget.delete_pages([actual_page_to_delete])
        
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

    def _handle_save_completed(self):
        """PDF 저장이 완료되었을 때 호출된다."""
        if hasattr(self, '_auto_return_to_main_after_save') and self._auto_return_to_main_after_save:
            self._auto_return_to_main_after_save = False
            self.show_load_view()
            # 메인화면으로 돌아갈 때 데이터 새로고침
            self._pdf_load_widget.refresh_data()

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
            self._pdf_load_widget.refresh_data()
        elif clicked_button == save_button:
            self._save_document()
            # 저장 후 메인화면으로 돌아갈 때도 데이터 새로고침
            self._pdf_load_widget.refresh_data()
        # 취소 버튼을 누르면 아무것도 하지 않고 대화상자만 닫힘

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

    def adjust_viewer_layout(self, is_landscape: bool):
        """페이지 비율에 따라 뷰어 레이아웃을 조정한다."""
        self.set_splitter_sizes(is_landscape)

    def _handle_undo_request(self):
        """썸네일에서 Undo 요청이 왔을 때 PDF 뷰어의 되돌리기를 실행한다."""
        if self._pdf_view_widget and self.renderer:
            self._pdf_view_widget.undo_last_action()

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
    
    def load_document(self, pdf_paths: list):
        """PDF 및 이미지 문서를 로드하고 뷰를 전환한다."""
        if not pdf_paths:
            return

        if self.renderer:
            self.renderer.close()

        try:
            self.renderer = PdfRender()
            self.renderer.load_pdf(pdf_paths) # 경로 리스트를 전달
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
        self._info_panel.show()

        # 기본 스플리터 사이즈를 즉시 한 번 강제하여 초기 힌트를 통일
        self.set_splitter_sizes(False)

        name, region, special_note = self._collect_pending_basic_info()
        self._info_panel.update_basic_info(name, region, special_note)

        # UI가 표시된 다음 틱에 첫 페이지 렌더를 예약하여 초기 크기 기준을 보장한다.
        if self.renderer.get_page_count() > 0:
            QTimer.singleShot(0, lambda: self.go_to_page(0))

    def _save_document(self):
        """현재 상태(페이지 순서 포함)로 문서를 저장한다."""
        if self.renderer:
            print(f"저장할 페이지 순서: {self._page_order}")  # 디버그 출력
            # 저장 완료 후 자동으로 메인화면으로 돌아가도록 플래그 설정
            self._auto_return_to_main_after_save = True
            self._pdf_view_widget.save_pdf(page_order=self._page_order)
        
    def show_load_view(self):
        """PDF 뷰어를 닫고 초기 로드 화면으로 전환하며 모든 관련 리소스를 정리한다."""
        self.setWindowTitle("PDF Viewer")
        if self.renderer:
            self.renderer.close()
        
        self.renderer = None
        self.current_page = -1

        self._pdf_load_widget.show()
        
        # 뷰어 관련 위젯들 숨기기 및 초기화
        self._pdf_view_widget.hide()
        self._pdf_view_widget.set_renderer(None) # 뷰어 내부 상태 초기화
        self._thumbnail_viewer.hide()
        self._thumbnail_viewer.clear_thumbnails()
        self._info_panel.hide()
        self._info_panel.clear_info()

        self._update_page_navigation()

    def _handle_pdf_selected(self, pdf_paths: list):
        self._pending_basic_info = None
        self._info_panel.update_basic_info("", "", "")
        self.load_document(pdf_paths)

    def _handle_work_started(self, pdf_paths: list, metadata: dict):
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
            self._pending_basic_info = self._normalize_basic_info(metadata)
            self.load_document(pdf_paths)
            return

        worker_name = self._worker_name or metadata.get('worker', '')
        rn_value = metadata.get('rn')

        if not worker_name or not rn_value:
            self._pending_basic_info = self._normalize_basic_info(metadata)
            self.load_document(pdf_paths)
            return

        if not claim_subsidy_work(rn_value, worker_name):
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle("이미 작업 중")
            msg_box.setText("해당 신청 건은 다른 작업자가 진행 중입니다.")
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            
            # 메시지박스가 닫힐 때 자동으로 데이터 새로고침 실행
            msg_box.finished.connect(self._pdf_load_widget.refresh_data)
            msg_box.exec()
            return

        self._pending_basic_info = self._normalize_basic_info(metadata)
        self.load_document(pdf_paths)
        
        # PDF 로드 후 메일 content 표시
        if mail_content:
            self._pdf_view_widget.set_mail_content(mail_content)

    @staticmethod
    def _normalize_basic_info(metadata: dict | None) -> dict:
        if not metadata:
            return {'name': "", 'region': "", 'special_note': ""}

        def _coerce(value):
            if value is None:
                return ""
            return str(value).strip()

        return {
            'name': _coerce(metadata.get('name')),
            'region': _coerce(metadata.get('region')),
            'special_note': _coerce(metadata.get('special_note')),
        }

    def _collect_pending_basic_info(self) -> tuple[str, str, str]:
        info = self._pending_basic_info or {'name': "", 'region': "", 'special_note': ""}
        name = info.get('name', "")
        region = info.get('region', "")
        special_note = info.get('special_note', "")
        self._pending_basic_info = info
        return name, region, special_note

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

    def closeEvent(self, event):
        """애플리케이션 종료 시 PDF 문서 자원을 해제한다."""
        if self.renderer:
            self.renderer.close()
        event.accept()

    def _show_login_dialog(self):
        """로그인 다이얼로그를 표시하고 작업자 이름을 설정한다."""
        if self._login_dialog.exec() == QDialog.DialogCode.Accepted:
            self._worker_name = self._login_dialog.get_worker_name()
            self._update_worker_label()
        else:
            # 취소 시 앱 종료
            self.close()

    def _update_worker_label(self):
        """worker_label_2에 작업자 이름을 표시한다."""
        if hasattr(self, 'ui_worker_label_2') and self._worker_name:
            self.ui_worker_label_2.setText(f"작업자: {self._worker_name}")
        elif hasattr(self, 'ui_worker_label_2'):
            self.ui_worker_label_2.setText("작업자: 미로그인")

def create_app():
    """QApplication을 생성하고 메인 윈도우를 반환한다."""
    app = QApplication(sys.argv)
    try:
        apply_stylesheet(app, theme='dark_teal.xml')
    except Exception:
        pass
    window = MainWindow()
    return app, window
