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
        size_threshold_kb: int = 300,  # 페이지 당 300 KB 이상만 재압축
        user_rotations: dict = None,  # 사용자가 적용한 페이지별 회전 정보
        force_resize_pages: set = None # 강제 크기 조정을 적용할 페이지 번호
):
    """
    이미지·스캔으로 추정되거나 강제 조정이 요청된 페이지만 재렌더링-압축하고,
    나머지 페이지는 그대로 복사한다.
    return: 새 PDF 용량(MB) ― 실패 시 None
    """
    if not os.path.exists(input_path):
        return None

    src = pymupdf.open(input_path)
    dst = pymupdf.open()                     # 결과 PDF
    user_rotations = user_rotations or {}
    force_resize_pages = force_resize_pages or set()
    try:
        for i, page in enumerate(src):
            user_rotation = user_rotations.get(i, 0)
            # 강제 크기 조정이 요청된 페이지인지 확인
            is_forced = i in force_resize_pages
            
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

            # 조건: (이미지가 없거나 이미지 크기가 임계값 미만) 이고 (강제 조정이 아닐 때) -> 복사
            if (not image_list or image_size / 1024 < size_threshold_kb) and not is_forced and user_rotation == 0:
                dst.insert_pdf(src, from_page=i, to_page=i)
                continue
            

            # ── 여기부터 '무거운' 페이지 또는 '강제 조정' 페이지만 이미지-재렌더링 ──
            try:
                # === 뷰어 표시 형태 그대로 저장하는 로직 ===
                # 뷰어에서 보이는 A4 세로 기준 통일된 형태로 정규화하여 저장한다.

                # 1. A4 세로 기준 크기 정의 (포인트 단위)
                a4_rect = pymupdf.paper_rect("a4")  # 595.2 x 841.8 포인트
                a4_width, a4_height = a4_rect.width, a4_rect.height
                
                # 2. 페이지의 실제 시각적 표시 크기 계산
                # 회전이 적용된 후 사용자가 실제로 보게 되는 크기를 기준으로 해야 함
                total_rotation = (page.rotation + user_rotation) % 360
                
                # 페이지를 실제로 렌더링해서 시각적 크기를 얻어야 함
                # get_pixmap()을 통해 회전이 적용된 실제 표시 크기를 확인
                temp_matrix = pymupdf.Matrix(1.0, 1.0)  # 1:1 스케일로 임시 렌더링
                if user_rotation != 0:
                    rotation_matrix = pymupdf.Matrix(user_rotation)
                    temp_matrix = rotation_matrix * temp_matrix
                
                temp_pix = page.get_pixmap(matrix=temp_matrix, alpha=False, annots=False)
                
                # 실제 시각적 표시 크기 (픽셀 단위를 포인트로 변환)
                display_width = temp_pix.width * 72 / 72  # 72 DPI 기준
                display_height = temp_pix.height * 72 / 72
                
                # 3. A4 크기에 맞추되 비율을 유지하며 여백 최소화 스케일 계산
                # 회전 각도에 따라 목표 페이지 크기 결정
                is_landscape = (user_rotation % 180 == 90)  # 90도나 270도면 가로 방향
                if is_landscape:
                    # A4 가로 방향 사용
                    target_width, target_height = a4_height, a4_width
                else:
                    # A4 세로 방향 사용
                    target_width, target_height = a4_width, a4_height

                scale_x = target_width / display_width
                scale_y = target_height / display_height

                # 잘림 없이 전체가 들어가도록 더 작은 스케일 사용
                fit_scale = min(scale_x, scale_y)
                
                # 4. 최종 변환 매트릭스 생성
                # 먼저 DPI 품질 향상을 위한 줌 적용
                quality_zoom = dpi / 72
                # 그 다음 A4 정규화를 위한 스케일 적용
                final_scale = fit_scale * quality_zoom
                
                # 5. 최종 렌더링 (실제 시각적 크기를 기준으로 계산된 스케일 적용)
                # 최종 스케일 매트릭스 생성
                final_matrix = pymupdf.Matrix(final_scale, final_scale)
                
                # 사용자 회전이 있다면 추가 회전 매트릭스 생성
                if user_rotation != 0:
                    rotation_matrix = pymupdf.Matrix(user_rotation)
                    # 회전 후 스케일 적용 (뷰어와 동일한 순서)
                    final_matrix = rotation_matrix * final_matrix
                
                pix = page.get_pixmap(matrix=final_matrix, alpha=False, annots=True)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                # 6. JPEG 이미지 버퍼 생성
                img_buf = io.BytesIO()
                img.save(img_buf, format="JPEG", quality=jpeg_quality, optimize=True, progressive=True)
                img_buf.seek(0)

                # 7. 회전 각도에 따라 A4 페이지 방향 결정 (90도/270도는 가로, 0도/180도는 세로)
                if is_landscape:
                    # A4 가로 방향으로 페이지 생성 (너비와 높이 교체)
                    new_p = dst.new_page(width=a4_height, height=a4_width)
                else:
                    # A4 세로 방향으로 페이지 생성
                    new_p = dst.new_page(width=a4_width, height=a4_height)
                # 회전값은 0으로 설정 (뷰어에서 보이는 형태가 이미 올바른 방향)
                new_p.set_rotation(0)
                
                # 8. 렌더링된 이미지를 페이지 중앙에 배치
                # 이미지 크기 계산
                img_width = pix.width / quality_zoom
                img_height = pix.height / quality_zoom

                # 중앙 배치를 위한 오프셋 계산 (가로/세로 방향에 따라 다름)
                if is_landscape:
                    # A4 가로 방향일 때
                    x_offset = (a4_height - img_width) / 2
                    y_offset = (a4_width - img_height) / 2
                else:
                    # A4 세로 방향일 때
                    x_offset = (a4_width - img_width) / 2
                    y_offset = (a4_height - img_height) / 2

                # 이미지 삽입 영역 정의
                insert_rect = pymupdf.Rect(x_offset, y_offset, x_offset + img_width, y_offset + img_height)
                new_p.insert_image(insert_rect, stream=img_buf.read())
                
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

