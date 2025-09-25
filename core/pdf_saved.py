# pdf_utils.py
import pymupdf
from PIL import Image
import io
import gc
import os

def _is_a4_size(width_cm: float, height_cm: float, tolerance: float = 2.0) -> bool:
    """페이지가 A4 크기 범위 내인지 확인한다."""
    a4_width, a4_height = 21.0, 29.7
    vertical_match = (abs(width_cm - a4_width) <= tolerance and 
                     abs(height_cm - a4_height) <= tolerance)
    horizontal_match = (abs(width_cm - a4_height) <= tolerance and
                       abs(height_cm - a4_width) <= tolerance)
    return vertical_match or horizontal_match

def compress_pdf_file(
        input_path: str,
        output_path: str,
        jpeg_quality: int = 65,
        dpi: int = 120,
        size_threshold_kb: int = 300  # 페이지 당 300 KB 이상만 재압축
):
    """
    이미지·스캔으로 추정되는 '무거운' 페이지만 재렌더링-압축하고,
    나머지 페이지는 그대로 복사한다.
    return: 새 PDF 용량(MB) ― 실패 시 None
    """
    if not os.path.exists(input_path):
        return None

    src = pymupdf.open(input_path)
    dst = pymupdf.open()                     # 결과 PDF
    try:
        # A4 페이지의 인치 크기 (세로 기준)
        a4_inch_height = 11.69
        
        for i, page in enumerate(src):
            # --- 개선된 용량 추정 --------------------------
            # 페이지와 관련된 모든 객체의 크기를 측정
            try:
                # 1. content stream 크기
                content_size = 0
                for xref in page.get_contents():
                    try:
                        content_size += len(src.xref_stream(xref))
                    except:
                        pass
                
                # 2. 페이지의 이미지 크기 추정
                image_size = 0
                image_list = page.get_images()
                for img_index, img in enumerate(image_list):
                    try:
                        xref = img[0]
                        img_data = src.xref_stream(xref)
                        image_size += len(img_data)
                    except:
                        pass
                
                # 3. 총 크기 계산 (content + 이미지만 측정, 폰트는 제외)
                total_size = content_size + image_size
                
            except Exception:
                total_size = 0

            # threshold 를 넘지 않으면 '가벼운 텍스트 PDF' 로 간주 → 그대로 복사
            if total_size / 1024 < size_threshold_kb:
                dst.insert_pdf(src, from_page=i, to_page=i)
                continue
            
            # -------------------------------------------

            # ── 여기부터 '무거운' 페이지만 이미지-재렌더링 ──
            try:
                # 1. 페이지의 시각적 크기 계산 (회전 고려)
                rect = page.rect
                rotation = page.rotation
                if rotation == 90 or rotation == 270:
                    visual_width_pt, visual_height_pt = rect.height, rect.width
                else:
                    visual_width_pt, visual_height_pt = rect.width, rect.height

                # 2. 시각적 크기(cm)로 A4 여부 판단
                width_cm = visual_width_pt * 0.0352778
                height_cm = visual_height_pt * 0.0352778
                
                # 3. 적응형 DPI 계산 (물리적 크기 기준)
                page_height_inch = page.rect.height / 72
                adaptive_dpi = max(30, int(dpi * (a4_inch_height / page_height_inch))) if page_height_inch > 0 else dpi
                
                # 4. 이미지 렌더링 (회전 없이, 물리적 방향 그대로)
                pix = page.get_pixmap(dpi=adaptive_dpi, alpha=False, annots=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                # 5. PIL을 사용하여 명시적으로 이미지 회전
                if rotation != 0:
                    # PIL의 회전은 반시계 방향이므로, PyMuPDF의 시계 방향 회전을 변환
                    # 270(시계) -> 90(반시계) / 90(시계) -> 270(반시계)
                    pil_rotation_angle = (360 - rotation) % 360
                    if pil_rotation_angle > 0:
                        img = img.rotate(pil_rotation_angle, expand=True)

                # 6. JPEG 버퍼 생성
                img_buf = io.BytesIO()
                img.save(img_buf, format="JPEG", quality=jpeg_quality, optimize=True, progressive=True)
                img_buf.seek(0)

                # 7. 최종 저장될 페이지의 크기 및 방향 결정 (시각적 기준)
                a4_rect = pymupdf.paper_rect("a4")
                if _is_a4_size(width_cm, height_cm):
                    # 이미 A4 크기 -> 원본 물리적 크기 유지
                    target_width, target_height = page.rect.width, page.rect.height
                else:
                    # 큰 페이지 -> 시각적 방향에 맞는 A4 크기로 조정
                    is_visual_landscape = visual_width_pt > visual_height_pt
                    if is_visual_landscape:
                        target_width, target_height = a4_rect.height, a4_rect.width
                    else:
                        target_width, target_height = a4_rect.width, a4_rect.height

                # 8. 새 페이지 생성 및 이미지 삽입
                new_p = dst.new_page(width=target_width, height=target_height)
                new_p.insert_image(new_p.rect, stream=img_buf.read())
                
            except Exception as e:
                # 실패하면 그대로 복사(품질 보존 우선)
                print(f"[compress] page {i+1} fallback copy: {e}")
                dst.insert_pdf(src, from_page=i, to_page=i)

            finally:
                gc.collect()

        dst.save(
            output_path,
            garbage=4, deflate=True,
            clean=True, pretty=False
        )
        final_mb = os.path.getsize(output_path) / (1024 * 1024)
        return final_mb
    finally:
        src.close()
        dst.close()

def compress_pdf_with_multiple_stages(input_path, output_path, target_size_mb=3):
    """
    여러 단계의 압축을 시도하여 PDF를 목표 크기로 압축하는 함수
    
    Args:
        input_path (str): 입력 PDF 파일 경로
        output_path (str): 출력 PDF 파일 경로
        target_size_mb (int): 목표 파일 크기 (MB)
    
    Returns:
        bool: 압축 성공 여부
    """
    import os
    import shutil
    
    # 1) 원본이 목표 크기 이하면 그대로 사용
    orig_mb = os.path.getsize(input_path) / (1024 * 1024)
    if orig_mb <= target_size_mb:
        shutil.move(input_path, output_path)
        return True

    # 2) 1단계 압축 시도 (중간 품질)
    compressed_mb = compress_pdf_file(
        input_path=input_path,
        output_path=output_path,
        jpeg_quality=83,   # 중간 품질
        dpi=146,           # 중간 해상도
        size_threshold_kb=300
    )
    print(f"1단계 압축 후 크기: {compressed_mb} MB")
    if compressed_mb is not None and compressed_mb <= target_size_mb:
        return True

    # 3) 2단계 압축 시도 (낮은 품질)
    compressed_mb = compress_pdf_file(
        input_path=input_path,
        output_path=output_path,
        jpeg_quality=75,   # 낮은 품질
        dpi=125,           # 낮은 해상도
        size_threshold_kb=0  # 모든 페이지 강제 이미지화
    )
    print(f"2단계 압축 후 크기: {compressed_mb} MB")
    if compressed_mb is not None and compressed_mb <= target_size_mb:
        return True

    # 4) 3단계 압축 시도 (최저 품질)
    compressed_mb = compress_pdf_file(
        input_path=input_path,
        output_path=output_path,
        jpeg_quality=68,   # 최저 품질
        dpi=100,            # 최저 해상도
        size_threshold_kb=0  # 모든 페이지 강제 이미지화
    )
    print(f"3단계 압축 후 크기: {compressed_mb} MB")
    if compressed_mb is not None and compressed_mb <= target_size_mb:
        return True

    # 5) 모든 압축 실패시 원본 저장
    try:
        shutil.move(input_path, output_path)
        return False  # 압축 실패했지만 원본은 저장됨
    except Exception as e:
        print(f"[오류] 원본 파일 이동 실패: {e}")
        return False
