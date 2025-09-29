import sys
import time
import os
from pathlib import Path

from PyQt6.QtCore import Qt, QThreadPool, QRunnable, pyqtSignal, QObject
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QMainWindow,
                             QMessageBox, QSplitter, QStackedWidget, QWidget, QFileDialog, QStatusBar,
                             QPushButton, QLabel)
from qt_material import apply_stylesheet

from core.pdf_render import PdfRender
from core.pdf_saved import compress_pdf_with_multiple_stages
from widgets.pdf_load_widget import PdfLoadWidget
from widgets.pdf_view_widget import PdfViewWidget
from widgets.thumbnail_view_widget import ThumbnailViewWidget
from widgets.info_panel_widget import InfoPanelWidget
from widgets.todo_widget import ToDoWidget


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
        self.setWindowTitle("PDF Viewer")
        self.setGeometry(100, 100, 1200, 800)

        self.renderer: PdfRender | None = None
        self.current_page = -1
        self.thread_pool = QThreadPool()
        
        # --- 위젯 인스턴스 생성 ---
        self.thumbnail_viewer = ThumbnailViewWidget()
        self.pdf_view_widget = PdfViewWidget()
        self.pdf_load_widget = PdfLoadWidget()
        self.info_panel = InfoPanelWidget()
        self.todo_widget = ToDoWidget(self)

        # --- 메인 레이아웃 설정 ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.pdf_load_widget)
        self.main_splitter.addWidget(self.pdf_view_widget)
        
        self.main_splitter.setSizes([600, 600])

        main_layout.addWidget(self.thumbnail_viewer, 1)
        main_layout.addWidget(self.main_splitter, 4)
        main_layout.addWidget(self.info_panel, 1)
        
        # --- 초기 위젯 상태 설정 ---
        self.pdf_view_widget.hide()
        self.thumbnail_viewer.hide()
        self.info_panel.hide()
        self.todo_widget.hide()

        # --- 메뉴바 및 액션 설정 ---
        self._setup_menus()

        # --- 상태바 및 페이지 네비게이션 UI 설정 ---
        self.statusBar = QStatusBar(self)
        self.setStatusBar(self.statusBar)
        
        nav_widget = QWidget()
        nav_layout = QHBoxLayout(nav_widget)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        
        self.test_button = QPushButton("테스트")
        self.pushButton_prev = QPushButton("이전")
        self.pushButton_next = QPushButton("다음")
        self.label_page_nav = QLabel("N/A")
        
        nav_layout.addWidget(self.test_button)
        nav_layout.addWidget(self.pushButton_prev)
        nav_layout.addWidget(self.label_page_nav)
        nav_layout.addWidget(self.pushButton_next)
        
        self.statusBar.addPermanentWidget(nav_widget)

        # --- 시그널 연결 ---
        self._setup_connections()

    def _setup_menus(self):
        """메뉴바를 설정합니다."""
        pass # 메뉴바 설정 로직 추가

    def _setup_connections(self):
        """애플리케이션의 모든 시그널-슬롯 연결을 설정한다."""
        self.pdf_load_widget.pdf_selected.connect(self.load_document)
        self.thumbnail_viewer.page_selected.connect(self.go_to_page)
        self.thumbnail_viewer.page_change_requested.connect(self.change_page)
        self.pdf_view_widget.page_change_requested.connect(self.change_page)
        self.pdf_view_widget.page_aspect_ratio_changed.connect(self.set_splitter_sizes)
        self.pdf_view_widget.save_completed.connect(self.show_load_view) # 저장 완료 시 로드 화면으로 전환
        
        # 정보 패널 업데이트 연결
        self.pdf_view_widget.pdf_loaded.connect(self.info_panel.update_file_info)
        self.pdf_view_widget.page_info_updated.connect(self.info_panel.update_page_info)

        # 페이지 네비게이션 버튼 클릭 시그널 연결
        self.pushButton_prev.clicked.connect(lambda: self.change_page(-1))
        self.pushButton_next.clicked.connect(lambda: self.change_page(1))
        
        # 테스트 버튼 시그널 연결
        self.test_button.clicked.connect(self.start_batch_test)
        
        # --- 전역 단축키 설정 ---
        toggle_todo_action = QAction(self)
        toggle_todo_action.setShortcut(Qt.Key.Key_QuoteLeft) # '~' 키
        toggle_todo_action.triggered.connect(self.todo_widget.toggle_overlay)
        self.addAction(toggle_todo_action)
        
    def start_batch_test(self):
        """PDF 일괄 테스트 Worker를 시작한다."""
        self.statusBar.showMessage("PDF 일괄 테스트를 시작합니다...", 0)
        self.test_worker = PdfBatchTestWorker()
        self.test_worker.signals.progress.connect(self.statusBar.showMessage)
        self.test_worker.signals.error.connect(self._on_batch_test_error)
        self.test_worker.signals.finished.connect(self._on_batch_test_finished)
        self.test_worker.signals.load_pdf.connect(self.load_document_for_test)
        self.test_worker.signals.rotate_90_maybe.connect(self._rotate_90_maybe_for_test)
        self.test_worker.signals.focus_page2_maybe.connect(self._focus_page2_maybe_for_test)
        self.test_worker.signals.save_pdf.connect(self._save_document_for_test)
        
        self.thread_pool.start(self.test_worker)

    def _rotate_90_maybe_for_test(self):
        """10% 확률로 현재 페이지를 90도 회전(첫 페이지 기준)"""
        try:
            import random
            if self.renderer and self.renderer.get_page_count() > 0:
                if self.pdf_view_widget.current_page != 0:
                    self.go_to_page(0)
                if random.random() < 0.10:
                    self.pdf_view_widget.rotate_current_page_by_90_sync()
        except Exception as e:
            if not self.test_worker._is_stopped and self.pdf_view_widget.get_current_pdf_path():
                filename = Path(self.pdf_view_widget.get_current_pdf_path()).name
                self.test_worker.signals.error.emit(filename, f"회전 처리 중 오류: {e}")

    def _focus_page2_maybe_for_test(self):
        """50% 확률로 2페이지로 포커스를 이동 (존재 시)"""
        try:
            import random
            if self.renderer and self.renderer.get_page_count() >= 2:
                if random.random() < 0.50:
                    self.go_to_page(1)
        except Exception as e:
            if not self.test_worker._is_stopped and self.pdf_view_widget.get_current_pdf_path():
                filename = Path(self.pdf_view_widget.get_current_pdf_path()).name
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
        rotations = self.pdf_view_widget.get_page_rotations()
        force_resize_pages = self.pdf_view_widget.get_force_resize_pages()

        # 난수 기반 도장 데이터 구성: 현재 페이지(또는 2페이지)에 1개 삽입
        stamp_data: dict[int, list[dict]] = {}
        try:
            from PyQt6.QtGui import QPixmap
            import random
            stamp_path = Path(__file__).resolve().parent.parent / "assets" / "도장1.png"
            pix = QPixmap(str(stamp_path))
            if not pix.isNull():
                # 대상 페이지: 현재 페이지 기준 (1페이지 또는 2페이지)
                target_page = self.pdf_view_widget.current_page if self.pdf_view_widget.current_page >= 0 else 0
                # 페이지 픽셀 크기 확보 (뷰 캐시 또는 동기 렌더링)
                page_pixmap = self.pdf_view_widget.page_cache.get(target_page)
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
                stamp_data[target_page] = [{
                    'pixmap': pix,
                    'x_ratio': x_ratio,
                    'y_ratio': y_ratio,
                    'w_ratio': w_ratio,
                    'h_ratio': h_ratio,
                }]
        except Exception:
            pass

        try:
            compress_pdf_with_multiple_stages(
                input_bytes=input_bytes,
                output_path=save_path,
                target_size_mb=3,
                rotations=rotations,
                force_resize_pages=force_resize_pages,
                stamp_data=stamp_data
            )
        except Exception as e:
            if not self._is_stopped:
                # 저장 중 오류가 발생하면 원본 파일명을 특정하기 어려우므로, 현재 열린 파일명을 기준으로 함
                error_filename = "Unknown"
                if self.renderer.pdf_path:
                    error_filename = Path(self.renderer.pdf_path[0]).name
                self.test_worker.signals.error.emit(error_filename, str(e))


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
        
        self.statusBar.showMessage(f"오류로 테스트가 중단되었습니다: {error_msg}", 10000)
        QMessageBox.critical(self, title, message)

    def _on_batch_test_finished(self):
        """일괄 테스트 완료 시 호출될 슬롯"""
        self.statusBar.showMessage("모든 PDF 파일 테스트를 성공적으로 완료했습니다.", 8000)
        QMessageBox.information(self, "테스트 완료", "지정된 모든 PDF 파일의 열기/저장 테스트를 성공적으로 완료했습니다.")

    def adjust_viewer_layout(self, is_landscape: bool):
        """페이지 비율에 따라 뷰어 레이아웃을 조정한다."""
        self.set_splitter_sizes(is_landscape)

    def set_splitter_sizes(self, is_landscape: bool):
        """가로/세로 모드에 따라 QSplitter의 크기를 설정한다."""
        if is_landscape:
            # 가로 페이지: 뷰어 85%, 썸네일 15%
            self.main_splitter.setSizes([int(self.width() * 0.15), int(self.width() * 0.85)])
        else:
            # 세로 페이지: 뷰어 75%, 썸네일 25% (기존과 유사)
            self.main_splitter.setSizes([int(self.width() * 0.25), int(self.width() * 0.75)])
    
    def _update_page_navigation(self, current_page: int, total_pages: int):
        """페이지 네비게이션 상태(라벨, 버튼 활성화)를 업데이트한다."""
        if total_pages > 0:
            self.label_page_nav.setText(f"{current_page + 1} / {total_pages}")
        else:
            self.label_page_nav.setText("N/A")

        self.pushButton_prev.setEnabled(total_pages > 0 and current_page > 0)
        self.pushButton_next.setEnabled(total_pages > 0 and current_page < total_pages - 1)

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

        # 첫 번째 파일 이름을 기준으로 창 제목 설정
        self.setWindowTitle(f"PDF Viewer - {Path(pdf_paths[0]).name}")
        
        self.thumbnail_viewer.set_renderer(self.renderer)
        self.pdf_view_widget.set_renderer(self.renderer)

        if self.renderer.get_page_count() > 0:
            self.go_to_page(0)

        self.pdf_load_widget.hide()
        self.pdf_view_widget.show()
        self.thumbnail_viewer.show()
        self.info_panel.show()
        
    def show_load_view(self):
        """PDF 뷰어를 닫고 초기 로드 화면으로 전환하며 모든 관련 리소스를 정리한다."""
        self.setWindowTitle("PDF Viewer")
        if self.renderer:
            self.renderer.close()
        
        self.renderer = None
        self.current_page = -1

        self.pdf_load_widget.show()
        
        # 뷰어 관련 위젯들 숨기기 및 초기화
        self.pdf_view_widget.hide()
        self.pdf_view_widget.set_renderer(None) # 뷰어 내부 상태 초기화
        self.thumbnail_viewer.hide()
        self.thumbnail_viewer.clear_thumbnails()
        self.info_panel.hide()
        self.info_panel.clear_info()

        self._update_page_navigation(0, 0)

    def go_to_page(self, page_num: int):
        """지정된 페이지 번호로 뷰를 이동시킨다."""
        if self.renderer and 0 <= page_num < self.renderer.get_page_count():
            self.current_page = page_num
            self.pdf_view_widget.show_page(page_num)
            self.thumbnail_viewer.set_current_page(page_num)
            self._update_page_navigation(self.current_page, self.renderer.get_page_count())
    
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