def compress_pdf_with_multiple_stages(input_path, output_path, target_size_mb=3, rotations=None, force_resize_pages=None):
    """
    여러 단계의 압축을 시도하여 PDF를 목표 크기로 압축하는 함수
    
    Args:
        input_path (str): 입력 PDF 파일 경로
        output_path (str): 출력 PDF 파일 경로
        target_size_mb (int): 목표 파일 크기 (MB)
        rotations (dict, optional): {page_num: rotation_angle} 형태의 딕셔너리. Defaults to None.
        force_resize_pages (set, optional): 강제 크기 조정을 적용할 페이지 번호. Defaults to None.
    
    Returns:
        bool: 압축 성공 여부
    """
    import os
    import shutil
    
    rotations = rotations if rotations is not None else {}
    force_resize_pages = force_resize_pages if force_resize_pages is not None else set()

    # 1) 원본 파일이 목표 크기 이하면 그대로 사용 (단, 회전 정보나 강제 조정이 있으면 압축 시도)
    orig_mb = os.path.getsize(input_path) / (1024 * 1024)
    if orig_mb <= target_size_mb and not rotations and not force_resize_pages:
        shutil.copy2(input_path, output_path)
        return True

    # 2) 1단계 압축 시도 (중간 품질)
    compressed_mb = compress_pdf_file(
        input_path=input_path,
        output_path=output_path,
        jpeg_quality=83,   # 중간 품질
        dpi=146,           # 중간 해상도
        size_threshold_kb=300,
        user_rotations=rotations,
        force_resize_pages=force_resize_pages
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
        size_threshold_kb=0,  # 모든 페이지 강제 이미지화
        user_rotations=rotations,
        force_resize_pages=force_resize_pages
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
        size_threshold_kb=0,  # 모든 페이지 강제 이미지화
        user_rotations=rotations,
        force_resize_pages=force_resize_pages
    )
    print(f"3단계 압축 후 크기: {compressed_mb} MB")
    if compressed_mb is not None and compressed_mb <= target_size_mb:
        return True

    # 5) 모든 압축 실패시 원본 저장
    try:
        shutil.copy2(input_path, output_path)
        return False  # 압축 실패했지만 원본은 저장됨
    except Exception as e:
        print(f"[오류] 최종 파일 복사 실패: {e}")
        return False
