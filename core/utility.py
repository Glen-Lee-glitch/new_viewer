"""
유틸리티 함수 모음

이 모듈은 여러 모듈에서 공통으로 사용되는 유틸리티 함수들을 제공한다.
"""


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
