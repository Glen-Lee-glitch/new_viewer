import pymupdf
from pathlib import Path
import os
import platform
from PIL import Image, ImageDraw, ImageFont
import io

def find_korean_font():
    """시스템에서 한글 폰트 파일 경로를 찾습니다."""
    system = platform.system()
    
    if system == "Windows":
        font_dirs = [
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
        ]
        font_files = [
            "malgun.ttf",  # 맑은 고딕
            "malgunbd.ttf",  # 맑은 고딕 Bold
            "gulim.ttc",  # 굴림
        ]
        
        for font_dir in font_dirs:
            if os.path.exists(font_dir):
                for font_file in font_files:
                    font_path = os.path.join(font_dir, font_file)
                    if os.path.exists(font_path):
                        return font_path
    
    elif system == "Darwin":  # macOS
        font_dirs = [
            "/System/Library/Fonts/Supplemental",
            "/Library/Fonts",
        ]
        font_files = ["AppleGothic.ttf"]
        
        for font_dir in font_dirs:
            if os.path.exists(font_dir):
                for font_file in font_files:
                    font_path = os.path.join(font_dir, font_file)
                    if os.path.exists(font_path):
                        return font_path
    
    elif system == "Linux":
        font_dirs = [
            "/usr/share/fonts/truetype/nanum",
            "/usr/share/fonts/truetype/liberation",
        ]
        font_files = ["NanumGothic.ttf"]
        
        for font_dir in font_dirs:
            if os.path.exists(font_dir):
                for font_file in font_files:
                    font_path = os.path.join(font_dir, font_file)
                    if os.path.exists(font_path):
                        return font_path
    
    return None

