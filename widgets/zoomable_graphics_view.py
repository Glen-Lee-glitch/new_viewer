from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QGraphicsView


class ZoomableGraphicsView(QGraphicsView):
    """Ctrl + 마우스 휠로 확대/축소, Shift + 휠로 수평 스크롤이 가능한 QGraphicsView"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def wheelEvent(self, event):
        """마우스 휠 이벤트를 재정의하여 확대/축소 및 수평 스크롤 기능 구현"""
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            zoom_in_factor = 1.15
            zoom_out_factor = 1 / zoom_in_factor

            if event.angleDelta().y() > 0:
                zoom_factor = zoom_in_factor
            else:
                zoom_factor = zoom_out_factor
            
            self.scale(zoom_factor, zoom_factor)
        elif event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
            # Shift 키와 함께 휠을 돌리면 수평 스크롤
            h_bar = self.horizontalScrollBar()
            h_bar.setValue(h_bar.value() - event.angleDelta().y())
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        """마우스 클릭 시 Ctrl 키 상태에 따라 드래그 모드 변경"""
        if event.button() == Qt.MouseButton.LeftButton and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """마우스 버튼에서 손을 떼면 드래그 모드를 원래대로 복원"""
        super().mouseReleaseEvent(event)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)



