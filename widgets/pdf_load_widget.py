from pathlib import Path
import math
import pandas as pd
from datetime import datetime
import pytz

from PyQt6 import uic
from PyQt6.QtCore import pyqtSignal, QPoint, Qt, QSettings
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
    QButtonGroup,
    QApplication, # QApplication import 추가
    QStyle,
    QStyleOptionButton,
    QAbstractItemView,
)

from core.sql_manager import (
    fetch_recent_subsidy_applications, 
    fetch_application_data_by_rn, 
    fetch_give_works,
    fetch_today_subsidy_applications_by_worker,
    fetch_today_unfinished_subsidy_applications,
    get_email_by_thread_id,
    check_gemini_flags,
    update_give_works_worker,
    update_rns_worker_id,
    update_subsidy_status_if_new
)
from core.utility import get_converted_path
from widgets.email_view_dialog import EmailViewDialog
from widgets.detail_form_dialog import DetailFormDialog
from widgets.alert_dialog import show_alert, show_toast
from widgets.subsidy_history_dialog import SubsidyHistoryDialog
from widgets.give_memo_dialog import GiveMemoDialog

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


class ButtonDelegate(QStyledItemDelegate):
    """버튼 모양을 그리는 델리게이트 (최적화용)"""
    def __init__(self, parent=None, text="시작"):
        super().__init__(parent)
        self.text = text

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        # 기본 배경 그리기 (선택 상태 등 처리)
        super().paint(painter, option, index)
        
        # 버튼 스타일 옵션 설정
        button_opt = QStyleOptionButton()
        # 셀 크기보다 약간 작게 설정하여 여백 주기
        margin = 4
        button_opt.rect = option.rect.adjusted(margin, margin, -margin, -margin)
        button_opt.text = self.text
        button_opt.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Active
        
        # 버튼 그리기
        QApplication.style().drawControl(QStyle.ControlElement.CE_PushButton, button_opt, painter)


