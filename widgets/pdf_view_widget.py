from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import (QObject, QRunnable, Qt, QThreadPool, pyqtSignal)
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (QApplication, QFileDialog, QGraphicsPixmapItem,
                                 QGraphicsScene, QGraphicsView, QMessageBox,
                                 QWidget)

import pymupdf
from core.edit_mixin import ViewModeMixin
from core.insert_utils import add_stamp_item
from core.pdf_render import PdfRender
from core.pdf_saved import compress_pdf_with_multiple_stages
from .crop_dialog import CropDialog
from .floating_toolbar import FloatingToolbarWidget
from .stamp_overlay_widget import StampOverlayWidget
from .zoomable_graphics_view import ZoomableGraphicsView


# --- 백그라운드 Worker 정의 ---

class WorkerSignals(QObject):
    """
    Worker 스레드에서 발생할 수 있는 시그널 정의
    - finished: 렌더링 완료 시 (페이지 번호, 렌더링된 QPixmap)
    - error: 렌더링 오류 시 (페이지 번호, 에러 메시지)
    - save_finished: 저장 완료 시 (경로, 성공 여부)
    - save_error: 저장 오류 시 (에러 메시지)
    """
    finished = pyqtSignal(int, QPixmap)
    error = pyqtSignal(int, str)
    save_finished = pyqtSignal(str, bool)
    save_error = pyqtSignal(str)


class PdfRenderWorker(QRunnable):
    """단일 PDF 페이지를 렌더링하는 Worker 스레드"""

    def __init__(self, pdf_bytes: bytes, page_num: int, zoom_factor: float = 2.0, user_rotation: int = 0):
        super().__init__()
        self.pdf_bytes = pdf_bytes
        self.page_num = page_num
        self.zoom_factor = zoom_factor
        self.user_rotation = user_rotation
        self.signals = WorkerSignals()

    @staticmethod
    def _is_a4_size(width_cm: float, height_cm: float, tolerance: float = 2.0) -> bool:
        """페이지가 A4 크기 범위 내인지 확인한다."""
        a4_width, a4_height = 21.0, 29.7
        vertical_match = (abs(width_cm - a4_width) <= tolerance and
                         abs(height_cm - a4_height) <= tolerance)
        horizontal_match = (abs(width_cm - a4_height) <= tolerance and
                           abs(height_cm - a4_width) <= tolerance)
        return vertical_match or horizontal_match

    def run(self):
        """백그라운드 스레드에서 렌더링 실행. 핵심 로직은 PdfRender 클래스에 위임."""
        try:
            # PdfRender의 스레드 안전 메서드를 호출 (A4 변환된 바이트 데이터 사용)
            pixmap = PdfRender.render_page_thread_safe(
                self.pdf_bytes, self.page_num, self.zoom_factor, self.user_rotation
            )
            self.signals.finished.emit(self.page_num, pixmap)

        except Exception as e:
            self.signals.error.emit(self.page_num, str(e))


class PdfSaveWorker(QRunnable):
    """QThreadPool에서 PDF 압축 및 저장을 실행하기 위한 Worker"""

    def __init__(self, input_bytes: bytes, output_path: str,
                 rotations: dict | None = None,
                 force_resize_pages: set | None = None,
                 stamp_data: dict[int, list[dict]] | None = None):
        super().__init__()
        self.signals = WorkerSignals()
        self.input_bytes = input_bytes
        self.output_path = output_path
        self.rotations = rotations if rotations is not None else {}
        self.force_resize_pages = force_resize_pages if force_resize_pages is not None else set()
        self.stamp_data = stamp_data if stamp_data is not None else {}

    def run(self):
        """백그라운드 스레드에서 PDF 저장 및 압축 실행."""
        try:
            success = compress_pdf_with_multiple_stages(
                input_bytes=self.input_bytes,
                output_path=self.output_path,
                target_size_mb=3,
                rotations=self.rotations,
                force_resize_pages=self.force_resize_pages,
                stamp_data=self.stamp_data
            )
            self.signals.save_finished.emit(self.output_path, success)
        except Exception as e:
            self.signals.save_error.emit(str(e))


