# 지원금 신청서 처리 시스템 (Subsidy Application Processing System)

PyQt6 기반의 통합 지원금 신청서 처리 및 PDF 관리 시스템입니다. Gmail API를 통한 이메일 자동 수집, Gemini AI를 활용한 문서 분석, MySQL 데이터베이스 연동, 그리고 고성능 PDF 뷰어/편집기를 제공합니다.

## 📋 목차

- [주요 기능](#-주요-기능)
- [시스템 아키텍처](#-시스템-아키텍처)
- [프로젝트 구조](#-프로젝트-구조)
- [설치 및 실행](#-설치-및-실행)
- [의존성](#-의존성)
- [핵심 컴포넌트](#-핵심-컴포넌트)
- [사용법](#-사용법)
- [데이터베이스 구조](#-데이터베이스-구조)
- [API 통합](#-api-통합)
- [개발 가이드](#-개발-가이드)

## ✨ 주요 기능

### 📄 PDF 뷰어 및 편집
- **고화질 PDF 렌더링**: 200 DPI 고해상도 렌더링
- **A4 자동 변환**: 모든 PDF를 A4 규격으로 통일하여 일관된 뷰어 경험 제공
- **썸네일 네비게이션**: 좌측 패널에서 페이지 미리보기 및 빠른 이동
- **페이지 회전 및 줌**: 개별 페이지 회전, 확대/축소 및 팬(pan) 기능
- **도장 삽입**: '원본대조필' 등 사용자 정의 도장을 PDF에 삽입
- **텍스트 삽입**: 사용자 정의 텍스트를 PDF에 삽입
- **이미지 크롭**: 페이지의 특정 영역을 잘라내는 기능
- **페이지 삭제**: 불필요한 페이지 제거
- **페이지 순서 변경**: 드래그 앤 드롭으로 페이지 재배열
- **PDF 압축 저장**: 다단계 압축을 통한 파일 크기 최적화
- **Undo/Redo**: 작업 취소 및 재실행 기능

### 📧 이메일 통합
- **Gmail API 연동**: Gmail에서 지원금 신청서가 첨부된 이메일 자동 수집
- **자동 다운로드**: 이메일 첨부 파일 자동 다운로드 및 저장
- **이메일 내용 표시**: PDF 뷰어에서 원본 이메일 내용 오버레이 표시
- **이메일 답장 기능**: 처리 완료 후 이메일 답장 작성 및 전송
- **스레드 기반 처리**: 백그라운드에서 이메일 수집 및 처리

### 🤖 AI 문서 분석 (Gemini)
- **구매계약서 분석**: Gemini AI를 통한 구매계약서 자동 정보 추출
  - 계약일자, 고객명, 전화번호, 이메일, 차종 등
- **초본(주민등록등본) 분석**: 초본 문서에서 정보 자동 추출
  - 이름, 생년월일, 주소 등
- **청년생애 분석**: 청년생애 전환 지원금 관련 정보 추출
- **다자녀 분석**: 다자녀 지원금 관련 정보 추출
- **이상치 감지**: 추출된 정보의 이상치 자동 감지 및 표시
- **지역별 자동 처리**: 특정 지역(서울, 울산, 부산) 문서 자동 분석

### 💾 데이터베이스 연동
- **MySQL 통합**: 지원금 신청서 데이터를 MySQL 데이터베이스에 저장 및 관리
- **작업자 관리**: 작업자별 작업 배정 및 진행 상황 추적
- **상태 관리**: 신청서 처리 상태(pending, 처리중, 지원완료 등) 추적
- **작업 잠금**: 동시 작업 방지를 위한 작업 잠금 메커니즘
- **진행도 추적**: 작업자별 일일 처리 건수 및 통계

### 👥 작업자 관리
- **로그인 시스템**: 작업자 인증 및 권한 관리
- **관리자 기능**: 관리자(매니저, 팀장, 이사) 전용 기능
- **작업 배정**: 신청서를 작업자에게 자동/수동 배정
- **작업자 진행도**: 작업자별 일일 처리 현황 대시보드
- **알림 시스템**: 처리 완료 건 알림 및 통계

### 📋 작업 관리
- **할 일 목록**: PDF 작업과 관련된 체크리스트 관리
- **필수 서류 확인**: 구매계약서, 초본, 공동명의, 다자녀 등 필수 서류 확인
- **이상치 표시**: AI 분석 결과 이상치 자동 표시
- **기본 정보 표시**: 신청자 이름, 지역, 특이사항 등 정보 표시

### 🎨 사용자 인터페이스
- **다크 테마**: qt-material을 활용한 현대적인 UI
- **반응형 레이아웃**: 썸네일, 뷰어, 정보 패널 분할 레이아웃
- **플로팅 툴바**: 편집 기능에 빠르게 접근
- **단축키 지원**: 키보드 단축키로 빠른 작업
- **설정 다이얼로그**: 사용자 설정 관리

## 🏗️ 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                      사용자 인터페이스                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ PDF 뷰어 │  │ 썸네일   │  │ 정보패널 │  │ 할일목록 │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    비즈니스 로직 레이어                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │PDF 렌더링│  │PDF 편집  │  │PDF 저장  │  │SQL 관리  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  MySQL DB    │  │  Gmail API   │  │  Gemini AI   │
│              │  │              │  │              │
│ - 신청서 정보 │  │ - 이메일 수집 │  │ - 문서 분석  │
│ - 작업자 정보 │  │ - 첨부파일   │  │ - 정보 추출  │
│ - 처리 상태   │  │ - 답장 전송  │  │ - 이상치 감지│
└──────────────┘  └──────────────┘  └──────────────┘
```

## 🏗️ 프로젝트 구조

```
new_viewer/
├── core/                          # 핵심 비즈니스 로직
│   ├── pdf_render.py             # PDF 렌더링 엔진 (A4 변환, 고해상도 렌더링)
│   ├── pdf_saved.py              # PDF 압축 및 저장
│   ├── edit_mixin.py             # 편집 기능 믹스인 (도장, 텍스트, 크롭 등)
│   ├── insert_utils.py           # 이미지/페이지 삽입 유틸리티
│   ├── delete_utils.py           # 페이지 삭제 유틸리티
│   ├── sql_manager.py            # MySQL 데이터베이스 관리
│   ├── mail_utils.py             # 이메일 처리 유틸리티
│   ├── workers.py                # 백그라운드 작업자 (배치 테스트 등)
│   ├── utility.py                # 공통 유틸리티 함수
│   └── etc_tools.py              # 기타 도구 함수
│
├── widgets/                       # UI 컴포넌트
│   ├── main_window.py            # 메인 윈도우 (애플리케이션 진입점)
│   ├── pdf_view_widget.py        # PDF 뷰어 위젯
│   ├── thumbnail_view_widget.py  # 썸네일 뷰어
│   ├── pdf_load_widget.py        # PDF 로드 위젯 (신청서 목록)
│   ├── info_panel_widget.py      # 정보 패널 (기본 정보, 페이지 정보)
│   ├── floating_toolbar.py       # 플로팅 툴바
│   ├── stamp_overlay_widget.py   # 도장 오버레이
│   ├── mail_content_overlay.py   # 이메일 내용 오버레이
│   ├── zoomable_graphics_view.py # 줌 가능한 그래픽 뷰
│   ├── crop_dialog.py            # 크롭 다이얼로그
│   ├── todo_widget.py            # 할 일 목록 위젯
│   ├── login_dialog.py           # 로그인 다이얼로그
│   ├── mail_dialog.py            # 이메일 답장 다이얼로그
│   ├── settings_dialog.py        # 설정 다이얼로그
│   ├── config_dialog.py          # 구성 다이얼로그
│   ├── worker_progress_dialog.py # 작업자 진행도 다이얼로그
│   ├── alarm_widget.py           # 알림 위젯
│   ├── gemini_results_dialog.py  # Gemini AI 결과 다이얼로그
│   ├── necessary_widget.py       # 필수 서류 확인 위젯
│   ├── ev_helper_dialog.py       # EV 입력 도우미 다이얼로그
│   ├── page_delete_dialog.py     # 페이지 삭제 확인 다이얼로그
│   ├── unqualified_document_dialog.py  # 부적격 문서 다이얼로그
│   └── custom_item.py            # 커스텀 리스트 아이템
│
├── get_mail_logics/              # 이메일 수집 및 처리 로직
│   ├── thread.py                 # 이메일 수집 스레드 (Gmail API, Gemini AI)
│   ├── db_mail.py                # 이메일 데이터베이스 처리
│   ├── pdf_annotation_guard.py   # PDF 주석 손실 감지
│   └── token123.json             # Gmail API 토큰
│
├── ui/                           # Qt Designer UI 파일
│   ├── main_window.ui
│   ├── pdf_view_widget.ui
│   ├── thumbnail_viewer.ui
│   ├── pdf_load_area.ui
│   ├── info_panel.ui
│   ├── floating_toolbar.ui
│   ├── stamp_overlay.ui
│   ├── mail_content_overlay.ui
│   ├── to_do_widget.ui
│   ├── login_dialog.ui
│   ├── mail_dialog.ui
│   ├── settings.ui
│   ├── config_dialog.ui
│   ├── worker_progress.ui
│   ├── alarm_widget.ui
│   ├── gemini_results_dialog.ui
│   ├── necessary_widget.ui
│   ├── ev_helper_dialog.ui
│   ├── page_delete_dialog.ui
│   └── unqualified_document_dialog.ui
│
├── assets/                       # 리소스 파일
│   ├── 도장1.png                 # 도장 이미지
│   ├── 원본대조필.png            # 원본대조필 도장
│   └── 체크.png                  # 체크 아이콘
│
├── test/                         # 테스트 파일
│   ├── test.py                   # PDF 처리 테스트
│   ├── hard_test.py              # 하드웨어 테스트
│   ├── overlay_test.py           # 오버레이 테스트
│   ├── 800.pdf                   # 테스트 PDF
│   └── download.pdf              # 테스트 PDF
│
├── main.py                       # 애플리케이션 진입점
├── requirements.txt             # Python 의존성 목록
├── pyproject.toml                # 프로젝트 설정 (uv)
├── uv.lock                       # uv 잠금 파일
└── README.md                     # 프로젝트 문서
```

## 🚀 설치 및 실행

### 사전 요구사항

- Python 3.13 이상
- MySQL 데이터베이스 서버 (192.168.0.114:3306)
- Gmail API 인증 정보 (`credentials_3.json`)
- Gemini API 키

### 1. 저장소 클론

```bash
git clone <repository-url>
cd new_viewer
```

### 2. 의존성 설치

#### uv 사용 (권장)

```bash
# uv가 설치되어 있지 않은 경우
# Windows: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# Linux/Mac: curl -LsSf https://astral.sh/uv/install.sh | sh

uv sync
```

#### pip 사용

```bash
pip install -r requirements.txt
```

### 3. 환경 설정

#### MySQL 데이터베이스 설정

`core/sql_manager.py` 파일에서 데이터베이스 연결 정보를 수정하세요:

```python
DB_CONFIG = {
    'host': '192.168.0.114',
    'port': 3306,
    'user': 'my_pc_user',
    'password': 'your_password',
    'db': 'greetlounge',
    'charset': 'utf8mb4'
}
```

#### Gmail API 설정

1. Google Cloud Console에서 프로젝트 생성
2. Gmail API 활성화
3. OAuth 2.0 클라이언트 ID 생성
4. `credentials_3.json` 파일을 프로젝트 루트에 배치
5. 첫 실행 시 브라우저에서 인증하여 `token123.json` 생성

#### Gemini API 설정

`get_mail_logics/config.py` 파일에 API 키를 설정하세요:

```python
API_KEY = "your_gemini_api_key"
```

### 4. 애플리케이션 실행

```bash
python main.py
```

### 5. 이메일 수집 스레드 실행 (선택사항)

별도 터미널에서 이메일 수집 스레드를 실행할 수 있습니다:

```python
from get_mail_logics.thread import db_mail_thread
db_mail_thread()
```

## 📋 의존성

### 핵심 의존성

- **PyQt6** (>=6.6.0): GUI 프레임워크
- **PyMuPDF** (>=1.23.0): PDF 처리 및 렌더링
- **Pillow** (>=10.0.0): 이미지 처리
- **pynput** (>=1.8.1): 키보드/마우스 입력 처리

### 데이터 처리

- **pandas**: 데이터 분석 및 처리
- **openpyxl**: Excel 파일 처리

### 데이터베이스

- **mysql-connector-python**: MySQL 데이터베이스 연결
- **pymysql**: MySQL 데이터베이스 연결 (대체)

### Google API

- **google-api-python-client**: Google API 클라이언트
- **google-auth**: Google 인증
- **google-auth-oauthlib**: OAuth 2.0 라이브러리
- **google-auth-httplib2**: HTTP 라이브러리

### AI/ML

- **google-generativeai**: Gemini AI 클라이언트

### HTTP 요청

- **httpx**: 비동기 HTTP 클라이언트
- **requests**: HTTP 라이브러리

### 기타

- **qt-material**: PyQt6 다크 테마
- **pytz**: 시간대 처리
- **pathlib2**: 경로 처리
- **filelock**: 파일 잠금
- **reportlab**: PDF 생성
- **PyPDF2**: PDF 처리

## 🔧 핵심 컴포넌트

### PdfRender (core/pdf_render.py)

PDF 문서를 A4 규격으로 자동 변환하고 고해상도로 렌더링하는 엔진입니다.

**주요 기능:**
- PDF를 A4 규격으로 자동 변환
- 200 DPI 고해상도 렌더링
- 썸네일 생성
- 메모리 효율적인 처리
- 스레드 안전한 렌더링

**사용 예시:**
```python
from core.pdf_render import PdfRender

renderer = PdfRender()
renderer.load_pdf(['path/to/file.pdf'])
pixmap = renderer.render_page(0, zoom=2.0)
```

### MainWindow (widgets/main_window.py)

메인 애플리케이션 윈도우로, 모든 위젯과 기능을 통합 관리합니다.

**주요 기능:**
- 위젯 간 시그널-슬롯 연결
- 페이지 네비게이션 관리
- 작업자 인증 및 권한 관리
- 데이터베이스 연동
- 이메일 다이얼로그 관리
- 설정 관리

### PdfViewWidget (widgets/pdf_view_widget.py)

PDF 페이지를 렌더링하고 표시하는 핵심 위젯입니다.

**주요 기능:**
- PDF 페이지 렌더링 및 표시
- 줌/팬 기능
- 페이지 회전
- 백그라운드 렌더링
- 도장, 텍스트, 크롭 등 편집 기능 연동
- 이메일 내용 오버레이
- Undo/Redo 기능

### SqlManager (core/sql_manager.py)

MySQL 데이터베이스와의 모든 상호작용을 관리합니다.

**주요 기능:**
- 지원금 신청서 조회 및 업데이트
- 작업자 관리
- 작업 배정 및 잠금
- Gemini AI 결과 조회
- 이메일 답장 저장
- 통계 및 진행도 조회

**주요 함수:**
- `fetch_recent_subsidy_applications()`: 최근 신청서 조회
- `claim_subsidy_work()`: 작업 배정 및 잠금
- `update_subsidy_status()`: 상태 업데이트
- `insert_reply_email()`: 이메일 답장 저장
- `fetch_gemini_contract_results()`: Gemini 분석 결과 조회

### 이메일 수집 스레드 (get_mail_logics/thread.py)

Gmail API를 통해 이메일을 수집하고 처리하는 백그라운드 스레드입니다.

**주요 기능:**
- Gmail에서 새 이메일 자동 수집
- 첨부 파일 자동 다운로드
- PDF 전처리 (3MB 이상 파일)
- Gemini AI 큐에 추가 (특정 지역)
- 데이터베이스에 정보 저장

**처리 흐름:**
1. Gmail API로 새 이메일 확인
2. 첨부 파일 다운로드
3. PDF 전처리 (필요시)
4. Gemini AI 큐에 추가 (지역별)
5. 데이터베이스에 저장

### Gemini AI 워커 (get_mail_logics/thread.py)

PDF 문서를 분석하여 정보를 추출하는 AI 워커입니다.

**주요 기능:**
- 구매계약서 분석 (계약일자, 고객명, 전화번호, 이메일 등)
- 초본 분석 (이름, 생년월일, 주소 등)
- 청년생애 분석
- 다자녀 분석
- 결과를 데이터베이스에 저장

### StampOverlayWidget (widgets/stamp_overlay_widget.py)

PDF 위에 도장 이미지를 오버레이하는 위젯입니다.

**주요 기능:**
- 사용자가 도장 위치를 선택
- 도장 이미지 삽입
- 도장 크기 조절

### MailDialog (widgets/mail_dialog.py)

이메일 답장을 작성하고 전송하는 다이얼로그입니다.

**주요 기능:**
- 이메일 답장 작성
- 신청완료/서류미비 선택
- Gmail API를 통한 전송
- 데이터베이스에 저장

## 🎯 사용법

### 1. 로그인

애플리케이션 시작 시 로그인 다이얼로그가 표시됩니다. 등록된 작업자 이름을 입력하세요.

### 2. 신청서 목록 확인

메인 화면에서 최근 접수된 지원금 신청서 목록을 확인할 수 있습니다.

**표시 정보:**
- RN 번호
- 지역
- 작업자
- 이름
- 특이사항
- 이상치 표시 (O/X)
- 처리 결과

### 3. 신청서 열기

목록에서 신청서를 더블클릭하거나 컨텍스트 메뉴에서 "작업 시작"을 선택합니다.

**작업 배정:**
- 신청서가 자동으로 현재 작업자에게 배정됩니다
- 이미 다른 작업자가 작업 중이면 경고 메시지가 표시됩니다
- 관리자는 조회 모드로 열 수 있습니다

### 4. PDF 편집

**도장 삽입:**
1. 플로팅 툴바에서 도장 버튼 클릭
2. 도장 선택 (원본대조필 등)
3. PDF에서 원하는 위치 클릭

**텍스트 삽입:**
1. 정보 패널에서 텍스트 입력
2. 폰트 크기 설정
3. "텍스트 삽입" 버튼 클릭
4. PDF에서 원하는 위치 클릭

**페이지 회전:**
- 플로팅 툴바의 회전 버튼 사용
- 또는 단축키 사용

**페이지 삭제:**
- 컨텍스트 메뉴에서 "페이지 삭제" 선택
- 확인 다이얼로그에서 확인

**페이지 순서 변경:**
- 썸네일에서 드래그 앤 드롭으로 순서 변경

**크롭:**
1. 플로팅 툴바에서 크롭 버튼 클릭
2. 크롭할 영역 선택
3. 확인

### 5. 할 일 목록 확인

할 일 목록 위젯에서 필수 확인 사항을 체크할 수 있습니다:
- 지원신청서 서명
- 지원신청서 차종
- 지원신청서 보조금 금액
- (공동명의 시) 구매계약서 고객명 대표자명 일치
- (공동명의 시) 구매계약서 대표자/공동명의자 서명 전부 존재

### 6. Gemini AI 결과 확인

정보 패널에서 "Gemini 결과" 버튼을 클릭하여 AI 분석 결과를 확인할 수 있습니다:
- 구매계약서 정보 (계약일자, 고객명, 전화번호, 이메일)
- 초본 정보 (이름, 생년월일, 주소)
- 청년생애 정보
- 다자녀 정보

### 7. PDF 저장

플로팅 툴바의 저장 버튼을 클릭하여 편집된 PDF를 저장합니다.

**저장 과정:**
1. 다단계 압축 처리
2. 데이터베이스에 저장 경로 업데이트
3. 상태를 "지원완료"로 변경

### 8. 이메일 답장

저장 완료 후 이메일 답장 다이얼로그가 자동으로 열립니다.

**답장 작성:**
1. 메일 타입 선택 (신청완료/서류미비)
2. 신청번호 입력 (신청완료인 경우)
3. 내용 작성
4. 전송

### 9. 작업자 진행도 확인

메뉴에서 "작업자 진행도"를 선택하여 작업자별 일일 처리 현황을 확인할 수 있습니다.

### 10. 설정

메뉴에서 "설정"을 선택하여 다음을 설정할 수 있습니다:
- 단축키 설정
- 새로고침 간격
- 기타 애플리케이션 설정

## 💾 데이터베이스 구조

### 주요 테이블

#### subsidy_applications
지원금 신청서 정보를 저장하는 메인 테이블입니다.

**주요 컬럼:**
- `RN`: 신청서 번호 (Primary Key)
- `region`: 지역
- `worker`: 배정된 작업자
- `name`: 신청자 이름
- `special_note`: 특이사항
- `status`: 처리 상태 (pending, 처리중, 지원완료 등)
- `recent_thread_id`: 최근 이메일 스레드 ID
- `finished_file_path`: 처리 완료된 PDF 경로
- `status_updated_at`: 상태 업데이트 시간

#### emails
이메일 정보를 저장하는 테이블입니다.

**주요 컬럼:**
- `thread_id`: 이메일 스레드 ID (Primary Key)
- `received_date`: 수신 날짜
- `from_email_address`: 발신자 이메일
- `title`: 이메일 제목
- `content`: 이메일 내용
- `attached_file`: 첨부 파일 여부
- `attached_file_path`: 첨부 파일 경로
- `file_rendered`: 파일 렌더링 여부

#### reply_emails
이메일 답장 정보를 저장하는 테이블입니다.

**주요 컬럼:**
- `id`: 답장 ID (Primary Key, Auto Increment)
- `thread_id`: 원본 이메일 스레드 ID
- `RN`: 신청서 번호
- `worker`: 작업자
- `to_address`: 수신자 이메일
- `content`: 답장 내용
- `mail_type`: 메일 타입 (신청완료/서류미비)
- `app_num`: 신청번호
- `status`: 처리 상태 (pending, error, finished)
- `created_date`: 생성 날짜
- `replied_date`: 답장 전송 날짜
- `team`: 팀 정보

#### workers
작업자 정보를 저장하는 테이블입니다.

**주요 컬럼:**
- `name`: 작업자 이름 (Primary Key)
- `level`: 직급 (매니저, 팀장, 이사 등)
- `affiliation`: 소속

#### gemini_results
Gemini AI 분석 결과 플래그를 저장하는 테이블입니다.

**주요 컬럼:**
- `RN`: 신청서 번호 (Primary Key)
- `구매계약서`: 구매계약서 존재 여부
- `초본`: 초본 존재 여부
- `공동명의`: 공동명의 여부
- `다자녀`: 다자녀 여부
- `청년생애`: 청년생애 여부

#### test_ai_구매계약서
Gemini AI가 추출한 구매계약서 정보를 저장하는 테이블입니다.

**주요 컬럼:**
- `RN`: 신청서 번호 (Primary Key)
- `ai_계약일자`: 계약일자
- `ai_이름`: 고객명
- `전화번호`: 전화번호
- `이메일`: 이메일 주소

#### test_ai_초본
Gemini AI가 추출한 초본 정보를 저장하는 테이블입니다.

**주요 컬럼:**
- `RN`: 신청서 번호 (Primary Key)
- `name`: 이름
- `birth_date`: 생년월일
- `address_1`: 주소 1
- `address_2`: 주소 2
- `issue_date`: 발급일자

## 🔌 API 통합

### Gmail API

Gmail API를 사용하여 이메일을 수집하고 답장을 전송합니다.

**필요한 권한:**
- `https://www.googleapis.com/auth/gmail.modify`: 이메일 읽기/수정
- `https://www.googleapis.com/auth/spreadsheets`: 스프레드시트 접근 (선택사항)

**설정 방법:**
1. Google Cloud Console에서 프로젝트 생성
2. Gmail API 활성화
3. OAuth 2.0 클라이언트 ID 생성
4. `credentials_3.json` 파일 다운로드
5. 애플리케이션 실행 시 브라우저에서 인증
6. `token123.json` 자동 생성

**주요 기능:**
- 새 이메일 자동 수집 (20초마다)
- 첨부 파일 다운로드
- 이메일 답장 전송
- 라벨 관리

### Gemini AI API

Google Gemini AI를 사용하여 PDF 문서를 분석하고 정보를 추출합니다.

**사용 모델:**
- `gemini-2.5-flash`: 빠른 응답을 위한 경량 모델

**분석 대상:**
- 구매계약서: 계약일자, 고객명, 전화번호, 이메일, 차종 등
- 초본: 이름, 생년월일, 주소 등
- 청년생애: 지역명, 기간 등
- 다자녀: 자녀 생년월일 등

**처리 흐름:**
1. 이메일 첨부 파일 다운로드
2. 특정 지역(서울, 울산, 부산) 확인
3. Gemini 큐에 추가
4. 백그라운드에서 PDF 분석
5. 결과를 데이터베이스에 저장

## 🛠️ 개발 가이드

### 코드 스타일

- **PyQt6 규칙 준수**: `.cursor/rules/pyqt6-rule.mdc` 참고
- **MySQL 규칙 준수**: `.cursor/rules/mysql-rules.mdc` 참고
- **네이밍 컨벤션**: camelCase 사용
- **UI 컴포넌트**: `ui_` 접두사 사용
- **보호된 멤버**: 단일 언더스코어 (`_`) 사용

### 아키텍처 패턴

- **MVC 패턴**: Model-View-Controller 분리
- **시그널-슬롯**: Qt의 시그널-슬롯 메커니즘 활용
- **믹스인**: 공통 기능을 믹스인으로 분리 (`EditMixin`, `ViewModeMixin`)
- **워커 스레드**: 무거운 작업은 백그라운드 스레드에서 처리

### 주요 설계 원칙

1. **UI와 비즈니스 로직 분리**: `widgets/`와 `core/` 분리
2. **재사용 가능한 컴포넌트**: 각 위젯은 독립적으로 동작
3. **에러 처리**: 모든 데이터베이스 및 API 호출에 예외 처리
4. **스레드 안전성**: 백그라운드 작업은 스레드 안전하게 구현
5. **메모리 효율성**: 대용량 PDF 처리 시 메모리 관리

### 테스트

#### 단위 테스트

```bash
python -m pytest test/
```

#### 배치 테스트

애플리케이션 내에서 "일괄 테스트" 기능을 사용하여 여러 PDF 파일을 테스트할 수 있습니다.

### 디버깅

- **로그 출력**: `print()` 문을 사용한 디버깅
- **트레이스백**: `traceback.print_exc()` 사용
- **Qt Creator**: UI 파일 디버깅

### 성능 최적화

- **페이지 캐싱**: 렌더링된 페이지를 캐시하여 재사용
- **백그라운드 렌더링**: 페이지 렌더링을 백그라운드 스레드에서 처리
- **지연 로딩**: 필요한 시점에만 데이터 로드
- **PDF 압축**: 저장 시 다단계 압축으로 파일 크기 최적화

## 📝 라이선스

이 프로젝트는 개인/교육 목적으로 개발되었습니다.

## 🤝 기여

프로젝트 개선을 위한 제안이나 버그 리포트를 환영합니다.

## 📞 문의

프로젝트 관련 문의사항이 있으시면 이슈를 등록해주세요.
