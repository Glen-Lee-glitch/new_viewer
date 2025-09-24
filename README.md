# PDF Viewer 프로젝트 리팩토링 계획: 컴포넌트 단위 파일 분리

## 1. 목표
현재 `core/widgets.py` 파일에 모든 UI 관련 클래스가 집중되어 있어 가독성과 유지보수성이 저하되고 있습니다.
'컴포넌트(위젯) 단위'로 파일을 분리하여 코드 구조를 개선하고, 각 위젯의 독립성을 높여 향후 기능 확장 및 수정이 용이하도록 만듭니다.

## 2. 변경 전후 구조 비교

### 변경 전 (Before)
```
new_viewer/
├── core/
│   ├── widgets.py  # <-- MainWindow, PdfViewWidget 등 모든 위젯 클래스 포함
│   └── pdf_render.py
├── ui/
│   └── ...
└── main.py
```

### 변경 후 (After)
```
new_viewer/
├── core/
│   └── pdf_render.py          # PDF 렌더링 등 핵심 로직
├── widgets/                   # <-- 신규: UI 컴포넌트(위젯) 패키지
│   ├── __init__.py
│   ├── main_window.py         # MainWindow, create_app()
│   ├── pdf_view_widget.py
│   ├── thumbnail_view_widget.py
│   ├── floating_toolbar.py
│   ├── pdf_load_widget.py
│   ├── stamp_overlay_widget.py
│   └── zoomable_graphics_view.py
├── ui/
│   └── ...
└── main.py
```

## 3. 주요 변경 사항
1.  **`widgets` 패키지 생성**: UI 컴포넌트를 관리할 `widgets/` 디렉토리를 생성합니다.
2.  **`core/widgets.py` 파일 분리**:
    -   `core/widgets.py` 내부의 각 Qt 위젯 클래스(`MainWindow`, `PdfViewWidget` 등)를 `widgets/` 디렉토리 아래의 개별 Python 파일로 분리합니다.
    -   `create_app` 함수는 `MainWindow`와 함께 `widgets/main_window.py`로 이동합니다.
3.  **`core/widgets.py` 파일 삭제**: 모든 클래스가 이전된 후, 기존 `core/widgets.py` 파일은 삭제합니다.
4.  **Import 구문 수정**:
    -   분리된 파일 간의 의존성(예: `PdfViewWidget`가 `FloatingToolbarWidget`를 사용하는 경우)을 해결하기 위해 `import` 경로를 수정합니다.
    -   `main.py`에서 `create_app`을 임포트하는 경로를 `from widgets.main_window import create_app`으로 변경합니다.
5.  **`widgets/__init__.py` 설정**: 각 위젯 클래스를 `widgets` 패키지 레벨에서 쉽게 임포트할 수 있도록 설정하여 사용 편의성을 높입니다.

이 작업을 통해 각 UI 컴포넌트의 코드가 명확하게 분리되어, 특정 기능을 찾거나 수정할 때 훨씬 수월해질 것으로 기대됩니다.
