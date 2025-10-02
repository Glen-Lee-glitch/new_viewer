from pathlib import Path
import math

from PyQt6 import uic
from PyQt6.QtCore import pyqtSignal, QPoint, Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QWidget,
    QTableWidgetItem,
    QMenu,
    QHeaderView,
)

from core.sql_manager import fetch_recent_subsidy_applications

class PdfLoadWidget(QWidget):
    """PDF 로드 영역 위젯"""
    pdf_selected = pyqtSignal(list)  # 여러 파일 경로(리스트)를 전달하도록 변경
    work_started = pyqtSignal(list, dict)
    
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
        if hasattr(self, 'center_refresh_btn'):
            self.center_refresh_btn.setText("데이터 새로고침")
            
        if hasattr(self, 'complement_table_widget'):
            self.setup_table()
    
    def setup_table(self):
        """테이블 위젯 초기 설정"""
        table = self.complement_table_widget
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(['RN', '지역', '작업자', '파일여부'])

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

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
            row_data = {
                'rn': self._sanitize_text(row.get('RN', '')),
                'region': self._sanitize_text(row.get('region', '')),
                'worker': self._sanitize_text(row.get('worker', '')),
                'name': self._sanitize_text(row.get('name', '')),
                'special_note': self._sanitize_text(row.get('special_note', '')),
            }

            rn_item = QTableWidgetItem(row_data['rn'])
            rn_item.setData(Qt.ItemDataRole.UserRole, row_data)
            table.setItem(row_index, 0, rn_item)

            table.setItem(row_index, 1, QTableWidgetItem(row_data['region']))

            worker_item = QTableWidgetItem(row_data['worker'])
            worker_item.setData(Qt.ItemDataRole.UserRole, row_data['worker'])
            table.setItem(row_index, 2, worker_item)

            file_path = self._normalize_file_path(row.get('original_filepath'))
            status_text = str(row.get('file_status', '부'))
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

        metadata = self._extract_row_metadata(rn_item)
        metadata['rn'] = metadata.get('rn') or self._safe_item_text(rn_item)
        metadata['region'] = metadata.get('region') or self._safe_item_text(table.item(row, 1))
        metadata['worker'] = metadata.get('worker') or self._safe_item_text(table.item(row, 2))

        # 원본 파일 경로를 그대로 전달 (pdf_render.py에서 분할 파일 감지 처리)
        self.work_started.emit([str(resolved_path)], metadata)
    
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
        
        path_str = path_str.strip()

        if path_str.upper().startswith('C:'):
            path_str = r'\\DESKTOP-KMJ' + path_str[2:]

        return path_str.strip()
    
    def setup_connections(self):
        """시그널-슬롯 연결"""
        if hasattr(self, 'center_open_btn'):
            self.center_open_btn.clicked.connect(self.open_pdf_file)
        if hasattr(self, 'center_refresh_btn'):
            self.center_refresh_btn.clicked.connect(self.refresh_data)
    
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
    
    def refresh_data(self):
        """sql 데이터 새로고침"""
        self.populate_recent_subsidy_rows()

    @staticmethod
    def _sanitize_text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            if math.isnan(value):
                return ""
            return str(int(value)) if value.is_integer() else str(value)
        value_str = str(value).strip()
        return "" if value_str.lower() == "nan" else value_str

    @staticmethod
    def _safe_item_text(item: QTableWidgetItem | None) -> str:
        if item is None:
            return ""
        return item.text().strip()

    def _extract_row_metadata(self, rn_item: QTableWidgetItem | None) -> dict:
        if rn_item is None:
            return {'rn': "", 'name': "", 'region': "", 'worker': "", 'special_note': ""}
        data = rn_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return {'rn': "", 'name': "", 'region': "", 'worker': "", 'special_note': ""}
        return {
            'rn': data.get('rn', ""),
            'name': data.get('name', ""),
            'region': data.get('region', ""),
            'worker': data.get('worker', ""),
            'special_note': data.get('special_note', ""),
        }
