"""페이지 삭제 관련 유틸리티 함수들"""

from typing import Optional, Dict, Any, Union
from PyQt6.QtWidgets import QWidget


def prompt_page_delete(parent: QWidget, page_number: Union[int, list[int]]) -> Optional[Dict[str, Any]]:
    """
    페이지 삭제 확인 다이얼로그를 띄우고 사용자 선택을 반환한다.
    
    Args:
        parent: 부모 위젯
        page_number: 삭제할 페이지 번호 (1부터 시작하는 시각적 번호) 또는 페이지 번호 리스트
    
    Returns:
        삭제를 확인한 경우: {"confirmed": True, "reason": str, "custom_text": str}
        취소한 경우: None
    """
    from widgets.page_delete_dialog import PageDeleteDialog
    
    dialog = PageDeleteDialog(page_number, parent)
    if dialog.exec() == PageDeleteDialog.DialogCode.Accepted:
        delete_info = dialog.get_delete_info()
        return {
            "confirmed": True,
            "reason": delete_info["reason"],
            "custom_text": delete_info["custom_text"]
        }
    
    return None
