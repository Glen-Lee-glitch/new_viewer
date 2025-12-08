import pymupdf
from pathlib import Path

def extract_as_is():
    # 경로 설정 (pdf_rotation.py 참조)
    base_dir = Path(__file__).parent.parent
    test_dir = base_dir / "test"
    
    input_pdf = test_dir / "11.pdf"
    output_pdf = test_dir / "11_results.pdf"

    print(f"Input: {input_pdf}")

    if not input_pdf.exists():
        print(f"오류: 파일을 찾을 수 없습니다 -> {input_pdf}")
        return

    try:
        # PyMuPDF로 파일 열기
        doc = pymupdf.open(input_pdf)
        
        # 아무런 변형 없이 그대로 저장
        doc.save(output_pdf)
        doc.close()
        
        print(f"완료: {output_pdf} 에 저장되었습니다.")
        
    except Exception as e:
        print(f"처리 중 오류 발생: {e}")

if __name__ == "__main__":
    extract_as_is()
