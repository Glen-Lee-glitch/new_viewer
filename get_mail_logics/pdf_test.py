import pymupdf
from pathlib import Path

def test_page1_images():
    """11.pdf의 1페이지 이미지 분석"""
    base_dir = Path(__file__).parent.parent
    test_dir = base_dir / "test"
    
    input_pdf = test_dir / "11.pdf"
    
    if not input_pdf.exists():
        print(f"오류: 파일을 찾을 수 없습니다 -> {input_pdf}")
        return
    
    try:
        doc = pymupdf.open(input_pdf)
        page1 = doc[0]
        
        print(f"\n{'='*60}")
        print(f"[TEST] 11.pdf Page 1 이미지 상세 분석")
        print(f"{'='*60}\n")
        
        # 페이지 기본 정보
        print(f"[페이지 정보]")
        print(f"  Rotation: {page1.rotation}°")
        print(f"  Size: {page1.rect.width:.2f} x {page1.rect.height:.2f} pt")
        print(f"  Size: {page1.rect.width * 0.0352778:.2f} x {page1.rect.height * 0.0352778:.2f} cm")
        print()
        
        # 이미지 정보 수집
        images = page1.get_images()
        print(f"[이미지 목록]")
        print(f"  총 {len(images)}개의 이미지 발견\n")
        
        for i, img_info in enumerate(images):
            xref = img_info[0]
            print(f"  [이미지 #{i+1}]")
            print(f"    Xref: {xref}")
            
            # 이미지 위치 정보
            try:
                img_rects = page1.get_image_rects(xref)
                if img_rects:
                    for j, rect in enumerate(img_rects):
                        print(f"    위치 #{j+1}:")
                        print(f"      Rect: {rect}")
                        print(f"      크기: {rect.width:.2f} x {rect.height:.2f} pt")
                        print(f"      크기: {rect.width * 0.0352778:.2f} x {rect.height * 0.0352778:.2f} cm")
                        print(f"      좌표: ({rect.x0:.2f}, {rect.y0:.2f}) ~ ({rect.x1:.2f}, {rect.y1:.2f})")
                else:
                    print(f"    위치: 확인 불가")
            except Exception as e:
                print(f"    위치 확인 실패: {e}")
            
            # 이미지 데이터 정보
            try:
                base_image = doc.extract_image(xref)
                print(f"    확장자: {base_image['ext']}")
                print(f"    크기: {len(base_image['image'])} bytes")
                print(f"    색상 공간: {base_image.get('colorspace', 'N/A')}")
                print(f"    너비: {base_image.get('width', 'N/A')} px")
                print(f"    높이: {base_image.get('height', 'N/A')} px")
            except Exception as e:
                print(f"    이미지 데이터 추출 실패: {e}")
            
            print()
        
        # 이미지 배치 분석
        print(f"[이미지 배치 분석]")
        if len(images) >= 2:
            try:
                rects1 = page1.get_image_rects(images[0][0])
                rects2 = page1.get_image_rects(images[1][0])
                
                if rects1 and rects2:
                    rect1 = rects1[0]
                    rect2 = rects2[0]
                    
                    print(f"  이미지 1: {rect1.width * 0.0352778:.2f} x {rect1.height * 0.0352778:.2f} cm")
                    print(f"  이미지 2: {rect2.width * 0.0352778:.2f} x {rect2.height * 0.0352778:.2f} cm")
                    print(f"  이미지 1 위치: x={rect1.x0 * 0.0352778:.2f}cm, y={rect1.y0 * 0.0352778:.2f}cm")
                    print(f"  이미지 2 위치: x={rect2.x0 * 0.0352778:.2f}cm, y={rect2.y0 * 0.0352778:.2f}cm")
                    
                    # 두 이미지가 붙어있는지 확인
                    if abs(rect1.x1 - rect2.x0) < 1.0 or abs(rect2.x1 - rect1.x0) < 1.0:
                        print(f"  → 두 이미지가 가로로 붙어있음 (간격: {abs(rect1.x1 - rect2.x0) * 0.0352778:.2f}cm)")
                    elif abs(rect1.y1 - rect2.y0) < 1.0 or abs(rect2.y1 - rect1.y0) < 1.0:
                        print(f"  → 두 이미지가 세로로 붙어있음 (간격: {abs(rect1.y1 - rect2.y0) * 0.0352778:.2f}cm)")
            except Exception as e:
                print(f"  배치 분석 실패: {e}")
        
        print(f"\n{'='*60}\n")
        
        doc.close()
        
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_page1_images()

