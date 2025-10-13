from PyQt6.QtWidgets import QApplication


def copy_to_clipboard(apply_number: str, priority_text: str = "") -> str:
    """
    신청번호와 우선순위를 클립보드에 복사한다.
    
    Args:
        apply_number: 신청번호
        priority_text: 우선순위 텍스트 (선택사항)
    
    Returns:
        클립보드에 복사된 텍스트
    """
    # 우선순위가 있으면 신청번호 뒤에 추가
    if priority_text:
        clipboard_text = f"#{apply_number} {priority_text}"
    else:
        clipboard_text = f"#{apply_number}"
    
    # 클립보드에 복사
    clipboard = QApplication.clipboard()
    clipboard.setText(clipboard_text)
    
    return clipboard_text
