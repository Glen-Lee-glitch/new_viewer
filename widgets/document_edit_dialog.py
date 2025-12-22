import sys
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, 
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame,
    QApplication, QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt

class DocumentItemWidget(QWidget):
    """서류 항목 하나를 표시하고 수정/삭제하는 위젯"""
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.is_deleted = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        
        self.line_edit = QLineEdit(text)
        self.btn_delete = QPushButton("삭제")
        self.btn_delete.setFixedWidth(50)
        self.btn_delete.setStyleSheet("background-color: #f44336; color: white;")
        
        layout.addWidget(self.line_edit)
        layout.addWidget(self.btn_delete)
        
        self.btn_delete.clicked.connect(self.mark_as_deleted)

    def mark_as_deleted(self):
        self.is_deleted = True
        self.hide()
        self.deleteLater()

    def get_text(self):
        return self.line_edit.text().strip()

class DocumentListEditor(QWidget):
    """서류 리스트를 관리하는 탭 내부 위젯"""
    def __init__(self, items=None, parent=None):
        super().__init__(parent)
        self.main_layout = QVBoxLayout(self)
        
        # 스크롤 영역 설정
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.scroll_content)
        
        self.main_layout.addWidget(self.scroll)
        
        # 항목 추가 버튼
        self.btn_add = QPushButton("+ 항목 추가")
        self.btn_add.clicked.connect(lambda: self.add_item(""))
        self.main_layout.addWidget(self.btn_add)
        
        if items:
            for item in items:
                self.add_item(item)

    def add_item(self, text):
        widget = DocumentItemWidget(text)
        self.scroll_layout.addWidget(widget)

    def get_items(self):
        items = []
        for i in range(self.scroll_layout.count()):
            widget = self.scroll_layout.itemAt(i).widget()
            if isinstance(widget, DocumentItemWidget) and not widget.is_deleted:
                text = widget.get_text()
                if text:
                    items.append(text)
        return items

class DocumentEditDialog(QDialog):
    """서류 상세 수정 다이얼로그"""
    def __init__(self, region_name, data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"서류 수정 - {region_name}")
        self.resize(400, 500)
        
        layout = QVBoxLayout(self)
        
        self.tab_widget = QTabWidget()
        
        # 데이터 초기화
        self.original_data = data if data else {"general_documents": [], "additional_documents": []}
        
        self.general_editor = DocumentListEditor(self.original_data.get("general_documents", []))
        self.additional_editor = DocumentListEditor(self.original_data.get("additional_documents", []))
        
        self.tab_widget.addTab(self.general_editor, "일반서류")
        self.tab_widget.addTab(self.additional_editor, "추가서류")
        
        layout.addWidget(self.tab_widget)
        
        # 하단 버튼
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("저장")
        self.btn_save.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_cancel = QPushButton("취소")
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(btn_layout)
        
        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def get_data(self):
        """수정된 데이터를 dict 형태로 반환"""
        data = self.original_data.copy()
        data.update({
            "general_documents": self.general_editor.get_items(),
            "additional_documents": self.additional_editor.get_items()
        })
        return data

if __name__ == "__main__":
    app = QApplication(sys.argv)
    test_data = {
        "general_documents": ["(테슬라)구매계약서", "(지역별)지원신청서", "주민등록초본"],
        "additional_documents": ["배터리변경"]
    }
    dialog = DocumentEditDialog("테스트 지역", test_data)
    if dialog.exec():
        print("Updated Data:", dialog.get_data())
