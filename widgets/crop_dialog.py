from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import Qt, QRectF, QPointF, QSizeF, QMarginsF
from PyQt6.QtGui import QPixmap, QColor, QBrush, QPen
from PyQt6.QtWidgets import QDialog, QGraphicsScene, QGraphicsRectItem

A4_PORTRAIT_RATIO = 21.0 / 29.7  # width / height

class ResizableCropRectItem(QGraphicsRectItem):
    """오른쪽 하단 핸들로만 크기 조절이 가능한, 고정 종횡비의 자르기 영역 아이템"""
    
    handle_size = 20.0 # 핸들 크기
    
    def __init__(self, rect):
        super().__init__(rect)
        self._is_resizing = False
        
        # 스타일 설정
        fill_color = QColor(255, 255, 0, 80)
        self.setBrush(QBrush(fill_color))
        
        border_color = QColor(255, 200, 0)
        pen = QPen(border_color, 4, Qt.PenStyle.DashLine)
        pen.setCosmetic(True) # 줌 레벨과 상관없이 선 굵기 유지
        self.setPen(pen)
        
        # 마우스 호버 이벤트를 받도록 설정
        self.setAcceptHoverEvents(True)
        # ItemIsMovable 플래그를 추가하여 전체 이동 허용
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable)

    def set_bounds(self, bounds_rect: QRectF):
        self._bounds_rect = bounds_rect

    def handle_rect(self) -> QRectF:
        """리사이즈 핸들의 사각형 영역을 반환한다."""
        rect = self.rect()
        return QRectF(
            rect.right() - self.handle_size,
            rect.bottom() - self.handle_size,
            self.handle_size,
            self.handle_size
        )

    def hoverMoveEvent(self, event):
        """핸들 위에 마우스가 올라가면 커서 모양을 변경한다."""
        if self.handle_rect().contains(event.pos()):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        """핸들을 클릭했을 때 리사이징을 시작하고, 아닐 경우 일반 이동을 처리한다."""
        if self.handle_rect().contains(event.pos()):
            self._is_resizing = True
            event.accept()
        else:
            self._is_resizing = False
            # 크기 조절이 아닐 경우, 부모 클래스의 이동 로직을 사용
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """마우스를 드래그할 때 크기 조절 또는 이동을 처리한다."""
        if self._is_resizing:
            self.prepareGeometryChange()
            
            current_rect = self.rect()
            new_bottom_right = event.pos()

            new_top_left = current_rect.topLeft()
            new_width = new_bottom_right.x() - new_top_left.x()
            new_height = new_bottom_right.y() - new_top_left.y()

            if new_width <= 0: new_width = 1
            if new_height <= 0: new_height = 1

            if new_width / new_height > A4_PORTRAIT_RATIO:
                new_height = new_width / A4_PORTRAIT_RATIO
            else:
                new_width = new_height * A4_PORTRAIT_RATIO

            new_rect = QRectF(new_top_left, QSizeF(new_width, new_height))
            
            if hasattr(self, '_bounds_rect') and self._bounds_rect and not self._bounds_rect.contains(new_rect):
                if new_rect.right() > self._bounds_rect.right():
                    new_width = self._bounds_rect.right() - new_rect.left()
                    new_height = new_width / A4_PORTRAIT_RATIO
                if new_rect.bottom() > self._bounds_rect.bottom():
                    new_height = self._bounds_rect.bottom() - new_rect.top()
                    new_width = new_height * A4_PORTRAIT_RATIO
                new_rect.setSize(QSizeF(new_width, new_height))

            self.setRect(new_rect)
        else:
            super().mouseMoveEvent(event)
            
            if hasattr(self, '_bounds_rect') and self._bounds_rect:
                # sceneBoundingRect()는 아이템의 위치(pos)와 사각형(rect)을 모두 고려한 절대 좌표를 반환
                scene_bounds = self.sceneBoundingRect()
                if scene_bounds.left() < self._bounds_rect.left():
                    self.setX(self.x() + self._bounds_rect.left() - scene_bounds.left())
                if scene_bounds.top() < self._bounds_rect.top():
                    self.setY(self.y() + self._bounds_rect.top() - scene_bounds.top())
                if scene_bounds.right() > self._bounds_rect.right():
                    self.setX(self.x() + self._bounds_rect.right() - scene_bounds.right())
                if scene_bounds.bottom() > self._bounds_rect.bottom():
                    self.setY(self.y() + self._bounds_rect.bottom() - scene_bounds.bottom())

    def mouseReleaseEvent(self, event):
        """마우스 버튼을 놓으면 리사이징을 종료한다."""
        self._is_resizing = False
        super().mouseReleaseEvent(event)

    def paint(self, painter, option, widget=None):
        """사각형과 리사이즈 핸들을 그린다."""
        super().paint(painter, option, widget)
        
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor(255, 200, 0)))
        painter.setPen(QPen(QColor(255, 255, 255), 2, Qt.PenStyle.SolidLine))
        
        painter.drawEllipse(self.handle_rect())

