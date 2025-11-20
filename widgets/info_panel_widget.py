import re
from datetime import datetime, date
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

        if hasattr(self, 'pushButton_insert_text'):
            self.pushButton_insert_text.clicked.connect(self._on_insert_text_clicked)

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
                    
                    # 날짜 차이 계산 (일 단위)
                    date_diff = (input_date - today).days
                    
                    # 디버그 메시지 출력
                    if region:
                        print(f"{region}의 출고예정일 {text} (D+{date_diff})")
                    else:
                        print(f"지역 추적 불가 - 출고예정일 {text} (D+{date_diff})")
                        
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
