import pymupdf
from pathlib import Path
import os
import platform
from PIL import Image, ImageDraw, ImageFont
import io
import psycopg2
import sys
# 상위 디렉토리 접근을 위해 sys.path 추가
try:
    sys.path.append(str(Path(__file__).parent.parent))
except:
    pass
from core.data_manage import DB_CONFIG

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
        
        # [DEBUG START] 1페이지 객체 분석
        print(f"\n{'='*50}")
        print(f"[DEBUG] 11.pdf Page 1 심층 분석 시작")
        try:
            page1 = doc[0]
            
            # 1. Annotation (주석/서명) 확인
            print(f"\n[1. Annotations (주석/서명)]")
            annots = list(page1.annots())
            if not annots:
                print(" -> 발견된 Annotation 없음")
            for i, annot in enumerate(annots):
                # annot.type: [id, name] ex) [0, 'Text'], [15, 'Ink']
                print(f"  #{i+1} Type: {annot.type[0]} ({annot.type[1]})")
                print(f"      Rect: {annot.rect}")
                print(f"      Info: {annot.info}")
                # Line 타입인 경우 vertices 정보 출력
                if annot.type[0] == 3:
                    try:
                        if hasattr(annot, "vertices"):
                            vertices = annot.vertices
                            print(f"      Vertices: {vertices}")
                            print(f"      Vertices 타입: {type(vertices)}, 길이: {len(vertices) if vertices else 0}")
                            if vertices and len(vertices) >= 2:
                                print(f"      첫 번째 점: {vertices[0]}, 타입: {type(vertices[0])}")
                                print(f"      두 번째 점: {vertices[1]}, 타입: {type(vertices[1])}")
                                # Point 객체인 경우 좌표 출력
                                if hasattr(vertices[0], 'x'):
                                    print(f"      첫 번째 점 좌표: ({vertices[0].x}, {vertices[0].y})")
                                    print(f"      두 번째 점 좌표: ({vertices[1].x}, {vertices[1].y})")
                        else:
                            print(f"      Vertices: 속성 없음")
                    except Exception as e:
                        print(f"      Vertices: 접근 불가 - {e}")

            # 2. Images (이미지) 확인
            print(f"\n[2. Images (이미지)]")
            images = page1.get_images()
            if not images:
                print(" -> 발견된 Image 없음")
            for i, img in enumerate(images):
                xref = img[0]
                try:
                    bbox = page1.get_image_rects(xref)
                    print(f"  #{i+1} Xref: {xref}, Loc: {bbox}")
                except:
                    print(f"  #{i+1} Xref: {xref} (위치 확인 불가)")

            # 3. Drawings (벡터 그래픽 - 펜으로 쓴 것 같은 선들) 확인
            print(f"\n[3. Drawings (벡터 그래픽)]")
            drawings = page1.get_drawings()
            print(f"  -> 총 {len(drawings)}개의 드로잉 패스 발견")
            # 너무 많을 수 있으니 처음 5개만 샘플 출력
            for i, d in enumerate(drawings[:5]):
                print(f"  #{i+1} Type: {d['type']}, Rect: {d['rect']}")

        except Exception as e:
            print(f"[DEBUG] 분석 중 에러 발생: {e}")
        print(f"{'='*50}\n")
        # [DEBUG END]

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
            # xref별로 한 번만 압축하고, 각 위치 정보를 모두 저장
            xref_to_image_data = {}  # xref -> (image_bytes, image_ext, original_size)
            xref_to_locations = {}  # xref -> [(page_num, img_rect, page_rotation), ...]
            
            for page_num, page in enumerate(doc):
                # 페이지 회전값 저장
                page_rotation = page.rotation
                
                image_list = page.get_images()
                if image_list:
                    for img in image_list:
                        try:
                            xref = img[0]
                            img_name = img[7]
                            
                            # 위치 찾기 (회전값을 고려하여 정확한 좌표 사용)
                            img_rects = []
                            try:
                                # 회전값을 0으로 설정하여 물리적 좌표 얻기
                                page.set_rotation(0)
                                img_rects = page.get_image_rects(xref)
                                page.set_rotation(page_rotation)  # 원상복구
                            except:
                                try:
                                    page.set_rotation(0)
                                    img_rects = page.get_image_rects(img_name)
                                    page.set_rotation(page_rotation)  # 원상복구
                                except:
                                    page.set_rotation(page_rotation)  # 실패 시에도 원상복구
                                    pass
                            
                            if not img_rects:
                                continue
                            
                            # 이미지 데이터는 한 번만 추출 (같은 xref는 같은 이미지)
                            if xref not in xref_to_image_data:
                                base_image = doc.extract_image(xref)
                                image_bytes = base_image["image"]
                                image_ext = base_image["ext"]
                                xref_to_image_data[xref] = (image_bytes, image_ext, len(image_bytes))
                            
                            # 모든 위치 정보 저장
                            if xref not in xref_to_locations:
                                xref_to_locations[xref] = []
                            
                            # 각 위치를 모두 저장
                            for img_rect in img_rects:
                                xref_to_locations[xref].append((page_num, img_rect, page_rotation))
                            
                        except Exception:
                            continue
            
            # 압축 작업 준비
            tasks = []
            task_info = []
            for xref, (image_bytes, image_ext, original_size) in xref_to_image_data.items():
                tasks.append((image_bytes, image_ext))
                task_info.append((xref, original_size))

            print(f"[INFO] 총 {len(tasks)}개의 이미지를 압축합니다.")

            # 2. 병렬 압축 실행
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(compress_single_image, tasks))
            
            # 3. 결과 적용 (순차)
            # xref별로 압축된 이미지를 모든 위치에 재삽입
            for (xref, original_size), compressed_image_bytes in zip(task_info, results):
                if compressed_image_bytes:
                    compressed_size = len(compressed_image_bytes)
                    if compressed_size < original_size * 0.9:
                        # 이 xref가 사용되는 모든 위치에 대해 처리
                        if xref in xref_to_locations:
                            locations = xref_to_locations[xref]
                            
                            # 첫 번째 위치에서 이미지 삭제 (한 번만 삭제하면 모든 위치에서 삭제됨)
                            if locations:
                                first_page_num, _, _ = locations[0]
                                try:
                                    page = doc[first_page_num]
                                    current_rotation = page.rotation
                                    page.set_rotation(0)
                                    page.delete_image(xref)
                                    page.set_rotation(current_rotation)
                                except Exception as e:
                                    print(f"[WARNING] 이미지 삭제 실패 (Page {first_page_num + 1}, Xref {xref}): {e}")
                            
                            # 모든 위치에 압축된 이미지 재삽입
                            for page_num, img_rect, page_rotation in locations:
                                try:
                                    page = doc[page_num]
                                    
                                    # 현재 페이지 회전값 확인
                                    current_rotation = page.rotation
                                    
                                    # 회전값을 0으로 설정하여 정확한 좌표로 이미지 삽입
                                    page.set_rotation(0)
                                    
                                    # 이미지 재삽입 (img_rect는 이미 회전값 0 기준으로 저장됨)
                                    page.insert_image(img_rect, stream=compressed_image_bytes)
                                    
                                    # 원본 회전값 복구
                                    page.set_rotation(current_rotation)
                                    
                                except Exception as e:
                                    print(f"[WARNING] 이미지 재삽입 실패 (Page {page_num + 1}, Xref {xref}): {e}")
                                    import traceback
                                    traceback.print_exc()
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
                    
                    # 회전값이 없는 경우: 이미지로 렌더링하여 삽입 (주석 포함)
                    if rot == 0:
                        try:
                            # 페이지를 이미지로 렌더링 (주석 포함)
                            mat = pymupdf.Matrix(scale, scale)
                            pix = page.get_pixmap(matrix=mat, alpha=False, annots=True)
                            
                            # 이미지를 바이트로 변환
                            img_bytes = pix.tobytes("png")
                            
                            # 새 페이지에 이미지 삽입
                            new_page.insert_image(dest_rect, stream=img_bytes)
                            print(f"[INFO] Page {page.number + 1}: 회전값 없음, 이미지 렌더링으로 처리")
                        except Exception as img_error:
                            # 이미지 렌더링 실패 시 기존 방식 사용
                            print(f"[WARNING] Page {page.number + 1} 이미지 렌더링 실패, 기존 방식 사용: {img_error}")
                            new_page.show_pdf_page(dest_rect, doc, page.number, rotate=apply_rot)
                    else:
                        # 회전값이 있는 경우: 기존 방식 사용 (주석 보존 필요)
                        new_page.show_pdf_page(dest_rect, doc, page.number, rotate=apply_rot)
                        
                        # 주석 보존 (회전값이 있는 경우에만 주석을 개별적으로 복사)
                        try:
                            annotations_list = list(page.annots())  # 제너레이터를 리스트로 변환
                            if annotations_list:
                                for annot in annotations_list:
                                    try:
                                        # 원본 주석의 좌표
                                        annot_rect = annot.rect
                                        
                                        # 스케일 및 중앙 정렬에 맞춰 좌표 변환
                                        new_x0 = x + (annot_rect.x0 - src_rect.x0) * scale
                                        new_y0 = y + (annot_rect.y0 - src_rect.y0) * scale
                                        new_x1 = x + (annot_rect.x1 - src_rect.x0) * scale
                                        new_y1 = y + (annot_rect.y1 - src_rect.y0) * scale
                                        
                                        new_annot_rect = pymupdf.Rect(new_x0, new_y0, new_x1, new_y1)
                                        
                                        # 주석 타입 확인 및 복사
                                        annot_type = annot.type[0] if annot.type else -1
                                        
                                        # 1. FreeText (텍스트 박스, 타자기) - 타입 2
                                        if annot_type == 2:
                                            content = annot.info.get("content", "") if annot.info else ""
                                            if content:
                                                new_annot = new_page.add_freetext_annot(new_annot_rect, content)
                                                try:
                                                    # FreeText 주석의 배경색은 update(fill_color=...)로 설정해야 함
                                                    fill_color = annot.colors.get("fill") if annot.colors else None
                                                    if fill_color:
                                                        # fill_color는 (r, g, b) 튜플 형태 (0-1 범위)
                                                        new_annot.update(fill_color=fill_color)
                                                    
                                                    # 테두리 색상은 set_colors로 설정
                                                    stroke_color = annot.colors.get("stroke") if annot.colors else None
                                                    if stroke_color:
                                                        new_annot.set_colors(stroke=stroke_color)
                                                    
                                                    # 기타 속성 복사 (폰트 크기, 텍스트 색상 등)
                                                    if annot.info:
                                                        if "fontsize" in annot.info:
                                                            new_annot.update(fontsize=annot.info.get("fontsize"))
                                                        if "text_color" in annot.info:
                                                            new_annot.update(text_color=annot.info.get("text_color"))
                                                    
                                                    new_annot.update()
                                                except Exception as e:
                                                    # 디버깅을 위해 예외 출력 (필요시 주석 처리)
                                                    # print(f"[WARNING] FreeText 주석 속성 복사 실패: {e}")
                                                    pass
                                        
                                        # 2. Text (스티커 메모) - 타입 0
                                        elif annot_type == 0:
                                            content = annot.info.get("content", "") if annot.info else ""
                                            if content:
                                                new_annot = new_page.add_text_annot(new_annot_rect.tl, content)
                                                try:
                                                    stroke_color = annot.colors.get("stroke") if annot.colors else None
                                                    if stroke_color:
                                                        new_annot.set_colors(stroke=stroke_color)
                                                    new_annot.update()
                                                except:
                                                    pass
                                        
                                        # 3. Highlight (형광펜) - 타입 8
                                        elif annot_type == 8:
                                            new_annot = new_page.add_highlight_annot(new_annot_rect)
                                            try:
                                                stroke_color = annot.colors.get("stroke") if annot.colors else None
                                                if stroke_color:
                                                    new_annot.set_colors(stroke=stroke_color)
                                                new_annot.update()
                                            except:
                                                pass

                                        # 4. Line (선) - 타입 3
                                        elif annot_type == 3:
                                            try:
                                                # Line 주석의 vertices를 사용하여 시작점과 끝점 계산
                                                p1_new = None
                                                p2_new = None
                                                
                                                # vertices 접근 시도 (Line 주석은 vertices가 필수)
                                                try:
                                                    vertices = annot.vertices
                                                    if vertices and len(vertices) >= 2:
                                                        # Line 주석의 vertices는 보통 4개 점: [시작, 끝, 시작, 끝] 또는 2개: [시작, 끝]
                                                        # 첫 번째와 두 번째 점을 사용
                                                        p1_old = vertices[0]
                                                        p2_old = vertices[1]
                                                        
                                                        # Point 객체인 경우
                                                        if isinstance(p1_old, pymupdf.Point):
                                                            p1_new = pymupdf.Point(x + (p1_old.x - src_rect.x0) * scale, y + (p1_old.y - src_rect.y0) * scale)
                                                            p2_new = pymupdf.Point(x + (p2_old.x - src_rect.x0) * scale, y + (p2_old.y - src_rect.y0) * scale)
                                                        # 리스트/튜플 형태인 경우
                                                        elif isinstance(p1_old, (list, tuple)) and len(p1_old) >= 2:
                                                            p1_new = pymupdf.Point(x + (p1_old[0] - src_rect.x0) * scale, y + (p1_old[1] - src_rect.y0) * scale)
                                                            p2_new = pymupdf.Point(x + (p2_old[0] - src_rect.x0) * scale, y + (p2_old[1] - src_rect.y0) * scale)
                                                        # dict 형태인 경우 (x, y 키를 가진 경우)
                                                        elif isinstance(p1_old, dict):
                                                            p1_new = pymupdf.Point(x + (p1_old.get('x', p1_old.get(0, 0)) - src_rect.x0) * scale, 
                                                                                  y + (p1_old.get('y', p1_old.get(1, 0)) - src_rect.y0) * scale)
                                                            p2_new = pymupdf.Point(x + (p2_old.get('x', p2_old.get(0, 0)) - src_rect.x0) * scale,
                                                                                  y + (p2_old.get('y', p2_old.get(1, 0)) - src_rect.y0) * scale)
                                                        # 속성으로 접근하는 경우
                                                        elif hasattr(p1_old, 'x') and hasattr(p1_old, 'y'):
                                                            p1_new = pymupdf.Point(x + (p1_old.x - src_rect.x0) * scale, y + (p1_old.y - src_rect.y0) * scale)
                                                            p2_new = pymupdf.Point(x + (p2_old.x - src_rect.x0) * scale, y + (p2_old.y - src_rect.y0) * scale)
                                                except Exception as vertices_error:
                                                    # vertices 접근 실패 시 디버깅 정보 출력
                                                    print(f"[DEBUG] Line 주석 vertices 접근 실패: {vertices_error}, vertices={getattr(annot, 'vertices', 'N/A')}")
                                                
                                                # vertices로 점을 얻지 못한 경우 rect 사용 (fallback)
                                                if p1_new is None or p2_new is None:
                                                    annot_rect = annot.rect
                                                    # Line 주석의 rect는 선을 감싸는 경계 상자이므로,
                                                    # 실제 선의 방향을 추정하기 어렵습니다.
                                                    # 하지만 일반적으로 rect의 중심을 지나는 대각선을 사용
                                                    # 또는 rect의 좌하단과 우상단을 사용할 수도 있음
                                                    # 일단 원본과 유사하게 보이도록 좌하단-우상단 사용
                                                    p1_new = pymupdf.Point(x + (annot_rect.x0 - src_rect.x0) * scale, y + (annot_rect.y1 - src_rect.y0) * scale)
                                                    p2_new = pymupdf.Point(x + (annot_rect.x1 - src_rect.x0) * scale, y + (annot_rect.y0 - src_rect.y0) * scale)
                                                    print(f"[WARNING] Line 주석 vertices 없음, rect 사용: {annot_rect}")
                                                
                                                # Line 주석 생성
                                                new_annot = new_page.add_line_annot(p1_new, p2_new)
                                                
                                                # 속성 복사
                                                try:
                                                    if annot.border:
                                                        new_annot.set_border(annot.border)
                                                    if annot.colors:
                                                        stroke = annot.colors.get("stroke")
                                                        if stroke:
                                                            new_annot.set_colors(stroke=stroke)
                                                    new_annot.update()
                                                except Exception as attr_error:
                                                    # 속성 복사 실패해도 주석은 생성되었으므로 계속 진행
                                                    pass
                                            except Exception as line_error:
                                                # Line 주석 처리 실패 시 로그 출력 (디버깅용)
                                                print(f"[WARNING] Line 주석 복사 실패 (Page {page.number + 1}): {line_error}")
                                                import traceback
                                                traceback.print_exc()
                                                pass

                                        # 5. Square (4), Circle (5) - 도형
                                        elif annot_type in [4, 5]:
                                            if annot_type == 5:
                                                new_annot = new_page.add_circle_annot(new_annot_rect)
                                            else:
                                                new_annot = new_page.add_square_annot(new_annot_rect)
                                            try:
                                                if annot.border:
                                                    new_annot.set_border(annot.border)
                                                if annot.colors:
                                                    stroke = annot.colors.get("stroke")
                                                    fill = annot.colors.get("fill")
                                                    new_annot.set_colors(stroke=stroke, fill=fill)
                                                new_annot.update()
                                            except:
                                                pass

                                        # 6. Ink (펜/서명) - 타입 15
                                        elif annot_type == 15:
                                            if hasattr(annot, "vertices") and annot.vertices:
                                                old_ink = annot.vertices
                                                new_ink = []
                                                for stroke in old_ink:
                                                    new_stroke = [pymupdf.Point(x + (p.x - src_rect.x0) * scale, y + (p.y - src_rect.y0) * scale) for p in stroke]
                                                    new_ink.append(new_stroke)
                                                if new_ink:
                                                    new_annot = new_page.add_ink_annot(new_ink)
                                                    try:
                                                        if annot.border:
                                                            new_annot.set_border(annot.border)
                                                        if annot.colors:
                                                            stroke = annot.colors.get("stroke")
                                                            if stroke:
                                                                new_annot.set_colors(stroke=stroke)
                                                        new_annot.update()
                                                    except:
                                                        pass
                                        
                                    except Exception as annot_error:
                                        # 개별 주석 처리 실패 시 계속 진행
                                        continue
                                
                        except Exception as e:
                            # 주석 목록 가져오기 실패 시 무시
                            pass
                    
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
            
            # [DEBUG START] 결과 파일 1페이지 객체 분석
            print(f"\n{'='*50}")
            print(f"[DEBUG] 11_results.pdf Page 1 심층 분석 시작")
            try:
                page1 = result_doc[0]
                
                # 1. Annotation (주석/서명) 확인
                print(f"\n[1. Annotations (주석/서명)]")
                annots = list(page1.annots())
                if not annots:
                    print(" -> 발견된 Annotation 없음")
                for i, annot in enumerate(annots):
                    # annot.type: [id, name] ex) [0, 'Text'], [15, 'Ink']
                    print(f"  #{i+1} Type: {annot.type[0]} ({annot.type[1]})")
                    print(f"      Rect: {annot.rect}")
                    print(f"      Info: {annot.info}")
                    if annot.type[0] == 19: # Widget
                        print(f"      Field Value: {annot.field_value}")

                # 2. Images (이미지) 확인
                print(f"\n[2. Images (이미지)]")
                images = page1.get_images()
                if not images:
                    print(" -> 발견된 Image 없음")
                for i, img in enumerate(images):
                    xref = img[0]
                    try:
                        bbox = page1.get_image_rects(xref)
                        print(f"  #{i+1} Xref: {xref}, Loc: {bbox}")
                    except:
                        print(f"  #{i+1} Xref: {xref} (위치 확인 불가)")

                # 3. Drawings (벡터 그래픽) 확인
                print(f"\n[3. Drawings (벡터 그래픽)]")
                drawings = page1.get_drawings()
                print(f"  -> 총 {len(drawings)}개의 드로잉 패스 발견")
                for i, d in enumerate(drawings[:5]):
                    print(f"  #{i+1} Type: {d['type']}, Rect: {d['rect']}")

            except Exception as e:
                print(f"[DEBUG] 분석 중 에러 발생: {e}")
            print(f"{'='*50}\n")
            # [DEBUG END]

            for i, page in enumerate(result_doc):
                print(f"[DEBUG] 결과 Page {i+1} - Rotation: {page.rotation}, Size: (Width: {page.rect.width:.2f}, Height: {page.rect.height:.2f})")
            result_doc.close()
        except Exception as e:
            print(f"[WARNING] 결과 파일 검증 중 오류: {e}")
        
        print(f"완료: {output_pdf} 에 저장되었습니다.")
        
    except Exception as e:
        import traceback
        traceback.print_exc()


