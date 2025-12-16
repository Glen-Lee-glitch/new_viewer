import sys
import json
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QFileDialog, QDockWidget, 
                             QListWidget, QWidget, QVBoxLayout, QPushButton, 
                             QInputDialog, QMessageBox, QToolBar, QTabWidget,
                             QTableWidget, QTableWidgetItem, QHBoxLayout, QLabel, 
                             QSpinBox, QFontComboBox, QDialog, QComboBox, QLineEdit, QDialogButtonBox,
                             QDateEdit)
from PyQt6.QtGui import QAction, QIcon, QFont
from PyQt6.QtCore import Qt, QDate
from pdf_viewer import PDFViewer
import pymupdf  # Replaced fitz
import re

class FieldSelectionDialog(QDialog):
    def __init__(self, parent=None, items=None):
        super().__init__(parent)
        self.setWindowTitle("Add Field")
        self.setFixedWidth(300)
        
        self.layout = QVBoxLayout(self)
        
        # Label
        self.layout.addWidget(QLabel("Select Field Name:"))
        
        # ComboBox
        self.combo = QComboBox()
        if items:
            self.combo.addItems(items)
        self.layout.addWidget(self.combo)
        
        # Direct Input Field (Hidden by default)
        self.input_label = QLabel("Enter Custom Name:")
        self.input_field = QLineEdit()
        self.input_label.hide()
        self.input_field.hide()
        
        self.layout.addWidget(self.input_label)
        self.layout.addWidget(self.input_field)
        
        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)
        
        # Signals
        self.combo.currentTextChanged.connect(self.on_selection_change)
        
    def on_selection_change(self, text):
        if text == "직접 입력":
            self.input_label.show()
            self.input_field.show()
            self.input_field.setFocus()
        else:
            self.input_label.hide()
            self.input_field.hide()
            
    def get_result(self):
        if self.combo.currentText() == "직접 입력":
            return self.input_field.text()
        return self.combo.currentText()

class CoordinatorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.layout = QHBoxLayout(self)
        
        # Left side: PDF Viewer
        self.viewer_container = QWidget()
        self.viewer_layout = QVBoxLayout(self.viewer_container)
        self.viewer = PDFViewer()
        self.viewer.point_clicked.connect(self.handle_point_click)
        self.viewer_layout.addWidget(self.viewer)
        
        # Toolbar for Coordinator
        self.toolbar = QToolBar("Coordinator Toolbar")
        self.open_action = QAction("Open PDF", self)
        self.open_action.triggered.connect(self.open_pdf)
        self.toolbar.addAction(self.open_action)
        
        self.save_action = QAction("Save JSON", self)
        self.save_action.triggered.connect(self.save_json)
        self.toolbar.addAction(self.save_action)
        
        self.viewer_layout.insertWidget(0, self.toolbar)
        
        # Right side: Points List
        self.points_list = QListWidget()
        self.points_list.setMaximumWidth(300)
        
        self.layout.addWidget(self.viewer_container)
        self.layout.addWidget(self.points_list)
        
        # Data
        self.points_data = []
        self.current_pdf_path = None

    def open_pdf(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF File", "", "PDF Files (*.pdf)"
        )
        
        if file_path:
            self.current_pdf_path = file_path
            self.viewer.load_document(file_path)
            self.points_data = []
            self.points_list.clear()
            # We need to access MainWindow to show status message, or use a local label
            # For simplicity, we can print or ignore, or find parent window.
            # print(f"Loaded: {file_path}")

    def handle_point_click(self, x, y):
        # List of predefined fields
        items = [
            "제조사_담장자", "제조사_연락처", "구매자_이름", "신청번호",
            "구매자_생년월일", "구매자_연락처", "차량명", "차대번호",
            "차량번호", "차량출고일", "직접 입력"
        ]
        
        dialog = FieldSelectionDialog(self, items)
        if dialog.exec():
            name = dialog.get_result()
            
            if name:
                point_info = {
                    "id": name,
                    "page": self.viewer.current_page_num + 1,
                    "x": round(x, 2),
                    "y": round(y, 2),
                    "description": ""
                }
                
                self.points_data.append(point_info)
                self.points_list.addItem(f"{name}: ({point_info['x']}, {point_info['y']})")

    def save_json(self):
        if not self.points_data:
            QMessageBox.warning(self, "No Data", "No points marked to save.")
            return
            
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save JSON File", "", "JSON Files (*.json)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.points_data, f, indent=4, ensure_ascii=False)
                QMessageBox.information(self, "Success", f"Saved {len(self.points_data)} points to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file: {e}")

class FillerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        
        # Top Controls
        controls_layout = QHBoxLayout()
        
        self.btn_load_json = QPushButton("Load Template (JSON)")
        self.btn_load_json.clicked.connect(self.load_json)
        
        self.btn_load_pdf = QPushButton("Load PDF")
        self.btn_load_pdf.clicked.connect(self.load_pdf)
        
        controls_layout.addWidget(self.btn_load_json)
        controls_layout.addWidget(self.btn_load_pdf)
        
        # Font Settings
        self.font_combo = QFontComboBox()
        # Default to Malgun Gothic for Korean support
        self.font_combo.setCurrentFont(QFont("Malgun Gothic"))
        
        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(5, 72)
        self.spin_font_size.setValue(10)
        
        controls_layout.addWidget(QLabel("Font:"))
        controls_layout.addWidget(self.font_combo)
        controls_layout.addWidget(QLabel("Size:"))
        controls_layout.addWidget(self.spin_font_size)
        
        self.layout.addLayout(controls_layout)
        
        # File Labels
        self.lbl_json_path = QLabel("No JSON loaded")
        self.lbl_pdf_path = QLabel("No PDF loaded")
        self.layout.addWidget(self.lbl_json_path)
        self.layout.addWidget(self.lbl_pdf_path)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Field ID", "Description", "Value"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.layout.addWidget(self.table)
        
        # Generate Button
        self.btn_generate = QPushButton("Generate Filled PDF")
        self.btn_generate.clicked.connect(self.generate_pdf)
        self.layout.addWidget(self.btn_generate)
        
        # Data
        self.json_data = []
        self.current_json_path = None
        self.current_pdf_path = None

    def load_json(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Template JSON", "", "JSON Files (*.json)"
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.json_data = json.load(f)
                self.current_json_path = file_path
                self.lbl_json_path.setText(f"JSON: {os.path.basename(file_path)}")
                self.populate_table()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load JSON: {e}")

    def load_pdf(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF File", "", "PDF Files (*.pdf)"
        )
        if file_path:
            self.current_pdf_path = file_path
            self.lbl_pdf_path.setText(f"PDF: {os.path.basename(file_path)}")

    def populate_table(self):
        self.table.setRowCount(len(self.json_data))
        for row, item in enumerate(self.json_data):
            self.table.setItem(row, 0, QTableWidgetItem(item.get("id", "")))
            self.table.setItem(row, 1, QTableWidgetItem(item.get("description", "")))
            self.table.setItem(row, 2, QTableWidgetItem("")) # Empty value initially

    def generate_pdf(self):
        if not self.current_pdf_path or not self.json_data:
            QMessageBox.warning(self, "Missing Files", "Please load both JSON template and PDF file.")
            return

        # Get values from table
        input_values = {}
        for row in range(self.table.rowCount()):
            field_id = self.table.item(row, 0).text()
            value = self.table.item(row, 2).text()
            input_values[field_id] = value

        # Ask where to save
        output_path, _ = QFileDialog.getSaveFileName(
            self, "Save Filled PDF", "", "PDF Files (*.pdf)"
        )
        
        if not output_path:
            return

        try:
            # Font handling
            font_name = self.font_combo.currentText()
            font_size = self.spin_font_size.value()
            
            font_file = None
            # Common Korean fonts on Windows
            import matplotlib.font_manager as fm
            system_fonts = fm.findSystemFonts(fontpaths=None, fontext='ttf')
            
            selected_font_path = None
            for path in system_fonts:
                if font_name.lower() in path.lower() or os.path.basename(path).lower().startswith(font_name.lower().replace(" ", "")):
                    selected_font_path = path
                    break
            
            if not selected_font_path:
                 # Fallback to Malgun Gothic if available
                 if os.path.exists("C:/Windows/Fonts/malgun.ttf"):
                     selected_font_path = "C:/Windows/Fonts/malgun.ttf"

            self.generate_pdf_corrected(output_path, selected_font_path, font_size)
            QMessageBox.information(self, "Done", f"PDF saved to {output_path}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate PDF: {e}")
            import traceback
            traceback.print_exc()

    def generate_pdf_corrected(self, output_path, font_path, font_size):
        # Helper to do the actual generation cleanly
        doc = pymupdf.open(self.current_pdf_path)
        
        font_obj = None
        if font_path:
            try:
                font_obj = pymupdf.Font(fontfile=font_path)
            except:
                pass
        
        input_values = {}
        for row in range(self.table.rowCount()):
            input_values[self.table.item(row, 0).text()] = self.table.item(row, 2).text()

        for item in self.json_data:
            page_num = item.get("page", 1) - 1
            if page_num < 0 or page_num >= len(doc):
                continue
                
            page = doc[page_num]
            text = input_values.get(item["id"], "")
            if not text:
                continue
            
            x = item["x"]
            y = item["y"]
            
            start_x = x
            if font_obj:
                width = font_obj.text_length(text, fontsize=font_size)
                start_x = x - (width / 2)
                # insert_text with fontfile
                page.insert_text((start_x, y), text, fontfile=font_path, fontsize=font_size, color=(0, 0, 0))
            else:
                # Fallback to default font, basic centering estimation (not perfect)
                # pymupdf default font is Helvetica usually
                width = pymupdf.get_text_length(text, fontsize=font_size) 
                start_x = x - (width / 2)
                page.insert_text((start_x, y), text, fontsize=font_size, color=(0, 0, 0))
                
        doc.save(output_path)


class ShippingDateWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        
        # 기본 설정
        self.base_pdf_path = "출고배정표.pdf"
        self.image_path = None
        self.image_rect_coords = {'x0': 90.0, 'y0': 191.2, 'x1': 530.9, 'y1': 684.9}
        
        # UI 구성
        
        # 1. Base PDF 상태 표시
        self.lbl_base_pdf = QLabel(f"Base PDF: {self.base_pdf_path}")
        self.check_base_pdf()
        self.layout.addWidget(self.lbl_base_pdf)

        # 2. Image Selection
        img_layout = QHBoxLayout()
        self.btn_select_img = QPushButton("Select Image (PNG)")
        self.btn_select_img.clicked.connect(self.select_image)
        self.lbl_img_path = QLabel("No image selected")
        img_layout.addWidget(self.btn_select_img)
        img_layout.addWidget(self.lbl_img_path)
        self.layout.addLayout(img_layout)
        
        # 3. Date Selection
        date_layout = QHBoxLayout()
        date_layout.addWidget(QLabel("출고예정일:"))
        self.date_edit = QDateEdit()
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)
        date_layout.addWidget(self.date_edit)
        self.layout.addLayout(date_layout)
        
        # 4. Generate Button
        self.btn_generate = QPushButton("Generate '출고배정표_완료.pdf'")
        self.btn_generate.clicked.connect(self.generate_pdf)
        self.layout.addWidget(self.btn_generate)
        
        self.layout.addStretch()

    def check_base_pdf(self):
        if os.path.exists(self.base_pdf_path):
            self.lbl_base_pdf.setStyleSheet("color: green")
            self.lbl_base_pdf.setText(f"Base PDF Found: {self.base_pdf_path}")
        else:
            self.lbl_base_pdf.setStyleSheet("color: red")
            self.lbl_base_pdf.setText(f"Base PDF Not Found: {self.base_pdf_path} (Please place it in the same directory)")

    def select_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Image Files (*.png *.jpg *.jpeg)"
        )
        if file_path:
            self.image_path = file_path
            self.lbl_img_path.setText(os.path.basename(file_path))

    def generate_pdf(self):
        if not os.path.exists(self.base_pdf_path):
            QMessageBox.critical(self, "Error", f"Base PDF not found: {self.base_pdf_path}")
            return
            
        if not self.image_path:
            QMessageBox.warning(self, "Missing Image", "Please select an image file.")
            return

        target_date_str = self.date_edit.date().toString("yyyy-MM-dd")
        output_path = "출고배정표_완료.pdf"
        
        try:
            doc = pymupdf.open(self.base_pdf_path)
            
            # --- 날짜 업데이트 로직 ---
            font_path = "C:/Windows/Fonts/malgunbd.ttf"
            fontname = "malgunbd"
            if not os.path.exists(font_path):
                font_path = "C:/Windows/Fonts/malgun.ttf"
                fontname = "malgun"
            
            for page in doc:
                blocks = page.get_text("blocks")
                for block in blocks:
                    original_rect = pymupdf.Rect(block[:4])
                    text = block[4].strip()
                    
                    if "출고예정일" in text:
                        # 텍스트 지우기
                        redact_rect = pymupdf.Rect(original_rect.x0 - 5, original_rect.y0 - 5, 
                                               original_rect.x1 + 5, original_rect.y1 + 5)
                        page.add_redact_annot(redact_rect, fill=(1, 1, 1))
                        page.apply_redactions()
                        
                        # 새 텍스트 입력
                        new_text_content = f"출고예정일 : {target_date_str}"
                        insert_rect = pymupdf.Rect(
                            original_rect.x0,
                            original_rect.y0 - 2,
                            original_rect.x0 + 250,
                            original_rect.y1 + 10
                        )
                        
                        page.insert_textbox(
                            insert_rect, 
                            new_text_content, 
                            fontsize=12,
                            fontname=fontname,
                            fontfile=font_path,
                            align=0,
                            color=(0, 0, 0)
                        )

            # --- 이미지 삽입 로직 ---
            if len(doc) > 0:
                page = doc[0]
                image_rect = pymupdf.Rect(
                    self.image_rect_coords['x0'],
                    self.image_rect_coords['y0'],
                    self.image_rect_coords['x1'],
                    self.image_rect_coords['y1']
                )
                page.insert_image(image_rect, filename=self.image_path)
            
            # 폰트 서브셋팅 (사용되지 않는 글자 데이터 제거 - 용량 대폭 감소)
            doc.subset_fonts()
            
            # 압축 저장: garbage=4 (최대 최적화), deflate=True (압축), clean=True (구조 정리)
            doc.save(output_path, garbage=4, deflate=True, clean=True)
            doc.close()
            
            QMessageBox.information(self, "Success", f"Successfully generated: {output_path}\n(Highly Compressed)")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate PDF: {e}")
            import traceback
            traceback.print_exc()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("PDF Tool (Picker & Filler)")
        self.resize(1200, 800)
        
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        self.coordinator = CoordinatorWidget()
        self.filler = FillerWidget()
        self.shipping_date = ShippingDateWidget()
        
        self.tabs.addTab(self.coordinator, "Coordinate Picker")
        self.tabs.addTab(self.filler, "PDF Filler")
        self.tabs.addTab(self.shipping_date, "Shipping Date")

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
