from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import (QObject, QRunnable, Qt, QThreadPool, pyqtSignal, QPointF, QSizeF)
from PyQt6.QtGui import QImage, QPainter, QPixmap, QFont, QFontMetrics, QPen
from PyQt6.QtWidgets import (QApplication, QFileDialog, QGraphicsPixmapItem,
                                 QGraphicsScene, QGraphicsView, QMessageBox,
                                 QWidget, QGraphicsItem, QMenu)

import pymupdf
from core.workers import PdfRenderWorker, PdfSaveWorker
from core.edit_mixin import ViewModeMixin, EditMixin
from core.insert_utils import add_stamp_item
from core.pdf_render import PdfRender
from core.pdf_saved import compress_pdf_with_multiple_stages, export_deleted_pages
from .crop_dialog import CropDialog
from .floating_toolbar import FloatingToolbarWidget
from .stamp_overlay_widget import StampOverlayWidget
from .zoomable_graphics_view import ZoomableGraphicsView
from .custom_item import MovableStampItem
from .mail_content_overlay import MailContentOverlay

class PdfViewWidget(QWidget, ViewModeMixin, EditMixin):
    """PDF 뷰어 위젯"""
    page_change_requested = pyqtSignal(int)
    page_aspect_ratio_changed = pyqtSignal(bool)  # is_landscape: 가로가 긴 페이지 여부
    save_completed = pyqtSignal()  # 저장 완료 후 화면 전환을 위한 신호
    page_delete_requested = pyqtSignal(int) # '보이는' 페이지 번호로 삭제를 요청하는 신호

    # --- 정보 패널 연동을 위한 신호 ---
    pdf_loaded = pyqtSignal(str, float, int)  # file_path, file_size_mb, total_pages
    page_info_updated = pyqtSignal(int, float, float, int)  # page_num, width, height, rotation

    def __init__(self):
        super().__init__()
        self.renderer = PdfRender()
        self.pdf_path: str | None = None
        self.scene = QGraphicsScene(self)
        self.current_page_item: QGraphicsPixmapItem | None = None

        # --- 페이지 별 오버레이 아이템 "데이터" 관리 ---
        self._overlay_items: dict[int, list[dict]] = {}
        
        # --- 되돌리기(Undo)를 위한 작업 기록 ---
        self._history_stack: list[tuple] = []

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

        self.init_ui()

        # --- 툴바 추가 ---
        self.toolbar = FloatingToolbarWidget(self)
        self.toolbar.show()

        # --- 스탬프 오버레이 추가 ---
        self.stamp_overlay = StampOverlayWidget(self)

        # --- 메일 컨텐츠 오버레이 추가 ---
        self.mail_overlay = MailContentOverlay(self)

        # --- 툴바 시그널 연결 ---
        self.toolbar.stamp_menu_requested.connect(self._toggle_stamp_overlay)
        self.toolbar.fit_to_width_requested.connect(self.set_fit_to_width)
        self.toolbar.fit_to_page_requested.connect(self.set_fit_to_page)
        self.toolbar.rotate_90_requested.connect(self._rotate_current_page)
        self.toolbar.crop_requested.connect(self._open_crop_dialog) # 자르기 신호 연결
        self.toolbar.toggle_mail_overlay_requested.connect(self._toggle_mail_overlay)

        # --- 스탬프 오버레이 시그널 연결 ---
        self.stamp_overlay.stamp_selected.connect(self._activate_stamp_mode)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _activate_stamp_mode(self, stamp_info: dict): # 변경: image_path: str -> stamp_info: dict
        """스탬프 오버레이에서 도장이 선택되면 호출된다."""
        try:
            desired_width = stamp_info['width'] # 먼저 desired_width를 가져옴

            # stamp_info에 미리 생성된 pixmap이 있는지 확인
            if 'pixmap' in stamp_info:
                pixmap = stamp_info['pixmap']
            else:
                # pixmap이 없으면 path에서 로드
                image_path = stamp_info['path']
                pixmap = QPixmap(image_path)
                if pixmap.isNull():
                    raise FileNotFoundError(f"이미지 파일을 로드할 수 없습니다: {image_path}")

            self._stamp_pixmap = pixmap
            self._stamp_desired_width = desired_width
            self._is_stamp_mode = True
            self.setCursor(Qt.CursorShape.CrossCursor)
            print(f"스탬프 모드 활성화: {stamp_info.get('path', '사용자 지정 텍스트')}, 너비: {desired_width}px")

        except FileNotFoundError as e:
            QMessageBox.warning(self, "오류", str(e))
            self._deactivate_stamp_mode()
        except Exception as e:
            QMessageBox.warning(self, "오류", f"스탬프 이미지를 처리하는 중 오류가 발생했습니다: {e}")
            self._deactivate_stamp_mode()

    def _deactivate_stamp_mode(self):
        """스탬프 모드를 비활성화한다."""
        self._is_stamp_mode = False
        self._stamp_pixmap = None
        self.unsetCursor()
        print("스탬프 모드 비활성화")

    def activate_text_stamp_mode(self, text: str, font_size: int):
        """info_panel로부터 텍스트와 폰트 크기를 받아 스탬프 모드를 활성화한다."""
        if not text:
            return
            
        pixmap = self._create_pixmap_from_text(text, font_size)
        
        stamp_info = {
            'path': f'text_{text[:10]}',
            'width': -1, # 크기 조절 안 함
            'pixmap': pixmap
        }
        self._activate_stamp_mode(stamp_info)

    def _create_pixmap_from_text(self, text: str, font_size: int) -> QPixmap:
        """주어진 텍스트로부터 QPixmap 이미지를 생성한다."""
        font = QFont("Malgun Gothic", font_size, QFont.Weight.Bold)
        
        # 텍스트 크기를 계산하기 위한 FontMetrics
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(text)
        text_height = fm.height()

        # 텍스트 크기에 약간의 여백을 더해 QPixmap 생성
        pixmap = QPixmap(text_width + 20, text_height + 10)
        pixmap.fill(Qt.GlobalColor.transparent) # 투명 배경

        # QPainter를 사용하여 Pixmap에 텍스트 그리기
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(font)
        painter.setPen(Qt.GlobalColor.black) # 텍스트 색상
        
        # 텍스트를 중앙에 그리기
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
        
        return pixmap

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
                # 여러 페이지 모드인지 확인
                if dialog.is_multi_page_mode():
                    target_pages = dialog.get_target_pages()
                    if target_pages:
                        # 총 페이지 수로 유효성 검증
                        total_pages = self.renderer.get_page_count()
                        valid_pages = [p for p in target_pages if 0 <= p < total_pages]
                        invalid_pages = [p for p in target_pages if p >= total_pages]
                        
                        if invalid_pages:
                            QMessageBox.warning(
                                self, "경고",
                                f"유효하지 않은 페이지 번호가 있습니다: {[p+1 for p in invalid_pages]}\n"
                                f"(총 {total_pages}페이지)\n\n"
                                f"유효한 페이지에만 자르기를 적용합니다."
                            )
                        
                        if valid_pages:
                            self._apply_crop_to_multiple_pages(crop_rect, valid_pages)
                        else:
                            QMessageBox.warning(self, "오류", "적용할 유효한 페이지가 없습니다.")
                    else:
                        QMessageBox.warning(self, "오류", "페이지 번호를 올바르게 입력해주세요.\n예: 1,2,3 또는 1-5 또는 1-3,7,9-10")
                else:
                    # 단일 페이지 모드
                    self._apply_crop_to_current_page(crop_rect)
        else:
            # '취소' 눌렀을 때
            print("자르기 취소됨")

    def _apply_crop_to_current_page(self, crop_rect_normalized):
        """현재 페이지에 자르기를 적용하고 화면을 업데이트한다."""
        self._apply_crop_to_multiple_pages(crop_rect_normalized, [self.current_page])

    def _apply_crop_to_multiple_pages(self, crop_rect_normalized, page_nums: list[int]):
        """여러 페이지에 동일한 자르기를 적용하고 화면을 업데이트한다."""
        if not self.renderer or not page_nums:
            return
            
        try:
            # --- 되돌리기를 위해 자르기 전 PDF 데이터(bytes) 저장 ---
            before_crop_bytes = bytes(self.renderer.get_pdf_bytes())
            self._history_stack.append((
                'crop_pages',
                -1,  # 대표 페이지는 쓰지 않음
                {'pages': list(page_nums), 'bytes': before_crop_bytes}
            ))

            # 정규화된 QRectF를 튜플로 변환
            crop_tuple = (
                crop_rect_normalized.x(),
                crop_rect_normalized.y(), 
                crop_rect_normalized.width(),
                crop_rect_normalized.height()
            )
            
            # 스탬프가 있는 페이지 확인 및 경고
            pages_with_stamps = [p for p in page_nums if p in self._overlay_items and self._overlay_items[p]]
            if pages_with_stamps:
                reply = QMessageBox.question(
                    self, '경고',
                    f'다음 페이지에 스탬프가 있습니다: {[p+1 for p in sorted(pages_with_stamps)]}\n\n'
                    f'해당 페이지의 모든 스탬프가 삭제됩니다.\n계속하시겠습니까?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                
                if reply == QMessageBox.StandardButton.No:
                    return
                
                # 스탬프 삭제
                for page_num in pages_with_stamps:
                    del self._overlay_items[page_num]
            
            # 자르기 적용
            self.renderer.apply_crop_to_pages(page_nums, crop_tuple)
            
            # --- 중요 ---
            # 자르기가 적용되면 PDF 데이터 자체가 변경되므로, 기존의 모든 페이지 캐시는 무효화됩니다.
            # 캐시를 비워서 모든 페이지(현재 페이지 포함)를 새로운 데이터로 다시 렌더링하도록 강제합니다.
            self.page_cache.clear()
            
            # 현재 페이지가 자른 페이지 중 하나라면 다시 렌더링
            if self.current_page in page_nums:
                self._start_render_job(self.current_page)
            
            # 썸네일 업데이트 (자른 모든 페이지)
            if hasattr(self, 'thumbnail_updated'):
                for page_num in page_nums:
                    self.thumbnail_updated.emit(page_num)
            
            if len(page_nums) == 1:
                print(f"페이지 {page_nums[0] + 1} 자르기 적용 완료")
            else:
                print(f"{len(page_nums)}개 페이지 자르기 적용 완료: {[p+1 for p in sorted(page_nums)]}")
            
            # 성공 메시지 표시
            QMessageBox.information(
                self, "자르기 완료",
                f"{len(page_nums)}개 페이지에 자르기가 적용되었습니다.\n"
                f"페이지: {', '.join(str(p+1) for p in sorted(page_nums))}"
            )
            
        except Exception as e:
            print(f"자르기 적용 오류: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "오류", f"자르기 적용 중 오류가 발생했습니다:\n{e}")

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

    def toggle_stamp_overlay(self):
        """(공개 메서드) 스탬프 오버레이를 토글한다."""
        self._toggle_stamp_overlay()

    def _toggle_stamp_overlay(self):
        """스탬프 오버레이를 토글한다."""
        if self.stamp_overlay.isVisible():
            self.stamp_overlay.hide()
        else:
            self.stamp_overlay.show_overlay(self.size())
    
    def _toggle_mail_overlay(self):
        """메일 오버레이를 토글한다."""
        if self.mail_overlay.isVisible():
            self.mail_overlay.hide()
        else:
            if self.mail_overlay._content:  # content가 있을 때만 표시
                self.mail_overlay.show_overlay(self.size())
    
    def toggle_mail_overlay(self):
        """(공개 메서드) 메일 오버레이를 토글한다."""
        self._toggle_mail_overlay()

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
                scene_pos = self.pdf_graphics_view.mapToScene(self.pdf_graphics_view.mapFrom(self, event.pos()))
                # 씬 좌표를 현재 페이지 아이템의 내부 좌표로 변환
                item_pos = self.current_page_item.mapFromScene(scene_pos)
                self._add_stamp_to_page(item_pos)
            
            # 스탬프를 한 번 찍으면 모드 해제
            self._deactivate_stamp_mode()
            event.accept()
        else:
            super().mousePressEvent(event)

    def _add_stamp_to_page(self, position):
        """페이지에 스탬프를 추가하고, MovableStampItem으로 관리한다."""
        if not self._stamp_pixmap or not self.current_page_item:
            return

        # --- Begin integrated logic from core.insert_utils ---
        
        # 1. Scale pixmap if needed
        if self._stamp_desired_width > 0:
            scaled_pixmap = self._stamp_pixmap.scaledToWidth(
                self._stamp_desired_width, Qt.TransformationMode.SmoothTransformation
            )
        else:
            scaled_pixmap = self._stamp_pixmap

        # 2. Calculate centered position
        stamp_center_x = scaled_pixmap.width() / 2
        stamp_center_y = scaled_pixmap.height() / 2
        final_pos = QPointF(position.x() - stamp_center_x, position.y() - stamp_center_y)

        # 3. Adjust position to stay within page bounds
        stamp_rect = scaled_pixmap.rect().translated(final_pos.toPoint())
        page_rect = self.current_page_item.boundingRect()
        
        dx = 0
        dy = 0
        if stamp_rect.left() < page_rect.left():
            dx = page_rect.left() - stamp_rect.left()
        elif stamp_rect.right() > page_rect.right():
            dx = page_rect.right() - stamp_rect.right()

        if stamp_rect.top() < page_rect.top():
            dy = page_rect.top() - stamp_rect.top()
        elif stamp_rect.bottom() > page_rect.bottom():
            dy = page_rect.bottom() - stamp_rect.bottom()

        if dx != 0 or dy != 0:
            final_pos += QPointF(dx, dy)

        # --- End integrated logic ---

        page_pixmap = self.page_cache.get(self.current_page)
        if page_pixmap:
            page_width = page_pixmap.width()
            page_height = page_pixmap.height()

            # --- 방어 코드 추가 ---
            if page_width == 0 or page_height == 0:
                print("오류: 페이지 크기가 0이라 스탬프를 추가할 수 없습니다.")
                return 

            # Create the data dictionary FIRST
            stamp_data = {
                'pixmap': scaled_pixmap,
                'x_ratio': final_pos.x() / page_width,
                'y_ratio': final_pos.y() / page_height,
                'w_ratio': scaled_pixmap.width() / page_width,
                'h_ratio': scaled_pixmap.height() / page_height,
                'original_pixmap': scaled_pixmap.copy(),
                'background_applied': False,
            }

            if self.current_page not in self._overlay_items:
                self._overlay_items[self.current_page] = []
            self._overlay_items[self.current_page].append(stamp_data)

            # Create our custom item and add it to the scene
            page_size = QSizeF(page_width, page_height)
            stamp_item = MovableStampItem(
                scaled_pixmap,
                self.current_page_item,
                stamp_data,
                page_size,
                page_index=self.current_page,
                history_callback=self._on_stamp_background_toggled,
                delete_callback=self._on_stamp_delete_requested,
            )
            stamp_item.setPos(final_pos)

            self._history_stack.append(('add_stamp', self.current_page, None))
            print(f"페이지 {self.current_page + 1}에 스탬프 추가 및 이동 가능: {stamp_item.pos()}")

    def resizeEvent(self, event):
        """뷰어 크기가 변경될 때 툴바와 오버레이 위치를 재조정한다."""
        super().resizeEvent(event)
        # 툴바를 상단 중앙에 배치 (가로 중앙, 세로 상단에서 10px)
        x = (self.width() - self.toolbar.width()) // 2
        y = 10
        self.toolbar.move(x, y)
        if self.stamp_overlay and self.stamp_overlay.isVisible():
            self.stamp_overlay.setGeometry(0, 0, self.width(), self.height())
        if self.mail_overlay and self.mail_overlay.isVisible():
            self.mail_overlay.show_overlay(self.size())
    
    def keyPressEvent(self, event):
        """키보드 'Q', 'E'를 눌러 페이지를 변경하고, Ctrl+Z로 되돌리기를 실행한다."""
        if event.key() == Qt.Key.Key_Z and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self._undo_last_action()
        elif event.key() == Qt.Key.Key_Delete:
            self._prompt_delete_current_page()
        elif event.key() == Qt.Key.Key_Q:
            self.page_change_requested.emit(-1)
        elif event.key() == Qt.Key.Key_E:
            self.page_change_requested.emit(1)
        else:
            super().keyPressEvent(event)

    def _prompt_delete_current_page(self):
        """현재 페이지 삭제 여부를 묻는 확인 창을 띄운다."""
        if self.current_page < 0:
            return

        visual_page_num = self.current_page + 1

        reply = QMessageBox.question(
            self,
            '페이지 삭제 확인',
            f'{visual_page_num} 페이지를 정말로 삭제하시겠습니까?\n\n이 작업은 되돌릴 수 없습니다.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            # MainWindow에 현재 '보이는' 페이지의 삭제를 요청한다.
            self.page_delete_requested.emit(self.current_page)

    def delete_pages(self, pages_to_delete: list[int]):
        """(공개 메서드) 지정된 '실제' 페이지 인덱스를 삭제하고 데이터를 업데이트한다."""
        if not self.renderer or not pages_to_delete:
            return

        pdf_bytes = self.renderer.get_pdf_bytes()
        if pdf_bytes:
            try:
                pdf_copy = bytes(pdf_bytes)
                base_path = self.get_current_pdf_path()
                base_name = Path(base_path).stem if base_path else "untitled"
                export_deleted_pages(
                    pdf_bytes=pdf_copy,
                    page_indices=pages_to_delete,
                    output_dir=r"\\DESKTOP-KMJ\Users\HP\Desktop\greet_db\files\2025_4Q_deleted",
                    base_name=base_name,
                )
            except Exception as save_error:
                print(f"삭제 페이지 보관 중 오류: {save_error}")

        try:
            # EditMixin의 메서드를 사용하여 페이지 삭제 및 데이터 재정렬
            self._delete_pages_and_update_data(pages_to_delete)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"페이지를 삭제하는 중 오류가 발생했습니다:\n{e}")

    def save_pdf(self, page_order: list[int] | None = None, worker_name: str = ""):
        """PDF 저장 프로세스를 시작한다."""
        try:
            if not self.renderer or not self.renderer.get_pdf_bytes():
                QMessageBox.warning(self, "저장 오류", "저장할 PDF 파일이 없습니다.")
                self.save_completed.emit()  # 저장 실패 시에도 정리 작업 수행
                return

            if page_order is None:
                page_order = list(range(self.renderer.get_page_count()))

            # 자동 경로 생성
            from datetime import datetime
            from pathlib import Path as PathLib
            
            base_dir = r'\\DESKTOP-KMJ\Users\HP\Desktop\greet_db\files\finished'
            today = datetime.now().strftime('%Y-%m-%d')
            
            # 작업자 이름이 없으면 "미지정" 폴더 사용
            worker_folder = worker_name if worker_name else "미지정"
            
            # 최종 저장 경로 구성
            save_dir = PathLib(base_dir) / worker_folder / today
            save_dir.mkdir(parents=True, exist_ok=True)
            
            # 원본 파일명 가져오기
            default_path = self.get_current_pdf_path() or "untitled.pdf"
            original_filename = PathLib(default_path).name
            
            # 최종 저장 경로
            output_path = str(save_dir / original_filename)
            
            # 파일이 이미 존재하는 경우 타임스탬프 추가
            if PathLib(output_path).exists():
                timestamp = datetime.now().strftime('%H%M%S')
                stem = PathLib(original_filename).stem
                suffix = PathLib(original_filename).suffix
                output_path = str(save_dir / f"{stem}_{timestamp}{suffix}")
            
            print(f"자동 저장 경로: {output_path}")

            input_bytes = self.renderer.get_pdf_bytes()
            rotations = self.get_page_rotations()  # <--- 파라미터 없이 원본 데이터 전달
            stamp_data = self.get_stamp_items_data() # <--- 파라미터 없이 원본 데이터 전달

            worker = PdfSaveWorker(
                input_bytes=input_bytes, output_path=output_path,
                rotations=rotations,
                stamp_data=stamp_data,
                page_order=page_order
            )

            worker.signals.save_finished.connect(self._on_save_finished)
            worker.signals.save_error.connect(self._on_save_error)

            print(f"'{output_path}' 경로로 PDF 저장을 시작합니다...")
            self.thread_pool.start(worker)
            
        except Exception as e:
            # 예상치 못한 예외 발생 시에도 정리 작업 수행
            QMessageBox.critical(self, "저장 오류", f"저장 중 예상치 못한 오류가 발생했습니다:\n\n{str(e)}")
            self.save_completed.emit()

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
        
        # 저장 오류 시에도 save_completed 시그널을 emit하여 상위에서 정리 작업 수행
        self.save_completed.emit()

    def get_stamp_items_data(self) -> dict[int, list[dict]]:
        """
        모든 페이지에 추가된 스탬프 아이템들의 "데이터"를 반환한다.
        """
        return self._overlay_items

    def get_page_rotations(self) -> dict:
        """사용자가 적용한 페이지별 회전 정보를 반환한다."""
        return self.page_rotations

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
        self._overlay_items.clear() # 새 파일 로드 시 오버레이 아이템 초기화
        
        # 메일 오버레이 숨김
        if hasattr(self, 'mail_overlay'):
            self.mail_overlay.hide()

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
        self.set_fit_to_page()

        if self.current_page in self._overlay_items:
            page_width = pixmap.width()
            page_height = pixmap.height()
            
            for stamp_data in self._overlay_items[self.current_page]:
                stamp_pixmap = stamp_data['pixmap']
                
                # QGraphicsPixmapItem 대신 MovableStampItem 사용
                page_size = QSizeF(pixmap.width(), pixmap.height())
                stamp_item = MovableStampItem(
                    stamp_pixmap,
                    self.current_page_item,
                    stamp_data,
                    page_size,
                    page_index=self.current_page,
                    history_callback=self._on_stamp_background_toggled,
                    delete_callback=self._on_stamp_delete_requested,
                )
                
                # 저장된 비율을 기반으로 위치 설정
                pos_x = stamp_data.get('x_ratio', 0.0) * page_width
                pos_y = stamp_data.get('y_ratio', 0.0) * page_height
                stamp_item.setPos(pos_x, pos_y)

    def _on_stamp_background_toggled(
        self,
        *,
        page_index: int,
        stamp_data: dict,
        previous_pixmap: QPixmap,
        previous_state: bool,
        new_pixmap: QPixmap,
        new_state: bool,
    ) -> None:
        """콜백: 스탬프 배경 토글 시 히스토리에 기록한다."""
        stamp_data['pixmap'] = new_pixmap
        stamp_data['background_applied'] = new_state
        if 'original_pixmap' not in stamp_data:
            stamp_data['original_pixmap'] = previous_pixmap.copy()

        self._history_stack.append(
            (
                'stamp_background',
                page_index,
                {
                    'stamp_data': stamp_data,
                    'previous_pixmap': previous_pixmap,
                    'previous_state': previous_state,
                    'new_pixmap': new_pixmap,
                    'new_state': new_state,
                },
            )
        )
    
    def _on_stamp_delete_requested(self, page_index: int, stamp_data: dict, stamp_item):
        """콜백: 스탬프 삭제 요청 시 데이터에서 제거하고 히스토리에 기록한다."""
        # 1. _overlay_items에서 해당 stamp_data 찾아서 제거
        if page_index in self._overlay_items:
            try:
                # stamp_data의 참조를 찾아서 제거
                self._overlay_items[page_index].remove(stamp_data)
                print(f"페이지 {page_index + 1}의 스탬프를 데이터에서 제거했습니다. (남은 개수: {len(self._overlay_items[page_index])})")
            except ValueError:
                print(f"경고: 페이지 {page_index + 1}에서 삭제할 스탬프 데이터를 찾을 수 없습니다.")
        
        # 2. scene에서 아이템 제거
        scene = stamp_item.scene()
        if scene:
            scene.removeItem(stamp_item)
        
        # 3. 히스토리에 기록 (되돌리기 지원)
        # stamp_data의 복사본을 저장 (원본 pixmap 포함)
        stamp_data_copy = {
            'pixmap': stamp_data.get('pixmap').copy() if stamp_data.get('pixmap') else None,
            'x_ratio': stamp_data.get('x_ratio', 0.0),
            'y_ratio': stamp_data.get('y_ratio', 0.0),
            'w_ratio': stamp_data.get('w_ratio', 0.0),
            'h_ratio': stamp_data.get('h_ratio', 0.0),
            'original_pixmap': stamp_data.get('original_pixmap').copy() if stamp_data.get('original_pixmap') else None,
            'background_applied': stamp_data.get('background_applied', False),
        }
        
        self._history_stack.append(
            ('delete_stamp', page_index, stamp_data_copy)
        )
        
        print(f"페이지 {page_index + 1}의 스탬프를 삭제했습니다.")

    def _undo_last_action(self):
        """마지막으로 수행한 작업을 되돌린다."""
        if not self._history_stack:
            print("되돌릴 작업이 없습니다.")
            return

        action, page_num, data = self._history_stack.pop()

        if action == 'add_stamp':
            if page_num in self._overlay_items and self._overlay_items[page_num]:
                self._overlay_items[page_num].pop()
                print(f"페이지 {page_num + 1}의 마지막 스탬프를 제거했습니다.")
        
        elif action == 'rotate_page':
            old_rotation = data
            self.page_rotations[page_num] = old_rotation
            # 캐시 제거해서 새로 렌더링하도록 함
            if page_num in self.page_cache:
                del self.page_cache[page_num]
            print(f"페이지 {page_num + 1}의 회전을 되돌렸습니다.")

        elif action in ('crop_page', 'crop_pages'):
            pages = []
            if action == 'crop_pages' and isinstance(data, dict):
                before_bytes = data.get('bytes')
                pages = data.get('pages', [])
            else:
                # 과거 호환: ('crop_page', page_num, bytes)
                before_bytes = data
                if page_num >= 0:
                    pages = [page_num]

            if before_bytes:
                self.renderer.set_pdf_bytes(before_bytes)
                self.page_cache.clear()
                print(
                    "여러 페이지 자르기를 되돌렸습니다."
                    if len(pages) != 1 else f"페이지 {pages[0] + 1}의 자르기를 되돌렸습니다."
                )

            # 현재 페이지가 영향받은 페이지였다면 화면 갱신
            if not pages or self.current_page in pages:
                self.show_page(self.current_page)

        elif action == 'stamp_background':
            info = data or {}
            stamp_data = info.get('stamp_data')
            previous_pixmap = info.get('previous_pixmap')
            previous_state = info.get('previous_state')

            if stamp_data and previous_pixmap is not None:
                stamp_data['pixmap'] = previous_pixmap
                stamp_data['background_applied'] = bool(previous_state)
                if 'original_pixmap' not in stamp_data:
                    stamp_data['original_pixmap'] = previous_pixmap.copy()

                if page_num == self.current_page:
                    self.show_page(self.current_page)
        
        elif action == 'delete_stamp':
            # 삭제된 스탬프를 복원한다
            if data:
                if page_num not in self._overlay_items:
                    self._overlay_items[page_num] = []
                self._overlay_items[page_num].append(data)
                print(f"페이지 {page_num + 1}의 삭제된 스탬프를 복원했습니다.")

        # 현재 보고 있는 페이지의 작업을 되돌렸다면, 화면을 새로고침
        if page_num == self.current_page:
            self.show_page(self.current_page)

    def undo_last_action(self):
        """공개 메서드: 마지막 작업을 되돌린다."""
        self._undo_last_action()

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

        # 되돌리기를 위해 이전 회전 값 저장
        self._history_stack.append(('rotate_page', self.current_page, current_user_rotation))
        
        # 현재 페이지를 다시 렌더링 (회전 적용)
        if self.current_page >= 0:
            # 캐시에서 제거하여 새로 렌더링하도록 함
            if self.current_page in self.page_cache:
                del self.page_cache[self.current_page]
            
            self._show_loading_message()
            self._start_render_job(self.current_page)

    def get_current_pdf_path(self) -> str | None:
        """현재 열려있는 PDF 파일의 경로를 반환한다."""
        return self.pdf_path

    def get_page_rotations(self) -> dict:
        """사용자가 적용한 페이지별 회전 정보를 반환한다."""
        return self.page_rotations

    def set_mail_content(self, content: str):
        """메일 content를 오버레이에 표시"""
        if content:
            self.mail_overlay.set_content(content)
            self.mail_overlay.show_overlay(self.size())  # 처음에는 자동으로 보임
        else:
            self.mail_overlay.hide()
