import re
from datetime import datetime, date, timedelta
from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import QWidget, QMessageBox
from PyQt6.QtCore import pyqtSignal

class InfoPanelWidget(QWidget):
    """PDF 파일 및 페이지 정보를 표시하는 위젯"""
    text_stamp_requested = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "info_panel.ui"
        uic.loadUi(str(ui_path), self)
        
        self._delivery_day_gap: int | None = None # day_gap 저장 변수

        if hasattr(self, 'pushButton_insert_text'):
            self.pushButton_insert_text.clicked.connect(self._on_insert_text_clicked)
        
        # 라디오 버튼 시그널 연결
        if hasattr(self, 'radioButton_2'):
            self.radioButton_2.toggled.connect(self._on_radio_button_2_toggled)
            
        if hasattr(self, 'radioButton_3'):
            self.radioButton_3.toggled.connect(self._on_radio_button_subsidy_toggled)

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
                
                # 보조금 조회
                amount_str = fetch_subsidy_amount(region, model)
                
                if amount_str:
                    self.text_edit.setText(amount_str)
                else:
                    print(f"보조금 정보 없음 (지역: {region}, 모델: {model})")
                    self.text_edit.setText("보조금 정보 없음")

    def clear_info(self):
        """모든 정보 라벨을 'N/A'로 초기화한다."""
        self.label_current_page.setText("N/A")
        self.label_page_dims.setText("N/A")
        self.label_page_rotation.setText("N/A")
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
        """현재 페이지 관련 정보를 업데이트한다."""
        self.label_current_page.setText(str(page_num + 1))  # 0-based to 1-based
        self.label_page_dims.setText(f"{width:.2f} x {height:.2f} (pt)")
        self.label_page_rotation.setText(f"{rotation}°")

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