class PdfViewWidget(QWidget, ViewModeMixin):
    """PDF 뷰어 위젯"""
    page_change_requested = pyqtSignal(int)
    page_aspect_ratio_changed = pyqtSignal(bool)  # is_landscape: 가로가 긴 페이지 여부
    save_completed = pyqtSignal()  # 저장 완료 후 화면 전환을 위한 신호

    # --- 정보 패널 연동을 위한 신호 ---
    pdf_loaded = pyqtSignal(str, float, int)  # file_path, file_size_mb, total_pages
    page_info_updated = pyqtSignal(int, float, float, int)  # page_num, width, height, rotation

    def __init__(self):
        super().__init__()
        self.renderer: PdfRender | None = None
        self.pdf_path: str | None = None
        self.scene = QGraphicsScene(self)
        self.current_page_item: QGraphicsPixmapItem | None = None

        # --- 페이지 별 오버레이 아이템 "데이터" 관리 ---
        self._overlay_items: dict[int, list[dict]] = {}
        
        # --- 오버레이 위젯 ---
        self.stamp_overlay = None

        # --- 스탬프 모드 ---
        self._is_stamp_mode = False
        self._stamp_pixmap: QPixmap | None = None
        self._stamp_desired_width: int = 110

        # --- 비동기 처리 및 캐싱 설정 ---
        self.thread_pool = QThreadPool.globalInstance()
        self.page_cache = {}  # 페이지 캐시: {page_num: QPixmap}
        self.rendering_jobs = set()  # 현재 렌더링 중인 페이지 번호
        self.current_page = -1
        self.page_rotations = {}  # 페이지별 사용자 회전 각도 저장 {page_num: rotation}
        self.force_resize_pages = set() # 사용자가 수동으로 크기 조정을 요청한 페이지 번호

        self.init_ui()

        # --- 툴바 추가 ---
        self.toolbar = FloatingToolbarWidget(self)
        self.toolbar.show()

        # --- 스탬프 오버레이 추가 ---
        self.stamp_overlay = StampOverlayWidget(self)

        # --- 툴바 시그널 연결 ---
        self.toolbar.resize_page_requested.connect(self._toggle_force_resize)
        self.toolbar.stamp_menu_requested.connect(self._toggle_stamp_overlay)
        self.toolbar.fit_to_width_requested.connect(self.set_fit_to_width)
        self.toolbar.fit_to_page_requested.connect(self.set_fit_to_page)
        self.toolbar.rotate_90_requested.connect(self._rotate_current_page)
        self.toolbar.crop_requested.connect(self._open_crop_dialog) # 자르기 신호 연결
        self.toolbar.save_pdf_requested.connect(self.save_pdf) # 저장 신호 연결

        # --- 스탬프 오버레이 시그널 연결 ---
        self.stamp_overlay.stamp_selected.connect(self._activate_stamp_mode)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _activate_stamp_mode(self, stamp_info: dict): # 변경: image_path: str -> stamp_info: dict
        """스탬프 오버레이에서 도장이 선택되면 호출된다."""
        try:
            image_path = stamp_info['path']
            desired_width = stamp_info['width']

            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                raise FileNotFoundError(f"이미지 파일을 로드할 수 없습니다: {image_path}")

            self._stamp_pixmap = pixmap
            self._stamp_desired_width = desired_width # 전달받은 너비 저장
            self._is_stamp_mode = True
            self.setCursor(Qt.CursorShape.CrossCursor)
            print(f"스탬프 모드 활성화: {image_path}, 너비: {desired_width}px")

        except FileNotFoundError as e:
            QMessageBox.warning(self, "오류", str(e))
            self._deactivate_stamp_mode()
        except Exception as e:
            QMessageBox.warning(self, "오류", f"도장 이미지를 처리하는 중 오류가 발생했습니다: {e}")
            self._deactivate_stamp_mode()

    def _deactivate_stamp_mode(self):
        """스탬프 모드를 비활성화한다."""
        self._is_stamp_mode = False
        self._stamp_pixmap = None
        self.unsetCursor()
        print("스탬프 모드 비활성화")

    def _open_crop_dialog(self):
        """자르기 다이얼로그를 연다."""
        if self.current_page < 0 or not self.renderer or not self.renderer.get_pdf_bytes():
            QMessageBox.warning(self, "알림", "자르기할 페이지가 선택되지 않았습니다.")
            return

        # 1. 현재 페이지에 스탬프가 있는지 확인
        if self.current_page in self._overlay_items and self._overlay_items[self.current_page]:
            reply = QMessageBox.question(self, '경고',
                                           '이 페이지의 모든 스탬프(이미지)를 삭제하고 자르기를 진행하시겠습니까?',
                                           QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                           QMessageBox.StandardButton.No)

            if reply == QMessageBox.StandardButton.No:
                return  # 사용자가 '아니오'를 선택하면 자르기 취소

            # 2. 사용자가 '예'를 선택하면 현재 페이지의 스탬프 삭제
            del self._overlay_items[self.current_page]
            
            # 3. 화면을 다시 그려서 스탬프가 삭제된 것을 반영
            # 현재 캐시된 페이지를 다시 로드하여 화면을 갱신
            if self.current_page in self.page_cache:
                self._display_pixmap(self.page_cache[self.current_page])
                QApplication.processEvents() # 화면 업데이트를 즉시 반영


        # 다이얼로그에 표시할 선명한 미리보기용 이미지를 새로 렌더링한다.
        pdf_bytes = self.renderer.get_pdf_bytes()
        page_num = self.current_page
        user_rotation = self.page_rotations.get(page_num, 0)
        
        # zoom_factor=2.0 (약 200DPI)로 선명한 이미지를 생성
        preview_pixmap = PdfRender.render_page_thread_safe(
            pdf_bytes,
            page_num,
            zoom_factor=2.0,
            user_rotation=user_rotation
        )
        
        dialog = CropDialog(self)
        dialog.set_page_pixmap(preview_pixmap)
        
        # 다이얼로그 실행
        if dialog.exec():
            # 자르기 적용
            crop_rect = dialog.get_crop_rect_in_page_coords()
            if not crop_rect.isEmpty():
                self._apply_crop_to_current_page(crop_rect)
        else:
            # '취소' 눌렀을 때
            print("자르기 취소됨")

    def _apply_crop_to_current_page(self, crop_rect_normalized):
        """현재 페이지에 자르기를 적용하고 화면을 업데이트한다."""
        if not self.renderer:
            return
            
        try:
            # 정규화된 QRectF를 튜플로 변환
            crop_tuple = (
                crop_rect_normalized.x(),
                crop_rect_normalized.y(), 
                crop_rect_normalized.width(),
                crop_rect_normalized.height()
            )
            
            # 자르기 적용
            self.renderer.apply_crop_to_page(self.current_page, crop_tuple)
            
            # --- 중요 ---
            # 자르기가 적용되면 PDF 데이터 자체가 변경되므로, 기존의 모든 페이지 캐시는 무효화됩니다.
            # 캐시를 비워서 모든 페이지(현재 페이지 포함)를 새로운 데이터로 다시 렌더링하도록 강제합니다.
            self.page_cache.clear()
            
            # 현재 페이지 다시 렌더링
            self._start_render_job(self.current_page)
            
            # 썸네일 업데이트
            if hasattr(self, 'thumbnail_updated'):
                self.thumbnail_updated.emit(self.current_page)
                
            print(f"페이지 {self.current_page + 1} 자르기 적용 완료")
            
        except Exception as e:
            print(f"자르기 적용 오류: {e}")
            import traceback
            traceback.print_exc()

    def apply_default_crop_to_current_page_sync(self):
        """(공개 메소드, 동기식) 현재 페이지에 기본 자르기를 적용하고 렌더링이 끝날 때까지 기다린다."""
        if self.current_page < 0 or not self.renderer or not self.renderer.get_pdf_bytes():
            return
        
        # 1. 기본 자르기 영역 계산 (다이얼로그를 직접 사용하되 보여주지 않음)
        pdf_bytes = self.renderer.get_pdf_bytes()
        page_num = self.current_page
        user_rotation = self.page_rotations.get(page_num, 0)
        preview_pixmap = PdfRender.render_page_thread_safe(
            pdf_bytes, page_num, zoom_factor=2.0, user_rotation=user_rotation
        )
        
        temp_dialog = CropDialog(self)
        temp_dialog.set_page_pixmap(preview_pixmap)
        crop_rect_normalized = temp_dialog.get_crop_rect_in_page_coords()
        
        if crop_rect_normalized.isEmpty():
            print(f"페이지 {page_num + 1}의 기본 자르기 영역을 계산할 수 없습니다.")
            return

        # 2. 자르기 적용 (기존 메소드 재사용)
        self._apply_crop_to_current_page(crop_rect_normalized)
        
        # 3. 화면 업데이트를 강제로 처리하고 기다림
        QApplication.instance().processEvents()

    def _toggle_force_resize(self):
        """현재 페이지를 강제 크기 조정 목록에 추가하거나 제거한다."""
        if self.current_page < 0:
            return
            
        if self.current_page in self.force_resize_pages:
            self.force_resize_pages.remove(self.current_page)
            print(f"페이지 {self.current_page + 1}: 크기 조정 해제")
        else:
            self.force_resize_pages.add(self.current_page)
            print(f"페이지 {self.current_page + 1}: 크기 조정 적용")

    def _toggle_stamp_overlay(self):
        """스탬프 오버레이를 토글한다."""
        if self.stamp_overlay.isVisible():
            self.stamp_overlay.hide()
        else:
            self.stamp_overlay.show_overlay(self.size())
    
    def init_ui(self):
        """UI 파일을 로드하고 초기화"""
        ui_path = Path(__file__).parent.parent / "ui" / "pdf_view_widget.ui"
        uic.loadUi(str(ui_path), self)
        
        # Graphics View 설정
        if hasattr(self, 'pdf_graphics_view'):
            self.pdf_graphics_view.setScene(self.scene)
            self.setup_graphics_view()
    
    def setup_graphics_view(self):
        """Graphics View 초기 설정"""
        view = self.pdf_graphics_view
        view.setAlignment(Qt.AlignmentFlag.AlignCenter)  # 뷰의 콘텐츠를 항상 중앙에 정렬
        view.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform |
            QPainter.RenderHint.TextAntialiasing
        )
        view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
    
    def mousePressEvent(self, event):
        """마우스 클릭 이벤트를 처리한다 (스탬프 모드)."""
        if self._is_stamp_mode and event.button() == Qt.MouseButton.LeftButton:
            if self.current_page_item:
                # 뷰의 좌표를 씬 좌표로 변환
                scene_pos = self.pdf_graphics_view.mapToScene(event.pos())
                # 씬 좌표를 현재 페이지 아이템의 내부 좌표로 변환
                item_pos = self.current_page_item.mapFromScene(scene_pos)
                self._add_stamp_to_page(item_pos)
            
            # 스탬프를 한 번 찍으면 모드 해제
            self._deactivate_stamp_mode()
            event.accept()
        else:
            super().mousePressEvent(event)

    def _add_stamp_to_page(self, position):
        """페이지에 스탬프를 추가한다."""
        if not self._stamp_pixmap or not self.current_page_item:
            return

        # 2. 저장해 둔 너비(_stamp_desired_width)를 desired_width 인자로 전달합니다.
        stamp_item = add_stamp_item(
            stamp_pixmap=self._stamp_pixmap,
            page_item=self.current_page_item,
            position=position,
            desired_width=self._stamp_desired_width # 이 부분을 수정
        )

        # 페이지별로 스탬프 "데이터"를 관리 (QGraphicsPixmapItem 객체 대신)
        page_pixmap = self.page_cache.get(self.current_page)
        if page_pixmap:
            page_width = page_pixmap.width()
            page_height = page_pixmap.height()

            stamp_data = {
                'pixmap': stamp_item.pixmap(),
                'x_ratio': stamp_item.pos().x() / page_width,
                'y_ratio': stamp_item.pos().y() / page_height,
                'w_ratio': stamp_item.boundingRect().width() / page_width,
                'h_ratio': stamp_item.boundingRect().height() / page_height,
            }

            if self.current_page not in self._overlay_items:
                self._overlay_items[self.current_page] = []
            self._overlay_items[self.current_page].append(stamp_data)

        print(f"페이지 {self.current_page + 1}에 스탬프 추가: {stamp_item.pos()}")

    def resizeEvent(self, event):
        """뷰어 크기가 변경될 때 툴바 위치를 재조정한다."""
        super().resizeEvent(event)
        # 툴바를 상단 중앙에 배치 (가로 중앙, 세로 상단에서 10px)
        x = (self.width() - self.toolbar.width()) // 2
        y = 10
        self.toolbar.move(x, y)
        if self.stamp_overlay and self.stamp_overlay.isVisible():
            self.stamp_overlay.setGeometry(0, 0, self.width(), self.height())
    
    def keyPressEvent(self, event):
        """키보드 'Q', 'E'를 눌러 페이지를 변경한다."""
        if event.key() == Qt.Key.Key_Q:
            self.page_change_requested.emit(-1)
        elif event.key() == Qt.Key.Key_E:
            self.page_change_requested.emit(1)
        else:
            super().keyPressEvent(event)

    def save_pdf(self):
        """PDF 저장 프로세스를 시작한다."""
        if not self.renderer or not self.renderer.get_pdf_bytes():
            QMessageBox.warning(self, "저장 오류", "저장할 PDF 파일이 없습니다.")
            return

        default_path = self.get_current_pdf_path() or "untitled.pdf"
        output_path, _ = QFileDialog.getSaveFileName(
            self, "PDF로 저장", default_path, "PDF Files (*.pdf)"
        )

        if not output_path:
            return

        input_bytes = self.renderer.get_pdf_bytes()
        rotations = self.get_page_rotations()
        force_resize_pages = self.get_force_resize_pages()
        stamp_data = self.get_stamp_items_data()

        worker = PdfSaveWorker(
            input_bytes=input_bytes, output_path=output_path,
            rotations=rotations, force_resize_pages=force_resize_pages,
            stamp_data=stamp_data
        )

        worker.signals.save_finished.connect(self._on_save_finished)
        worker.signals.save_error.connect(self._on_save_error)

        print(f"'{output_path}' 경로로 PDF 저장을 시작합니다...")
        self.thread_pool.start(worker)

    def _on_save_finished(self, output_path: str, success: bool):
        """PDF 저장이 완료되었을 때 호출된다."""
        if success:
            QMessageBox.information(self, "저장 완료", f"'{output_path}'\n\n파일이 성공적으로 저장되었습니다.")
        else:
            QMessageBox.warning(
                self, "압축 실패",
                f"파일을 목표 크기로 압축하지 못했습니다.\n\n"
                f"'{output_path}' 경로에 원본 품질로 저장되었습니다."
            )
        
        self.save_completed.emit()

    def _on_save_error(self, error_msg: str):
        """PDF 저장 중 오류가 발생했을 때 호출된다."""
        QMessageBox.critical(self, "저장 오류", f"PDF를 저장하는 중 오류가 발생했습니다:\n\n{error_msg}")

    def get_stamp_items_data(self) -> dict[int, list[dict]]:
        """
        모든 페이지에 추가된 스탬프 아이템들의 "데이터"를 반환한다.
        이제 이 메서드는 QGraphicsPixmapItem 객체에 접근하지 않으므로 안전하다.
        """
        return self._overlay_items

    def set_renderer(self, renderer: PdfRender | None):
        """PDF 렌더러를 설정하고 캐시를 초기화한다."""
        self.renderer = renderer # PdfRender 인스턴스
        self.pdf_path = renderer.pdf_path if renderer else None

        # 기존 상태 초기화
        self.scene.clear()
        self.current_page_item = None
        self.page_cache.clear() # 이전 PDF 파일 정보를 잊어버리기
        self.rendering_jobs.clear()
        self.current_page = -1 # 지금 보고 있는 페이지 없음 (존재하지 않는 페이지 번호로 -1로 설정)
        self.page_rotations = {} # 새 파일 로드 시 회전 정보 초기화
        self.force_resize_pages.clear() # 새 파일 로드 시 크기 조정 정보 초기화
        self._overlay_items.clear() # 새 파일 로드 시 오버레이 아이템 초기화

        # --- 파일 정보 시그널 발생 ---
        if self.renderer:
            file_path = self.renderer.pdf_path
            try:
                file_size = Path(file_path).stat().st_size / (1024 * 1024)
            except (FileNotFoundError, TypeError):
                file_size = 0.0
            
            total_pages = self.renderer.get_page_count()
            self.pdf_loaded.emit(file_path, file_size, total_pages)

    def show_page(self, page_num: int):
        """지정된 페이지를 뷰에 표시한다. 캐시를 확인하고, 없으면 백그라운드 렌더링을 시작한다."""
        if not self.renderer or not self.renderer.get_pdf_bytes() or page_num < 0 or page_num >= self.renderer.get_page_count():
            return

        self.current_page = page_num
        
        # --- 페이지 정보 시그널 발생 ---
        try:
            page = self.renderer.doc.load_page(page_num)
            rect = page.rect
            rotation = page.rotation
            self.page_info_updated.emit(page_num, rect.width, rect.height, rotation)
        except Exception:
            # 오류 발생 시 기본값으로 전송
            self.page_info_updated.emit(page_num, 0, 0, 0)


        if page_num in self.page_cache:
            # 캐시에 있으면 바로 표시
            pixmap = self.page_cache[page_num]
            self._display_pixmap(pixmap)
        else:
            # 캐시에 없으면 로딩 메시지 표시 후 렌더링 시작
            self._show_loading_message()
            self._start_render_job(page_num)

        # 인접 페이지 미리 렌더링
        self._pre_render_adjacent_pages(page_num)

    def _start_render_job(self, page_num: int):
        """지정된 페이지의 백그라운드 렌더링 작업을 시작한다."""
        pdf_bytes = self.renderer.get_pdf_bytes()
        if (not self.renderer or not pdf_bytes or
                page_num < 0 or page_num >= self.renderer.get_page_count()):
            return
        if page_num in self.page_cache or page_num in self.rendering_jobs:
            return

        self.rendering_jobs.add(page_num)
        # 현재 회전 각도를 워커에 전달
        user_rotation = self.page_rotations.get(page_num, 0)
        worker = PdfRenderWorker(pdf_bytes, page_num, zoom_factor=2.0, user_rotation=user_rotation)
        worker.signals.finished.connect(self._on_page_rendered)
        worker.signals.error.connect(self._on_render_error)
        self.thread_pool.start(worker)

    def _on_page_rendered(self, page_num: int, pixmap: QPixmap):
        """페이지 렌더링이 완료되었을 때 호출된다."""
        self.page_cache[page_num] = pixmap
        if page_num in self.rendering_jobs:
            self.rendering_jobs.remove(page_num)

        if page_num == self.current_page:
            self._display_pixmap(pixmap)

    def _on_render_error(self, page_num: int, error_msg: str):
        """페이지 렌더링 중 오류 발생 시 호출된다."""
        if page_num in self.rendering_jobs:
            self.rendering_jobs.remove(page_num)

        if page_num == self.current_page:
            self.scene.clear()
            QMessageBox.warning(self, "렌더링 오류", f"페이지 {page_num + 1}을(를) 표시하는 중 오류 발생: {error_msg}")

    def _display_pixmap(self, pixmap: QPixmap):
        """주어진 QPixmap을 씬에 표시한다."""
        self.scene.clear()
        self.current_page_item = self.scene.addPixmap(pixmap)
        
        # A4 세로 기준으로 페이지 비율을 평가
        # A4 세로 비율: 21:29.7 ≈ 1:1.414
        a4_portrait_ratio = 29.7 / 21.0
        page_ratio = pixmap.height() / pixmap.width()
        
        # 페이지가 A4 세로보다 가로가 상대적으로 긴지 판단
        is_landscape = page_ratio < a4_portrait_ratio
        self.page_aspect_ratio_changed.emit(is_landscape)

        # A4 세로 기준 통일된 뷰 적용
        self._fit_current_page_to_view()

        # --- 이 페이지에 해당하는 오버레이 아이템(스탬프 등)이 있다면 다시 그리기 ---
        if self.current_page in self._overlay_items:
            page_width = pixmap.width()
            page_height = pixmap.height()
            
            for stamp_data in self._overlay_items[self.current_page]:
                stamp_pixmap = stamp_data['pixmap']
                
                # QGraphicsPixmapItem 재생성 및 부모 설정
                stamp_item = QGraphicsPixmapItem(stamp_pixmap, self.current_page_item)
                
                # 저장된 비율을 기반으로 위치 설정
                pos_x = stamp_data['x_ratio'] * page_width
                pos_y = stamp_data['y_ratio'] * page_height
                stamp_item.setPos(pos_x, pos_y)

    def _show_loading_message(self):
        """로딩 중 메시지를 표시한다."""
        self.scene.clear()
        self.current_page_item = None
        # 나중에 더 예쁜 스피너 등으로 교체 가능
        self.scene.addText(f"페이지 {self.current_page + 1} 로딩 중...")

    def _pre_render_adjacent_pages(self, page_num: int):
        """현재 페이지의 이전/다음 페이지를 미리 렌더링한다."""
        self._start_render_job(page_num + 1)
        self._start_render_job(page_num - 1)

    def rotate_current_page_by_90_sync(self):
        """(공개 메소드, 동기식) 현재 페이지를 90도 회전시키고 렌더링이 끝날 때까지 기다린다."""
        if not self.renderer or self.current_page < 0:
            return

        # 1. 회전 각도 업데이트
        current_user_rotation = self.page_rotations.get(self.current_page, 0)
        new_user_rotation = (current_user_rotation + 90) % 360
        self.page_rotations[self.current_page] = new_user_rotation
        
        # 2. 캐시 제거
        if self.current_page in self.page_cache:
            del self.page_cache[self.current_page]

        # 3. 동기 렌더링
        try:
            pdf_bytes = self.renderer.get_pdf_bytes()
            if not pdf_bytes:
                raise Exception("PDF 바이트 데이터를 가져올 수 없습니다.")
            
            # 비동기 워커의 로직을 그대로 가져와서 동기적으로 실행
            pixmap = PdfRender.render_page_thread_safe(
                pdf_bytes, self.current_page, zoom_factor=2.0, user_rotation=new_user_rotation
            )
            
            # 4. 캐시에 저장하고 즉시 표시
            self.page_cache[self.current_page] = pixmap
            self._display_pixmap(pixmap)
            
            # Qt 이벤트 루프가 화면을 업데이트할 시간을 줌
            QApplication.instance().processEvents()

        except Exception as e:
            QMessageBox.warning(self, "렌더링 오류", f"페이지 {self.current_page + 1}을(를) 동기 렌더링하는 중 오류 발생: {e}")


    def rotate_current_page_by_90(self):
        """(공개 메소드) 현재 페이지를 90도 회전시킨다."""
        self._rotate_current_page()

    def _rotate_current_page(self):
        """(내부 메소드) 현재 페이지를 90도 회전시킨다."""
        if not self.current_page_item:
            return
        
        # 회전 각도 업데이트 (90도씩 증가, 360도에서 0으로 리셋)
        current_user_rotation = self.page_rotations.get(self.current_page, 0)
        new_user_rotation = (current_user_rotation + 90) % 360
        self.page_rotations[self.current_page] = new_user_rotation
        
        # 현재 페이지를 다시 렌더링 (회전 적용)
        if self.current_page >= 0:
            # 캐시에서 제거하여 새로 렌더링하도록 함
            if self.current_page in self.page_cache:
                del self.page_cache[self.current_page]
            
            self._show_loading_message()
            self._start_render_job(self.current_page)

    def _fit_current_page_to_view(self):
        """A4 세로 기준 통일된 뷰로 페이지를 표시 (모든 페이지 타입 고려)"""
        if not self.current_page_item:
            return
        
        # 모든 페이지를 A4 세로 기준으로 통일된 방식으로 표시
        # 페이지가 뷰포트보다 크면 축소하여 전체가 보이도록 하고,
        # 작으면 적절한 크기로 확대하여 표시
        self._fit_page_optimized()

    def _fit_current_page_to_page(self):
        """현재 페이지 전체가 보이도록 뷰를 조정 (Fit to Page)"""
        if not hasattr(self, 'pdf_graphics_view') or not self.current_page_item:
            return

        view = self.pdf_graphics_view
        
        # 스크롤바 정책 설정
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # 현재 페이지 아이템만을 기준으로 fitInView 적용
        view.fitInView(self.current_page_item, Qt.AspectRatioMode.KeepAspectRatio)

    def _fit_current_page_to_width(self):
        """현재 페이지의 폭이 뷰어의 폭에 맞도록 뷰를 조정 (Fit to Width)"""
        if not hasattr(self, 'pdf_graphics_view') or not self.current_page_item:
            return

        view = self.pdf_graphics_view
        page_rect = self.current_page_item.boundingRect()

        if page_rect.width() == 0:
            return

        # 폭 맞춤 시에는 세로 스크롤바가 필요할 수 있음
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # 뷰포트의 가용 너비 계산
        viewport_width = view.viewport().width()
        
        # 스케일 팩터 계산
        scale_factor = viewport_width / page_rect.width()
        
        # 스케일 적용 후 세로 스크롤바가 생길 것으로 예상되면, 스크롤바 폭을 제외하고 다시 계산
        scaled_height = page_rect.height() * scale_factor
        if scaled_height > view.viewport().height():
            scrollbar_width = view.style().pixelMetric(view.style().PixelMetric.PM_ScrollBarExtent)
            viewport_width -= scrollbar_width
        
        # 최종 스케일 팩터 계산 및 적용
        scale_factor = viewport_width / page_rect.width()
        
        from PyQt6.QtGui import QTransform
        transform = QTransform()
        transform.scale(scale_factor, scale_factor)
        view.setTransform(transform)

        # 페이지를 뷰 중앙에 배치
        view.centerOn(self.current_page_item)

    def _fit_page_optimized(self):
        """페이지 방향(세로/가로)을 감지하여 A4 표준에 맞게 최적화된 뷰를 제공한다."""
        if not hasattr(self, 'pdf_graphics_view') or not self.current_page_item:
            return

        view = self.pdf_graphics_view
        page_rect = self.current_page_item.boundingRect()

        if page_rect.width() == 0 or page_rect.height() == 0:
            return

        # 페이지 방향 결정 (너비가 높이보다 크면 가로)
        is_page_landscape = page_rect.width() > page_rect.height()

        # A4 비율 정의
        a4_portrait_ratio = 29.7 / 21.0  # 높이/너비
        a4_landscape_ratio = 21.0 / 29.7 # 높이/너비
        
        # 페이지 방향에 따라 목표 A4 비율 설정
        target_a4_ratio = a4_landscape_ratio if is_page_landscape else a4_portrait_ratio

        # 뷰포트 크기
        viewport_rect = view.viewport().rect()
        viewport_width = viewport_rect.width()
        viewport_height = viewport_rect.height()

        # 뷰포트를 목표 A4 비율에 맞춘 가상(effective) 뷰포트 계산
        # 너비/높이 비율을 비교하여 effective viewport를 계산한다.
        # 뷰포트가 목표 비율보다 가로로 넓으면, 높이를 기준으로 너비 조정
        if viewport_width / viewport_height > (1 / target_a4_ratio):
             effective_height = viewport_height
             effective_width = viewport_height / target_a4_ratio
        else: # 뷰포트가 목표 비율보다 세로로 길면, 너비를 기준으로 높이 조정
            effective_width = viewport_width
            effective_height = viewport_width * target_a4_ratio

        # 스크롤바 정책: 페이지가 효과적 뷰포트보다 크면 스크롤바 표시
        # 약간의 여유(95%)를 두어 불필요한 스크롤바 방지
        if (page_rect.width() > effective_width * 0.95 or 
            page_rect.height() > effective_height * 0.95):
            view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 페이지를 효과적 뷰포트에 맞도록 스케일 계산
        scale_x = effective_width / page_rect.width()
        scale_y = effective_height / page_rect.height()
        
        # 페이지가 잘리지 않도록 더 작은 스케일 사용 (축소 우선)
        scale_factor = min(scale_x, scale_y)
        
        # 여백 최소화: A4 크기의 98%까지 사용
        margin_utilization = 0.98
        scale_factor *= margin_utilization
        
        # --- 기본 확대 레벨 설정 ---
        # 사용자가 요청한 대로, 기본적으로 두 단계 확대된 상태로 보이도록 스케일 팩터를 1.4배 증가
        default_zoom_level = 1
        scale_factor *= default_zoom_level

        # 너무 작아지지 않도록 최소 스케일 제한
        min_scale = 0.1
        scale_factor = max(scale_factor, min_scale)
        
        # 변환 매트릭스 적용
        from PyQt6.QtGui import QTransform
        transform = QTransform()
        transform.scale(scale_factor, scale_factor)
        view.setTransform(transform)
        
        # 페이지를 뷰 중앙에 배치
        view.centerOn(self.current_page_item)

    # ViewModeMixin의 메서드를 오버라이드하여 A4 세로 기준 통일된 뷰 사용
    def set_fit_to_page(self):
        """A4 세로 기준 통일된 뷰로 페이지 전체가 보이도록 조정"""
        self._fit_page_optimized()

    def set_fit_to_width(self):
        """A4 세로 기준 통일된 뷰로 페이지 폭에 맞도록 조정"""
        self._fit_page_optimized()

    def get_current_pdf_path(self) -> str | None:
        """현재 열려있는 PDF 파일의 경로를 반환한다."""
        return self.pdf_path

    def get_page_rotations(self) -> dict:
        """사용자가 적용한 페이지별 회전 정보를 반환한다."""
        return self.page_rotations

    def get_force_resize_pages(self) -> set:
        """사용자가 수동으로 크기 조정을 요청한 페이지 목록을 반환한다."""
        return self.force_resize_pages