class PdfLoadWidget(QWidget):
    """PDF 로드 영역 위젯"""
    pdf_selected = pyqtSignal(list, dict)  # 여러 파일 경로(리스트)와 메타데이터(딕셔너리) 전달
    work_started = pyqtSignal(list, dict)
    rn_selected = pyqtSignal(str) # 추가
    ai_review_requested = pyqtSignal(str) # AI 검토 요청 시그널
    data_refreshed = pyqtSignal()  # 데이터 새로고침 완료 시그널
    
    def __init__(self):
        super().__init__()
        self._pdf_view_widget = None
        self._is_context_menu_work = False  # 컨텍스트 메뉴를 통한 작업 시작 여부
        self._filter_mode = 'all'  # 필터 모드: 'all', 'my', 'unfinished'
        self._worker_name = ''  # 현재 로그인한 작업자 이름
        self._worker_id = None  # 현재 로그인한 작업자 ID
        self._payment_request_load_enabled = True  # 지급신청 로드 체크박스 상태 (기본값: True)
        self._is_first_load = True # 프로그램 시작 시 첫 로드 여부 플래그
        self.init_ui()
        self.setup_connections()
    
    def init_ui(self):
        """UI 파일을 로드하고 초기화"""
        ui_path = Path(__file__).parent.parent / "ui" / "pdf_load_area.ui"
        uic.loadUi(str(ui_path), self)
        
        if hasattr(self, 'center_open_btn'):
            self.center_open_btn.setText("로컬에서 PDF 열기")
        
        if hasattr(self, 'center_open_rn_btn'):
            self.center_open_rn_btn.setText("RN번호로 열기")
            
        if hasattr(self, 'center_refresh_btn'):
            self.center_refresh_btn.setText("데이터 새로고침")
        
        # 지원 테이블 설정
        if hasattr(self, 'complement_table_widget'):
            self.setup_table()
        
        # 지급 테이블 설정
        if hasattr(self, 'tableWidget'):
            self.setup_give_works_table()
        
        # 필터 라디오 버튼 그룹 설정
        self._setup_filter_buttons()
    
    def setup_table(self):
        """테이블 위젯 초기 설정"""
        table = self.complement_table_widget
        # 컬럼 수 6개로 증가 (기존 5개 + 버튼 컬럼)
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(['지역', 'RN', '작업자', '상태', 'AI', 'PDF열기'])

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        # 단일 행 선택 모드 설정
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        
        # 커스텀 배경색이 alternatingRowColors에 의해 덮어씌워지는 것을 방지
        table.setAlternatingRowColors(False)
        
        # 커스텀 델리게이트 적용 (기존 HighlightDelegate)
        table.setItemDelegate(HighlightDelegate(table))
        
        # AI 컬럼(4번)에 '보기' 버튼, 마지막 컬럼(5번)에 '시작' 버튼 델리게이트 적용
        # setItemDelegateForColumn은 전체 델리게이트보다 우선순위가 높음
        table.setItemDelegateForColumn(4, ButtonDelegate(table, "보기"))
        table.setItemDelegateForColumn(5, ButtonDelegate(table, "시작"))

        self.populate_recent_subsidy_rows()
        table.customContextMenuRequested.connect(self.show_context_menu)
        table.cellClicked.connect(self._handle_cell_clicked)
        # 선택 변경 시그널 연결
        table.itemSelectionChanged.connect(lambda: self.rn_selected.emit(self.get_selected_rn() or ""))
    
    def _handle_cell_clicked(self, row, column):
        """테이블 셀 클릭 시 처리"""
        # '보기' 컬럼(5번) 클릭 시 작업 시작
        if column == 5:
            self._is_context_menu_work = True
            self._start_work_by_row(row)
            self._is_context_menu_work = False
        # 'AI' 컬럼(4번) 클릭 시 AI 결과 보기
        elif column == 4:
            self._show_gemini_results(row)
    
    def _handle_give_works_cell_clicked(self, row, column):
        """지급 테이블 셀 클릭 시 처리"""
        # 버튼 컬럼(4번) 클릭 시 RN 출력 및 파일 검색
        if column == 4:
            table = self.tableWidget
            rn_item = table.item(row, 0)  # RN은 0번 컬럼
            if rn_item:
                rn = rn_item.text().strip()
                print(f"[지급 시작] RN: {rn}")
                
                # 현재 작업자 이름으로 payments 테이블 업데이트 (작업자가 비어있을 때만)
                worker_item = table.item(row, 1)  # 작업자 컬럼(1번)
                existing_worker = worker_item.text().strip() if worker_item else ""
                
                if existing_worker:
                    print(f"[지급 시작] 작업자 업데이트 건너뜀: 이미 '{existing_worker}'로 할당됨")
                elif self._worker_name:
                    # sql_manager.py에서 업데이트된 PostgreSQL용 함수 사용
                    success = update_give_works_worker(rn, self._worker_name)
                    if success:
                        print(f"[지급 시작] 작업자 업데이트 완료: {self._worker_name}")
                        if worker_item:
                            worker_item.setText(self._worker_name)
                    else:
                        print(f"[지급 시작] 작업자 업데이트 실패")
                else:
                    print(f"[지급 시작] 작업자 이름이 설정되지 않았습니다.")
                
                # 파일 경로 설정 (기존 로직 유지)
                search_dir = Path(get_converted_path(r"C:\Users\HP\Desktop\Tesla\24q4\지급\지급서류\merged"))
                
                # RN이 포함된 PDF 파일 검색
                pdf_files = list(search_dir.glob(f"*{rn}*.pdf"))
                
                if pdf_files:
                    pdf_path = pdf_files[0]  # 첫 번째 파일 사용
                    print(f"[지급 시작] 파일 존재: {pdf_path.name}")
                    # PDF 파일을 열어서 편집 모드로 진입 (지급 테이블 시작 플래그 및 RN 전달)
                    self.pdf_selected.emit([str(pdf_path)], {'is_give_works': True, 'rn': rn})
                else:
                    print(f"[지급 시작] 파일 없음: RN {rn}에 해당하는 PDF 파일을 찾을 수 없습니다.")
    
    def _handle_give_works_cell_double_clicked(self, row, column):
        """지급 테이블 셀 더블 클릭 시 처리"""
        # 메모 컬럼이 현재 구성에 없으므로 일단 패스 (나중에 필요시 추가)
        pass
    
    def setup_give_works_table(self):
        """지급 테이블 위젯 초기 설정"""
        table = self.tableWidget
        
        # 컬럼 수 5개로 조정 (RN, 작업자, 지역, 상태, PDF열기)
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(['RN', '작업자', '지역', '상태', 'PDF열기'])

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        # 셀 편집 비활성화
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        # 마지막 컬럼(4번)에 버튼 델리게이트 적용
        table.setItemDelegateForColumn(4, ButtonDelegate(table, "시작"))
        
        # 클릭 이벤트 연결
        table.cellClicked.connect(self._handle_give_works_cell_clicked)
        # 더블 클릭 이벤트 연결
        table.cellDoubleClicked.connect(self._handle_give_works_cell_double_clicked)
        
        self.populate_give_works_rows()
    
    def populate_give_works_rows(self):
        """
        payments 테이블 데이터를 지급 테이블 위젯에 채운다.
        """
        table = self.tableWidget
        try:
            df = fetch_give_works()
        except Exception as error:
            print(f"지급 데이터 로드 실패: {error}")
            table.setRowCount(0)
            return

        if df is None or df.empty:
            print("[populate_give_works_rows] 조회된 지급 데이터 없음.")
            table.setRowCount(0)
            return

        table.setRowCount(len(df))
        for row_index, (_, row) in enumerate(df.iterrows()):
            # 데이터 객체 생성
            row_data = {
                'rn': self._sanitize_text(row.get('RN', '')),
                'worker': self._sanitize_text(row.get('worker', '')),
                'region': self._sanitize_text(row.get('region', '')),
                'status': self._sanitize_text(row.get('give_status', '')),
                'memo': self._sanitize_text(row.get('memo', '')),
                'give_file_path': self._sanitize_text(row.get('give_file_path', ''))
            }
            
            # RN 아이템
            rn_item = QTableWidgetItem(row_data['rn'])
            rn_item.setData(Qt.ItemDataRole.UserRole, row_data) # 전체 데이터 저장
            table.setItem(row_index, 0, rn_item)
            
            # 나머지 아이템
            table.setItem(row_index, 1, QTableWidgetItem(row_data['worker']))
            table.setItem(row_index, 2, QTableWidgetItem(row_data['region']))
            table.setItem(row_index, 3, QTableWidgetItem(row_data['status']))
            
            # 버튼 컬럼 아이템 추가 (4번) - 델리게이트가 그려줌
            button_item = QTableWidgetItem("")
            table.setItem(row_index, 4, button_item)

    def populate_recent_subsidy_rows(self):
        """최근 지원금 신청 데이터를 테이블에 채운다."""
        table = self.complement_table_widget
        
        # 필터 모드에 따라 다른 SQL 함수 호출
        try:
            if self._filter_mode == 'all':
                df = fetch_recent_subsidy_applications()
            elif self._filter_mode == 'my':
                if not self._worker_id:
                    table.setRowCount(0)
                    return
                df = fetch_today_subsidy_applications_by_worker(self._worker_id)
            elif self._filter_mode == 'unfinished':
                df = fetch_today_unfinished_subsidy_applications()
            else:
                df = fetch_recent_subsidy_applications()
        
        except Exception as error:  # pragma: no cover - UI 경고용
            QMessageBox.warning(self, "데이터 로드 실패", f"지원금 신청 데이터 조회 중 오류가 발생했습니다.\n{error}")
            table.setRowCount(0)
            return

        if df is None or df.empty:
            print("[populate_recent_subsidy_rows] 조회된 지원금 신청 데이터 없음.")
            table.setRowCount(0)
            return

        self._check_unassigned_subsidies(df)

        row_count = len(df)
        table.setRowCount(row_count)

        for row_index, (_, row) in enumerate(df.iterrows()):
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
                'mail_count': row.get('mail_count', 0),  # mail_count 추가
                'outlier': self._sanitize_text(row.get('outlier', '')),  # 이상치 정보 추가
                'original_filepath': self._normalize_file_path(row.get('original_filepath')), # 이 줄을 추가
                'child_birth_date': row.get('child_birth_date', ''), # 다자녀 생년월일 추가
                '다자녀': row.get('다자녀', 0), # 다자녀 플래그 추가
                'ai_계약일자': row.get('ai_계약일자'),  # 구매계약서 필드 추가
                'ai_이름': row.get('ai_이름'),
                '전화번호': row.get('전화번호'),
                '이메일': row.get('이메일'),
                '차종': row.get('차종'),  # 차종 필드 추가
                'chobon_name': row.get('name'),  # 'name' 컬럼 사용
                'chobon_birth_date': row.get('birth_date'), # 'birth_date' 컬럼 사용
                'chobon_address_1': row.get('address_1'), # 'address_1' 컬럼 사용
                'chobon': row.get('chobon', 0),  # chobon 칼럼 추가
                'is_법인': row.get('is_법인', 0),  # is_법인 칼럼 추가
                'page_number': row.get('page_number'),  # page_number 추가
                'issue_date': row.get('issue_date'), # issue_date 추가
                'birth_date': row.get('birth_date', ''), # birth_date 추가
                'address_1': row.get('address_1', ''), # address_1 추가
                'all_ai': row.get('all_ai', 0)  # all_ai 추가
            }

            # 'AI' 칼럼 값 계산 - rns.all_ai 컬럼 사용
            ai_status = 'O' if row_data.get('all_ai', 0) == 1 else 'X'
            
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

            # 버튼 컬럼 아이템 추가 (5번) - 델리게이트가 그려줌
            button_item = QTableWidgetItem("")
            table.setItem(row_index, 5, button_item)
            
            # finished_file_path를 row_data에 추가
            row_data['finished_file_path'] = self._normalize_file_path(row.get('finished_file_path'))
            rn_item.setData(Qt.ItemDataRole.UserRole, row_data)

            # --- Row Highlighting ---
            # urgent 칼럼이 1이면 전체 행에 빨간색 하이라이트 (최우선)
            if row_data['urgent'] == 1:
                highlight_color = QColor(220, 53, 69, 180)  # 빨간색 (Bootstrap의 danger 색상과 유사)
                text_color = QColor("white")
                
                # 모든 컬럼에 하이라이트 적용
                for col in range(table.columnCount()):
                    item = table.item(row_index, col)
                    if item:
                        item.setData(HighlightRole, highlight_color)
                        item.setForeground(text_color)
            # urgent가 아닌 경우에만 mail_count 하이라이트 적용
            elif row_data.get('mail_count', 0) >= 2:
                mail_highlight_color = QColor(255, 249, 170, 180)  # 연한 노란색
                mail_text_color = QColor("black")
                
                # RN 컬럼(1번)에만 하이라이트 적용
                rn_item = table.item(row_index, 1)
                if rn_item:
                    rn_item.setData(HighlightRole, mail_highlight_color)
                    rn_item.setForeground(mail_text_color)
        
        # AI 체크박스 필터링 적용
        self._apply_ai_filter()

    def _check_unassigned_subsidies(self, df: pd.DataFrame):
        """
        10분 이상 할당되지 않은 보조금에 대해 확인하고 알림을 표시합니다.
        미할당 상태가 지속되면 한 주기를 건너뛰고 다시 알림을 보냅니다.
        """
        if df is None or df.empty:
            return

        # KST timezone 설정
        kst = pytz.timezone('Asia/Seoul')

        for _, row in df.iterrows():
            try:
                # _alert_tracker 딕셔너리가 없으면 생성
                if not hasattr(self, '_alert_tracker'):
                    self._alert_tracker = {}

                worker_val = row.get('worker')
                rn_val = row.get('RN')
                
                # '추후 신청' 상태인 경우 알림 건너뛰기
                if row.get('result') == '추후 신청':
                    continue
                
                # 작업자가 없거나 비어있는 경우
                if not worker_val or pd.isna(worker_val) or str(worker_val).strip() == "":
                    recent_received_date = row.get('recent_received_date')

                    if pd.notna(recent_received_date):
                        # pandas timestamp 등을 python datetime으로 변환
                        if isinstance(recent_received_date, pd.Timestamp):
                            received_time = recent_received_date.to_pydatetime()
                        elif isinstance(recent_received_date, str):
                            received_time = datetime.strptime(str(recent_received_date), "%Y-%m-%d %H:%M:%S")
                        else:
                            received_time = recent_received_date

                        # received_time이 datetime 객체인 경우에만 계산
                        if isinstance(received_time, datetime):
                            # timezone-aware datetime으로 통일
                            now = datetime.now(kst)
                            
                            # received_time이 naive인 경우 timezone-aware로 변환
                            # PostgreSQL의 timestampz는 timezone-aware이지만, 
                            # pandas나 문자열 파싱 결과는 naive일 수 있음
                            if received_time.tzinfo is None:
                                # naive datetime을 KST로 가정하고 변환
                                received_time = kst.localize(received_time)
                            else:
                                # 이미 timezone-aware인 경우 KST로 변환
                                received_time = received_time.astimezone(kst)
                            
                            # 10분 이상 미할당된 경우 (600초)
                            if (now - received_time).total_seconds() >= 600:
                                
                                # 첫 로드 시에는 알림을 보내지 않음
                                if self._is_first_load:
                                    continue

                                # 애플리케이션이 활성화되어 있지 않을 때만 토스트 알림을 띄움
                                if not QApplication.activeWindow() == self.window():
                                    alert_state = self._alert_tracker.get(rn_val, 0)
                                    alert_message = (
                                        f"10분 이상 작업자가 배정되지 않았습니다.\n"
                                        f"RN: {rn_val}\n"
                                        f"접수시간: {received_time.strftime('%Y-%m-%d %H:%M:%S')}"
                                    )
                                    
                                    if alert_state == 0:
                                        # 상태 0: 첫 알림
                                        print(f"[알림] 10분 이상 미할당: {rn_val} (접수시간: {received_time.strftime('%Y-%m-%d %H:%M:%S')})")
                                        show_toast("미배정 알림", alert_message, self, received_time)
                                        self._alert_tracker[rn_val] = 1
                                    
                                    elif alert_state == 1:
                                        # 상태 1: 알림 후 첫 새로고침, 알림 건너뛰기
                                        self._alert_tracker[rn_val] = 2

                                    elif alert_state == 2:
                                        # 상태 2: 알림 후 두 번째 새로고침, 다시 알림
                                        print(f"[알림] 미할당 지속: {rn_val} (접수시간: {received_time.strftime('%Y-%m-%d %H:%M:%S')})")
                                        show_toast("미배정 지속 알림", alert_message, self, received_time)
                                        self._alert_tracker[rn_val] = 1 # 다시 다음 주기는 건너뛰도록 상태 1로 복귀
                else:
                    # 작업자가 할당된 경우, 추적 목록에서 제거하여 알림 로직 초기화
                    if rn_val in self._alert_tracker:
                        del self._alert_tracker[rn_val]

            except Exception as e:
                # Log the error for debugging, but don't crash the UI
                print(f"Error checking unassigned subsidy for RN {row.get('RN', 'N/A')}: {e}")
        
        # 첫 로드 완료 처리
        if self._is_first_load:
            self._is_first_load = False

    def show_context_menu(self, pos: QPoint):
        """테이블 컨텍스트 메뉴 표시"""
        table = self.complement_table_widget
        global_pos = table.viewport().mapToGlobal(pos)

        # 클릭한 위치의 행 확인
        item = table.itemAt(pos)
        if item is None:
            return
        
        row = item.row()
        rn_item = table.item(row, 1)  # RN 컬럼(1번)
        
        # mail_count 확인
        mail_count = 0
        if rn_item:
            row_data = rn_item.data(Qt.ItemDataRole.UserRole)
            if isinstance(row_data, dict):
                mail_count_raw = row_data.get('mail_count', 0)
                # 숫자 타입 변환 (pandas에서 가져온 값이 float일 수 있음)
                try:
                    mail_count = int(mail_count_raw) if mail_count_raw is not None else 0
                except (ValueError, TypeError):
                    mail_count = 0

        menu = QMenu(self)  
        
        # '비고' 메뉴 추가
        note_action = menu.addAction("비고")
        
        # mail_count >= 2인 경우에만 '이메일 확인하기' 메뉴 추가 (하이라이트 조건과 동일)
        email_action = None
        if mail_count >= 2:
            menu.addSeparator()  # 구분선 추가
            email_action = menu.addAction("이메일 확인하기")
        
        action = menu.exec(global_pos)

        # action이 None이면 아무것도 하지 않음 (메뉴 밖 클릭 또는 ESC)
        if action is None:
            return

        if action == email_action:
            self._show_email_view(row)
        elif action == note_action:
            # TODO: '비고' 기능 구현 예정
            pass
    
    def _show_email_view(self, row: int):
        """이메일 확인 다이얼로그를 표시한다."""
        table = self.complement_table_widget
        rn_item = table.item(row, 1)  # RN 컬럼(1번)
        
        if not rn_item:
            QMessageBox.warning(self, "오류", "데이터를 불러올 수 없습니다.")
            return
        
        # 행 데이터에서 recent_thread_id 가져오기
        row_data = rn_item.data(Qt.ItemDataRole.UserRole)
        if not row_data or not isinstance(row_data, dict):
            QMessageBox.warning(self, "오류", "데이터를 불러올 수 없습니다.")
            return
        
        recent_thread_id = row_data.get('recent_thread_id', '')
        if not recent_thread_id:
            QMessageBox.information(self, "정보", "연결된 이메일 thread_id가 없습니다.")
            return
        
        # thread_id로 이메일 정보 조회
        email_data = get_email_by_thread_id(recent_thread_id)
        if not email_data:
            QMessageBox.warning(self, "오류", "이메일 정보를 찾을 수 없습니다.")
            return
        
        # 이메일 확인 다이얼로그 표시
        dialog = EmailViewDialog(
            title=email_data.get('title', ''),
            content=email_data.get('content', ''),
            parent=self
        )
        dialog.exec()
    
    def _show_gemini_results(self, row: int):
        """AI 결과 다이얼로그(상세 정보)를 비모달로 표시한다."""
        table = self.complement_table_widget
        rn_item = table.item(row, 1)  # RN 컬럼(1번)
        
        if not rn_item:
            QMessageBox.warning(self, "오류", "데이터를 불러올 수 없습니다.")
            return
        
        # RN 추출
        rn = rn_item.text().strip()
        if not rn:
            QMessageBox.warning(self, "오류", "RN을 찾을 수 없습니다.")
            return
        
        # gemini_results 존재 여부 확인 (기존 로직 유지)
        flags = check_gemini_flags(rn)
        if not flags:
            QMessageBox.warning(self, "경고", f"RN '{rn}'에 대한 AI 결과가 없습니다.")
            return
        
        # DetailFormDialog 비모달로 생성하고 표시
        dialog = DetailFormDialog(parent=self)
        dialog.load_data(rn)
        dialog.show()  # 비모달로 표시

    def start_selected_work(self):
        """선택된 행을 emit하여 다운로드 로직이 처리하도록 한다."""
        table = self.complement_table_widget
        selected_items = table.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "선택 필요", "작업을 시작할 행을 선택해주세요.")
            return

        row = selected_items[0].row()
        
        self._is_context_menu_work = True
        self._start_work_by_row(row)
        self._is_context_menu_work = False

    def _start_work_by_row(self, row):
        """특정 행의 작업을 시작한다."""
        table = self.complement_table_widget
        rn_item = table.item(row, 1)  # RN은 1번 컬럼

        # AI 결과가 있는 경우 -> AI 결과 창 열기
        ai_item = table.item(row, 4)
        if ai_item and ai_item.text() == 'O':
            if rn_item:
                self.ai_review_requested.emit(rn_item.text())

        # 파일 경로는 SQL의 original_filepath에서 가져옴
        row_data = rn_item.data(Qt.ItemDataRole.UserRole)
        if not row_data or not isinstance(row_data, dict):
            QMessageBox.warning(self, "파일 없음", "데이터를 불러올 수 없습니다.")
            return

        worker = row_data.get('worker')
        finished_file_path = row_data.get('finished_file_path')
        original_file_path = row_data.get('original_filepath')
        
        # RN 추출
        rn = self._safe_item_text(rn_item)
        
        # 작업자가 비어있을 때 worker_id 업데이트 (지급 테이블과 유사한 로직)
        if not worker or not worker.strip():
            if self._worker_id:
                success = update_rns_worker_id(rn, self._worker_id)
                if success:
                    print(f"[지원 시작] 작업자 ID 업데이트 완료: {self._worker_id} (RN: {rn})")
                    # 테이블의 작업자 컬럼(2번)도 업데이트
                    worker_item = table.item(row, 2)
                    if worker_item and self._worker_name:
                        worker_item.setText(self._worker_name)
                    # row_data와 worker 변수도 업데이트
                    row_data['worker'] = self._worker_name
                    worker = self._worker_name
                    rn_item.setData(Qt.ItemDataRole.UserRole, row_data)
                else:
                    print(f"[지원 시작] 작업자 ID 업데이트 실패 (RN: {rn})")
            else:
                print(f"[지원 시작] 작업자 ID가 설정되지 않았습니다.")
        else:
            print(f"[지원 시작] 작업자 업데이트 건너뜀: 이미 '{worker}'로 할당됨")

        # status가 '신규'일 때만 '처리중'으로 업데이트
        status_updated = update_subsidy_status_if_new(rn, '처리중')
        if status_updated:
            print(f"[지원 시작] status 업데이트 완료: '신규' -> '처리중' (RN: {rn})")
            # 테이블의 '결과' 컬럼(3번)도 업데이트
            result_item = table.item(row, 3)
            if result_item:
                result_item.setText('처리중')
        else:
            pass

        # 결과 상태 확인 (3번 컬럼) - 업데이트 이후의 값을 확인
        result_item = table.item(row, 3)
        result_text = self._safe_item_text(result_item)

        file_path = ""
        # '추후 신청'인 경우 원본 파일 경로 우선 사용
        if result_text == "추후 신청" and original_file_path:
            file_path = self._normalize_file_path(original_file_path)
            print(f"[지원 시작] '추후 신청' 건이므로 원본 파일 경로 사용: {file_path}")
        # 작업자가 할당된 경우, finished_file_path 우선 사용
        elif worker and finished_file_path:
            file_path = finished_file_path
        # 그 외의 경우 original_filepath 사용
        else:
            if original_file_path:
                file_path = self._normalize_file_path(original_file_path)

        if not file_path:
            QMessageBox.warning(self, "파일 없음", "연결된 파일 경로가 없습니다.")
            return

        # 정규화된 파일 경로 -> 추후에 load_document 에서 사용
        resolved_path = Path(file_path)
        if not resolved_path.exists():
            QMessageBox.warning(
                self,
                "파일 없음",
                f"경로를 찾을 수 없습니다.\n{resolved_path}"
            )
            return

        metadata = self._extract_row_metadata(rn_item)

        # '추후 신청'인 경우 메타데이터에서도 finished_file_path 제거 (원본으로 로드하기 위함)
        if result_text == "추후 신청":
            metadata['finished_file_path'] = ""
            metadata['file_rendered'] = 0
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
    
    @staticmethod
    def _normalize_file_path(raw_path):
        return get_converted_path(raw_path)
    
    def _setup_filter_buttons(self):
        """필터 라디오 버튼 그룹 설정"""
        if not (hasattr(self, 'radioButton_all_rows') and 
                hasattr(self, 'radioButton_my_rows') and 
                hasattr(self, 'radioButton_unfinished_rows')):
            return
        
        # QButtonGroup으로 묶어서 단일 선택 보장
        self._filter_button_group = QButtonGroup(self)
        self._filter_button_group.addButton(self.radioButton_all_rows, 0)  # 'all'
        self._filter_button_group.addButton(self.radioButton_my_rows, 1)    # 'my'
        self._filter_button_group.addButton(self.radioButton_unfinished_rows, 2)  # 'unfinished'
        
        # 기본값: 전체보기 선택
        self.radioButton_all_rows.setChecked(True)
        
        # 버튼 클릭 시 필터 적용
        self._filter_button_group.buttonClicked.connect(self._on_filter_changed)
    
    def _on_filter_changed(self, button):
        """필터 변경 시 호출되는 슬롯"""
        if button == self.radioButton_all_rows:
            self._filter_mode = 'all'
        elif button == self.radioButton_my_rows:
            self._filter_mode = 'my'
        elif button == self.radioButton_unfinished_rows:
            self._filter_mode = 'unfinished'
        
        # 테이블 데이터 다시 로드 (필터 적용)
        self.populate_recent_subsidy_rows()
    
    def _on_ai_filter_changed(self):
        """AI 체크박스 상태 변경 시 호출되는 슬롯"""
        self._apply_ai_filter()
    
    def _apply_ai_filter(self):
        """AI 체크박스 상태에 따라 테이블 행을 필터링한다."""
        if not hasattr(self, 'ai_checkbox') or not hasattr(self, 'complement_table_widget'):
            return
        
        table = self.complement_table_widget
        is_checked = self.ai_checkbox.isChecked()
        
        # 체크박스가 체크되어 있으면 AI='O'인 row만 표시
        for row_index in range(table.rowCount()):
            ai_item = table.item(row_index, 4)  # AI 컬럼은 4번 인덱스
            if ai_item:
                ai_value = ai_item.text()
                # AI='O'인 경우에만 표시, 체크박스가 해제되어 있으면 모두 표시
                table.setRowHidden(row_index, is_checked and ai_value != 'O')
    
    def set_worker_name(self, worker_name: str):
        """작업자 이름을 설정한다."""
        self._worker_name = worker_name or ''
    
    def set_worker_id(self, worker_id: int | None):
        """작업자 ID를 설정한다."""
        self._worker_id = worker_id
    
    def set_payment_request_load_enabled(self, enabled: bool):
        """지급신청 로드 체크박스 상태를 설정한다."""
        self._payment_request_load_enabled = enabled
    
    def setup_connections(self):
        """시그널-슬롯 연결"""
        if hasattr(self, 'center_open_btn'):
            self.center_open_btn.clicked.connect(self.open_pdf_file)
        if hasattr(self, 'center_refresh_btn'):
            self.center_refresh_btn.clicked.connect(lambda: self.refresh_data(force_refresh_give_works=True))
        if hasattr(self, 'center_open_rn_btn'):
            self.center_open_rn_btn.clicked.connect(self.open_by_rn)
        if hasattr(self, 'pushButton_more'):
            self.pushButton_more.clicked.connect(self.open_history_dialog)
        if hasattr(self, 'ai_checkbox'):
            self.ai_checkbox.stateChanged.connect(self._on_ai_filter_changed)
    
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
            
        # AI 결과가 있는 경우 -> AI 결과 창 열기 (all_ai 컬럼 사용)
        all_ai = data.get('all_ai', 0) == 1
        if all_ai:
            self.ai_review_requested.emit(rn)

        # 파일 경로 확인
        file_path = self._normalize_file_path(data.get('original_filepath'))
        
        if not file_path:
            QMessageBox.warning(self, "파일 없음", "해당 RN에 연결된 파일 경로가 DB에 없습니다.")
            return

        worker = data.get('worker')
        finished_file_path = data.get('finished_file_path')
        original_file_path = data.get('original_filepath')

        file_path = ""
        if worker and finished_file_path:
            file_path = finished_file_path
        else:
            if original_file_path:
                file_path = self._normalize_file_path(original_file_path)

        if not file_path:
            QMessageBox.warning(self, "파일 없음", "해당 RN에 연결된 파일 경로가 DB에 없습니다.")
            return

        resolved_path = Path(file_path)
        if not resolved_path.exists():
            QMessageBox.warning(self, "파일 없음", f"파일을 찾을 수 없습니다.\n{resolved_path}")
            return
            
        
        # SQL 함수 수정 필요 (sql_manager.py의 fetch_application_data_by_rn에 child_birth_date와 다자녀 칼럼 추가 필요)
        # 이미 쿼리에 포함되어 있다면 data 딕셔너리에 자동으로 들어옴.
        # 위 fetch_application_data_by_rn 함수 확인 결과:
        # "       gr.구매계약서, gr.초본, gr.공동명의, gr.다자녀, "
        # "       d.child_birth_date, cb.issue_date, "
        # ... 로 child_birth_date와 다자녀가 조회되고 있음.
        
        # 메타데이터 구성 (start_selected_work와 포맷 통일)
        metadata = {
            'rn': data.get('RN', rn),
            'name': data.get('name', ''),
            'region': data.get('region', ''),
            'worker': data.get('worker', ''),
            'finished_file_path': data.get('finished_file_path', ''), # 추가
            '구매계약서': data.get('구매계약서', 0),
            '초본': data.get('초본', 0),
            '공동명의': data.get('공동명의', 0),
            'ai_계약일자': data.get('ai_계약일자'),
            'ai_이름': data.get('ai_이름'),
            '전화번호': data.get('전화번호'),
            '이메일': data.get('이메일'),
            '차종': data.get('차종'),  # 차종 필드 추가
            'chobon_name': data.get('name'),
            'chobon_birth_date': data.get('birth_date'),
            'chobon_address_1': data.get('address_1'),
            'chobon': data.get('chobon', 0),
            'special_note': data.get('special_note', ''),
            'recent_thread_id': data.get('recent_thread_id', ''),
            'file_rendered': data.get('file_rendered', 0),
            'urgent': data.get('urgent', 0),
            'mail_count': data.get('mail_count', 0),
            'outlier': data.get('outlier', ''),
            'original_filepath': original_file_path, # original_filepath로 수정
            'is_법인': data.get('is_법인', 0),
            'is_context_menu_work': True, # 컨텍스트 메뉴와 동일하게 동작하도록 True로 설정
            'page_number': data.get('page_number'), # page_number 추가
            'issue_date': data.get('issue_date'), # issue_date 추가
            'birth_date': data.get('birth_date', ''), # birth_date 추가
            'address_1': data.get('address_1', '') # address_1 추가
        }
        
        # 작업 시작 시그널 발생
        self.work_started.emit([str(resolved_path)], metadata)

    def open_history_dialog(self):
        """더보기(More) 버튼 클릭 시 전체 내역 다이얼로그 표시"""
        dialog = SubsidyHistoryDialog(parent=self, worker_id=self._worker_id)
        
        # 다이얼로그의 시그널을 메인 위젯의 시그널과 연결 (릴레이)
        dialog.work_started.connect(self.work_started.emit)
        dialog.ai_review_requested.connect(self.ai_review_requested.emit)
        
        dialog.exec()

    def open_pdf_file(self):
        """로컬에서 PDF 또는 이미지 파일을 연다 (다중 선택 가능)"""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "파일 선택",
            "",
            "지원 파일 (*.pdf *.png *.jpg *.jpeg);;PDF Files (*.pdf);;Image Files (*.png *.jpg *.jpeg);;All Files (*)"
        )
        
        if paths:
            self.pdf_selected.emit(paths, {})
    
    def refresh_data(self, force_refresh_give_works: bool = False):
        """sql 데이터 새로고침
        
        Args:
            force_refresh_give_works: True이면 체크박스 상태와 관계없이 지급 테이블을 새로고침합니다.
                                     False이면 체크박스가 체크되어 있을 때만 지급 테이블을 새로고침합니다.
        """
        self.populate_recent_subsidy_rows()
        
        # 지급 테이블 새로고침 여부 결정
        should_refresh_give_works = force_refresh_give_works
        if not should_refresh_give_works:
            # 인스턴스 변수에서 체크박스 상태 확인
            should_refresh_give_works = self._payment_request_load_enabled
        
        if should_refresh_give_works and hasattr(self, 'tableWidget'):
            self.populate_give_works_rows()
        
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
            return {'rn': "", 'name': "", 'region': "", 'worker': "", 'special_note': "", 'recent_thread_id': "", 'file_rendered': 0, 'urgent': 0, 'mail_count': 0, 'outlier': "", 'is_context_menu_work': False}
        data = rn_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return {'rn': "", 'name': "", 'region': "", 'worker': "", 'special_note': "", 'recent_thread_id': "", 'file_rendered': 0, 'urgent': 0, 'mail_count': 0, 'outlier': "", 'is_context_menu_work': False}
        return {
            'rn': data.get('rn', ""),
            'name': data.get('name', ""),
            'region': data.get('region', ""),
            'worker': data.get('worker', ""),
            'special_note': data.get('special_note', ""),
            'recent_thread_id': data.get('recent_thread_id', ""),
            'file_rendered': data.get('file_rendered', 0),
            'urgent': data.get('urgent', 0),
            'mail_count': data.get('mail_count', 0),
            'outlier': data.get('outlier', ""),
            'original_filepath': data.get('original_filepath', ""), # 이 줄을 추가
            'finished_file_path': data.get('finished_file_path', ''), # 추가
            '구매계약서': data.get('구매계약서', 0),  # 구매계약서 플래그 추가
            '초본': data.get('초본', 0),  # 초본 플래그 추가
            '공동명의': data.get('공동명의', 0),  # 공동명의 플래그 추가
            'ai_계약일자': data.get('ai_계약일자'),  # 구매계약서 필드 추가
            'ai_이름': data.get('ai_이름'),
            '전화번호': data.get('전화번호'),
            '이메일': data.get('이메일'),
            '차종': data.get('차종'),  # 차종 필드 추가
            'chobon_name': data.get('name'),  # 'name' 컬럼 사용
            'chobon_birth_date': data.get('birth_date'), # 'birth_date' 컬럼 사용
            'chobon_address_1': data.get('address_1'), # 'address_1' 컬럼 사용
            'chobon': data.get('chobon', 0),  # chobon 칼럼 추가
            'is_법인': data.get('is_법인', 0),  # is_법인 칼럼 추가
            'is_context_menu_work': False,  # 기본값은 False, 실제 값은 start_selected_work에서 설정
            'child_birth_date': data.get('child_birth_date', ''), # 다자녀 자녀 생년월일 목록 추가
            '다자녀': data.get('다자녀', 0), # 다자녀 플래그 추가
            'page_number': data.get('page_number'), # page_number 추가
            'issue_date': data.get('issue_date'), # issue_date 추가
            'birth_date': data.get('birth_date', ''), # birth_date 추가
            'address_1': data.get('address_1', '') # address_1 추가
        }

    def get_selected_rn(self) -> str | None:
        """현재 선택된 행의 RN을 반환한다."""
        if not hasattr(self, 'complement_table_widget'):
            return None
            
        table = self.complement_table_widget
        # 선택된 범위(SelectionRange)를 확인
        ranges = table.selectedRanges()
        if not ranges:
            # 선택된 아이템으로 대체 확인
            selected_items = table.selectedItems()
            if not selected_items:
                return None
            row = selected_items[0].row()
        else:
            # 첫 번째 선택 영역의 첫 번째 행 사용
            row = ranges[0].topRow()
        
        # RN 컬럼은 1번
        rn_item = table.item(row, 1)
        if rn_item:
            return rn_item.text().strip()
        return None
