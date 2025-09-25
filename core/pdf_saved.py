# pdf_utils.py
import pymupdf
from PIL import Image
import io
import gc
import os

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
            image_list = []
            image_size = 0
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

            # 페이지에 이미지가 없거나, 이미지 자체의 크기가 임계값 미만이면 '압축 불필요'로 간주
            if not image_list or image_size / 1024 < size_threshold_kb:
                dst.insert_pdf(src, from_page=i, to_page=i)
                continue
            
            # -------------------------------------------

            # ── 여기부터 '무거운' 페이지만 이미지-재렌더링 ──
            try:
                # === WYSIWYG 원칙에 따른 렌더링 로직 ===
                # 페이지의 원본 비율과 크기를 '그대로' 유지하며 압축한다.

                # 1. 렌더링 해상도(DPI)에 따른 확대/축소 매트릭스 생성
                # 이 매트릭스는 페이지 크기나 비율을 바꾸지 않고, 렌더링 품질만 결정한다.
                zoom_matrix = pymupdf.Matrix(dpi / 72, dpi / 72)
                
                # 2. get_pixmap()은 페이지의 원본 회전을 자동으로 처리하여 렌더링한다.
                pix = page.get_pixmap(matrix=zoom_matrix, alpha=False, annots=True)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                # 3. JPEG 이미지 버퍼 생성
                img_buf = io.BytesIO()
                img.save(img_buf, format="JPEG", quality=jpeg_quality, optimize=True, progressive=True)
                img_buf.seek(0)

                # 4. 원본 페이지와 '동일한 크기'로 새 페이지를 생성한다.
                # page.rect는 회전이 적용되지 않은 원본 크기를 나타낸다.
                new_p = dst.new_page(
                    width=page.rect.width,
                    height=page.rect.height,
                )
                
                # 5. 원본 페이지의 회전 값을 그대로 새 페이지에 설정한다.
                new_p.set_rotation(page.rotation)
                
                # 6. 생성된 페이지에 압축된 이미지를 삽입한다.
                # new_p.rect는 페이지의 사각형 영역을 나타낸다.
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

def compress_pdf_with_multiple_stages(input_path, output_path, target_size_mb=3, rotations=None):
    """
    여러 단계의 압축을 시도하여 PDF를 목표 크기로 압축하는 함수
    
    Args:
        input_path (str): 입력 PDF 파일 경로
        output_path (str): 출력 PDF 파일 경로
        target_size_mb (int): 목표 파일 크기 (MB)
        rotations (dict, optional): {page_num: rotation_angle} 형태의 딕셔너리. Defaults to None.
    
    Returns:
        bool: 압축 성공 여부
    """
    import os
    import shutil
    
    rotations = rotations if rotations is not None else {}
    rotated_input_path = input_path

    # 1) 회전 정보가 있으면, 먼저 회전을 적용한 임시 파일을 생성한다.
    if rotations:
        try:
            doc = pymupdf.open(input_path)
            for page_num, rotation_angle in rotations.items():
                if 0 <= page_num < len(doc):
                    page = doc.load_page(page_num)
                    # 원본 회전값에 사용자 회전값을 더함
                    new_rotation = (page.rotation + rotation_angle) % 360
                    page.set_rotation(new_rotation)
            
            # 회전이 적용된 새 임시 파일을 사용
            rotated_input_path = input_path + ".rotated.tmp"
            doc.save(rotated_input_path, garbage=4, deflate=True)
            doc.close()
        except Exception as e:
            print(f"[오류] PDF 회전 적용 실패: {e}")
            # 회전 실패 시 원본을 그대로 사용
            rotated_input_path = input_path

    # 2) 원본(또는 회전된 파일)이 목표 크기 이하면 그대로 사용
    orig_mb = os.path.getsize(rotated_input_path) / (1024 * 1024)
    if orig_mb <= target_size_mb:
        shutil.move(rotated_input_path, output_path)
        # .rotated.tmp 파일이 생성되었다면 여기서 input_path는 원본 임시파일이므로 삭제하면 안됨
        # PdfSaveWorker의 finally 블록에서 모든 .tmp 파일을 정리함
        return True

    # 3) 1단계 압축 시도 (중간 품질)
    compressed_mb = compress_pdf_file(
        input_path=rotated_input_path,
        output_path=output_path,
        jpeg_quality=83,   # 중간 품질
        dpi=146,           # 중간 해상도
        size_threshold_kb=300
    )
    print(f"1단계 압축 후 크기: {compressed_mb} MB")
    if compressed_mb is not None and compressed_mb <= target_size_mb:
        return True

    # 4) 2단계 압축 시도 (낮은 품질)
    compressed_mb = compress_pdf_file(
        input_path=rotated_input_path,
        output_path=output_path,
        jpeg_quality=75,   # 낮은 품질
        dpi=125,           # 낮은 해상도
        size_threshold_kb=0  # 모든 페이지 강제 이미지화
    )
    print(f"2단계 압축 후 크기: {compressed_mb} MB")
    if compressed_mb is not None and compressed_mb <= target_size_mb:
        return True

    # 5) 3단계 압축 시도 (최저 품질)
    compressed_mb = compress_pdf_file(
        input_path=rotated_input_path,
        output_path=output_path,
        jpeg_quality=68,   # 최저 품질
        dpi=100,            # 최저 해상도
        size_threshold_kb=0  # 모든 페이지 강제 이미지화
    )
    print(f"3단계 압축 후 크기: {compressed_mb} MB")
    if compressed_mb is not None and compressed_mb <= target_size_mb:
        return True

    # 6) 모든 압축 실패시 회전된 버전(또는 원본) 저장
    try:
        shutil.move(rotated_input_path, output_path)
        return False  # 압축 실패했지만 회전된 버전은 저장됨
    except Exception as e:
        print(f"[오류] 최종 파일 이동 실패: {e}")
        return False
