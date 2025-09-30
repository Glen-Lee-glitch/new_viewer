from PyQt6.QtCore import pyqtSignal, QPointF, QSizeF, Qt, QRectF
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QGraphicsPixmapItem, QMenu

class MovableStampItem(QGraphicsPixmapItem):
    """A stamp item that can be moved and updates its data dictionary when moved."""

    def __init__(self, pixmap, parent_item, stamp_data: dict, page_size: QSizeF):
        super().__init__(pixmap, parent_item)
        self.stamp_data = stamp_data
        self.page_size = page_size
        self._drag_start_pos = QPointF()

        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsSelectable)

    def mousePressEvent(self, event):
        """Stores the starting position of the drag."""
        self._drag_start_pos = self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handles item dragging and constrains movement to the parent's bounds."""
        super().mouseMoveEvent(event)

        # parentItem() is the page QGraphicsPixmapItem
        parent = self.parentItem()
        if not parent:
            return

        # Get the bounding rectangles
        parent_rect = parent.boundingRect()
        item_rect = self.boundingRect()
        
        # Current item position in parent coordinates
        current_pos = self.pos()
        
        # Calculate the next position based on the bounding rect
        new_x = current_pos.x()
        new_y = current_pos.y()

        # Constrain X position
        if new_x < parent_rect.left():
            new_x = parent_rect.left()
        elif new_x + item_rect.width() > parent_rect.right():
            new_x = parent_rect.right() - item_rect.width()
            
        # Constrain Y position
        if new_y < parent_rect.top():
            new_y = parent_rect.top()
        elif new_y + item_rect.height() > parent_rect.bottom():
            new_y = parent_rect.bottom() - item_rect.height()
            
        # Apply the constrained position
        constrained_pos = QPointF(new_x, new_y)
        if current_pos != constrained_pos:
            self.setPos(constrained_pos)

    def mouseReleaseEvent(self, event):
        """When drag is finished, updates the data dictionary if position changed."""
        super().mouseReleaseEvent(event)
        new_pos = self.pos()
        if new_pos != self._drag_start_pos:
            page_width = self.page_size.width()
            page_height = self.page_size.height()
            
            if page_width > 0 and page_height > 0:
                self.stamp_data['x_ratio'] = new_pos.x() / page_width
                self.stamp_data['y_ratio'] = new_pos.y() / page_height
                print(f"Stamp moved, updated ratio: {self.stamp_data['x_ratio']:.3f}, {self.stamp_data['y_ratio']:.3f}")

    def contextMenuEvent(self, event):
        """Creates and shows a context menu on right-click."""
        menu = QMenu()
        apply_background_action = menu.addAction("배경 입히기")

        # 메뉴를 화면의 이벤트 발생 위치에 표시합니다.
        # 나중에 선택된 액션에 따라 기능을 연결할 수 있습니다.
        menu.exec(event.screenPos())

    def paint(self, painter, option, widget=None):
        """Draws the pixmap and a dashed border if the item is selected."""
        # 1. Draw the original pixmap first
        super().paint(painter, option, widget)

        # 2. If the item is selected, draw a dashed border
        if self.isSelected():
            pen = QPen(Qt.GlobalColor.black, 2, Qt.PenStyle.DashLine)
            # Make the pen cosmetic to keep the line width constant regardless of zoom
            pen.setCosmetic(True) 
            painter.setPen(pen)
            
            # Draw rectangle around the bounding rect of the pixmap
            painter.drawRect(self.boundingRect())
