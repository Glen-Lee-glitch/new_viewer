"""
유틸리티 함수 모음

이 모듈은 여러 모듈에서 공통으로 사용되는 유틸리티 함수들을 제공한다.
"""
import platform
from pathlib import Path
import sys
from core.data_manage import is_sample_data_mode  # 추가

def normalize_basic_info(metadata: dict | None) -> dict:
    """
    메타데이터 딕셔너리를 표준화된 형식으로 변환한다.
    
    Args:
        metadata: 변환할 메타데이터 딕셔너리 (None 가능)
        
    Returns:
        표준화된 딕셔너리 {'name': str, 'region': str, 'special_note': str, 'rn': str, 'is_context_menu_work': bool}
        
    Note:
        - None 값은 빈 문자열로 변환
        - 모든 값은 문자열로 변환 후 trim 처리
        - 누락된 키에 대해 기본값 제공
    """
    if not metadata:
        return {'name': "", 'region': "", 'special_note': "", 'rn': ""}

    def _coerce(value):
        if value is None:
            return ""
        return str(value).strip()

    return {
        'name': _coerce(metadata.get('name')),
        'region': _coerce(metadata.get('region')),
        'special_note': _coerce(metadata.get('special_note')),
        'rn': _coerce(metadata.get('rn')),  # RN 추가
        'is_context_menu_work': metadata.get('is_context_menu_work', False)  # 컨텍스트 메뉴 작업 여부
    }

def get_converted_path(path: str | Path) -> str:
    """
    OS 환경에 따라 파일 경로를 변환한다.
    
    Args:
        path: 원본 파일 경로
        
    Returns:
        변환된 파일 경로 문자열
    """
    if not path:
        return ""
        
    path_str = str(path).strip()
    
    # 따옴표 제거
    if (path_str.startswith('"') and path_str.endswith('"')) or \
       (path_str.startswith("'") and path_str.endswith("'")):
        if len(path_str) >= 2:
            path_str = path_str[1:-1]
    
    path_str = path_str.strip()

    # --- 샘플 데이터 모드 경로 처리 ---
    if is_sample_data_mode():
        # 경로 정규화 (슬래시/백슬래시 통일)
        norm_path = path_str.replace('\\', '/')
        if norm_path.startswith('sample/') or 'sample/' in norm_path:
            # 파일명만 추출하거나 sample/ 이후의 경로를 사용
            if 'sample/' in norm_path:
                rel_path = norm_path[norm_path.index('sample/'):]
            else:
                rel_path = norm_path
            
            # 실행 환경에 따른 베이스 경로 설정
            if hasattr(sys, '_MEIPASS'):
                base_path = Path(sys._MEIPASS)
            else:
                base_path = Path(__file__).parent.parent
            
            # 절대 경로 반환
            return str(base_path / rel_path)
    # ----------------------------------

    system = platform.system()
    
    if system == 'Darwin':  # macOS
        # 1. Windows 경로 구분자(\)를 Mac용(/)으로 변경
        path_str = path_str.replace('\\', '/')
        
        # 2. UNC 경로 (//Server/Share) 처리
        if path_str.startswith('//'):
            # //Server/Share/... -> /Volumes/Share/...
            parts = path_str.split('/')
            # ['', '', 'Server', 'Share', ...]
            if len(parts) >= 4:
                path_str = '/Volumes/' + '/'.join(parts[3:])
                
        # 3. 드라이브 문자 처리 (C:/Users -> /Volumes/Users)
        elif path_str.upper().startswith('C:'):
            # C:/Users -> /Volumes/Users 로 변환 (일반적인 패턴)
            if '/Users' in path_str:
                idx = path_str.index('/Users')
                path_str = '/Volumes' + path_str[idx:]
            else:
                # 그 외 C: 경로는 단순히 C:를 제거하고 /Volumes를 붙임 (위험할 수 있음)
                path_str = path_str.replace('C:', '/Volumes')
                
    else:  # Windows
        # 기존 로직: C: 로 시작하면 네트워크 경로로 변환
        if path_str.upper().startswith('C:'):
             path_str = r'\\DESKTOP-KMJ' + path_str[2:]
             
    return path_str
