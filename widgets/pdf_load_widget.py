from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import pyqtSignal, QPoint, Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QWidget,
    QTableWidgetItem,
    QMenu,
)

from core.sql_manager import fetch_recent_subsidy_applications

class PdfLoadWidget(QWidget):
    """PDF 로드 영역 위젯"""
    pdf_selected = pyqtSignal(list)  # 여러 파일 경로(리스트)를 전달하도록 변경
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.setup_connections()
        self._pdf_view_widget = None
    
    def init_ui(self):
        """UI 파일을 로드하고 초기화"""
        ui_path = Path(__file__).parent.parent / "ui" / "pdf_load_area.ui"
        uic.loadUi(str(ui_path), self)
        
        if hasattr(self, 'center_open_btn'):
            self.center_open_btn.setText("로컬에서 PDF 열기")
        if hasattr(self, 'center_import_btn'):
            self.center_import_btn.setText("메일에서 가져오기")
            
        if hasattr(self, 'complement_table_widget'):
            self.setup_table()
    
    def setup_table(self):
        """테이블 위젯 초기 설정"""
        table = self.complement_table_widget
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(['RN', '지역', '작업자', '파일여부'])
        table.setAlternatingRowColors(True)
        self.populate_recent_subsidy_rows()
        table.customContextMenuRequested.connect(self.show_context_menu)

    def populate_recent_subsidy_rows(self):
        """최근 지원금 신청 데이터를 테이블에 채운다."""
        table = self.complement_table_widget
        try:
            df = fetch_recent_subsidy_applications()
        except Exception as error:  # pragma: no cover - UI 경고용
            QMessageBox.warning(self, "데이터 로드 실패", f"지원금 신청 데이터 조회 중 오류가 발생했습니다.\n{error}")
            table.setRowCount(0)
            return

        if df is None or df.empty:
            table.setRowCount(0)
            return

        row_count = len(df)
        table.setRowCount(row_count)

        for row_index, (_, row) in enumerate(df.iterrows()):
            table.setItem(row_index, 0, QTableWidgetItem(str(row.get('RN', ''))))
            table.setItem(row_index, 1, QTableWidgetItem(str(row.get('region', ''))))
            worker_item = QTableWidgetItem(str(row.get('worker', '')))
            worker_item.setData(Qt.ItemDataRole.UserRole, row.get('worker'))
            table.setItem(row_index, 2, worker_item)

            file_path = self._normalize_file_path(row.get('file_path'))
            status_text = str(row.get('file_status', '부')) if file_path else '부'
            status_item = QTableWidgetItem(status_text)
            status_item.setData(Qt.ItemDataRole.UserRole, file_path)
            table.setItem(row_index, 3, status_item)

    def show_context_menu(self, pos: QPoint):
        """테이블 컨텍스트 메뉴 표시"""
        table = self.complement_table_widget
        global_pos = table.viewport().mapToGlobal(pos)

        menu = QMenu(self)  
        start_action = menu.addAction("작업 시작하기")
        action = menu.exec(global_pos)

        if action == start_action:
            self.start_selected_work()

    def start_selected_work(self):
        """선택된 행을 emit하여 다운로드 로직이 처리하도록 한다."""
        table = self.complement_table_widget
        selected_items = table.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "선택 필요", "작업을 시작할 행을 선택해주세요.")
            return

        row = selected_items[0].row()
        rn_item = table.item(row, 0)
        file_item = table.item(row, 3)

        if file_item is None:
            QMessageBox.warning(self, "파일 없음", "연결된 파일 경로가 없습니다.")
            return

        file_path = self._normalize_file_path(file_item.data(Qt.ItemDataRole.UserRole))

        if not file_path:
            QMessageBox.warning(self, "파일 없음", "연결된 파일 경로가 없습니다.")
            return

        resolved_path = Path(file_path)
        if not resolved_path.exists():
            QMessageBox.warning(
                self,
                "파일 없음",
                f"경로를 찾을 수 없습니다.\n{resolved_path}"
            )
            return

        self.pdf_selected.emit([str(resolved_path)])

    @staticmethod
    def _normalize_file_path(raw_path):
        if raw_path is None:
            return None

        if isinstance(raw_path, Path):
            path_str = str(raw_path)
        else:
            path_str = str(raw_path)

        path_str = path_str.strip()
        if path_str.startswith('"') and path_str.endswith('"') and len(path_str) >= 2:
            path_str = path_str[1:-1]
        elif path_str.startswith("'") and path_str.endswith("'") and len(path_str) >= 2:
            path_str = path_str[1:-1]

        return path_str.strip()
    
    def setup_connections(self):
        """시그널-슬롯 연결"""
        if hasattr(self, 'center_open_btn'):
            self.center_open_btn.clicked.connect(self.open_pdf_file)
        if hasattr(self, 'center_import_btn'):
            self.center_import_btn.clicked.connect(self.import_from_email)
    
    def open_pdf_file(self):
        """로컬에서 PDF 또는 이미지 파일을 연다 (다중 선택 가능)"""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "파일 선택",
            "",
            "지원 파일 (*.pdf *.png *.jpg *.jpeg);;PDF Files (*.pdf);;Image Files (*.png *.jpg *.jpeg);;All Files (*)"
        )
        
        if paths:
            self.pdf_selected.emit(paths)
    
    def import_from_email(self):
        """메일에서 PDF 가져오기 (향후 구현)"""
        QMessageBox.information(self, "알림", "메일 가져오기 기능은 향후 구현 예정입니다.")
