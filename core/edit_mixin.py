from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsView, QStyle


class ViewModeMixin:
    """
    PDF 뷰어의 보기 모드(페이지 맞춤, 폭 맞춤)를 관리하는 믹스인 클래스.

    이 믹스인을 사용하는 클래스는 `pdf_graphics_view` (QGraphicsView)와
    `current_page_item` (QGraphicsPixmapItem) 속성을 가지고 있어야 합니다.
    """

    def set_fit_to_page(self):
        """A4 세로 기준 통일된 뷰로 페이지 전체가 보이도록 조정"""
        self._fit_page_optimized()

    def set_fit_to_width(self):
        """A4 세로 기준 통일된 뷰로 페이지 폭에 맞도록 조정"""
        self._fit_page_optimized()

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
