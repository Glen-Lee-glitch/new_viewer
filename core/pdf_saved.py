# pdf_utils.py
import pymupdf
from PIL import Image
import io
import gc
import os
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
import logging
from pathlib import Path
from datetime import datetime


def compress_pdf_file(
        input_bytes: bytes,
        output_path: str,
        jpeg_quality: int = 65,
        dpi: int = 120,
        size_threshold_kb: int = 300,
        user_rotations: dict = None,
        stamp_data: dict[int, list[dict]] = None,
        page_order: list[int] = None,
):
    """
    이미지·스캔으로 추정되거나 강제 조정이 요청된 페이지만 재렌더링-압축하고,
    나머지 페이지는 그대로 복사한다.
    return: 새 PDF 용량(MB) ― 실패 시 None
    """
    if not input_bytes:
        return None

    src = pymupdf.open(stream=input_bytes, filetype="pdf")
    dst = pymupdf.open()
    user_rotations = user_rotations or {}
    stamp_data = stamp_data or {}

    if page_order is None:
        page_order = list(range(src.page_count))
    
    # --- 여기서 데이터 키 변환 ---
    final_stamp_data = {}
    for actual_page_num, stamp_list in stamp_data.items():
        try:
            new_position = page_order.index(actual_page_num)
            final_stamp_data[new_position] = stamp_list
        except ValueError:
            pass # 순서에 없는 페이지는 무시
            
    final_rotations = {}
    for actual_page_num, rotation in user_rotations.items():
        try:
            new_position = page_order.index(actual_page_num)
            final_rotations[new_position] = rotation
        except ValueError:
            pass

    try:
        # for i, page in enumerate(src): # <--- 기존 루프를 아래 코드로 변경
        for new_idx, actual_page_idx in enumerate(page_order):
            page = src.load_page(actual_page_idx)
            # 루프 내에서 'i' 대신 'actual_page_idx' 사용
            user_rotation = final_rotations.get(new_idx, 0) # <--- 변환된 데이터 사용
            # 스탬프가 있는 페이지인지 확인
            has_stamps = new_idx in final_stamp_data # <--- 변환된 데이터 사용

            image_list = []
            image_size = 0
            # --- 개선된 용량 추정 --------------------------
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

            # 조건: (이미지가 없거나 이미지 크기가 임계값 미만) -> 복사
            # 회전이 적용된 페이지는 이 조건을 건너뛰고 재렌더링되도록 user_rotation == 0 조건을 제거
            # 스탬프가 있는 페이지는 항상 재렌더링
            if (not image_list or image_size / 1024 < size_threshold_kb) and not has_stamps:
                # 하지만, 회전이 없는 페이지만 복사하도록 내부에서 한 번 더 체크
                if user_rotation == 0:
                    dst.insert_pdf(src, from_page=actual_page_idx, to_page=actual_page_idx)
                    continue

            # ── 여기부터 '무거운' 페이지 또는 '강제 조정' 또는 '회전된' 페이지만 이미지-재렌더링 ──
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
                # 최종적으로 표시되는 이미지의 가로/세로 비율을 기준으로 목표 페이지 방향을 결정
                is_visual_landscape = display_width > display_height
                
                if is_visual_landscape:
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

                # 7. 최종 표시 방향에 따라 A4 페이지 방향 결정
                if is_visual_landscape:
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
                if is_visual_landscape:
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

                # 9. 스탬프 데이터가 있으면 페이지에 삽입
                if has_stamps:
                    for stamp in final_stamp_data[new_idx]: # <--- 변환된 데이터 사용
                        try:
                            stamp_pix: QPixmap = stamp['pixmap']
                            
                            # QPixmap을 PNG 바이트로 변환 (io.BytesIO -> QBuffer)
                            byte_array = QByteArray()
                            buffer = QBuffer(byte_array)
                            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                            stamp_pix.save(buffer, "PNG")
                            stamp_bytes = bytes(buffer.data())
                            
                            base_rect = insert_rect
                            
                            stamp_w = base_rect.width * stamp['w_ratio']
                            stamp_h = base_rect.height * stamp['h_ratio']
                            stamp_x = base_rect.x0 + base_rect.width * stamp['x_ratio']
                            stamp_y = base_rect.y0 + base_rect.height * stamp['y_ratio']
                            
                            stamp_rect = pymupdf.Rect(stamp_x, stamp_y, stamp_x + stamp_w, stamp_y + stamp_h)
                            
                            new_p.insert_image(stamp_rect, stream=stamp_bytes, overlay=True)

                        except Exception as e_stamp:
                            print(f"[compress] page {actual_page_idx+1} stamp insertion error: {e_stamp}")
                
            except Exception as e:
                # 실패하면 그대로 복사(품질 보존 우선)
                print(f"[compress] page {actual_page_idx+1} fallback copy: {e}")
                dst.insert_pdf(src, from_page=actual_page_idx, to_page=actual_page_idx)

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

