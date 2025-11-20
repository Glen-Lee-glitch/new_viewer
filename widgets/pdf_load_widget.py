from pathlib import Path
import math
import pandas as pd

from PyQt6 import uic
from PyQt6.QtCore import pyqtSignal, QPoint, Qt
from PyQt6.QtGui import QColor, QBrush, QPainter
from PyQt6.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QWidget,
    QTableWidgetItem,
    QMenu,
    QHeaderView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QInputDialog,
)

from core.sql_manager import fetch_recent_subsidy_applications, fetch_application_data_by_rn

# 하이라이트를 위한 커스텀 데이터 역할 정의
HighlightRole = Qt.ItemDataRole.UserRole + 1

class HighlightDelegate(QStyledItemDelegate):
    """특정 데이터 역할에 따라 배경색을 변경하는 델리게이트"""
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        # 커스텀 역할(HighlightRole)에 데이터가 있는지 확인
        highlight_color = index.data(HighlightRole)
        
        if highlight_color:
            # 커스텀 배경색이 있으면 직접 그리기
            painter.save()
            painter.fillRect(option.rect, QBrush(QColor(highlight_color)))
            painter.restore()
            
            # 이제 텍스트와 다른 요소들을 그리기 위해 기본 paint 호출
            super().paint(painter, option, index)
        else:
            # 커스텀 배경색이 없으면 기본 동작 수행
            super().paint(painter, option, index)


