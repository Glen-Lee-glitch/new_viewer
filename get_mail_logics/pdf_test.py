import pymupdf
from pathlib import Path

def extract_as_is():
    base_dir = Path(__file__).parent.parent
    test_dir = base_dir / "test"
    
    input_pdf = test_dir / "11.pdf"
    output_pdf = test_dir / "11_results.pdf"

    print(f"Input: {input_pdf}")

    if not input_pdf.exists():
        print(f"오류: 파일을 찾을 수 없습니다 -> {input_pdf}")
        return

    try:
        doc = pymupdf.open(input_pdf)
        
        text_content = "출고예정일 12/09"
        font_size = 20

        for i, page in enumerate(doc):
            # 1. 원본 회전값 저장 및 확인
            original_rot = page.rotation
            print(f"[DEBUG] Page {i+1} Original Rotation: {original_rot}")

            # 2. 좌표 계산을 위해 잠시 페이지 회전을 0으로 초기화
            page.set_rotation(0)

            font = pymupdf.Font("helv")
            text_width = font.text_length(text_content, fontsize=font_size)
            
            # 페이지 중앙 좌표 계산 (회전이 0인 상태이므로 단순 계산 가능)
            rect = page.rect
            x = (rect.width - text_width) / 2
            y = (rect.height / 2) + (font_size * 0.35)
            
            # 회전값에 따른 좌표 조정
            if original_rot == 270:
                x = x - 60  # 270도 회전 페이지: x 좌표 -60 (시각적으로 왼쪽으로 이동)
            elif original_rot == 0:
                y = y + 60  # 0도 회전 페이지: y 좌표 +60 (시각적으로 아래로 이동)

            # 3. 텍스트 삽입
            # 이전 시도: rotate=-original_rot (실패: 글자가 거꾸로/누워 보임)
            # 이번 시도: rotate=original_rot
            page.insert_text(
                (x, y), 
                text_content, 
                fontsize=font_size, 
                fontname="helv", 
                color=(0, 0, 0),
                rotate=original_rot  # 부호 변경 (양수 값 사용)
            )

            # 4. 페이지 회전값 원상복구
            page.set_rotation(original_rot)

        doc.save(output_pdf)
        doc.close()
        
        print(f"완료: {output_pdf} 에 저장되었습니다.")
        
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    extract_as_is()
