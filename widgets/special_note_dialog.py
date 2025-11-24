import sys
import os
from PyQt6.QtWidgets import (
    QDialog, QApplication, QCheckBox, QLineEdit, QGridLayout, QLabel, QMessageBox
)
from PyQt6.uic import loadUi

# Ensure we can import from core/widgets if needed in the future
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class SpecialNoteDialog(QDialog):
    # Define detailed items as class constants
    MISSING_DOCS_ITEMS = [
        '신청서1p', '신청서2p', '계약서1p', '계약서4p', 
        '초본', '등본', '가족', '지납세', '지세과', '기타'
    ]
    
    REQ_ITEMS = [
        '전입일', '중복', '거주지 다름', '기타'
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Load the UI file
        ui_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "special_note_dialog.ui")
        loadUi(ui_path, self)
        
        # Dynamic Widget Storage
        self.missing_checkboxes = {}  # {name: {'cb': QCheckBox, 'le': QLineEdit|None}}
        self.req_checkboxes = {}      # {name: {'cb': QCheckBox, 'le': QLineEdit|None}}
        
        # Initialize Dynamic UI
        self._init_dynamic_ui()

        # Connect Main Checkboxes to Visibility Logic
        self.checkBox_2.toggled.connect(self.update_ui_state)  # 서류미비
        self.checkBox.toggled.connect(self.update_ui_state)    # 요건
        self.checkBox_3.toggled.connect(self.update_ui_state)  # 기타
        
        # Initialize state (hide all sub-frames initially)
        self.update_ui_state()

        # Connect close button
        self.pushButton_2.clicked.connect(self.close)

        # Connect Send button
        self.pushButton.clicked.connect(self.on_send_clicked)

    def _init_dynamic_ui(self):
        """Generate checkboxes dynamically for Missing Docs and Requirements."""
        # Setup Missing Documents Frame (checkBox_2)
        self._setup_checkbox_grid(
            self.gridLayout_missing, 
            "↳ 서류미비 상세:", 
            self.MISSING_DOCS_ITEMS, 
            self.missing_checkboxes
        )
        
        # Setup Requirements Frame (checkBox)
        self._setup_checkbox_grid(
            self.gridLayout_req, 
            "↳ 요건 상세:", 
            self.REQ_ITEMS, 
            self.req_checkboxes
        )

    def _setup_checkbox_grid(self, layout: QGridLayout, label_text: str, items: list, storage: dict):
        """Helper to populate a grid layout with checkboxes and optional 'Other' input."""
        
        # Add Label at (0, 0) spanning multiple columns
        label = QLabel(label_text)
        label.setStyleSheet("color: gray;")
        layout.addWidget(label, 0, 0, 1, 4) 

        row = 1
        col = 0
        max_col = 4 # Number of columns for checkboxes

        for item_text in items:
            cb = QCheckBox(item_text)
            storage[item_text] = {'cb': cb, 'le': None}
            
            # Place checkbox
            layout.addWidget(cb, row, col)
            
            # If item is "기타", add a LineEdit
            if item_text == "기타":
                le = QLineEdit()
                le.setPlaceholderText("직접 입력")
                le.setVisible(False) # Initially hidden
                storage[item_text]['le'] = le
                
                # Connect toggle signal to show/hide LineEdit
                cb.toggled.connect(lambda checked, line_edit=le: line_edit.setVisible(checked))
                
                # Place LineEdit next to "기타" checkbox or wrapped
                if col < max_col - 1:
                    col += 1
                    layout.addWidget(le, row, col, 1, 2) # Span 2 columns
                    col += 1 # Skip one more due to span
                else:
                    # New row for LineEdit if no space
                    row += 1
                    layout.addWidget(le, row, 0, 1, 4)
                    col = max_col # Force next loop to new row if there were more items
            
            col += 1
            if col >= max_col:
                col = 0
                row += 1

    def update_ui_state(self):
        """Show/Hide sub-frames based on main checkbox state."""
        self.sub_frame_missing.setVisible(self.checkBox_2.isChecked())
        self.sub_frame_req.setVisible(self.checkBox.isChecked())
        self.sub_frame_other.setVisible(self.checkBox_3.isChecked())

    def validate_selection(self):
        """Check if at least one category is selected and required details are filled."""
        is_missing_checked = self.checkBox_2.isChecked()
        is_req_checked = self.checkBox.isChecked()
        is_other_checked = self.checkBox_3.isChecked()

        # 1. Check if any main category is selected
        if not (is_missing_checked or is_req_checked or is_other_checked):
            QMessageBox.warning(self, "경고", "사유 대분류를 최소 하나 이상 선택해주세요.")
            return False

        # 2. Check Missing Documents Details
        if is_missing_checked:
            any_detail_checked = False
            for name, widgets in self.missing_checkboxes.items():
                if widgets['cb'].isChecked():
                    any_detail_checked = True
                    # If 'Other' is checked, ensure text is entered
                    if name == '기타' and widgets['le']:
                         if not widgets['le'].text().strip():
                             QMessageBox.warning(self, "경고", "서류미비 - '기타' 사유를 입력해주세요.")
                             widgets['le'].setFocus()
                             return False
            
            if not any_detail_checked:
                QMessageBox.warning(self, "경고", "서류미비의 상세 사유를 하나 이상 선택해주세요.")
                return False

        # 3. Check Requirements Details
        if is_req_checked:
            any_detail_checked = False
            for name, widgets in self.req_checkboxes.items():
                if widgets['cb'].isChecked():
                    any_detail_checked = True
                    if name == '기타' and widgets['le']:
                         if not widgets['le'].text().strip():
                             QMessageBox.warning(self, "경고", "요건 - '기타' 사유를 입력해주세요.")
                             widgets['le'].setFocus()
                             return False
            
            if not any_detail_checked:
                QMessageBox.warning(self, "경고", "요건의 상세 사유를 하나 이상 선택해주세요.")
                return False

        # 4. Check Other (Main) Details
        if is_other_checked:
            if not self.lineEdit_other_detail.text().strip():
                QMessageBox.warning(self, "경고", "기타 상세 사유를 입력해주세요.")
                self.lineEdit_other_detail.setFocus()
                return False

        return True

    def on_send_clicked(self):
        """Handle send button click: gather data, print debug info, and close."""
        if not self.validate_selection():
            return

        results = self.get_selected_data()
        
        print("=== DEBUG: Selected Items ===")
        print(f"RN: {self.RN_lineEdit.text()}")
        print(f"서류미비: {results['missing']}")
        print(f"요건: {results['requirements']}")
        print(f"기타: {results['other']}")
        print("=============================")
        
        self.accept() # Close dialog with Accepted result

    def get_selected_data(self):
        """Collect all selected options."""
        data = {
            'missing': [],
            'requirements': [],
            'other': None
        }

        # 1. Missing Documents (서류미비)
        if self.checkBox_2.isChecked():
            for name, widgets in self.missing_checkboxes.items():
                cb = widgets['cb']
                le = widgets['le']
                if cb.isChecked():
                    if name == '기타' and le:
                        detail = le.text().strip()
                        if detail:
                            # Use input text directly instead of "기타(text)"
                            data['missing'].append(detail)
                        else:
                             data['missing'].append("기타(내용없음)")
                    else:
                        data['missing'].append(name)

        # 2. Requirements (요건)
        if self.checkBox.isChecked():
            for name, widgets in self.req_checkboxes.items():
                cb = widgets['cb']
                le = widgets['le']
                if cb.isChecked():
                    if name == '기타' and le:
                        detail = le.text().strip()
                        if detail:
                            # Use input text directly instead of "기타(text)"
                            data['requirements'].append(detail)
                        else:
                             data['requirements'].append("기타(내용없음)")
                    else:
                        data['requirements'].append(name)
        
        # 3. Other (기타 - 대분류)
        if self.checkBox_3.isChecked():
             text = self.lineEdit_other_detail.text().strip()
             if text:
                 data['other'] = text
             else:
                 data['other'] = "기타(내용없음)"
        
        return data

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    app.setStyleSheet("""
        QDialog { background-color: #f0f0f0; }
        QGroupBox { font-weight: bold; border: 1px solid gray; border-radius: 5px; margin-top: 10px; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
        QLineEdit { background-color: white; }
    """)
    
    dialog = SpecialNoteDialog()
    if dialog.exec():
        print("Dialog accepted.")
    else:
        print("Dialog rejected.")
    
    sys.exit()
