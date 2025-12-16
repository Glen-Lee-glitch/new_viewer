from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PyQt6.QtCore import Qt, pyqtSignal, QPointF
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QBrush, QColor
import pymupdf  # Replaced fitz

class PDFViewer(QGraphicsView):
    # Signal emitted when a point is clicked: (pdf_x, pdf_y)
    point_clicked = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        self.doc = None
        self.current_page_num = 0
        self.pixmap_item = None
        self.scale_factor = 1.0
        
        # Optimization for smooth panning/zooming
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def load_document(self, file_path):
        """Loads a PDF document."""
        if self.doc:
            self.doc.close()
        
        self.doc = pymupdf.open(file_path)
        self.current_page_num = 0
        self.show_page(self.current_page_num)

    def show_page(self, page_num):
        """Renders and displays the specified page number."""
        if not self.doc or page_num < 0 or page_num >= len(self.doc):
            return

        self.current_page_num = page_num
        page = self.doc[page_num]
        
        # Render page to image (zoom=2 for better quality)
        zoom = 2.0
        mat = pymupdf.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to QImage
        img_format = QImage.Format.Format_RGB888
        image = QImage(pix.samples, pix.width, pix.height, pix.stride, img_format)
        
        # Convert to QPixmap
        pixmap = QPixmap.fromImage(image)
        
        # Clear previous scene content
        self.scene.clear()
        
        # Add new pixmap
        self.pixmap_item = self.scene.addPixmap(pixmap)
        
        # Store scale factor to convert back to PDF coordinates
        # (Since we rendered at zoom=2.0)
        self.scale_factor = zoom

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if we are holding a modifier key (e.g., Ctrl) to avoid conflict with panning if needed
            # But currently DragMode.ScrollHandDrag handles left click drag. 
            # We need to distinguish click from drag. 
            # For simplicity, let's use Right Click to add points, or checking if the mouse moved.
            # Or temporarily switch modes. 
            
            # Better approach: If in 'add point' mode or if we just single click without moving.
            # Let's use Right Click for adding points to avoid conflict with ScrollHandDrag (Left Click)
            pass
            
        if event.button() == Qt.MouseButton.RightButton:
             scene_pos = self.mapToScene(event.position().toPoint())
             
             # Check if click is inside the PDF page
             if self.pixmap_item and self.pixmap_item.isUnderMouse():
                 # Convert scene coordinates to original PDF coordinates
                 pdf_x = scene_pos.x() / self.scale_factor
                 pdf_y = scene_pos.y() / self.scale_factor
                 
                 self.point_clicked.emit(pdf_x, pdf_y)
                 
                 # Draw a temporary marker
                 self.add_marker(scene_pos.x(), scene_pos.y())

        super().mousePressEvent(event)

    def add_marker(self, x, y):
        """Visually marks a point on the scene."""
        radius = 5
        pen = QPen(Qt.GlobalColor.red)
        brush = QBrush(Qt.GlobalColor.red)
        self.scene.addEllipse(x - radius, y - radius, radius * 2, radius * 2, pen, brush)

    def wheelEvent(self, event):
        """Zoom in/out with Ctrl + Wheel."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            zoom_in_factor = 1.25
            zoom_out_factor = 1 / zoom_in_factor

            if event.angleDelta().y() > 0:
                self.scale(zoom_in_factor, zoom_in_factor)
            else:
                self.scale(zoom_out_factor, zoom_out_factor)
        else:
            super().wheelEvent(event)

