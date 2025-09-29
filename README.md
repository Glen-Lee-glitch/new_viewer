# PDF Viewer

PyQt6 기반의 고성능 PDF 뷰어 애플리케이션입니다. PDF 문서를 A4 규격으로 자동 변환하여 일관된 뷰어 경험을 제공하며, 페이지 회전, 줌, 도장 삽입, 크롭 등 다양한 편집 기능을 지원합니다.

## ✨ 주요 기능

- **PDF 뷰어**: 고화질 PDF 렌더링 및 페이지 네비게이션
- **A4 자동 변환**: 모든 PDF를 A4 규격으로 통일하여 일관된 뷰어 경험 제공
- **썸네일 네비게이션**: 좌측 패널에서 페이지 미리보기 및 빠른 이동
- **페이지 회전 및 줌**: 개별 페이지 회전, 확대/축소 및 팬(pan) 기능
- **도장 삽입**: '원본대조필'과 같은 사용자 정의 도장을 PDF에 삽입
- **이미지 크롭**: 페이지의 특정 영역을 잘라내는 기능
- **할 일 목록**: PDF 작업과 관련된 할 일 목록 관리
- **PDF 압축 저장**: 다단계 압축을 통한 파일 크기 최적화
- **일괄 테스트**: 여러 PDF 파일의 열기/저장 테스트 기능
- **다크 테마**: qt-material을 활용한 현대적인 UI

## 🏗️ 프로젝트 구조

```
new_viewer/
├── core/                      # 핵심 비즈니스 로직
│   ├── pdf_render.py         # PDF 렌더링 엔진
│   ├── pdf_saved.py          # PDF 압축 및 저장
│   ├── edit_mixin.py         # 편집 기능 믹스인
│   └── insert_utils.py       # 이미지/페이지 삽입 유틸리티
├── widgets/                   # UI 컴포넌트
│   ├── main_window.py        # 메인 윈도우
│   ├── pdf_view_widget.py    # PDF 뷰어 위젯
│   ├── thumbnail_view_widget.py  # 썸네일 뷰어
│   ├── floating_toolbar.py   # 플로팅 툴바
│   ├── pdf_load_widget.py    # PDF 로드 위젯
│   ├── stamp_overlay_widget.py   # 도장 오버레이
│   ├── info_panel_widget.py  # 정보 패널
│   ├── zoomable_graphics_view.py  # 줌 가능한 그래픽 뷰
│   ├── crop_dialog.py        # 크롭 다이얼로그
│   └── todo_widget.py        # 할 일 목록 위젯
├── ui/                        # Qt Designer UI 파일
│   ├── crop_dialog.ui
│   ├── floating_toolbar.ui
│   ├── info_panel.ui
│   ├── pdf_load_area.ui
│   ├── pdf_view_widget.ui
│   ├── stamp_overlay.ui
│   ├── thumbnail_viewer.ui
│   └── to_do_widget.ui
├── assets/                    # 리소스 파일
│   ├── 도장1.png
│   └── 원본대조필.png
├── test/                      # 테스트 파일
│   ├── test.py
│   ├── hard_test.py
│   ├── 800.pdf
│   └── download.pdf
├── main.py                    # 애플리케이션 진입점
├── requirements.txt           # 의존성 목록
├── pyproject.toml             # 프로젝트 설정
└── README.md
```

## 🚀 설치 및 실행

### 1. 의존성 설치

```bash
# uv 사용 (권장)
uv sync

# 또는 pip 사용
pip install -r requirements.txt
```

### 2. 애플리케이션 실행

```bash
python main.py
```

## 📋 주요 의존성

- **PyQt6**: GUI 프레임워크
- **PyMuPDF**: PDF 처리 및 렌더링
- **Pillow**: 이미지 처리
- **qt-material**: 다크 테마 지원

## 🔧 핵심 컴포넌트

### PdfRender (core/pdf_render.py)
- PDF 문서를 A4 규격으로 자동 변환
- 고화질 렌더링 (200 DPI)
- 썸네일 생성
- 메모리 효율적인 처리

### MainWindow (widgets/main_window.py)
- 메인 애플리케이션 윈도우
- 위젯 간 시그널-슬롯 연결
- 페이지 네비게이션 관리
- 일괄 테스트 기능

### PdfViewWidget (widgets/pdf_view_widget.py)
- PDF 페이지 렌더링 및 표시
- 줌/팬 기능
- 페이지 회전
- 백그라운드 렌더링
- 도장, 크롭 등 편집 기능 연동

### StampOverlayWidget (widgets/stamp_overlay_widget.py)
- PDF 위에 도장 이미지를 오버레이
- 사용자가 도장 위치를 선택하고 삽입하도록 지원

### CropDialog (widgets/crop_dialog.py)
- 사용자가 페이지의 특정 영역을 선택하여 잘라낼 수 있는 다이얼로그 제공

## 🎯 사용법

1. **PDF 열기**: 파일 드래그 앤 드롭 또는 파일 선택
2. **페이지 이동**: 썸네일 클릭 또는 네비게이션 버튼 사용
3. **줌 조절**: 마우스 휠 또는 툴바 버튼
4. **페이지 회전**: 툴바의 회전 버튼 사용
5. **편집**: 툴바의 도장, 크롭 버튼으로 편집 기능 사용
6. **PDF 저장**: 툴바의 저장 버튼으로 압축된 PDF 저장

## 🧪 테스트

일괄 테스트 기능을 통해 여러 PDF 파일의 열기/저장을 자동화할 수 있습니다:

1. 테스트 버튼 클릭
2. 지정된 폴더의 모든 PDF 파일이 자동으로 처리됨
3. 결과는 별도 폴더에 저장됨

## 🔄 개발 상태

이 프로젝트는 리팩토링을 통해 컴포넌트 단위로 파일이 분리되어 있습니다. 각 위젯은 독립적으로 관리되며, 향후 기능 확장 및 유지보수가 용이한 구조로 설계되었습니다.

## 📝 라이선스

이 프로젝트는 개인/교육 목적으로 개발되었습니다.
