import re
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import QWidget, QMessageBox, QCheckBox, QTextEdit, QVBoxLayout, QDialog, QLabel, QPushButton, QHBoxLayout, QLineEdit, QDialogButtonBox, QScrollArea
from PyQt6.QtCore import pyqtSignal, QTimer, Qt

class RegionEditDialog(QDialog):
    """지역 수정을 위한 다이얼로그"""
    def __init__(self, current_region: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("지역 수정")
        self.setFixedWidth(300)
        
        layout = QVBoxLayout(self)
        
        # 기존 지역명 표시
        layout.addWidget(QLabel("기존 지역명:"))
        self.old_region_edit = QLineEdit(current_region)
        self.old_region_edit.setReadOnly(True)
        self.old_region_edit.setStyleSheet("background-color: #f0f0f0; color: #666;")
        layout.addWidget(self.old_region_edit)
        
        # 변경할 지역명 입력
        layout.addWidget(QLabel("변경할 지역명:"))
        self.new_region_edit = QLineEdit()
        self.new_region_edit.setPlaceholderText("새로운 지역명을 입력하세요")
        layout.addWidget(self.new_region_edit)
        
        # 버튼 박스
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
    def get_new_region(self) -> str:
        return self.new_region_edit.text().strip()

class SpecialEditDialog(QDialog):
    """특이사항 수정을 위한 다이얼로그 (행 기반)"""
    def __init__(self, current_special: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("특이사항 수정")
        self.setFixedWidth(400)
        self.setMinimumHeight(300)
        
        self.layout = QVBoxLayout(self)
        
        # 안내 문구
        self.layout.addWidget(QLabel("특이사항 항목 (한 행에 하나씩 입력하세요):"))
        
        # 스크롤 영역 (항목이 많아질 경우 대비)
        from PyQt6.QtWidgets import QScrollArea
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.items_layout = QVBoxLayout(self.scroll_content)
        self.items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)
        
        self.row_widgets = []
        
        # 기존 항목 추가
        if current_special:
            for item in current_special:
                self._add_row(item)
        else:
            # 항목이 하나도 없으면 빈 항목 하나 추가
            self._add_row("")
            
        # 추가 버튼
        self.add_btn = QPushButton("+ 항목 추가")
        self.add_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.add_btn.clicked.connect(lambda: self._add_row(""))
        self.layout.addWidget(self.add_btn)
        
        # 버튼 박스
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.layout.addWidget(button_box)
        
    def _add_row(self, text: str):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        
        line_edit = QLineEdit(text)
        line_edit.setPlaceholderText("특이사항 입력")
        row_layout.addWidget(line_edit)
        
        del_btn = QPushButton("삭제")
        del_btn.setFixedWidth(40)
        del_btn.setStyleSheet("background-color: #f44336; color: white;")
        del_btn.clicked.connect(lambda: self._remove_row(row_widget))
        row_layout.addWidget(del_btn)
        
        self.items_layout.addWidget(row_widget)
        self.row_widgets.append((row_widget, line_edit))
        
    def _remove_row(self, widget):
        if len(self.row_widgets) <= 1:
            # 최소 하나는 남겨둠 (또는 그냥 삭제 허용)
            # return
            pass
            
        for i, (w, _) in enumerate(self.row_widgets):
            if w == widget:
                self.items_layout.removeWidget(w)
                w.deleteLater()
                self.row_widgets.pop(i)
                break
                
    def get_special_list(self) -> list[str]:
        special_list = []
        for _, line_edit in self.row_widgets:
            text = line_edit.text().strip()
            if text:
                special_list.append(text)
        return special_list


class InfoPanelWidget(QWidget):
    """PDF 파일 및 페이지 정보를 표시하는 위젯"""
    text_stamp_requested = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "info_panel.ui"
        uic.loadUi(str(ui_path), self)
        
        self._delivery_day_gap: int | None = None # day_gap 저장 변수
        self._dynamic_checkboxes = [] # 동적으로 생성된 체크박스 리스트
        self._current_rn: str = "" # 현재 표시 중인 RN 저장
        self._initial_error_items = set() # 최초 로드된 에러 항목 저장 (비교용)
        self._is_ev_complement_mode = False # EV 보완 모드 여부
        
        # 현재 로그인한 작업자 정보
        self._worker_id: int | None = None

        # 자동 새로고침 타이머 설정 (20초)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(20000)
        self._refresh_timer.timeout.connect(self._on_refresh_timeout)

        if hasattr(self, 'pushButton_insert_text'):
            self.pushButton_insert_text.clicked.connect(self._on_insert_text_clicked)
        
        # 라디오 버튼 시그널 연결
        if hasattr(self, 'radioButton_2'):
            self.radioButton_2.toggled.connect(self._on_radio_button_2_toggled)
            
        if hasattr(self, 'radioButton_3'):
            self.radioButton_3.toggled.connect(self._on_radio_button_subsidy_toggled)

        # 메모 저장 버튼 연결
        if hasattr(self, 'pushButton_save_memo'):
            self.pushButton_save_memo.clicked.connect(self._on_save_memo_clicked)

        # 확인필요 버튼 연결
        if hasattr(self, 'pushButton_needs_check'):
            self.pushButton_needs_check.clicked.connect(self._on_needs_check_clicked)

        # 지역 수정 버튼 연결
        if hasattr(self, 'pushButton_edit_region'):
            self.pushButton_edit_region.clicked.connect(self._on_edit_region_clicked)

        # 특이사항 수정 버튼 연결
        if hasattr(self, 'pushButton_edit_special'):
            self.pushButton_edit_special.clicked.connect(self._on_edit_special_clicked)

        # 입력 필드를 읽기 전용으로 설정
        if hasattr(self, 'lineEdit_region'):
            self.lineEdit_region.setReadOnly(True)
            
        if hasattr(self, 'lineEdit_special'):
            self.lineEdit_special.setReadOnly(True)



    def _on_save_memo_clicked(self):
        """메모 저장 버튼 클릭 시 처리"""
        if not self._current_rn:
            QMessageBox.warning(self, "경고", "RN 정보가 없습니다.")
            return
        
        if self._worker_id is None:
            QMessageBox.warning(self, "경고", "작업자 정보가 없습니다. 다시 로그인해주세요.")
            return

        comment = self.textEdit_memo_input.toPlainText().strip()
        if not comment:
            return

        from core.sql_manager import insert_user_memo
        if insert_user_memo(self._current_rn, self._worker_id, comment):
            self.textEdit_memo_input.clear()
            self._refresh_memo_list()
        else:
            QMessageBox.critical(self, "오류", "메모 저장에 실패했습니다.")

    def _on_needs_check_clicked(self):
        """'확인필요' 버튼 클릭 시 처리"""
        if not self._current_rn:
            QMessageBox.warning(self, "경고", "RN 정보가 없습니다.")
            return

        reply = QMessageBox.question(
            self, "확인", 
            f"현재 RN({self._current_rn})의 상태를 '확인필요'로 변경하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            from core.sql_manager import update_subsidy_status
            if update_subsidy_status(self._current_rn, '확인필요'):
                QMessageBox.information(self, "성공", "상태가 '확인필요'로 변경되었습니다.")
                # 작업 리스트 갱신 등의 필요한 조치를 취할 수 있음
            else:
                QMessageBox.critical(self, "오류", "상태 변경에 실패했습니다.")

    def _refresh_memo_list(self):
        """현재 RN의 메모 리스트를 새로고침한다."""
        if not hasattr(self, 'listWidget_memos'):
            return
            
        self.listWidget_memos.clear()
        if not self._current_rn:
            return

        from core.sql_manager import fetch_user_memos
        memos = fetch_user_memos(self._current_rn)
        
        for memo in memos:
            # [12/31 14:20] 홍길동: 메모내용
            created_at = memo['created_at']
            if isinstance(created_at, datetime):
                time_str = created_at.strftime("%m/%d %H:%M")
            else:
                time_str = str(created_at)
                
            worker_name = memo.get('worker_name') or "알 수 없음"
            content = memo['comment']
            
            item_text = f"[{time_str}] {worker_name}: {content}"
            self.listWidget_memos.addItem(item_text)
            
        # 가장 최근 메모가 위로 오도록 함 (이미 ORDER BY created_at DESC)
        # 필요한 경우 스크롤을 맨 위로
        self.listWidget_memos.scrollToTop()

    def _on_edit_region_clicked(self):
        """지역 수정 버튼 클릭 시 처리"""
        if not self._current_rn:
            QMessageBox.warning(self, "경고", "RN 정보가 없습니다.")
            return

        current_region = self.lineEdit_region.text()
        dialog = RegionEditDialog(current_region, self)
        
        if dialog.exec():
            new_region = dialog.get_new_region()
            if not new_region:
                QMessageBox.warning(self, "경고", "변경할 지역명을 입력해주세요.")
                return
            
            if new_region == current_region:
                return

            # DB 업데이트
            from core.sql_manager import update_rn_region
            if update_rn_region(self._current_rn, new_region):
                self.lineEdit_region.setText(new_region)
                QMessageBox.information(self, "성공", "지역 정보가 수정되었습니다.")
            else:
                QMessageBox.critical(self, "오류", "지역 정보 수정에 실패했습니다.")

    def _on_edit_special_clicked(self):
        """특이사항 수정 버튼 클릭 시 처리"""
        if not self._current_rn:
            QMessageBox.warning(self, "경고", "RN 정보가 없습니다.")
            return

        # 현재 특이사항 리스트 가져오기
        current_text = self.lineEdit_special.text()
        # 콤마로 구분된 문자열을 리스트로 변환 (빈 문자열 처리)
        current_list = [s.strip() for s in current_text.split(',')] if current_text else []
        
        dialog = SpecialEditDialog(current_list, self)
        
        if dialog.exec():
            new_list = dialog.get_special_list()
            
            # DB 업데이트
            from core.sql_manager import update_rn_special
            if update_rn_special(self._current_rn, new_list):
                # UI 업데이트 (리스트를 콤마로 구분된 문자열로)
                self.lineEdit_special.setText(", ".join(new_list))
                QMessageBox.information(self, "성공", "특이사항 정보가 수정되었습니다.")
            else:
                QMessageBox.critical(self, "오류", "특이사항 정보 수정에 실패했습니다.")

    def showEvent(self, event):
        """위젯이 보여질 때 타이머 시작"""
        super().showEvent(event)
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def hideEvent(self, event):
        """위젯이 숨겨질 때 타이머 중지"""
        super().hideEvent(event)
        self._refresh_timer.stop()

    def _on_refresh_timeout(self):
        """타이머 타임아웃 시 작업 리스트 갱신"""
        if self._current_rn and self.isVisible():
            # 현재 RN으로 작업 리스트만 업데이트 (초기 로드 아님)
            # print(f"Auto-refreshing task list for RN: {self._current_rn}")
            self.update_task_list(self._current_rn, is_initial_load=False)

    def set_ev_complement_mode(self, is_enabled: bool, ev_memo: str = ""):
        """
        ev_complement 모드 설정.
        True일 경우 작업 리스트를 ev_memo를 보여주는 텍스트 영역으로 교체한다.
        False일 경우 기존 작업 리스트(체크박스)로 복원한다.
        """
        self._is_ev_complement_mode = is_enabled
        
        if not hasattr(self, 'groupBox_2'):
            return

        layout = self.groupBox_2.layout()
        if not layout:
            return

        # ev_memo용 QTextEdit가 없으면 생성하여 layout에 추가하고 숨겨둠.
        if not hasattr(self, '_ev_memo_text_edit'):
            self._ev_memo_text_edit = QTextEdit()
            self._ev_memo_text_edit.setReadOnly(True)
            self._ev_memo_text_edit.setVisible(False)
            layout.addWidget(self._ev_memo_text_edit)
            
        if is_enabled:
            # 기존 체크박스들 숨기기
            self._set_task_list_visible(False)
            # 텍스트 에디트 보이기 및 내용 설정
            # DB에서 가져온 '\n'을 실제 줄바꿈 문자인 '\n'으로 변환
            processed_memo = ev_memo.replace('\\n', '\n')
            self._ev_memo_text_edit.setText(processed_memo)
            self._ev_memo_text_edit.setVisible(True)
            self.groupBox_2.setTitle("보완 요청 사항") # 타이틀 변경
            
            # EV 보완 모드일 때는 체크박스가 새로 생성되지 않도록 해야 함
            # 이미 생성된 체크박스가 있다면 숨김 처리됨
        else:
            # 텍스트 에디트 숨기기
            self._ev_memo_text_edit.setVisible(False)
            self._ev_memo_text_edit.clear()
            # 기존 체크박스들 보이기
            self._set_task_list_visible(True)
            self.groupBox_2.setTitle("작업 리스트") # 타이틀 복원
            
            # 복원 시 현재 RN에 대한 작업 리스트 갱신 필요할 수 있음
            if self._current_rn:
                self.update_task_list(self._current_rn)

    def _set_task_list_visible(self, visible: bool):
        """작업 리스트 레이아웃 내의 위젯들의 가시성을 설정한다."""
        for checkbox in self._dynamic_checkboxes:
            checkbox.setVisible(visible)

    def set_worker_info(self, worker_id: int | None):
        """현재 로그인한 작업자 정보를 설정한다."""
        self._worker_id = worker_id

    def set_delivery_day_gap(self, day_gap: int | None):
        """출고예정일 계산을 위한 day_gap을 설정한다."""
        self._delivery_day_gap = day_gap

    def _adjust_to_weekday(self, target_date: date) -> date:
        """주말(토요일, 일요일) 또는 공휴일이면 다음 평일로 조정한다."""
        from core.sql_manager import fetch_holidays
        
        # 공휴일 조회 (캐싱을 위해 인스턴스 변수로 저장 가능하지만, 매번 조회로 단순화)
        holidays = fetch_holidays()
        
        # 최대 30일까지 체크 (무한 루프 방지)
        max_iterations = 30
        iteration = 0
        
        while iteration < max_iterations:
            weekday = target_date.weekday()  # 월요일=0, 일요일=6
            is_weekend = weekday >= 5  # 토요일(5) 또는 일요일(6)
            is_holiday = target_date in holidays
            
            # 주말이 아니고 공휴일도 아니면 평일이므로 반환
            if not is_weekend and not is_holiday:
                return target_date
            
            # 주말이거나 공휴일이면 다음 날로 이동
            target_date = target_date + timedelta(days=1)
            iteration += 1
        
        # 최대 반복 횟수에 도달한 경우 원래 날짜 반환 (에러 방지)
        return target_date

    def _on_radio_button_2_toggled(self, checked: bool):
        """출고예정일 라디오 버튼 상태 변경 시 호출"""
        if checked and self._delivery_day_gap is not None:
            if hasattr(self, 'text_edit'):
                # 오늘 날짜 + day_gap 계산
                today = date.today()
                target_date = today + timedelta(days=self._delivery_day_gap)
                
                # 주말이면 월요일로 조정
                target_date = self._adjust_to_weekday(target_date)
                
                # MM/DD 형식으로 변환
                formatted_date = target_date.strftime("%m/%d")
                
                # 텍스트 에디트에 설정
                self.text_edit.setText(formatted_date)

    def _on_radio_button_subsidy_toggled(self, checked: bool):
        """보조금 라디오 버튼 상태 변경 시 호출"""
        if checked:
            if hasattr(self, 'text_edit') and hasattr(self, 'lineEdit_rn_num'):
                from core.sql_manager import fetch_subsidy_region, fetch_subsidy_model, fetch_subsidy_amount
                
                rn = self.lineEdit_rn_num.text().strip()
                if not rn:
                    print("RN 정보가 없어 보조금을 조회할 수 없습니다.")
                    return
                
                # DB에서 지역과 모델 조회
                region = fetch_subsidy_region(rn)
                model = fetch_subsidy_model(rn)
                
                # 지역이 DB에 없으면 UI 값 사용
                if not region and hasattr(self, 'lineEdit_region'):
                    region = self.lineEdit_region.text().strip()
                
                if not region or not model:
                    print(f"지역({region}) 또는 모델({model}) 정보 부족으로 보조금 조회 불가")
                    return
                
                # 보조금 조회 (RN 전달하여 다자녀 추가 보조금 계산 포함)
                amount_str = fetch_subsidy_amount(region, model, rn)
                
                if amount_str:
                    self.text_edit.setText(amount_str)
                else:
                    print(f"보조금 정보 없음 (지역: {region}, 모델: {model})")
                    self.text_edit.setText("보조금 정보 없음")

    def clear_info(self):
        """정보 패널 초기화"""
        # 작업 리스트 체크박스 초기화
        self.reset_task_checkboxes()
        
        if hasattr(self, 'lineEdit_name'):
            self.lineEdit_name.clear()
        self.lineEdit_region.clear()
        self.lineEdit_special.clear()
        if hasattr(self, 'lineEdit_address'):
            self.lineEdit_address.clear()
        self._current_rn = "" # RN 초기화
        self._initial_error_items.clear() # 초기 항목 세트도 초기화
        if hasattr(self, 'lineEdit_rn_num'):
            self.lineEdit_rn_num.clear()  # RN 필드도 초기화
            
        # 메모 초기화
        if hasattr(self, 'listWidget_memos'):
            self.listWidget_memos.clear()
        if hasattr(self, 'textEdit_memo_input'):
            self.textEdit_memo_input.clear()

        # EV 보완 모드 초기화 (텍스트 에디트 숨김 등)
        self.set_ev_complement_mode(False)

    def update_file_info(self, file_path: str, file_size_mb: float, total_pages: int):
        """파일 관련 정보를 업데이트한다. (UI에서 파일 정보 그룹박스가 제거되어 비활성화됨)"""
        pass

    def update_total_pages(self, total_pages: int):
        """총 페이지 수 정보만 업데이트한다. (UI에서 파일 정보 그룹박스가 제거되어 비활성화됨)"""
        pass

    def update_page_info(self, page_num: int, width: float, height: float, rotation: int):
        """현재 페이지 관련 정보를 업데이트한다. (UI 요소가 제거되어 더 이상 사용되지 않음)"""
        pass

    def reset_task_checkboxes(self):
        """작업 리스트 체크박스들을 모두 해제 상태로 초기화하고 동적 체크박스를 제거한다."""
        # 동적 체크박스 제거
        for checkbox in self._dynamic_checkboxes:
            self.verticalLayout_task_list.removeWidget(checkbox)
            checkbox.deleteLater()
        self._dynamic_checkboxes = []

    def reset_text_radio_buttons(self):
        """텍스트 삽입 라디오 버튼을 '일반'으로 초기화한다."""
        if hasattr(self, 'radioButton_1'):
            self.radioButton_1.setChecked(True)

    def update_basic_info(self, name: str, region: str, special_note: str, rn: str = "", address: str = ""):
        """기본 정보를 업데이트한다."""
        self._current_rn = rn  # RN 저장
        
        if hasattr(self, 'lineEdit_name'):
            self.lineEdit_name.setText(name)
        self.lineEdit_region.setText(region)
        self.lineEdit_special.setText(special_note)
        if hasattr(self, 'lineEdit_address'):
            self.lineEdit_address.setText(address)
        if hasattr(self, 'lineEdit_rn_num'):
            self.lineEdit_rn_num.setText(rn)
            
        # RN이 있으면 작업 리스트 및 메모 업데이트
        if rn:
            self.update_task_list(rn, is_initial_load=True)
            self._refresh_memo_list()

    def update_task_list(self, rn: str, is_initial_load: bool = False):
        """RN 에러 데이터(validation_errors)를 기반으로 작업 리스트 체크박스를 동적으로 업데이트한다."""
        if not rn:
            return
            
        self._current_rn = rn  # RN 업데이트 보장

        # EV 보완 모드일 경우 작업 리스트(체크박스) 업데이트를 건너뜀
        if self._is_ev_complement_mode:
            # 단, 내부 데이터 처리를 위해 필요한 경우 로직 분리 가능
            # 현재는 UI 표시가 주 목적이므로 리턴
            return

        # 현재 체크된 상태 저장
        checked_states = {}
        for cb in self._dynamic_checkboxes:
            checked_states[cb.text()] = cb.isChecked()

        # 기존 작업 리스트 초기화
        self.reset_task_checkboxes()
        
        if not rn:
            return

        check_items = []
        
        try:
            from core.sql_manager import fetch_error_results
            # 해당 RN의 모든 에러 row를 가져옴
            error_rows = fetch_error_results(rn)
            
            for row in error_rows:
                # 1. null_fields 처리 (값이 존재하면 '파일 누락: 서류명' 추가)
                null_fields = row.get('null_fields')
                if null_fields:
                    doc_type = row.get('document_type', '알 수 없는 서류')
                    item_text = f"파일 누락: {doc_type}"
                    if item_text not in check_items:
                        check_items.append(item_text)

                # 2. validation_errors 처리 (딕셔너리 형태)
                validation_errors = row.get('validation_errors', {})
                if isinstance(validation_errors, dict):
                    for err_type, err_details in validation_errors.items():
                        # 값이 리스트든 문자열이든 상관없이 하나의 항목으로 표시
                        check_items.append(f"{err_type}: {err_details}")

        except Exception as e:
            print(f"작업 리스트 업데이트 중 오류 발생: {e}")
            return
        
        # 초기 로드인 경우 현재 아이템들을 '초기 아이템'으로 등록
        if is_initial_load:
            self._initial_error_items = set(check_items)

        if not check_items:
            return
        
        # 동적 체크박스 생성 및 추가
        for item in check_items:
            checkbox = QCheckBox(item)
            # 폰트 크기 조정 (기본보다 2pt 작게)
            font = checkbox.font()
            font.setPointSize(font.pointSize() - 2)
            checkbox.setFont(font)
            
            # 초기 리스트에 없던 새로운 항목이면 스타일 적용 (빨간색 굵게)
            if item not in self._initial_error_items:
                checkbox.setStyleSheet("QCheckBox { color: red; font-weight: bold; }")
            
            # 기존에 체크되어 있었다면 상태 복원
            if item in checked_states:
                checkbox.setChecked(checked_states[item])
            
            self.verticalLayout_task_list.addWidget(checkbox)
            self._dynamic_checkboxes.append(checkbox)

    def are_all_tasks_checked(self) -> bool:
        """모든 동적 체크박스가 체크되었는지 확인한다."""
        # EV 보완 모드일 경우 체크박스가 표시되지 않으므로 True 반환
        if self._is_ev_complement_mode:
            return True
            
        # 체크박스가 하나라도 체크되지 않았다면 False 반환
        for cb in self._dynamic_checkboxes:
            if cb.isVisible() and not cb.isChecked():
                return False
        return True

    def _validate_date_format(self, text: str) -> bool:
        """날짜 형식(MM/DD 또는 M/D)을 검증한다."""
        # MM/DD 또는 M/D 형식: 월(1-12), 일(1-31)
        pattern = r'^(0?[1-9]|1[0-2])/(0?[1-9]|[12][0-9]|3[01])$'
        return bool(re.match(pattern, text.strip()))

    def _on_insert_text_clicked(self):
        if hasattr(self, 'text_edit') and hasattr(self, 'font_spinBox'):
            text = self.text_edit.text()
            font_size = self.font_spinBox.value() # 스핀박스에서 폰트 크기 가져오기
            
            # 라디오 버튼 상태 확인
            if hasattr(self, 'radioButton_2') and self.radioButton_2.isChecked():
                # '출고예정일'이 선택된 경우 날짜 형식 검증
                if not text:
                    QMessageBox.warning(self, "입력 오류", "날짜를 입력해주세요.\n예: 11/27, 03/05, 3/5")
                    return
                
                if not self._validate_date_format(text):
                    QMessageBox.warning(
                        self, 
                        "입력 오류", 
                        "날짜 형식이 올바르지 않습니다.\n\n올바른 형식: MM/DD 또는 M/D\n예: 11/27, 03/05, 3/5, 11/04"
                    )
                    return
                
                # 지역 정보 가져오기
                region = ""
                if hasattr(self, 'lineEdit_region'):
                    region = self.lineEdit_region.text().strip()
                
                # 날짜 차이 계산
                try:
                    # 입력된 날짜 파싱 (MM/DD 또는 M/D 형식)
                    date_parts = text.strip().split('/')
                    month = int(date_parts[0])
                    day = int(date_parts[1])
                    
                    # 현재 날짜 (시간 제외, 날짜만)
                    today = date.today()
                    current_year = today.year
                    
                    # 입력된 날짜 객체 생성 (현재 연도 기준)
                    input_date = date(current_year, month, day)
                    
                    # 만약 입력된 날짜가 이미 지났다면 다음 해로 처리
                    if input_date < today:
                        input_date = date(current_year + 1, month, day)
                    
                    # 주말이면 월요일로 조정
                    input_date = self._adjust_to_weekday(input_date)
                    
                    # 날짜 차이 계산 (일 단위)
                    date_diff = (input_date - today).days
                    
                    # 조정된 날짜로 텍스트 업데이트 (주말이었던 경우)
                    adjusted_text = input_date.strftime("%m/%d")
                    if adjusted_text != text:
                        text = adjusted_text
                        self.text_edit.setText(text)
                    
                    # 디버그 메시지 출력
                    if region:
                        print(f"{region}의 출고예정일 {text} (D+{date_diff})")
                    else:
                        print(f"지역 추적 불가 - 출고예정일 {text} (D+{date_diff})")
                    
                    # 지역이 있고 'X'가 아니면 DB에 추가 시도
                    if region and region != 'X' and date_diff >= 0:
                        from core.sql_manager import insert_delivery_day_gap
                        success = insert_delivery_day_gap(region, date_diff)
                        if success:
                            print(f"출고예정일 테이블에 새 지역 추가: {region} (day_gap={date_diff})")
                        # 이미 존재하는 경우는 조용히 넘어감
                        
                except (ValueError, IndexError) as e:
                    # 날짜 파싱 실패 시 기존 메시지만 출력
                    if region:
                        print(f"{region}의 출고예정일 {text}")
                    else:
                        print("지역 추적 불가")
                    print(f"날짜 차이 계산 실패: {e}")
                
                # 날짜 형식이 올바르면 텍스트 앞에 '출고예정일' 추가
                text = f"출고예정일 {text}"
            
            if text:
                self.text_stamp_requested.emit(text, font_size) # 텍스트와 폰트 크기 함께 전달
                self.text_edit.clear() # 입력창 비우기
            else:
                # (선택사항) 사용자에게 텍스트를 입력하라는 메시지를 보여줄 수 있습니다.
                print("입력된 텍스트가 없습니다.")