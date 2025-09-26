import sys
import time
import os
from pathlib import Path

from PyQt6.QtCore import Qt, QThreadPool, QRunnable, pyqtSignal, QObject
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QMainWindow,
                             QMessageBox, QSplitter, QStackedWidget, QWidget, QFileDialog, QStatusBar,
                             QPushButton, QLabel)
from qt_material import apply_stylesheet

from core.pdf_render import PdfRender
from core.pdf_saved import compress_pdf_with_multiple_stages
from widgets.floating_toolbar import PdfSaveWorker
from widgets.pdf_load_widget import PdfLoadWidget
from widgets.pdf_view_widget import PdfViewWidget
from widgets.thumbnail_view_widget import ThumbnailViewWidget
from widgets.info_panel_widget import InfoPanelWidget


class BatchTestSignals(QObject):
    """PDF 일괄 테스트 Worker의 시그널 정의"""
    progress = pyqtSignal(str)
    error = pyqtSignal(str, str) # file_name, error_message
    finished = pyqtSignal()
    load_pdf = pyqtSignal(str) # UI에 PDF 로드를 요청하는 시그널
    rotate_page = pyqtSignal() # UI에 페이지 회전을 요청하는 시그널
    save_pdf = pyqtSignal()   # UI에 PDF 저장을 요청하는 시그널


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

        pdf_files = list(input_path.glob("*.pdf"))
        if not pdf_files:
            self.signals.error.emit("", f"테스트할 PDF 파일이 없습니다: {self.input_dir}")
            return
        
        self.signals.progress.emit(f"총 {len(pdf_files)}개의 PDF 파일 테스트 시작...")
        time.sleep(1)

        for pdf_file in pdf_files:
            if self._is_stopped: return

            try:
                # 1. UI에 PDF 로드 요청
                self.signals.progress.emit(f"'{pdf_file.name}' 로드 요청...")
                self.signals.load_pdf.emit(str(pdf_file))
                
                # 2. 2초 대기
                time.sleep(2)
                if self._is_stopped: return

                # 3. UI에 첫 페이지 90도 회전 요청
                self.signals.progress.emit(f"'{pdf_file.name}'의 첫 페이지를 90도 회전합니다...")
                self.signals.rotate_page.emit()
                
                # 회전 후 잠시 대기
                time.sleep(1)
                if self._is_stopped: return

                # 4. UI에 PDF 저장 요청
                self.signals.progress.emit(f"'{pdf_file.name}' 저장 요청...")
                self.signals.save_pdf.emit()
                
                # 5. 3초 대기
                time.sleep(3)

            except Exception as e:
                if not self._is_stopped:
                    self.signals.error.emit(pdf_file.name, str(e))
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
        
        # 툴바의 저장 요청 시그널 연결
        self.pdf_view_widget.toolbar.save_pdf_requested.connect(self._request_save_pdf)
        
        # 정보 패널 업데이트 연결
        self.pdf_view_widget.pdf_loaded.connect(self.info_panel.update_file_info)
        self.pdf_view_widget.page_info_updated.connect(self.info_panel.update_page_info)

        # 페이지 네비게이션 버튼 클릭 시그널 연결
        self.pushButton_prev.clicked.connect(lambda: self.change_page(-1))
        self.pushButton_next.clicked.connect(lambda: self.change_page(1))
        
        # 테스트 버튼 시그널 연결
        self.test_button.clicked.connect(self.start_batch_test)
        
        # PdfViewWidget의 내부 페이지 변경 요청 -> 실제 페이지 변경 로직 실행
        self.pdf_view_widget.page_change_requested.connect(self.change_page)

    def start_batch_test(self):
        """PDF 일괄 테스트 Worker를 시작한다."""
        self.statusBar.showMessage("PDF 일괄 테스트를 시작합니다...", 0)
        self.test_worker = PdfBatchTestWorker()
        self.test_worker.signals.progress.connect(self.statusBar.showMessage)
        self.test_worker.signals.error.connect(self._on_batch_test_error)
        self.test_worker.signals.finished.connect(self._on_batch_test_finished)
        self.test_worker.signals.load_pdf.connect(self.load_document_for_test)
        self.test_worker.signals.rotate_page.connect(self._rotate_first_page_for_test)
        self.test_worker.signals.save_pdf.connect(self._save_document_for_test)
        
        self.thread_pool.start(self.test_worker)

    def _rotate_first_page_for_test(self):
        """테스트 목적으로 첫 페이지를 90도 회전한다."""
        try:
            if self.renderer and self.renderer.get_page_count() > 0:
                
                # --- 테스트 디버그 기능 추가 ---
                # 현재 뷰어의 페이지가 첫 페이지(0)가 아니면 강제로 이동
                if self.pdf_view_widget.current_page != 0:
                    print(f"[DEBUG] 현재 페이지가 {self.pdf_view_widget.current_page + 1}이므로 첫 페이지로 이동합니다.")
                    self.go_to_page(0)

                # PdfViewWidget의 현재 페이지(첫 페이지) 회전 기능을 호출
                print(f"[DEBUG] 회전 명령: 첫 페이지({self.pdf_view_widget.current_page + 1}p)를 90도 회전합니다.")
                # 비동기 대신 동기 메소드 호출
                self.pdf_view_widget.rotate_current_page_by_90_sync()
                
        except Exception as e:
            if not self.test_worker._is_stopped and self.pdf_view_widget.get_current_pdf_path():
                filename = Path(self.pdf_view_widget.get_current_pdf_path()).name
                self.test_worker.signals.error.emit(filename, f"페이지 회전 중 오류: {e}")

    def load_document_for_test(self, pdf_path: str):
        """테스트 목적으로 문서를 UI에 로드한다."""
        self.load_document(pdf_path)

    def _save_document_for_test(self):
        """테스트 목적으로 현재 문서를 저장한다."""
        if not self.pdf_view_widget.get_current_pdf_path():
            # 이 경우는 거의 없지만, 방어 코드
            return

        input_path = self.pdf_view_widget.get_current_pdf_path()
        output_dir = Path(r'C:\Users\HP\Desktop\files\결과')
        output_file = output_dir / f"{Path(input_path).stem}_tested.pdf"

        # 기존 저장 로직과 유사하게 실행
        rotations = self.pdf_view_widget.get_page_rotations()
        force_resize_pages = self.pdf_view_widget.get_force_resize_pages()

        # 저장은 백그라운드에서 실행되지만, 여기서는 테스트의 일부로 직접 호출
        # 실제 저장 워커를 또 만들면 복잡해지므로, compress 함수를 직접 호출
        try:
            compress_pdf_with_multiple_stages(
                input_path=input_path,
                output_path=str(output_file),
                target_size_mb=3,
                rotations=rotations,
                force_resize_pages=force_resize_pages
            )
        except Exception as e:
            # 테스트 워커에 오류 전파
            if not self.test_worker._is_stopped:
                self.test_worker.signals.error.emit(Path(input_path).name, str(e))


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

    def _request_save_pdf(self):
        """PDF 저장 요청을 처리하고 파일 대화상자를 연다."""
        if not self.pdf_view_widget.get_current_pdf_path():
            self.statusBar.showMessage("저장할 PDF 파일이 열려있지 않습니다.", 5000)
            return
        
        self._start_save_process(self.pdf_view_widget.get_current_pdf_path())

    def _start_save_process(self, input_path: str):
        """실제 PDF 저장 프로세스를 시작한다."""
        # 파일 저장 경로 얻기
        default_filename = Path(input_path).stem + "_edited.pdf"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "PDF 저장",
            default_filename,
            "PDF Files (*.pdf)"
        )

        if not save_path:
            self.statusBar.showMessage("저장이 취소되었습니다.", 3000)
            return

        self.statusBar.showMessage(f"'{Path(save_path).name}' 파일 저장 중...", 0)
        
        # 페이지별 회전 정보 가져오기
        rotations = self.pdf_view_widget.get_page_rotations()
        # 페이지별 강제 크기 조정 정보 가져오기
        force_resize_pages = self.pdf_view_widget.get_force_resize_pages()

        # 백그라운드에서 압축 및 저장 실행
        worker = PdfSaveWorker(input_path, save_path, rotations, force_resize_pages)
        worker.signals.finished.connect(self._on_save_finished)
        worker.signals.error.connect(lambda msg: self.statusBar.showMessage(f"저장 오류: {msg}", 5000))
        self.thread_pool.start(worker)

    def _on_save_finished(self, path, success):
        self.statusBar.clearMessage()
        """저장 완료 시 호출될 슬롯"""
        if success:
            message = f"성공적으로 '{Path(path).name}'에 압축 저장되었습니다."
        else:
            message = f"'{Path(path).name}'에 원본 파일을 저장했습니다 (압축 실패)."
        
        self.statusBar.showMessage(message, 8000)
        QMessageBox.information(self, "저장 완료", message)

        # 저장 완료 후 초기 로드 화면으로 전환
        self.show_load_view()

    def _on_save_error(self, error_msg: str):
        """저장 중 오류 발생 시 호출될 슬롯"""
        self.statusBar.showMessage(f"오류 발생: {error_msg}", 8000)
        QMessageBox.critical(self, "저장 오류", f"PDF 저장 중 오류가 발생했습니다:\n{error_msg}")

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
