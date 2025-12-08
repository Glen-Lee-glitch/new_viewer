import pymupdf
import os
from pathlib import Path

# A4 크기 (포인트 단위)
A4_WIDTH = 595.276
A4_HEIGHT = 841.890

def adjust_pages_and_insert_text_safe(pdf_path: str, output_path: str, target_pages: list = None, text_content: str = "Inserted Text") -> str:
    """
    페이지를 올바르게 회전시키고, 잘림 방지를 위해 미세한 여백(Padding)을 적용하여 중앙에 배치합니다.
    """
    if not os.path.exists(pdf_path):
        print(f"[ERROR] 파일을 찾을 수 없습니다: {pdf_path}")
        return None
    
    try:
        source_doc = pymupdf.open(pdf_path)
        new_doc = pymupdf.open()
        
        # 처리할 페이지 목록 설정
        if target_pages:
            pages_to_process = [p - 1 for p in target_pages if 0 <= p - 1 < source_doc.page_count]
        else:
            pages_to_process = list(range(source_doc.page_count))
            
        font = pymupdf.Font("helv")
        
        for page_num_0based in range(source_doc.page_count):
            source_page = source_doc[page_num_0based]
            
            # 1. 처리 대상이 아니면 단순 복사
            if page_num_0based not in pages_to_process:
                new_doc.insert_pdf(source_doc, from_page=page_num_0based, to_page=page_num_0based)
                continue

            # 2. 회전 각도 계산 (270 -> 90도 회전 필요)
            rot = source_page.rotation
            if rot == 270:
                bake_rotation = 90
            elif rot == 90:
                bake_rotation = 270
            elif rot == 180:
                bake_rotation = 180
            else:
                bake_rotation = 0
            
            # 3. 새 A4 페이지 생성 (무조건 세로형)
            new_page = new_doc.new_page(width=A4_WIDTH, height=A4_HEIGHT)
            
            # 4. [핵심 수정] 안전 여백(Padding) 적용
            # 종이에 꽉 채우려다 잘리는 것을 막기 위해, 상하좌우 10포인트(약 3mm) 정도 여백을 줍니다.
            padding = 10 
            
            # 원본 크기 측정 (회전 고려)
            raw_rect = source_page.rect
            if rot in [90, 270]:
                visual_w = raw_rect.height
                visual_h = raw_rect.width
            else:
                visual_w = raw_rect.width
                visual_h = raw_rect.height
            
            # 안전 영역(Safe Zone) 계산: 전체 A4 크기에서 패딩을 뺀 영역
            safe_width = A4_WIDTH - (padding * 2)
            safe_height = A4_HEIGHT - (padding * 2)
            
            # 비율 유지하며 안전 영역에 맞추기 (Fit to Safe Zone)
            scale = min(safe_width / visual_w, safe_height / visual_h)
            
            # 최종 표시될 크기
            display_w = visual_w * scale
            display_h = visual_h * scale
            
            # 중앙 배치 좌표 계산
            x = (A4_WIDTH - display_w) / 2
            y = (A4_HEIGHT - display_h) / 2
            
            # 타겟 박스 생성
            target_rect = pymupdf.Rect(x, y, x + display_w, y + display_h)
            
            # 5. 내용 복사 (안전 박스 안에 집어넣음)
            new_page.show_pdf_page(target_rect, source_doc, page_num_0based, rotate=bake_rotation)
            
            print(f"[DEBUG] 페이지 {page_num_0based+1}: 회전 {rot}° -> 보정 {bake_rotation}° (안전 여백 적용)")

            # 6. 텍스트 삽입
            if text_content:
                font_size = 24
                text_width = font.text_length(text_content, fontsize=font_size)
                
                # 텍스트 좌표 계산 (페이지 정중앙)
                tx = (A4_WIDTH - text_width) / 2
                ty = (A4_HEIGHT / 2) + (font_size * 0.35)
                
                new_page.insert_text((tx, ty), text_content, fontsize=font_size, fontname="helv", color=(0,0,0), rotate=0)

        output_path = str(output_path)
        new_doc.save(output_path)
        new_doc.close()
        source_doc.close()
        print(f"[INFO] 저장 완료: {output_path}")
        return output_path

    except Exception as e:
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    test_dir = Path(__file__).parent.parent / "test"
    input_pdf = test_dir / "11.pdf"
    final_pdf = test_dir / "11_safe_fixed.pdf"
    
    if input_pdf.exists():
        print("작업 시작 (안전 여백 모드)...")
        adjust_pages_and_insert_text_safe(
            str(input_pdf), 
            str(final_pdf), 
            target_pages=[1], 
            text_content="it's test"
        )