import sys
import time
import os
from pathlib import Path

from PyQt6.QtCore import Qt, QThreadPool, QRunnable, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QMainWindow,
                             QMessageBox, QSplitter, QStackedWidget, QWidget, QFileDialog, QStatusBar,
                             QPushButton, QLabel)
from PyQt6 import uic
from qt_material import apply_stylesheet

from core.pdf_render import PdfRender
from core.pdf_saved import compress_pdf_with_multiple_stages
from widgets.pdf_load_widget import PdfLoadWidget
from widgets.pdf_view_widget import PdfViewWidget
from widgets.thumbnail_view_widget import ThumbnailViewWidget
from widgets.info_panel_widget import InfoPanelWidget
from widgets.todo_widget import ToDoWidget
from widgets.settings_dialog import SettingsDialog


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
        
        # --- 위젯 인스턴스 생성 ---
        self._thumbnail_viewer = ThumbnailViewWidget()
        self._pdf_view_widget = PdfViewWidget()
        self._pdf_load_widget = PdfLoadWidget()
        self._info_panel = InfoPanelWidget()
        self._todo_widget = ToDoWidget(self)
        self._settings_dialog = SettingsDialog(self)

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

    def _setup_menus(self):
        """메뉴바를 설정합니다."""
        pass # 메뉴바 설정 로직 추가

    def _setup_connections(self):
        """애플리케이션의 모든 시그널-슬롯 연결을 설정한다."""
        self._pdf_load_widget.pdf_selected.connect(self.load_document)
        self._thumbnail_viewer.page_selected.connect(self.go_to_page)
        self._thumbnail_viewer.page_change_requested.connect(self.change_page)
        self._thumbnail_viewer.page_order_changed.connect(self._update_page_order)
        self._pdf_view_widget.page_change_requested.connect(self.change_page)
        self._thumbnail_viewer.undo_requested.connect(self._handle_undo_request)
        self._thumbnail_viewer.page_delete_requested.connect(self._handle_page_delete_request)
        self._pdf_view_widget.page_aspect_ratio_changed.connect(self.set_splitter_sizes)
        self._pdf_view_widget.save_completed.connect(self.show_load_view) # 저장 완료 시 로드 화면으로 전환
        self._pdf_view_widget.toolbar.save_pdf_requested.connect(self._save_document)
        self._pdf_view_widget.toolbar.setting_requested.connect(self._open_settings_dialog)
        self._pdf_view_widget.page_delete_requested.connect(self._handle_page_delete_request)
        
        # 정보 패널 업데이트 연결
        self._pdf_view_widget.pdf_loaded.connect(self._info_panel.update_file_info)
        self._pdf_view_widget.page_info_updated.connect(self._info_panel.update_page_info)
        self._info_panel.text_stamp_requested.connect(self._pdf_view_widget.activate_text_stamp_mode)

        # 페이지 네비게이션 버튼 클릭 시그널 연결
        self.ui_push_button_prev.clicked.connect(lambda: self.change_page(-1))
        self.ui_push_button_next.clicked.connect(lambda: self.change_page(1))
        self.ui_push_button_reset.clicked.connect(self.show_load_view)
        
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

    def load_document_for_test(self, pdf_path: str):
        """테스트 목적으로 문서를 UI에 로드한다."""
        if isinstance(pdf_path, str):
            self.load_document([pdf_path])
        else:
            self.load_document(pdf_path)

    def _save_document_for_test(self, save_path: str):
        """테스트 목적으로 현재 문서를 저장한다. (랜덤 도장 삽입 포함)"""
        if not self.renderer or not self.renderer.get_pdf_bytes():
            return

        input_bytes = self.renderer.get_pdf_bytes()
        rotations = self._pdf_view_widget.get_page_rotations()

        # 난수 기반 도장 데이터 구성: 현재 페이지(또는 2페이지)에 1개 삽입
        stamp_data: dict[int, list[dict]] = {}
        try:
            from PyQt6.QtGui import QPixmap
            import random
            stamp_path = Path(__file__).resolve().parent.parent / "assets" / "도장1.png"
            pix = QPixmap(str(stamp_path))
            if not pix.isNull():
                # 대상 페이지: 현재 페이지 기준 (1페이지 또는 2페이지)
                target_page = self._pdf_view_widget.current_page if self._pdf_view_widget.current_page >= 0 else 0
                # 페이지 픽셀 크기 확보 (뷰 캐시 또는 동기 렌더링)
                page_pixmap = self._pdf_view_widget.page_cache.get(target_page)
                if page_pixmap is None and self.renderer and input_bytes:
                    user_rotation = rotations.get(target_page, 0)
                    page_pixmap = PdfRender.render_page_thread_safe(
                        input_bytes, target_page, zoom_factor=2.0, user_rotation=user_rotation
                    )
                if page_pixmap is None:
                    raise RuntimeError("페이지 미리보기 픽스맵을 얻지 못했습니다.")

                page_width = max(1, page_pixmap.width())
                page_height = max(1, page_pixmap.height())

                # 고정 픽셀 기준 크기(뷰 기본)와 동일하게: desired_width=110px
                desired_width_px = 110
                aspect = pix.height() / max(1, pix.width())
                desired_height_px = int(desired_width_px * aspect)

                # 비율로 변환 (저장 파이프라인은 비율을 사용)
                w_ratio = desired_width_px / page_width
                h_ratio = desired_height_px / page_height

                # 안전한 범위에서 무작위 위치
                max_x = max(0.0, 1.0 - w_ratio - 0.02)
                max_y = max(0.0, 1.0 - h_ratio - 0.02)
                x_ratio = random.uniform(0.02, max_x if max_x > 0.02 else 0.02)
                y_ratio = random.uniform(0.02, max_y if max_y > 0.02 else 0.02)
                entries = [{
                    'pixmap': pix,
                    'x_ratio': x_ratio,
                    'y_ratio': y_ratio,
                    'w_ratio': w_ratio,
                    'h_ratio': h_ratio,
                }]

                # 추가: '원본대조필' 도장도 동일 페이지에 랜덤 위치로 삽입 (고정 폭 320px)
                obc_path = Path(__file__).resolve().parent.parent / "assets" / "원본대조필.png"
                obc_pix = QPixmap(str(obc_path))
                if not obc_pix.isNull():
                    desired_width_px2 = 320
                    aspect2 = obc_pix.height() / max(1, obc_pix.width())
                    desired_height_px2 = int(desired_width_px2 * aspect2)

                    w_ratio2 = desired_width_px2 / page_width
                    h_ratio2 = desired_height_px2 / page_height

                    max_x2 = max(0.0, 1.0 - w_ratio2 - 0.02)
                    max_y2 = max(0.0, 1.0 - h_ratio2 - 0.02)
                    x_ratio2 = random.uniform(0.02, max_x2 if max_x2 > 0.02 else 0.02)
                    y_ratio2 = random.uniform(0.02, max_y2 if max_y2 > 0.02 else 0.02)

                    entries.append({
                        'pixmap': obc_pix,
                        'x_ratio': x_ratio2,
                        'y_ratio': y_ratio2,
                        'w_ratio': w_ratio2,
                        'h_ratio': h_ratio2,
                    })

                stamp_data[target_page] = entries
        except Exception:
            pass

        try:
            compress_pdf_with_multiple_stages(
                input_bytes=input_bytes,
                output_path=save_path,
                target_size_mb=3,
                rotations=rotations,
                stamp_data=stamp_data
            )
        except Exception as e:
            if not self._is_stopped:
                # 저장 중 오류가 발생하면 원본 파일명을 특정하기 어려우므로, 현재 열린 파일명을 기준으로 함
                error_filename = "Unknown"
                if self.renderer.pdf_path:
                    error_filename = Path(self.renderer.pdf_path[0]).name
                self.test_worker.signals.error.emit(error_filename, str(e))

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

        # UI가 표시된 다음 틱에 첫 페이지 렌더를 예약하여 초기 크기 기준을 보장한다.
        if self.renderer.get_page_count() > 0:
            QTimer.singleShot(0, lambda: self.go_to_page(0))

    def _save_document(self):
        """현재 상태(페이지 순서 포함)로 문서를 저장한다."""
        if self.renderer:
            print(f"저장할 페이지 순서: {self._page_order}")  # 디버그 출력
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

def create_app():
    """QApplication을 생성하고 메인 윈도우를 반환한다."""
    app = QApplication(sys.argv)
    try:
        apply_stylesheet(app, theme='dark_teal.xml')
    except Exception:
        pass
    window = MainWindow()
    return app, window