def compress_pdf_with_multiple_stages(
    input_bytes: bytes,
    output_path: str,
    target_size_mb: float,
    rotations: dict[int, int] | None = None,
    stamp_data: dict[int, list[dict]] | None = None,
    page_order: list[int] | None = None
) -> bool:
    """
    여러 단계를 거쳐 PDF를 압축하고 저장한다.
    
    Args:
        input_bytes (bytes): 입력 PDF 바이트 데이터
        output_path (str): 출력 PDF 파일 경로
        target_size_mb (float): 목표 파일 크기 (MB)
        rotations (dict, optional): {page_num: rotation_angle} 형태의 딕셔너리. Defaults to None.
        stamp_data (dict, optional): 페이지별 스탬프 데이터. Defaults to None.
        page_order (list, optional): 페이지 순서를 지정하는 리스트. None이면 원본 순서 유지. Defaults to None.
    
    Returns:
        bool: 압축 및 저장 성공 여부.
    """
    import os
    
    if not rotations:
        rotations = {}
    if not stamp_data:
        stamp_data = {}
    
    # 페이지 순서가 변경되었는지 확인
    is_order_changed = False
    if page_order is not None:
        # page_order가 [0, 1, 2, ...] 순서와 다르면 변경된 것으로 간주
        expected_order = list(range(len(page_order)))
        is_order_changed = page_order != expected_order

    # 1) 원본 파일이 목표 크기 이하면 그대로 사용 (단, 회전/스탬프/순서 변경이 있으면 압축 시도)
    orig_mb = len(input_bytes) / (1024 * 1024)
    if orig_mb <= target_size_mb and not rotations and not stamp_data and not is_order_changed:
        with open(output_path, "wb") as f:
            f.write(input_bytes)
        return True

    # 2) 1단계 압축 시도 (중간 품질)
    compressed_mb = compress_pdf_file(
        input_bytes=input_bytes,
        output_path=output_path,
        jpeg_quality=83,
        dpi=146,
        size_threshold_kb=300,
        user_rotations=rotations,
        stamp_data=stamp_data,
        page_order=page_order
    )
    print(f"1단계 압축 후 크기: {compressed_mb} MB")
    if compressed_mb is not None and compressed_mb <= target_size_mb:
        return True

    # 3) 2단계 압축 시도 (낮은 품질)
    compressed_mb = compress_pdf_file(
        input_bytes=input_bytes,
        output_path=output_path,
        jpeg_quality=75,
        dpi=125,
        size_threshold_kb=0,
        user_rotations=rotations,
        stamp_data=stamp_data,
        page_order=page_order
    )
    print(f"2단계 압축 후 크기: {compressed_mb} MB")
    if compressed_mb is not None and compressed_mb <= target_size_mb:
        return True

    # 4) 3단계 압축 시도 (최저 품질)
    compressed_mb = compress_pdf_file(
        input_bytes=input_bytes,
        output_path=output_path,
        jpeg_quality=68,
        dpi=100,
        size_threshold_kb=0,
        user_rotations=rotations,
        stamp_data=stamp_data,
        page_order=page_order
    )
    print(f"3단계 압축 후 크기: {compressed_mb} MB")
    if compressed_mb is not None and compressed_mb <= target_size_mb:
        return True

    # 5) 모든 압축 실패시 원본 저장
    try:
        with open(output_path, "wb") as f:
            f.write(input_bytes)
        return False  # 압축 실패했지만 원본은 저장됨
    except Exception as e:
        print(f"[오류] 최종 파일 복사 실패: {e}")
        return False

def export_deleted_pages(
        pdf_bytes: bytes,
        page_indices: list[int],
        output_dir: str | Path,
        base_name: str,
        delete_info: dict = None,
) -> list[Path]:
    """삭제된 페이지를 원본 그대로 개별 PDF로 저장한다."""
    if not pdf_bytes:
        return []

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    exported_files: list[Path] = []
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as src:
            total_pages = src.page_count

            for page_idx in sorted(set(page_indices)):
                if not (0 <= page_idx < total_pages):
                    continue

                temp_doc = pymupdf.open()
                try:
                    temp_doc.insert_pdf(src, from_page=page_idx, to_page=page_idx)
                    
                    # 삭제 사유 추출 및 파일명에 포함
                    reason = ""
                    if delete_info and delete_info.get("reason"):
                        reason_text = delete_info["reason"]
                        # "기타"인 경우 커스텀 텍스트 사용 (파일명에 적합하도록 정리)
                        if reason_text == "기타" and delete_info.get("custom_text"):
                            custom_text = delete_info["custom_text"].strip()
                            # 파일명에 사용할 수 없는 문자 제거
                            custom_text = "".join(c for c in custom_text if c.isalnum() or c in "._- ")
                            custom_text = custom_text.replace(" ", "_")[:20]  # 최대 20자로 제한
                            reason = f"기타_{custom_text}" if custom_text else "기타"
                        else:
                            reason = reason_text
                    
                    # 파일명 생성: {원본파일명}_{사유}_{페이지번호}.pdf
                    if reason:
                        file_name = f"{base_name}_{reason}_{page_idx + 1}.pdf"
                    else:
                        file_name = f"{base_name}_{page_idx + 1}.pdf"
                    
                    dest_path = destination / file_name
                    
                    # 파일이 이미 존재하면 타임스탬프 추가
                    if dest_path.exists():
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        if reason:
                            file_name = f"{base_name}_{reason}_{page_idx + 1}_{timestamp}.pdf"
                        else:
                            file_name = f"{base_name}_{page_idx + 1}_{timestamp}.pdf"
                        dest_path = destination / file_name
                    
                    temp_doc.save(str(dest_path), deflate=False, clean=False)
                    exported_files.append(dest_path)
                finally:
                    temp_doc.close()
    except Exception as exc:
        print(f"[export_deleted_pages] 오류: {exc}")

    return exported_files