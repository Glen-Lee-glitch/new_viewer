from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsView, QStyle


class ViewModeMixin:
    """
    PDF 뷰어의 보기 모드(페이지 맞춤, 폭 맞춤)를 관리하는 믹스인 클래스.

    이 믹스인을 사용하는 클래스는 `pdf_graphics_view` (QGraphicsView)와
    `scene` (QGraphicsScene) 속성을 가지고 있어야 합니다.
    """

    def set_fit_to_page(self):
        """페이지 전체가 보이도록 뷰를 조정합니다 (Fit to Page)."""
        if not hasattr(self, 'pdf_graphics_view') or not hasattr(self, 'scene') or not self.scene or not self.scene.items():
            return

        view: QGraphicsView = self.pdf_graphics_view
        
        # fitInView는 스크롤바를 고려하지만, 명확하게 보이지 않도록 정책 설정
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # fitInView는 내부적으로 transform을 리셋하고 적용합니다.
        view.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def set_fit_to_width(self):
        """페이지의 폭이 뷰어의 폭에 맞도록 뷰를 조정합니다 (Fit to Width)."""
        if not hasattr(self, 'pdf_graphics_view') or not hasattr(self, 'scene') or not self.scene or not self.scene.items():
            return

        view: QGraphicsView = self.pdf_graphics_view
        scene_rect = self.scene.itemsBoundingRect()

        if scene_rect.width() == 0:
            return

        # 폭 맞춤 시에는 세로 스크롤바가 필요할 수 있으므로 정책을 다시 설정합니다.
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # 뷰포트의 가용 너비 계산
        viewport_width = view.viewport().width()
        
        # 스케일 팩터 초기 계산
        scale_factor = viewport_width / scene_rect.width()
        
        # 스케일 적용 후 세로 스크롤바가 생길 것으로 예상되면, 스크롤바 폭을 제외하고 다시 계산합니다.
        scaled_height = scene_rect.height() * scale_factor
        if scaled_height > view.viewport().height():
            scrollbar_width = view.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
            viewport_width -= scrollbar_width
        
        # 최종 스케일 팩터 계산
        scale_factor = viewport_width / scene_rect.width()

        # 기존 변환을 리셋하고 새 스케일을 적용합니다.
        transform = QTransform()
        transform.scale(scale_factor, scale_factor)
        view.setTransform(transform)
