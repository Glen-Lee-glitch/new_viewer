import re
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import QWidget, QMessageBox, QCheckBox, QTextEdit, QVBoxLayout
from PyQt6.QtCore import pyqtSignal

class InfoPanelWidget(QWidget):
    """PDF 파일 및 페이지 정보를 표시하는 위젯"""
    text_stamp_requested = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "info_panel.ui"
        uic.loadUi(str(ui_path), self)
        
        self._delivery_day_gap: int | None = None # day_gap 저장 변수
        self._dynamic_checkboxes = [] # 동적으로 생성된 체크박스 리스트

        if hasattr(self, 'pushButton_insert_text'):
            self.pushButton_insert_text.clicked.connect(self._on_insert_text_clicked)
        
        # 라디오 버튼 시그널 연결
        if hasattr(self, 'radioButton_2'):
            self.radioButton_2.toggled.connect(self._on_radio_button_2_toggled)
            
        if hasattr(self, 'radioButton_3'):
            self.radioButton_3.toggled.connect(self._on_radio_button_subsidy_toggled)

    def set_ev_complement_mode(self, is_enabled: bool, ev_memo: str = ""):
        """
        ev_complement 모드 설정.
        True일 경우 작업 리스트를 ev_memo를 보여주는 텍스트 영역으로 교체한다.
        False일 경우 기존 작업 리스트(체크박스)로 복원한다.
        """
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
            # DB에서 가져온 '\\n'을 실제 줄바꿈 문자인 '\n'으로 변환
            processed_memo = ev_memo.replace('\\n', '\n')
            self._ev_memo_text_edit.setText(processed_memo)
            self._ev_memo_text_edit.setVisible(True)
            self.groupBox_2.setTitle("보완 요청 사항") # 타이틀 변경
        else:
            # 텍스트 에디트 숨기기
            self._ev_memo_text_edit.setVisible(False)
            self._ev_memo_text_edit.clear()
            # 기존 체크박스들 보이기
            self._set_task_list_visible(True)
            self.groupBox_2.setTitle("작업 리스트") # 타이틀 복원

    def _set_task_list_visible(self, visible: bool):
        """작업 리스트 레이아웃 내의 위젯들의 가시성을 설정한다."""
        if hasattr(self, 'checkBox_task_1'): self.checkBox_task_1.setVisible(visible)
        if hasattr(self, 'checkBox_task_2'): self.checkBox_task_2.setVisible(visible)
        if hasattr(self, 'checkBox_task_3'): self.checkBox_task_3.setVisible(visible)
        
        for checkbox in self._dynamic_checkboxes:
            checkbox.setVisible(visible)

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
        
        self.lineEdit_name.clear()
        self.lineEdit_region.clear()
        self.lineEdit_special.clear()
        if hasattr(self, 'lineEdit_rn_num'):
            self.lineEdit_rn_num.clear()  # RN 필드도 초기화

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
        # 정적 체크박스 해제 및 보이기 (기본 상태)
        if hasattr(self, 'checkBox_task_1'):
            self.checkBox_task_1.setChecked(False)
            self.checkBox_task_1.setVisible(True)
        if hasattr(self, 'checkBox_task_2'):
            self.checkBox_task_2.setChecked(False)
            self.checkBox_task_2.setVisible(True)
        if hasattr(self, 'checkBox_task_3'):
            self.checkBox_task_3.setChecked(False)
            self.checkBox_task_3.setVisible(True)
        
        # 동적 체크박스 제거
        for checkbox in self._dynamic_checkboxes:
            self.verticalLayout_task_list.removeWidget(checkbox)
            checkbox.deleteLater()
        self._dynamic_checkboxes = []

    def reset_text_radio_buttons(self):
        """텍스트 삽입 라디오 버튼을 '일반'으로 초기화한다."""
        if hasattr(self, 'radioButton_1'):
            self.radioButton_1.setChecked(True)

    def update_basic_info(self, name: str, region: str, special_note: str, rn: str = ""):
        """기본 정보를 업데이트한다."""
        self.lineEdit_name.setText(name)
        self.lineEdit_region.setText(region)
        self.lineEdit_special.setText(special_note)
        if hasattr(self, 'lineEdit_rn_num'):
            self.lineEdit_rn_num.setText(rn)
        
        # RN 에러 데이터에 따라 작업 리스트 업데이트
        self.update_task_list(rn)

    def update_task_list(self, rn: str):
        """RN 에러 데이터(validation_errors)를 기반으로 작업 리스트 체크박스를 동적으로 업데이트한다."""
        # 기존 작업 리스트 초기화 (정적 체크박스는 보이기 상태로 복귀됨)
        self.reset_task_checkboxes()
        
        if not rn:
            return

        check_items = []
        
        try:
            from core.sql_manager import fetch_error_results
            # 해당 RN의 모든 에러 row를 가져옴
            error_rows = fetch_error_results(rn)
            
            for row in error_rows:
                # null_fields는 무시하고 validation_errors만 처리
                validation_errors = row.get('validation_errors', {})
                
                if isinstance(validation_errors, dict):
                    for err_type, err_details in validation_errors.items():
                        # 값이 리스트든 문자열이든 상관없이 하나의 항목으로 표시
                        check_items.append(f"{err_type}: {err_details}")

        except Exception as e:
            print(f"작업 리스트 업데이트 중 오류 발생: {e}")
            return
        
        if not check_items:
            return

        # 체크리스트 항목이 있으면 정적 체크박스 숨기기
        if hasattr(self, 'checkBox_task_1'): self.checkBox_task_1.setVisible(False)
        if hasattr(self, 'checkBox_task_2'): self.checkBox_task_2.setVisible(False)
        if hasattr(self, 'checkBox_task_3'): self.checkBox_task_3.setVisible(False)
        
        # 동적 체크박스 생성 및 추가
        for item in check_items:
            checkbox = QCheckBox(item)
            # 폰트 크기 조정 (기본보다 2pt 작게)
            font = checkbox.font()
            font.setPointSize(font.pointSize() - 2)
            checkbox.setFont(font)
            
            self.verticalLayout_task_list.addWidget(checkbox)
            self._dynamic_checkboxes.append(checkbox)

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
