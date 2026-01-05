import sys
import os

# 프로젝트 루트 디렉토리를 sys.path에 추가하여 core 패키지를 찾을 수 있게 함
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

import psycopg2
from contextlib import closing
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QApplication,
    QSplitter,
    QWidget,
)
from PyQt6.QtCore import Qt

from core.data_manage import DB_CONFIG

class NotificationInfoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("공고문 관리")
        self.resize(900, 600)
        self.setMinimumSize(900, 600)
        # 최대화 및 최소화 버튼 활성화
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        
        self.data = {}
        self._load_data_from_db()
        
        self._init_ui()
        self._setup_styles()
        self._load_regions()

    def _load_data_from_db(self):
        """실제 DB에서 공고문 데이터를 불러옵니다."""
        try:
            with closing(psycopg2.connect(**DB_CONFIG)) as conn:
                with conn.cursor() as cursor:
                    # file_paths가 NULL이 아니고 배열 길이가 0보다 큰 데이터 조회
                    query = """
                        SELECT region, file_paths 
                        FROM ev_info 
                        WHERE file_paths IS NOT NULL 
                          AND array_length(file_paths, 1) > 0
                        ORDER BY region ASC
                    """
                    cursor.execute(query)
                    rows = cursor.fetchall()
                    
                    self.data = {row[0]: row[1] for row in rows}
        except Exception as e:
            print(f"DB 데이터 로드 실패: {e}")
            self.data = {}

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # 상단 타이틀
        self.title_label = QLabel("지역별 공고문 목록")
        self.title_label.setObjectName("titleLabel")
        main_layout.addWidget(self.title_label, stretch=1)

        # 스플리터 생성
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainSplitter")
        
        # 왼쪽: 지역 리스트 영역
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        region_label = QLabel("지역 선택")
        region_label.setObjectName("subHeader")
        
        self.region_list = QListWidget()
        self.region_list.setObjectName("regionList")
        self.region_list.itemClicked.connect(self._on_region_selected)
        
        left_layout.addWidget(region_label)
        left_layout.addWidget(self.region_list)
        
        # 오른쪽: 파일 리스트 영역
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.region_name_label = QLabel("지역을 선택해주세요")
        self.region_name_label.setObjectName("regionHeader")
        
        self.file_list = QListWidget()
        self.file_list.setObjectName("fileList")
        self.file_list.itemDoubleClicked.connect(self._on_file_double_clicked)
        
        right_layout.addWidget(self.region_name_label)
        right_layout.addWidget(self.file_list)
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(splitter, stretch=9)

    def _setup_styles(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
            }
            #titleLabel {
                font-size: 22px;
                font-weight: bold;
                color: #1a1a1a;
                margin-bottom: 5px;
            }
            #subHeader, #regionHeader {
                font-size: 14px;
                font-weight: bold;
                color: #666666;
                padding-bottom: 5px;
            }
            #regionHeader {
                font-size: 16px;
                color: #0078d4;
                border-bottom: 1px solid #eeeeee;
                margin-bottom: 10px;
            }
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: #fcfcfc;
                outline: none;
            }
            QListWidget::item {
                padding: 10px 15px;
                border-bottom: 1px solid #f0f0f0;
                color: #333333;
            }
            QListWidget::item:hover {
                background-color: #f0f7ff;
            }
            QListWidget::item:selected {
                background-color: #e1f0fe;
                color: #0078d4;
                font-weight: bold;
                border-left: 3px solid #0078d4;
            }
            #fileList::item {
                padding: 12px 15px;
            }
            QSplitter::handle {
                background-color: #f0f0f0;
            }
        """)

    def _load_regions(self):
        # file_paths가 있고 그 길이가 0보다 큰 지역만 리스트에 추가합니다.
        regions = sorted(self.data.keys())
        for region in regions:
            files = self.data.get(region, [])
            if files:  # 파일 리스트가 비어있지 않은 경우에만 추가
                item = QListWidgetItem(region)
                self.region_list.addItem(item)
        
        # 만약 표시할 지역이 하나도 없다면 안내 메시지 표시 가능
        if self.region_list.count() == 0:
            item = QListWidgetItem("공고문이 있는 지역이 없습니다.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.region_list.addItem(item)

    def _on_region_selected(self, item):
        region = item.text()
        self.region_name_label.setText(f"{region} 관련 파일")
        self.file_list.clear()
        
        files = self.data.get(region, [])
        if not files:
            no_file_item = QListWidgetItem("등록된 파일이 없습니다.")
            no_file_item.setFlags(Qt.ItemFlag.NoItemFlags)
            no_file_item.setForeground(Qt.GlobalColor.gray)
            self.file_list.addItem(no_file_item)
        else:
            for file in files:
                # 파일 경로에서 파일명만 표시하거나 전체 경로를 표시할 수 있습니다.
                # 여기서는 구분을 위해 전체 경로를 넣되, 스타일로 조절 가능합니다.
                self.file_list.addItem(QListWidgetItem(file))

    def _on_file_double_clicked(self, item):
        file_path = item.text()
        if os.path.exists(file_path):
            os.startfile(file_path)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # 부드러운 외관을 위해 Fusion 스타일 적용
    dialog = NotificationInfoDialog()
    dialog.show()
    sys.exit(app.exec())