import sys
import os
import re
from PyQt6.QtWidgets import (
    QDialog, QApplication, QCheckBox, QLineEdit, QGridLayout, QLabel, QMessageBox, QInputDialog,
    QFrame, QHBoxLayout, QWidget, QVBoxLayout, QSizePolicy, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, Qt
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
        
        # Initialize slide panel (must be before other UI initialization)
        self._init_slide_panel()
        
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

    def _init_slide_panel(self):
        """기존 UI를 감싸고 우측에 슬라이드 패널을 추가하는 레이아웃 재구성"""
        # 다이얼로그의 현재 크기 저장
        current_size = self.size()
        if current_size.width() < 500: current_size.setWidth(500)
        if current_size.height() < 300: current_size.setHeight(300)

        # 기존 레이아웃 가져오기
        old_layout = self.layout()
        if not old_layout:
            return
        
        # 기존 내용을 담을 컨테이너 위젯 생성
        self.original_content_widget = QWidget()
        self.original_content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # 새 VBox 레이아웃 생성 및 기존 아이템들을 모두 이동
        new_vbox = QVBoxLayout(self.original_content_widget)
        new_vbox.setContentsMargins(9, 9, 9, 9)
        new_vbox.setSpacing(6)
        
        while old_layout.count():
            item = old_layout.takeAt(0)
            if item.widget():
                new_vbox.addWidget(item.widget())
            elif item.layout():
                new_vbox.addLayout(item.layout())
            elif item.spacerItem():
                new_vbox.addItem(item.spacerItem())
        
        # 기존 레이아웃 안전하게 분리 (중복 레이아웃 경고 방지 핵심 트릭)
        QWidget().setLayout(old_layout)
        
        # 우측 슬라이드 패널 생성
        self.side_panel = QFrame()
        self.side_panel.setObjectName("side_panel")
        self.side_panel.setFrameShape(QFrame.Shape.StyledPanel)
        self.side_panel.setStyleSheet("""
            QFrame#side_panel {
                background-color: #f9f9f9;
                border-left: 1px solid #d0d0d0;
            }
            QRadioButton {
                color: #212121;
                font-size: 10pt;
                padding: 5px;
            }
        """)
        self.side_panel.setFixedWidth(0)
        self.side_panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        
        # 패널 내부 레이아웃
        self.side_panel_layout = QVBoxLayout(self.side_panel)
        self.side_panel_layout.setContentsMargins(10, 10, 10, 10)
        
        # 특이사항 라디오 버튼 추가
        self.rb_missing = QRadioButton("누락")
        self.rb_blurry = QRadioButton("흐릿")
        self.rb_necessary = QRadioButton("필요")
        self.side_panel_layout.addWidget(self.rb_missing)
        self.side_panel_layout.addWidget(self.rb_blurry)
        self.side_panel_layout.addWidget(self.rb_necessary)
        
        self.rb_group = QButtonGroup(self)
        self.rb_group.addButton(self.rb_missing)
        self.rb_group.addButton(self.rb_blurry)
        self.rb_group.addButton(self.rb_necessary)
        
        # 추가 UI: 지세과 + 누락 시 표시될 라벨
        self.label_address_needed = QLabel("필요 주소 내역")
        self.label_address_needed.setStyleSheet("color: #d32f2f; font-weight: bold; margin-top: 10px;")
        self.label_address_needed.setVisible(False)
        self.side_panel_layout.addWidget(self.label_address_needed)
        
        # Connect signal for radio button
        self.rb_missing.toggled.connect(self._update_extra_widgets_visibility)
        
        self.side_panel_layout.addStretch()
        
        # 다이얼로그의 메인 레이아웃을 가로(HBox)로 변경
        main_hbox_layout = QHBoxLayout(self)
        main_hbox_layout.setContentsMargins(0, 0, 0, 0)
        main_hbox_layout.setSpacing(0)
        
        # 좌측(기존 내용) + 우측(패널) 추가
        main_hbox_layout.addWidget(self.original_content_widget)
        main_hbox_layout.addWidget(self.side_panel)
        
        # 애니메이션 객체 생성 (maximumWidth 사용이 가장 안정적입니다)
        self.side_panel_animation = QPropertyAnimation(self.side_panel, b"maximumWidth")
        self.side_panel_animation.setDuration(300)
        self.side_panel_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        # 다이얼로그 크기 설정
        self.setMinimumSize(500, 300)
        self.resize(current_size)

    def _animate_side_panel(self, show: bool):
        """패널 열기/닫기 애니메이션"""
        target_width = 650 if show else 0
        
        if self.side_panel_animation.state() == QPropertyAnimation.State.Running:
            self.side_panel_animation.stop()
        
        current_width = self.side_panel.width()
        if current_width == target_width:
            return
        
        self.side_panel_animation.setStartValue(current_width)
        self.side_panel_animation.setEndValue(target_width)
        self.side_panel_animation.start()

    def on_cancel_clicked(self):
        """Handle cancel button click: update status to 'pdf 전처리' and close."""
        rn = self.RN_lineEdit.text().strip()
        
        if not rn:
            # RN이 없으면 그냥 닫음
            self.close()
            return

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
        
        # 지세과 체크박스 이벤트 연결
        if '지세과' in self.missing_checkboxes:
            self.missing_checkboxes['지세과']['cb'].toggled.connect(self._update_extra_widgets_visibility)

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
        
        # Connect all checkboxes (except "기타") to update side panel visibility for missing docs
        if is_missing_docs:
            for item_text in items:
                if item_text != "기타":
                    storage[item_text]['cb'].toggled.connect(self._update_side_panel_visibility)

    def _update_extra_widgets_visibility(self):
        """'지세과'가 체크되어 있고, 라디오버튼이 '누락'일 때 추가 위젯을 표시한다."""
        is_jise_checked = False
        if '지세과' in self.missing_checkboxes:
            is_jise_checked = self.missing_checkboxes['지세과']['cb'].isChecked()
        
        is_missing_rb_checked = self.rb_missing.isChecked()
        
        if is_jise_checked and is_missing_rb_checked:
            self.label_address_needed.setVisible(True)
        else:
            self.label_address_needed.setVisible(False)

    def _update_side_panel_visibility(self):
        """Update visibility of the side panel when any 서류미비 checkbox is toggled."""
        # Check if any checkbox is checked (excluding "기타" which has its own logic)
        any_checked = any(
            widgets['cb'].isChecked() and name != '기타' 
            for name, widgets in self.missing_checkboxes.items()
        )
        
        # 우측 패널 열기/닫기 애니메이션
        if hasattr(self, '_animate_side_panel'):
            self._animate_side_panel(any_checked)

    def update_ui_state(self):
        """Show/Hide sub-frames based on main checkbox state and adjust size."""
        self.sub_frame_missing.setVisible(self.checkBox_2.isChecked())
        self.sub_frame_req.setVisible(self.checkBox.isChecked())
        self.sub_frame_other.setVisible(self.checkBox_3.isChecked())
        
        # Adjust size to fit content tightly, but maintain minimum size
        QApplication.processEvents()
        self.adjustSize()
        # 최소 크기 보장
        if self.width() < 500:
            self.resize(500, self.height())
        if self.height() < 200:
            self.resize(self.width(), 200)
    
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
        
        # 사이드 패널의 라디오 버튼 값 가져오기 (detail_info로 저장)
        detail_info = None
        checked_button = self.rb_group.checkedButton()
        if checked_button:
            detail_info = checked_button.text()

        # 데이터베이스에 저장 (status='서류미비 요청'으로 변경)
        success = insert_additional_note(
            rn=rn,
            missing_docs=results['missing'] if results['missing'] else None,
            requirements=results['requirements'] if results['requirements'] else None,
            other_detail=results['other'],
            target_status='서류미비 요청',
            detail_info=detail_info
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