class CropDialog(QDialog):
    """PDF 페이지 자르기 다이얼로그"""
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "crop_dialog.ui"
        uic.loadUi(str(ui_path), self)
        
        self.scene = QGraphicsScene(self)
        self.page_preview_view.setScene(self.scene)
        self.pixmap_item = None
        self.crop_rect_item = None
        
        ok_button = self.buttonBox.button(self.buttonBox.StandardButton.Ok)
        if ok_button: ok_button.setText("자르기 적용")
        
        cancel_button = self.buttonBox.button(self.buttonBox.StandardButton.Cancel)
        if cancel_button: cancel_button.setText("취소")

    def set_page_pixmap(self, pixmap: QPixmap):
        """미리보기 Scene에 QPixmap과 A4 비율의 자르기 영역을 설정한다."""
        self.scene.clear()
        self.pixmap_item = self.scene.addPixmap(pixmap)
        page_rect = self.pixmap_item.boundingRect()
        
        # 1. 페이지 중앙에 95% 크기의 컨테이너 영역 계산
        container_rect = page_rect.marginsRemoved(
            QMarginsF(page_rect.width() * 0.025, page_rect.height() * 0.025,
                      page_rect.width() * 0.025, page_rect.height() * 0.025)
        )

        # 2. 컨테이너에 맞는 A4 세로 비율의 사각형 크기 계산
        container_ratio = container_rect.width() / container_rect.height()
        if container_ratio > A4_PORTRAIT_RATIO:
            crop_height = container_rect.height()
            crop_width = crop_height * A4_PORTRAIT_RATIO
        else:
            crop_width = container_rect.width()
            crop_height = crop_width / A4_PORTRAIT_RATIO

        # 3. 페이지 중앙에 배치될 초기 사각형 좌표 계산
        crop_top_left = page_rect.center() - QPointF(crop_width / 2, crop_height / 2)
        initial_crop_rect = QRectF(crop_top_left, QSizeF(crop_width, crop_height))

        self.crop_rect_item = ResizableCropRectItem(QRectF(0, 0, initial_crop_rect.width(), initial_crop_rect.height()))
        self.crop_rect_item.set_bounds(page_rect)
        self.crop_rect_item.setPos(initial_crop_rect.topLeft())
        self.scene.addItem(self.crop_rect_item)


    def _fit_view_with_margin(self):
        """뷰 크기에 맞춰 10px 여백을 두고 이미지를 꽉 채운다."""
        if not self.pixmap_item:
            return

        view = self.page_preview_view
        source_rect = self.pixmap_item.boundingRect()
        margin = 10
        target_rect = view.viewport().rect().adjusted(margin, margin, -margin, -margin)
        
        if source_rect.isEmpty() or target_rect.isEmpty():
            return
            
        x_scale = target_rect.width() / source_rect.width()
        y_scale = target_rect.height() / source_rect.height()
        scale = min(x_scale, y_scale)
        
        view.resetTransform()
        view.scale(scale, scale)
        view.centerOn(self.pixmap_item)

    def showEvent(self, event):
        """다이얼로그가 처음 표시될 때 호출된다."""
        super().showEvent(event)
        self._fit_view_with_margin()

    def resizeEvent(self, event):
        """다이얼로그 크기가 변경될 때마다 호출된다."""
        super().resizeEvent(event)
        self._fit_view_with_margin()

    def get_crop_rect_in_page_coords(self) -> QRectF:
        """페이지 좌표계에서의 자르기 영역 사각형을 반환한다."""
        if not self.crop_rect_item or not self.pixmap_item:
            return QRectF()
        
        # sceneBoundingRect는 아이템의 위치(pos)와 사각형(rect)을 모두 고려한 절대 좌표를 반환
        crop_scene_rect = self.crop_rect_item.sceneBoundingRect()
        page_rect = self.pixmap_item.boundingRect()
        
        if page_rect.width() == 0 or page_rect.height() == 0:
            return QRectF()
            
        # 페이지 좌표계로 정규화 (0.0 ~ 1.0)
        normalized_rect = QRectF(
            (crop_scene_rect.x() - page_rect.x()) / page_rect.width(),
            (crop_scene_rect.y() - page_rect.y()) / page_rect.height(),
            crop_scene_rect.width() / page_rect.width(),
            crop_scene_rect.height() / page_rect.height()
        )
        
        # 정규화된 값이 0.0 ~ 1.0 범위 내에 있도록 보정
        final_rect = normalized_rect.intersected(QRectF(0, 0, 1, 1))
        
        return final_rect