def fetch_rn_pdf_data():
    """DB에서 RN, file_path, page_number를 조회합니다."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        query = """
            SELECT r."RN", r.file_path, ar."구매계약서" 
            FROM rns r 
            INNER JOIN analysis_results ar ON r."RN" = ar."RN" 
            WHERE r.file_path IS NOT NULL AND ar."구매계약서" IS NOT NULL
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            rn, file_path, contract_json = row
            # JSONB에서 page_number 추출
            if isinstance(contract_json, str):
                import json
                try:
                    contract_json = json.loads(contract_json)
                except:
                    contract_json = {}
            
            # JSONB 객체(dict)인 경우
            page_number = contract_json.get("page_number") if isinstance(contract_json, dict) else None
            
            if page_number is not None:
                try:
                    results.append({
                        "rn": rn,
                        "file_path": file_path,
                        "page_number": int(page_number)
                    })
                except ValueError:
                    pass
        
        cursor.close()
        conn.close()
        return results
    except Exception as e:
        print(f"DB 조회 중 오류 발생: {e}")
        return []

def process_single_pdf_with_page(rn: str, file_path: str, page_number: int, output_dir: Path) -> bool:
    """단일 PDF 처리 함수: 특정 페이지에만 텍스트 삽입"""
    input_pdf = Path(file_path)
    output_pdf = output_dir / f"{rn}_result.pdf"
    
    # 윈도우 네트워크 경로 처리
    if platform.system() == "Windows" and file_path.startswith("\\\\"):
         input_pdf = Path(file_path)

    print(f"Input: {input_pdf}")

    if not input_pdf.exists():
        print(f"오류: 파일을 찾을 수 없습니다 -> {input_pdf}")
        return False

    try:
        doc = pymupdf.open(input_pdf)
        text_content = "출고예정일 12/09"
        font_size = 15

        # 파일 크기 확인 및 압축 저장
        file_size = input_pdf.stat().st_size
        limit_size = 7 * 1024 * 1024  # 7MB
        is_compressed = False

        if file_size > limit_size:
            print(f"[INFO] 입력 파일 크기: {file_size / 1024 / 1024:.2f} MB (7MB 초과)")
            print(f"[INFO] 이미지 압축을 시작합니다... (병렬 처리)")
            
            # 1. 압축 대상 이미지 정보 수집 (순차)
            xref_to_image_data = {}
            xref_to_locations = {}
            
            for page_num, page in enumerate(doc):
                page_rotation = page.rotation
                image_list = page.get_images()
                if image_list:
                    for img in image_list:
                        try:
                            xref = img[0]
                            img_name = img[7]
                            
                            img_rects = []
                            try:
                                page.set_rotation(0)
                                img_rects = page.get_image_rects(xref)
                                page.set_rotation(page_rotation)
                            except:
                                try:
                                    page.set_rotation(0)
                                    img_rects = page.get_image_rects(img_name)
                                    page.set_rotation(page_rotation)
                                except:
                                    page.set_rotation(page_rotation)
                                    pass
                            
                            if not img_rects:
                                continue
                            
                            if xref not in xref_to_image_data:
                                base_image = doc.extract_image(xref)
                                image_bytes = base_image["image"]
                                image_ext = base_image["ext"]
                                xref_to_image_data[xref] = (image_bytes, image_ext, len(image_bytes))
                            
                            if xref not in xref_to_locations:
                                xref_to_locations[xref] = []
                            
                            for img_rect in img_rects:
                                xref_to_locations[xref].append((page_num, img_rect, page_rotation))
                            
                        except Exception:
                            continue
            
            tasks = []
            task_info = []
            for xref, (image_bytes, image_ext, original_size) in xref_to_image_data.items():
                tasks.append((image_bytes, image_ext))
                task_info.append((xref, original_size))

            print(f"[INFO] 총 {len(tasks)}개의 이미지를 압축합니다.")

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(compress_single_image, tasks))
            
            for (xref, original_size), compressed_image_bytes in zip(task_info, results):
                if compressed_image_bytes:
                    compressed_size = len(compressed_image_bytes)
                    if compressed_size < original_size * 0.9:
                        if xref in xref_to_locations:
                            locations = xref_to_locations[xref]
                            if locations:
                                first_page_num, _, _ = locations[0]
                                try:
                                    page = doc[first_page_num]
                                    current_rotation = page.rotation
                                    page.set_rotation(0)
                                    page.delete_image(xref)
                                    page.set_rotation(current_rotation)
                                except Exception as e:
                                    pass
                            
                            for page_num, img_rect, page_rotation in locations:
                                try:
                                    page = doc[page_num]
                                    current_rotation = page.rotation
                                    page.set_rotation(0)
                                    page.insert_image(img_rect, stream=compressed_image_bytes)
                                    page.set_rotation(current_rotation)
                                except Exception as e:
                                    pass
            is_compressed = True
        else:
            print(f"[INFO] 입력 파일 크기: {file_size / 1024 / 1024:.2f} MB (7MB 이하) - 처리 생략")
            doc.close()
            return False
        
        # A4 리사이징 로직
        try:
            needs_resize = False
            A4_WIDTH, A4_HEIGHT = 595.276, 841.890
            TOLERANCE = 5.0

            for page in doc:
                original_rot = page.rotation
                page.set_rotation(0)
                w, h = page.rect.width, page.rect.height
                page.set_rotation(original_rot)
                
                long_side, short_side = max(w, h), min(w, h)
                if abs(long_side - A4_HEIGHT) > TOLERANCE or abs(short_side - A4_WIDTH) > TOLERANCE:
                    needs_resize = True
                    break
            
            if needs_resize:
                print("[INFO] A4 규격이 아닌 페이지가 감지되어 리사이징을 진행합니다.")
                new_doc = pymupdf.open()
                
                for page in doc:
                    rot = page.rotation
                    page.set_rotation(0)
                    src_rect = page.rect
                    tgt_width, tgt_height = A4_WIDTH, A4_HEIGHT
                    new_page = new_doc.new_page(width=tgt_width, height=tgt_height)
                    
                    if rot in [90, 270]:
                        src_w, src_h = src_rect.height, src_rect.width
                        apply_rot = 90 if rot == 270 else rot
                    else:
                        src_w, src_h = src_rect.width, src_rect.height
                        apply_rot = rot
                    
                    scale = min(tgt_width / src_w, tgt_height / src_h)
                    new_w = src_w * scale
                    new_h = src_h * scale
                    x = (tgt_width - new_w) / 2
                    y = (tgt_height - new_h) / 2
                    dest_rect = pymupdf.Rect(x, y, x + new_w, y + new_h)
                    
                    if rot == 0:
                        try:
                            mat = pymupdf.Matrix(scale, scale)
                            pix = page.get_pixmap(matrix=mat, alpha=False, annots=True)
                            img_bytes = pix.tobytes("png")
                            new_page.insert_image(dest_rect, stream=img_bytes)
                        except Exception:
                            new_page.show_pdf_page(dest_rect, doc, page.number, rotate=apply_rot)
                    else:
                        new_page.show_pdf_page(dest_rect, doc, page.number, rotate=apply_rot)
                        # 주석 복사 (간소화)
                        try:
                            for annot in page.annots():
                                # 여기에 주석 복사 로직이 들어가야 함 (extract_as_is 참조)
                                pass
                        except:
                            pass

                old_doc = doc
                doc = new_doc
                old_doc.close()
        except Exception as e:
            print(f"[WARNING] 리사이징 중 오류 발생: {e}")

        # 텍스트 삽입 (특정 페이지만)
        target_page_idx = page_number - 1
        if 0 <= target_page_idx < len(doc):
            print(f"[INFO] {page_number}페이지에 텍스트 삽입을 시작합니다...")
            page = doc[target_page_idx]
            try:
                original_rot = page.rotation
                page.set_rotation(0)
                
                text_image_bytes = create_text_image(text_content, font_size)
                
                if original_rot != 0:
                    img = Image.open(io.BytesIO(text_image_bytes))
                    rotated_img = img.rotate(original_rot, expand=True, fillcolor=(255, 255, 255, 0))
                    rotated_bytes = io.BytesIO()
                    rotated_img.save(rotated_bytes, format='PNG')
                    text_image_bytes = rotated_bytes.getvalue()
                
                text_image = pymupdf.open(stream=text_image_bytes, filetype="png")
                img_page = text_image[0]
                img_rect = img_page.rect
                img_width = img_rect.width
                img_height = img_rect.height
                text_image.close()
                
                rect = page.rect
                x = (rect.width - img_width) / 2
                y = (rect.height / 2) - (img_height / 2) + (font_size * 0.35)
                
                if original_rot == 270:
                    x = x - 60
                elif original_rot == 0:
                    y = y + 60
                
                image_rect = pymupdf.Rect(x, y, x + img_width, y + img_height)
                page.insert_image(image_rect, stream=text_image_bytes)
                page.set_rotation(original_rot)
                print(f"[INFO] Page {page_number}에 텍스트 '{text_content}' 삽입 완료")
            except Exception as e:
                print(f"[WARNING] 텍스트 삽입 실패: {e}")
        else:
            print(f"[WARNING] 요청한 페이지 {page_number}가 문서 범위를 벗어납니다 (총 {len(doc)}페이지)")

        # 저장
        if is_compressed:
            doc.save(output_pdf, deflate=True, garbage=4)
        else:
            doc.save(output_pdf)
        
        doc.close()
        print(f"완료: {output_pdf} 에 저장되었습니다.")
        return True

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False

def process_pdfs_from_database():
    """DB에서 데이터를 조회하여 일괄 처리합니다."""
    data_list = fetch_rn_pdf_data()
    print(f"[INFO] 총 {len(data_list)}개의 처리할 데이터를 찾았습니다.")
    
    base_dir = Path(__file__).parent.parent
    output_dir = base_dir / "test" / "test_results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    success_count = 0
    fail_count = 0
    
    for data in data_list:
        rn = data["rn"]
        file_path = data["file_path"]
        page_number = data["page_number"]
        
        print(f"\n[{rn}] 처리 시작 (페이지: {page_number})")
        if process_single_pdf_with_page(rn, file_path, page_number, output_dir):
            success_count += 1
        else:
            fail_count += 1
            
    print(f"\n{'='*50}")
    print(f"[RESULT] 총 {len(data_list)}건 중 성공: {success_count}, 실패: {fail_count}")
    print(f"결과 폴더: {output_dir}")

if __name__ == "__main__":
    # extract_as_is()
    process_pdfs_from_database()

