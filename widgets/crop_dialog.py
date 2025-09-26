from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPixmap, QColor, QBrush, QPen
from PyQt6.QtWidgets import QDialog, QGraphicsScene, QGraphicsRectItem


class CropDialog(QDialog):
    """PDF 페이지 자르기 다이얼로그"""
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "crop_dialog.ui"
        uic.loadUi(str(ui_path), self)
        
        self.scene = QGraphicsScene(self)
        self.page_preview_view.setScene(self.scene)
        self.pixmap_item = None
        self.crop_rect_item = None # 자르기 영역을 위한 아이템
        
        # 버튼 텍스트 설정
        ok_button = self.buttonBox.button(self.buttonBox.StandardButton.Ok)
        if ok_button: ok_button.setText("자르기 적용")
        
        cancel_button = self.buttonBox.button(self.buttonBox.StandardButton.Cancel)
        if cancel_button: cancel_button.setText("취소")

    def set_page_pixmap(self, pixmap: QPixmap):
        """미리보기 Scene에 QPixmap과 자르기 영역을 설정한다."""
        self.scene.clear()
        self.pixmap_item = self.scene.addPixmap(pixmap)

        # --- 반투명 노란색 자르기 영역 추가 ---
        # 1. 자르기 영역의 초기 크기를 이미지와 동일하게 설정
        crop_rect = self.pixmap_item.boundingRect()
        self.crop_rect_item = QGraphicsRectItem(crop_rect)

        # 2. 스타일 설정 (채우기: 반투명 노란색, 테두리: 노란색 점선)
        fill_color = QColor(255, 255, 0, 80)  # R, G, B, Alpha(투명도)
        self.crop_rect_item.setBrush(QBrush(fill_color))
        
        border_color = QColor(255, 200, 0)
        pen = QPen(border_color, 4, Qt.PenStyle.DashLine)
        pen.setCosmetic(True) # 줌 레벨과 상관없이 선 굵기 유지
        self.crop_rect_item.setPen(pen)

        # 3. 사용자가 움직일 수 있도록 설정 (향후 기능 확장용)
        self.crop_rect_item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable)
        self.crop_rect_item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        
        self.scene.addItem(self.crop_rect_item)

    def _fit_view_with_margin(self):
        """뷰 크기에 맞춰 10px 여백을 두고 이미지를 꽉 채운다."""
        if not self.pixmap_item:
            return

        view = self.page_preview_view
        source_rect = self.pixmap_item.boundingRect()
        
        # 뷰포트 크기를 기준으로 10px 여백을 둔 목표 사각형 계산
        margin = 10
        target_rect = view.viewport().rect().adjusted(margin, margin, -margin, -margin)
        
        if source_rect.isEmpty() or target_rect.isEmpty():
            return
            
        # 목표 사각형에 원본 이미지를 꽉 채우기 위한 스케일 계산
        x_scale = target_rect.width() / source_rect.width()
        y_scale = target_rect.height() / source_rect.height()
        scale = min(x_scale, y_scale)
        
        # 수동으로 변환(transform) 적용
        view.resetTransform()
        view.scale(scale, scale)
        view.centerOn(self.pixmap_item)

    def showEvent(self, event):
        """다이얼로그가 처음 표시될 때 호출된다."""
        super().showEvent(event)
        # showEvent 이후에 위젯의 최종 크기가 결정되므로, 여기서 한번 크기를 맞춰준다.
        self._fit_view_with_margin()

    def resizeEvent(self, event):
        """다이얼로그 크기가 변경될 때마다 호출된다."""
        super().resizeEvent(event)
        self._fit_view_with_margin()