def create_text_image(text: str, font_size: int = 20) -> bytes:
    """
    PIL을 사용하여 텍스트를 이미지로 변환하여 PNG 바이트를 반환합니다.
    """
    # 한글 폰트 찾기
    font_path = find_korean_font()
    
    try:
        if font_path:
            # 폰트 파일 로드 (폰트 크기를 포인트에서 픽셀로 변환, DPI 72 기준)
            font = ImageFont.truetype(font_path, int(font_size * 1.33))  # pt to px 변환
        else:
            # 기본 폰트 사용 (한글 지원 안 될 수 있음)
            font = ImageFont.load_default()
            print("⚠️ 한글 폰트를 찾을 수 없습니다. 기본 폰트를 사용합니다.")
    except Exception as e:
        print(f"⚠️ 폰트 로드 실패: {e}, 기본 폰트 사용")
        font = ImageFont.load_default()
    
    # 텍스트 크기 계산
    # 임시 이미지로 텍스트 크기 측정
    temp_img = Image.new('RGB', (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)
    bbox = temp_draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # 여백 추가하여 이미지 생성
    padding = 10
    img_width = text_width + padding * 2
    img_height = text_height + padding * 2
    
    # 투명 배경 이미지 생성
    img = Image.new('RGBA', (img_width, img_height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    # 텍스트 그리기 (검정색)
    draw.text((padding, padding), text, font=font, fill=(0, 0, 0, 255))
    
    # PNG 바이트로 변환
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    return img_bytes.getvalue()

import concurrent.futures

def compress_single_image(args):
    """
    이미지 데이터를 받아 압축된 바이트를 반환하는 워커 함수
    """
    image_bytes, image_ext = args
    try:
        # PIL로 이미지 열기
        img_pil = Image.open(io.BytesIO(image_bytes))
        
        # 이미지가 너무 크면 리샘플링 (최대 2000px)
        if img_pil.width > 2000 or img_pil.height > 2000:
            ratio = min(2000 / img_pil.width, 2000 / img_pil.height)
            new_width = int(img_pil.width * ratio)
            new_height = int(img_pil.height * ratio)
            img_pil = img_pil.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # JPEG로 압축
        compressed_bytes = io.BytesIO()
        if image_ext.lower() in ['jpeg', 'jpg']:
            if img_pil.mode != 'RGB':
                img_pil = img_pil.convert('RGB')
            img_pil.save(compressed_bytes, format='JPEG', quality=85, optimize=True)
        else:
            if img_pil.mode == 'RGBA':
                background = Image.new('RGB', img_pil.size, (255, 255, 255))
                background.paste(img_pil, mask=img_pil.split()[3])
                img_pil = background
            elif img_pil.mode != 'RGB':
                img_pil = img_pil.convert('RGB')
            img_pil.save(compressed_bytes, format='JPEG', quality=85, optimize=True)
        
        return compressed_bytes.getvalue()
    except Exception as e:
        return None

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
        font_size = 15

        # 파일 크기 확인 및 압축 저장
        file_size = input_pdf.stat().st_size
        limit_size = 7 * 1024 * 1024  # 7MB

        print("[DEBUG] PDF 압축 전 페이지 정보:")
        for i, page in enumerate(doc):
            print(f"[DEBUG] Page {i+1} - Rotation: {page.rotation}, Size: (Width: {page.rect.width:.2f}, Height: {page.rect.height:.2f})")

        if file_size > limit_size:
            print(f"[INFO] 입력 파일 크기: {file_size / 1024 / 1024:.2f} MB (7MB 초과)")
            print(f"[INFO] 이미지 압축을 시작합니다... (병렬 처리)")
            
            # 1. 압축 대상 이미지 정보 수집 (순차)
            tasks = []
            task_info = [] # (page_num, xref, img_rect, original_size)
            
            for page_num, page in enumerate(doc):
                image_list = page.get_images()
                if image_list:
                    for img in image_list:
                        try:
                            xref = img[0]
                            img_name = img[7]
                            
                            # 위치 찾기
                            img_rects = []
                            try:
                                img_rects = page.get_image_rects(xref)
                            except:
                                try:
                                    img_rects = page.get_image_rects(img_name)
                                except:
                                    pass
                            
                            if not img_rects:
                                continue
                            
                            img_rect = img_rects[0]
                            base_image = doc.extract_image(xref)
                            image_bytes = base_image["image"]
                            image_ext = base_image["ext"]
                            
                            tasks.append((image_bytes, image_ext))
                            task_info.append((page_num, xref, img_rect, len(image_bytes)))
                            
                        except Exception:
                            continue

            print(f"[INFO] 총 {len(tasks)}개의 이미지를 압축합니다.")

            # 2. 병렬 압축 실행
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(compress_single_image, tasks))
            
            # 3. 결과 적용 (순차)
            for (page_num, xref, img_rect, original_size), compressed_image_bytes in zip(task_info, results):
                if compressed_image_bytes:
                    compressed_size = len(compressed_image_bytes)
                    if compressed_size < original_size * 0.9:
                        try:
                            page = doc[page_num]
                            page.delete_image(xref)
                            page.insert_image(img_rect, stream=compressed_image_bytes)
                        except Exception as e:
                            print(f"[WARNING] 이미지 교체 실패: {e}")
        else:
            print(f"[INFO] 입력 파일 크기: {file_size / 1024 / 1024:.2f} MB (7MB 이하)")
            print(f"[INFO] 압축 없이 진행합니다...")
        
        # A4 리사이징 로직 (압축 후, 텍스트 삽입 전)
        try:
            print("[INFO] 페이지 크기 검사 및 리사이징 시작...")
            needs_resize = False
            A4_WIDTH, A4_HEIGHT = 595.276, 841.890
            TOLERANCE = 5.0

            for page in doc:
                # 회전값을 0으로 초기화하여 물리적 크기 확인
                original_rot = page.rotation
                page.set_rotation(0)
                w, h = page.rect.width, page.rect.height
                page.set_rotation(original_rot)  # 원상복구
                
                long_side, short_side = max(w, h), min(w, h)
                if abs(long_side - A4_HEIGHT) > TOLERANCE or abs(short_side - A4_WIDTH) > TOLERANCE:
                    needs_resize = True
                    break
            
            if needs_resize:
                print("[INFO] A4 규격이 아닌 페이지가 감지되어 리사이징을 진행합니다.")
                new_doc = pymupdf.open()
                
                for page in doc:
                    # 원본 회전값 저장
                    rot = page.rotation
                    
                    # 회전값을 0으로 초기화하여 물리적 크기 확인
                    page.set_rotation(0)
                    src_rect = page.rect
                    
                    # 모든 페이지를 A4 세로형으로 통일 (원본이 세로형이므로)
                    tgt_width, tgt_height = A4_WIDTH, A4_HEIGHT
                    
                    new_page = new_doc.new_page(width=tgt_width, height=tgt_height)
                    
                    # 스케일 및 회전값 계산
                    if rot in [90, 270]:
                        # 회전 시 가로/세로가 바뀌므로 교차해서 스케일 계산
                        src_w, src_h = src_rect.height, src_rect.width
                        # 270도일 때 거꾸로 나오면 90도로 보정 (180도 뒤집기)
                        apply_rot = 90 if rot == 270 else rot
                    else:
                        src_w, src_h = src_rect.width, src_rect.height
                        apply_rot = rot
                    
                    # 화면에 꽉 차게 Fit (비율 유지)
                    scale = min(tgt_width / src_w, tgt_height / src_h)
                    
                    new_w = src_w * scale
                    new_h = src_h * scale
                    x = (tgt_width - new_w) / 2
                    y = (tgt_height - new_h) / 2
                    dest_rect = pymupdf.Rect(x, y, x + new_w, y + new_h)
                    
                    # 내용 복사 (보정된 회전값 적용)
                    new_page.show_pdf_page(dest_rect, doc, page.number, rotate=apply_rot)
                    
                    # 회전값 적용하지 않음 (모든 페이지를 정방향 A4 세로형으로 통일)
                    # new_page.set_rotation(rot)
                    
                    # 원본 페이지 회전값 원상복구 (다음 처리를 위해)
                    page.set_rotation(rot)
                
                # 문서 교체
                old_doc = doc
                doc = new_doc
                old_doc.close()
                print("[INFO] 모든 페이지를 A4 규격으로 리사이징 완료.")
            else:
                print("[INFO] 모든 페이지가 이미 A4 규격 내에 있습니다.")
                
        except Exception as e:
            print(f"[WARNING] 리사이징 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()

        # 압축 여부와 관계없이 모든 페이지에 텍스트 삽입
        print(f"[INFO] 텍스트 삽입을 시작합니다...")
        for page_num, page in enumerate(doc):
            try:
                # 원본 회전값 저장
                original_rot = page.rotation
                
                # 좌표 계산을 위해 잠시 페이지 회전을 0으로 초기화
                page.set_rotation(0)
                
                # 텍스트를 이미지로 변환
                text_image_bytes = create_text_image(text_content, font_size)
                
                # 페이지 회전값이 있으면 텍스트 이미지를 같은 방향으로 회전시켜서 올곧게 보이도록 함
                if original_rot != 0:
                    # PIL로 이미지를 열어서 회전
                    img = Image.open(io.BytesIO(text_image_bytes))
                    # 페이지 회전과 같은 방향으로 회전 (뷰어가 보정할 때 올곧게 보이도록)
                    # PIL rotate는 반시계 방향이므로, original_rot 그대로 사용
                    rotated_img = img.rotate(original_rot, expand=True, fillcolor=(255, 255, 255, 0))
                    
                    # 회전된 이미지를 바이트로 변환
                    rotated_bytes = io.BytesIO()
                    rotated_img.save(rotated_bytes, format='PNG')
                    text_image_bytes = rotated_bytes.getvalue()
                
                # 이미지 크기 계산
                text_image = pymupdf.open(stream=text_image_bytes, filetype="png")
                img_page = text_image[0]
                img_rect = img_page.rect
                img_width = img_rect.width
                img_height = img_rect.height
                text_image.close()
                
                # 페이지 중앙 좌표 계산
                rect = page.rect
                x = (rect.width - img_width) / 2
                y = (rect.height / 2) - (img_height / 2) + (font_size * 0.35)
                
                # 회전값에 따른 좌표 조정
                if original_rot == 270:
                    x = x - 60
                elif original_rot == 0:
                    y = y + 60
                
                # 텍스트 이미지를 PDF 페이지에 삽입
                image_rect = pymupdf.Rect(x, y, x + img_width, y + img_height)
                page.insert_image(image_rect, stream=text_image_bytes)
                
                # 페이지 회전값 원상복구
                page.set_rotation(original_rot)
                
                print(f"[INFO] Page {page_num + 1}에 텍스트 '{text_content}' 삽입 완료 (회전: {original_rot}°)")
            except Exception as e:
                print(f"[WARNING] Page {page_num + 1} 텍스트 삽입 실패: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        # 텍스트 삽입 후 최종 결과 검증
        print("[DEBUG] 텍스트 삽입 완료 후 최종 페이지 정보:")
        for i, page in enumerate(doc):
            print(f"[DEBUG] Page {i+1} - Rotation: {page.rotation}, Size: (Width: {page.rect.width:.2f}, Height: {page.rect.height:.2f})")
        
        # 텍스트 삽입 후 모든 경우에 저장
        print(f"[INFO] 텍스트 삽입 완료. 최종 저장 중...")
        if file_size > limit_size:
            # 압축된 경우: 텍스트 삽입 후 압축 저장
            doc.save(output_pdf, deflate=True, garbage=4)
            
            # 압축된 결과물 크기 확인
            output_size = output_pdf.stat().st_size
            compression_ratio = (1 - output_size / file_size) * 100
            print(f"[INFO] 최종 출력 파일 크기: {output_size / 1024 / 1024:.2f} MB")
            print(f"[INFO] 압축률: {compression_ratio:.1f}% ({(file_size - output_size) / 1024 / 1024:.2f} MB 감소)")
        else:
            # 압축하지 않은 경우: 일반 저장
            doc.save(output_pdf)
            
            # 저장된 결과물 크기 확인
            output_size = output_pdf.stat().st_size
            print(f"[INFO] 최종 출력 파일 크기: {output_size / 1024 / 1024:.2f} MB")
        
        doc.close()
        
        # 저장된 결과 파일 검증
        print("[DEBUG] 저장된 결과 PDF 검증:")
        try:
            result_doc = pymupdf.open(output_pdf)
            for i, page in enumerate(result_doc):
                print(f"[DEBUG] 결과 Page {i+1} - Rotation: {page.rotation}, Size: (Width: {page.rect.width:.2f}, Height: {page.rect.height:.2f})")
            result_doc.close()
        except Exception as e:
            print(f"[WARNING] 결과 파일 검증 중 오류: {e}")
        
        print(f"완료: {output_pdf} 에 저장되었습니다.")
        
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    extract_as_is()
