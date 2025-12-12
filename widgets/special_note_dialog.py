import sys
import os
import re
from PyQt6.QtWidgets import (
    QDialog, QApplication, QCheckBox, QLineEdit, QGridLayout, QLabel, QMessageBox, QInputDialog
)
from PyQt6.uic import loadUi

# Ensure we can import from core/widgets if needed in the future
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.sql_manager import insert_additional_note

class SpecialNoteDialog(QDialog):
    # Define detailed items as class constants
    MISSING_DOCS_ITEMS = [
        '신청서1p', '신청서2p(동의서)', '계약서1p', '계약서4p', 
        '초본', '등본', '가족', '지납세', '지세과', '기타'
    ]
    
    REQ_ITEMS = [
        '전입일', '중복', '공동명의 거주지 다름', '자녀 생년월일 요건', '청년생애 요건', '기타'
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Load the UI file
        ui_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "special_note_dialog.ui")
        loadUi(ui_path, self)
        
        # Dynamic Widget Storage
        self.missing_checkboxes = {}  # {name: {'cb': QCheckBox, 'le': QLineEdit|None, 'label': QLabel|None}}
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
        self.pushButton_2.clicked.connect(self.on_cancel_clicked)

        # Connect Send button
        self.pushButton.clicked.connect(self.on_send_clicked)

    def on_cancel_clicked(self):
        """Handle cancel button click: update status to 'pdf 전처리' and close."""
        rn = self.RN_lineEdit.text().strip()
        
        if not rn:
            # RN이 없으면 그냥 닫음
            self.close()
            return

        # 취소 확인 (선택사항, 여기서는 즉시 실행)
        # reply = QMessageBox.question(self, '취소', '취소하시겠습니까? 상태가 "pdf 전처리"로 변경됩니다.',
        #                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        # if reply == QMessageBox.StandardButton.No:
        #     return

        # 데이터베이스 상태 업데이트 (특이사항 내용은 저장하지 않음)
        success = insert_additional_note(
            rn=rn,
            missing_docs=None,
            requirements=None,
            other_detail=None,
            target_status='pdf 전처리'
        )
        
        if success:
            # 성공 시 메시지 없이 조용히 닫거나, 필요 시 메시지 표시
            self.reject()  # 다이얼로그 취소 종료
        else:
            QMessageBox.warning(self, "알림", "상태 업데이트에 실패했습니다.\n(이미 메일 전송된 상태일 수 있습니다)")
            self.reject()

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
        is_missing_docs = (storage is self.missing_checkboxes)

        # First pass: Create and place all checkboxes
        for item_text in items:
            cb = QCheckBox(item_text)
            storage[item_text] = {'cb': cb, 'le': None}
            
            # Place checkbox
            layout.addWidget(cb, row, col)
            
            # If item is "기타", add a LineEdit (for both missing_docs and req)
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
                    col = 0  # Reset column after adding LineEdit in new row
            
            col += 1
            if col >= max_col:
                col = 0
                row += 1
        
        # Second pass: For 서류미비, add a single LineEdit for all items
        if is_missing_docs:
            # Find the last row used for checkboxes
            last_checkbox_row = row
            
            # Add a separator label
            separator_row = last_checkbox_row + 1
            separator_label = QLabel("해당 서류 내용:")
            separator_label.setStyleSheet("color: gray; font-size: 9pt;")
            separator_label.setVisible(False)
            layout.addWidget(separator_label, separator_row, 0, 1, 1)
            self.missing_docs_separator_label = separator_label
            
            # Add a single LineEdit for all 서류미비 items
            line_edit_row = separator_row
            le = QLineEdit()
            le.setPlaceholderText("상세 사유 입력")
            le.setVisible(False) # Initially hidden
            layout.addWidget(le, line_edit_row, 1, 1, 3)
            self.missing_docs_line_edit = le
            
            # Connect all checkboxes (except "기타") to update line edit visibility
            for item_text in items:
                if item_text != "기타":
                    storage[item_text]['cb'].toggled.connect(self._update_missing_docs_line_edits)

    def _update_missing_docs_line_edits(self):
        """Update visibility of the single line edit when any 서류미비 checkbox is toggled."""
        # Check if any checkbox is checked (excluding "기타" which has its own logic)
        any_checked = any(
            widgets['cb'].isChecked() and name != '기타' 
            for name, widgets in self.missing_checkboxes.items()
        )
        
        # Show/hide separator label and line edit
        if hasattr(self, 'missing_docs_separator_label'):
            self.missing_docs_separator_label.setVisible(any_checked)
        if hasattr(self, 'missing_docs_line_edit'):
            self.missing_docs_line_edit.setVisible(any_checked)

    def update_ui_state(self):
        """Show/Hide sub-frames based on main checkbox state and adjust size."""
        self.sub_frame_missing.setVisible(self.checkBox_2.isChecked())
        self.sub_frame_req.setVisible(self.checkBox.isChecked())
        self.sub_frame_other.setVisible(self.checkBox_3.isChecked())
        
        # Adjust size to fit content tightly
        QApplication.processEvents()
        self.adjustSize()
    
    def _is_valid_rn(self, rn_text):
        """Check if RN format matches 'RN' followed by 9 digits."""
        # ^RN : Starts with 'RN'
        # \d{9} : Exactly 9 digits
        # $ : End of string
        pattern = r'^RN\d{9}$'
        return bool(re.match(pattern, rn_text))

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

        # 5. Check RN last (with input dialog fallback and format validation)
        rn_text = self.RN_lineEdit.text().strip()
        
        # If empty, prompt for input
        while not rn_text:
            text, ok = QInputDialog.getText(self, "RN 입력", "RN 번호를 입력해주세요 (예: RN123456789):")
            if not ok:
                # User cancelled
                return False
            rn_text = text.strip()
            self.RN_lineEdit.setText(rn_text)
        
        # Validate Format
        if not self._is_valid_rn(rn_text):
            QMessageBox.warning(self, "경고", "RN 번호 형식이 올바르지 않습니다.\n\n형식: 'RN' + 숫자 9자리 (총 11자리)\n예: RN123456789")
            self.RN_lineEdit.setFocus()
            self.RN_lineEdit.selectAll()
            return False

        return True

    def on_send_clicked(self):
        """Handle send button click: validate, save to database, and close."""
        # 검증: 선택사항, RN 번호 등 모든 검증 완료 확인
        if not self.validate_selection():
            return

        # 데이터 수집
        results = self.get_selected_data()
        rn = self.RN_lineEdit.text().strip()
        
        # 데이터베이스에 저장 (status='작업자 확인'으로 변경)
        success = insert_additional_note(
            rn=rn,
            missing_docs=results['missing'] if results['missing'] else None,
            requirements=results['requirements'] if results['requirements'] else None,
            other_detail=results['other'],
            target_status='서류미비 요청'
        )
        
        if success:
            QMessageBox.information(self, "완료", "특이사항이 성공적으로 저장되었습니다.")
            self.accept()  # 다이얼로그 종료
        else:
            QMessageBox.critical(self, "오류", "데이터 저장 중 오류가 발생했습니다.\n다시 시도해주세요.")

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