class PdfLoadWidget(QWidget):
    """PDF 로드 영역 위젯"""
    pdf_selected = pyqtSignal(list)  # 여러 파일 경로(리스트)를 전달하도록 변경
    work_started = pyqtSignal(list, dict)
    ai_review_requested = pyqtSignal(str) # AI 검토 요청 시그널
    data_refreshed = pyqtSignal()  # 데이터 새로고침 완료 시그널
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.setup_connections()
        self._pdf_view_widget = None
        self._is_context_menu_work = False  # 컨텍스트 메뉴를 통한 작업 시작 여부
    
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
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(['지역', 'RN', '작업자', '결과', 'AI'])

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        # 커스텀 배경색이 alternatingRowColors에 의해 덮어씌워지는 것을 방지
        table.setAlternatingRowColors(False)
        
        # 커스텀 델리게이트 적용
        table.setItemDelegate(HighlightDelegate(table))

        self.populate_recent_subsidy_rows()
        table.customContextMenuRequested.connect(self.show_context_menu)
        table.cellDoubleClicked.connect(self._handle_cell_double_clicked)

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
        # 최대 20개 행까지만 표시
        display_count = min(row_count, 20)
        table.setRowCount(display_count)

        for row_index, (_, row) in enumerate(df.iterrows()):
            # 20개를 초과하면 중단
            if row_index >= 20:
                break
            row_data = {
                'rn': self._sanitize_text(row.get('RN', '')),
                'region': self._sanitize_text(row.get('region', '')),
                'worker': self._sanitize_text(row.get('worker', '')),
                'name': self._sanitize_text(row.get('name', '')),
                'special_note': self._sanitize_text(row.get('special_note', '')),
                'recent_thread_id': self._sanitize_text(row.get('recent_thread_id', '')),  # 추가
                'file_rendered': row.get('file_rendered', 0),  # file_rendered 상태 추가
                '구매계약서': row.get('구매계약서', 0), # 추가
                '초본': row.get('초본', 0), # 추가
                '공동명의': row.get('공동명의', 0),
                'urgent': row.get('urgent', 0),  # urgent 상태 추가
                'outlier': self._sanitize_text(row.get('outlier', '')),  # 이상치 정보 추가
                'original_filepath': self._normalize_file_path(row.get('original_filepath')) # 이 줄을 추가
            }

            # 'AI' 칼럼 값 계산
            ai_status = 'X'
            구매계약서 = row_data['구매계약서'] == 1
            초본 = row_data['초본'] == 1
            공동명의 = row_data['공동명의'] == 1

            if 구매계약서 and (초본 or 공동명의):
                ai_status = 'O'
            
            # 컬럼 순서: ['지역', 'RN', '작업자', '결과', 'AI', '이상치']
            region_item = QTableWidgetItem(row_data['region'])
            table.setItem(row_index, 0, region_item)

            rn_item = QTableWidgetItem(row_data['rn'])
            rn_item.setData(Qt.ItemDataRole.UserRole, row_data)  # RN 아이템에 전체 데이터 저장
            table.setItem(row_index, 1, rn_item)

            worker_item = QTableWidgetItem(row_data['worker'])
            worker_item.setData(Qt.ItemDataRole.UserRole, row_data['worker'])
            table.setItem(row_index, 2, worker_item)

            file_path = self._normalize_file_path(row.get('original_filepath'))
            # '결과' 칼럼 데이터 표시
            result_text = self._sanitize_text(row.get('result', ''))
            result_item = QTableWidgetItem(result_text)
            result_item.setData(Qt.ItemDataRole.UserRole, file_path)  # 파일 경로는 UserRole에 유지
            table.setItem(row_index, 3, result_item)

            # AI 상태 아이템 추가
            ai_item = QTableWidgetItem(ai_status)
            table.setItem(row_index, 4, ai_item)

            # --- Row Highlighting ---
            # urgent 칼럼이 1이면 빨간색 하이라이트
            if row_data['urgent'] == 1:
                highlight_color = QColor(220, 53, 69, 180)  # 빨간색 (Bootstrap의 danger 색상과 유사)
                text_color = QColor("white")
                
                # 모든 컬럼에 하이라이트 적용
                for col in range(table.columnCount()):
                    item = table.item(row_index, col)
                    if item:
                        item.setData(HighlightRole, highlight_color)
                        item.setForeground(text_color)

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
        # 컨텍스트 메뉴를 통한 작업 시작임을 표시
        self._is_context_menu_work = True
        
        table = self.complement_table_widget
        selected_items = table.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "선택 필요", "작업을 시작할 행을 선택해주세요.")
            self._is_context_menu_work = False  # 실패 시 플래그 리셋
            return

        row = selected_items[0].row() # tablewidget 에서 선택된 행 중 가장 첫 번째 행에 대해서 시작하도록
        rn_item = table.item(row, 1)  # RN은 이제 1번 컬럼

        # AI 결과가 있는 경우 -> AI 결과 창 열기
        ai_item = table.item(row, 4)
        if ai_item and ai_item.text() == 'O':
            if rn_item:
                self.ai_review_requested.emit(rn_item.text())

        # 파일 경로는 SQL의 original_filepath에서 가져옴
        row_data = rn_item.data(Qt.ItemDataRole.UserRole)
        if not row_data or not isinstance(row_data, dict):
            QMessageBox.warning(self, "파일 없음", "데이터를 불러올 수 없습니다.")
            self._is_context_menu_work = False
            return

        file_path = row_data.get('original_filepath')
        if not file_path:
            QMessageBox.warning(self, "파일 없음", "연결된 파일 경로가 없습니다.")
            self._is_context_menu_work = False
            return

        file_path = self._normalize_file_path(file_path)

        if not file_path:
            QMessageBox.warning(self, "파일 없음", "연결된 파일 경로가 없습니다.")
            self._is_context_menu_work = False
            return

        # 정규화된 파일 경로 -> 추후에 load_document 에서 사용
        resolved_path = Path(file_path)
        if not resolved_path.exists():
            QMessageBox.warning(
                self,
                "파일 없음",
                f"경로를 찾을 수 없습니다.\n{resolved_path}"
            )
            self._is_context_menu_work = False
            return

        metadata = self._extract_row_metadata(rn_item)
        metadata['rn'] = metadata.get('rn') or self._safe_item_text(rn_item)
        metadata['region'] = metadata.get('region') or self._safe_item_text(table.item(row, 0))  # 지역은 이제 0번 컬럼
        metadata['worker'] = metadata.get('worker') or self._safe_item_text(table.item(row, 2))
        
        # file_rendered 상태 추가
        metadata['file_rendered'] = rn_item.data(Qt.ItemDataRole.UserRole).get('file_rendered', 0)
        
        # 이상치 정보 추가
        metadata['outlier'] = rn_item.data(Qt.ItemDataRole.UserRole).get('outlier', '')
        
        # 컨텍스트 메뉴를 통한 작업 시작임을 metadata에 추가
        metadata['is_context_menu_work'] = self._is_context_menu_work

        # 원본 파일 경로를 그대로 전달 (pdf_render.py에서 분할 파일 ex. RN123_1.pdf, RN123_2.pdf 등 감지 처리)
        self.work_started.emit([str(resolved_path)], metadata)
        
        # 작업 시작 후 플래그 리셋
        self._is_context_menu_work = False
    
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
        if hasattr(self, 'pushButton'):
            self.pushButton.clicked.connect(self.open_by_rn)
    
    def open_by_rn(self):
        """RN 번호를 입력받아 작업을 시작한다."""
        rn, ok = QInputDialog.getText(self, "RN 검색", "RN 번호를 입력하세요 (예: RN00000):")
        
        if not ok or not rn.strip():
            return
            
        rn = rn.strip().upper() # 대문자 변환
        
        # DB에서 데이터 조회
        data = fetch_application_data_by_rn(rn)
        
        if not data:
            QMessageBox.warning(self, "검색 실패", f"RN 번호 '{rn}'에 해당하는 데이터를 찾을 수 없습니다.")
            return
            
        # AI 결과가 있는 경우 -> AI 결과 창 열기 (start_selected_work 로직과 동일하게)
        구매계약서 = data.get('구매계약서') == 1
        초본 = data.get('초본') == 1
        공동명의 = data.get('공동명의') == 1
        if 구매계약서 and (초본 or 공동명의):
            self.ai_review_requested.emit(rn)

        # 파일 경로 확인
        file_path = self._normalize_file_path(data.get('original_filepath'))
        
        if not file_path:
            QMessageBox.warning(self, "파일 없음", "해당 RN에 연결된 파일 경로가 DB에 없습니다.")
            return
            
        resolved_path = Path(file_path)
        if not resolved_path.exists():
            QMessageBox.warning(self, "파일 없음", f"파일을 찾을 수 없습니다.\n{resolved_path}")
            return
            
        # 메타데이터 구성 (start_selected_work와 포맷 통일)
        metadata = {
            'rn': data.get('RN', rn),
            'name': data.get('name', ''),
            'region': data.get('region', ''),
            'worker': data.get('worker', ''),
            'special_note': data.get('special_note', ''),
            'recent_thread_id': data.get('recent_thread_id', ''),
            'file_rendered': data.get('file_rendered', 0),
            'urgent': data.get('urgent', 0),
            'outlier': data.get('outlier', ''),
            'original_filepath': file_path,
            'is_context_menu_work': True # 컨텍스트 메뉴와 동일하게 동작하도록 True로 설정
        }
        
        # 작업 시작 시그널 발생
        self.work_started.emit([str(resolved_path)], metadata)

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
        self.data_refreshed.emit()  # 새로고침 완료 시그널 emit

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
            return {'rn': "", 'name': "", 'region': "", 'worker': "", 'special_note': "", 'recent_thread_id': "", 'file_rendered': 0, 'urgent': 0, 'outlier': "", 'is_context_menu_work': False}
        data = rn_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return {'rn': "", 'name': "", 'region': "", 'worker': "", 'special_note': "", 'recent_thread_id': "", 'file_rendered': 0, 'urgent': 0, 'outlier': "", 'is_context_menu_work': False}
        return {
            'rn': data.get('rn', ""),
            'name': data.get('name', ""),
            'region': data.get('region', ""),
            'worker': data.get('worker', ""),
            'special_note': data.get('special_note', ""),
            'recent_thread_id': data.get('recent_thread_id', ""),
            'file_rendered': data.get('file_rendered', 0),
            'urgent': data.get('urgent', 0),
            'outlier': data.get('outlier', ""),
            'original_filepath': data.get('original_filepath', ""), # 이 줄을 추가
            'is_context_menu_work': False  # 기본값은 False, 실제 값은 start_selected_work에서 설정
        }

    def _handle_cell_double_clicked(self, row, column):
        """테이블 셀 더블 클릭 시 AI 검토 요청을 emit한다."""
        # AI 칼럼(5번째)을 클릭했을 때만 동작하도록 수정
        if column == 4:
            ai_item = self.complement_table_widget.item(row, column)
            if ai_item and ai_item.text() == 'O':
                rn_item = self.complement_table_widget.item(row, 1) # RN은 1번 컬럼
                if rn_item:
                    self.ai_review_requested.emit(rn_item.text())
