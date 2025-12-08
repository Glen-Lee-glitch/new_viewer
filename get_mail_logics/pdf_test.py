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

            # 텍스트를 이미지로 변환 (한글 지원)
            text_image_bytes = create_text_image(text_content, font_size)
            
            # 이미지 크기 계산
            text_image = pymupdf.open(stream=text_image_bytes, filetype="png")
            img_page = text_image[0]
            img_rect = img_page.rect
            img_width = img_rect.width
            img_height = img_rect.height
            text_image.close()
            
            # 페이지 중앙 좌표 계산 (회전이 0인 상태이므로 단순 계산 가능)
            rect = page.rect
            x = (rect.width - img_width) / 2
            y = (rect.height / 2) - (img_height / 2) + (font_size * 0.35)
            
            # 회전값에 따른 좌표 조정
            if original_rot == 270:
                x = x - 60  # 270도 회전 페이지: x 좌표 -60 (시각적으로 왼쪽으로 이동)
            elif original_rot == 0:
                y = y + 60  # 0도 회전 페이지: y 좌표 +60 (시각적으로 아래로 이동)

            # 3. 이미지를 PDF 페이지에 삽입 (회전 상쇄 적용)
            # 페이지가 회전되어 있어도 텍스트가 올곧게 보이도록 이미지를 역회전
            # if original_rot != 0:
            #     # PIL로 이미지를 회전시켜서 페이지 회전을 상쇄
            #     img = Image.open(io.BytesIO(text_image_bytes))
            #     # 페이지가 270도(반시계) 회전되어 있다면, 텍스트도 270도(반시계) 회전되어 있어야
            #     # 뷰어가 시계방향으로 270도 돌렸을 때 똑바로 보임
            #     # PIL rotate는 반시계 방향이므로 original_rot 그대로 사용
            #     rotated_img = img.rotate(original_rot, expand=True, fillcolor=(255, 255, 255, 0))
            #     
            #     # 회전된 이미지 크기 재계산
            #     rotated_bytes = io.BytesIO()
            #     rotated_img.save(rotated_bytes, format='PNG')
            #     rotated_image_bytes = rotated_bytes.getvalue()
            #     
            #     # 회전된 이미지 크기 계산
            #     rotated_image = pymupdf.open(stream=rotated_image_bytes, filetype="png")
            #     rotated_img_page = rotated_image[0]
            #     rotated_img_rect = rotated_img_page.rect
            #     rotated_img_width = rotated_img_rect.width
            #     rotated_img_height = rotated_img_rect.height
            #     rotated_image.close()
            #     
            #     # 회전된 이미지 크기에 맞춰 좌표 재조정
            #     x_rotated = (rect.width - rotated_img_width) / 2
            #     y_rotated = (rect.height / 2) - (rotated_img_height / 2) + (font_size * 0.35)
            #     
            #     # 회전값에 따른 좌표 조정
            #     if original_rot == 270:
            #         x_rotated = x_rotated - 60
            #     elif original_rot == 0:
            #         y_rotated = y_rotated + 60
            #     
            #     # 회전된 이미지 삽입
            #     image_rect = pymupdf.Rect(x_rotated, y_rotated, x_rotated + rotated_img_width, y_rotated + rotated_img_height)
            #     page.insert_image(image_rect, stream=rotated_image_bytes)
            # else:
            #     # 회전이 없는 경우 그냥 삽입
            #     image_rect = pymupdf.Rect(x, y, x + img_width, y + img_height)
            #     page.insert_image(image_rect, stream=text_image_bytes)

            # 4. 페이지 회전값 원상복구
            page.set_rotation(original_rot)

        # 파일 크기 확인 및 압축 저장
        file_size = input_pdf.stat().st_size
        limit_size = 7 * 1024 * 1024  # 7MB

        if file_size > limit_size:
            print(f"[INFO] 파일 크기가 7MB를 초과합니다 ({file_size / 1024 / 1024:.2f} MB). 압축 저장을 시도합니다.")
            # deflate=True: 스트림 압축, garbage=4: 중복 객체 제거 및 정리
            # 너무 강하게 압축하지 않기 위해 이미지 다운샘플링 등은 하지 않음
            doc.save(output_pdf, deflate=True, garbage=4)
        else:
            print(f"[INFO] 파일 크기가 7MB 이하입니다 ({file_size / 1024 / 1024:.2f} MB). 일반 저장합니다.")
            doc.save(output_pdf)
            
        doc.close()
        
        print(f"완료: {output_pdf} 에 저장되었습니다.")
        
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    extract_as_is()
