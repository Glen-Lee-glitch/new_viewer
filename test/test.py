import os
import sys
import logging
import time
import random
from pathlib import Path

# 프로젝트 루트 경로를 sys.path에 추가하여 모듈을 임포트할 수 있도록 함
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from core.pdf_render import PdfRender
from core.pdf_saved import compress_pdf_with_multiple_stages
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def batch_process_pdfs(input_dir: str, output_dir: str):
    """
    지정된 디렉토리의 모든 PDF 파일을 열고 다른 디렉토리에 저장한다.

    Args:
        input_dir (str): PDF 파일이 있는 입력 디렉토리 경로.
        output_dir (str): 처리된 PDF 파일을 저장할 출력 디렉토리 경로.
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    if not input_path.is_dir():
        logging.error(f"입력 디렉토리를 찾을 수 없습니다: {input_dir}")
        return

    if not output_path.exists():
        logging.info(f"출력 디렉토리를 생성합니다: {output_dir}")
        output_path.mkdir(parents=True)

    # 파일명을 기준으로 순서를 보장
    pdf_files = sorted(list(input_path.glob("*.pdf")))
    if not pdf_files:
        logging.warning(f"입력 디렉토리에 PDF 파일이 없습니다: {input_dir}")
        return

    logging.info(f"총 {len(pdf_files)}개의 PDF 파일을 처리합니다.")

    for pdf_file in pdf_files:
        process_single_pdf(pdf_file, output_path)

def process_single_pdf(pdf_file: Path, output_dir: Path):
    """
    단일 PDF 파일을 열고 저장하는 과정을 처리하며 오류를 기록한다.
    """
    logging.info(f"--- 처리 시작: {pdf_file.name} ---")
    output_file = output_dir / f"{pdf_file.stem}_processed.pdf"
    renderer = None

    try:
        # 0. Qt 애플리케이션 컨텍스트 보장 (QPixmap 사용 위해 필요)
        if QApplication.instance() is None:
            _ = QApplication(sys.argv)

        # 1) 테스트PDF 열기 -> 2초 대기
        logging.info(f"파일 여는 중: {pdf_file}")
        renderer = PdfRender()
        # PdfRender.load_pdf는 경로 리스트를 받음
        renderer.load_pdf([str(pdf_file)])
        total_pages = renderer.get_page_count()
        logging.info(f"성공적으로 파일을 열었습니다. 총 페이지 수: {total_pages}")
        time.sleep(2)

        # 2) 10% 확률로 첫 페이지 90도 회전 -> 2초 대기
        rotations: dict[int, int] = {}
        if random.random() < 0.10:
            rotations[0] = 90
            logging.info("무작위 회전 적용: 첫 페이지 90도 회전")
        else:
            logging.info("회전 미적용 (90%) 경로")
        time.sleep(2)

        # 3) 50% 확률로 포커스를 2페이지로 이동(없으면 1페이지 유지) -> 1초 대기
        target_page = 0
        if total_pages >= 2 and random.random() < 0.50:
            target_page = 1
            logging.info("포커스 페이지: 2페이지로 이동")
        else:
            logging.info("포커스 페이지: 1페이지 유지")
        time.sleep(1)

        # 4) 도장 활성화 -> 1초 대기
        stamp_path = Path(__file__).resolve().parent.parent / "assets" / "도장1.png"
        stamp_pixmap = QPixmap(str(stamp_path))
        if stamp_pixmap.isNull():
            logging.warning(f"도장 이미지를 로드할 수 없습니다: {stamp_path}")
        else:
            logging.info(f"도장 활성화: {stamp_path.name}")
        time.sleep(1)

        # 5) 현재 페이지 랜덤 위치에 삽입 -> 1초 대기
        stamp_data: dict[int, list[dict]] = {}
        if not stamp_pixmap.isNull():
            # 스탬프 크기 비율: 너비 18% 고정, 높이는 원본 비율 유지
            w_ratio = 0.18
            aspect = stamp_pixmap.height() / max(1, stamp_pixmap.width())
            h_ratio = w_ratio * aspect
            # 페이지 안쪽에 배치되도록 여백 고려
            max_x = max(0.0, 1.0 - w_ratio - 0.02)
            max_y = max(0.0, 1.0 - h_ratio - 0.02)
            x_ratio = random.uniform(0.02, max_x if max_x > 0.02 else 0.02)
            y_ratio = random.uniform(0.02, max_y if max_y > 0.02 else 0.02)
            stamp_entry = {
                'pixmap': stamp_pixmap,
                'x_ratio': x_ratio,
                'y_ratio': y_ratio,
                'w_ratio': w_ratio,
                'h_ratio': h_ratio,
            }
            stamp_data[target_page] = [stamp_entry]
            logging.info(f"도장 삽입: page={target_page+1}, x={x_ratio:.2f}, y={y_ratio:.2f}, w={w_ratio:.2f}, h={h_ratio:.2f}")
        else:
            logging.info("도장 삽입 스킵: 스탬프 이미지를 찾지 못함")
        time.sleep(1)

        # 6) 파일 저장(결과 폴더에)
        logging.info(f"파일 저장 중: {output_file}")
        input_bytes = renderer.get_pdf_bytes()
        success = compress_pdf_with_multiple_stages(
            input_bytes=input_bytes,
            output_path=str(output_file),
            target_size_mb=3,
            rotations=rotations,
            force_resize_pages=set(),
            stamp_data=stamp_data,
        )

        if success:
            logging.info(f"성공적으로 파일을 저장했습니다: {output_file}")
        else:
            logging.warning(f"압축 저장에 실패하여 원본 파일을 복사했습니다: {output_file}")

    except Exception as e:
        logging.error(f"'{pdf_file.name}' 처리 중 오류 발생: {e}", exc_info=True)
    
    finally:
        if renderer:
            renderer.close()
        logging.info(f"--- 처리 완료: {pdf_file.name} ---\n")


if __name__ == '__main__':
    # 테스트를 위한 입력 및 출력 디렉토리 설정
    # 아래 경로를 실제 환경에 맞게 수정하세요.
    
    # os.path.expanduser('~')는 현재 사용자의 홈 디렉토리 경로를 반환합니다.
    # 예: 'C:/Users/Username' 또는 '/home/username'
    home_dir = os.path.expanduser('~')
    
    # 바탕화면에 'pdf_test_input'와 'pdf_test_output' 폴더를 사용한다고 가정
    test_input_directory = os.path.join(home_dir, 'Desktop', 'pdf_test_input')
    test_output_directory = os.path.join(home_dir, 'Desktop', 'pdf_test_output')
    
    # 입력 폴더가 없다면 생성하고 메시지를 출력
    if not os.path.exists(test_input_directory):
        os.makedirs(test_input_directory)
        print(f"'{test_input_directory}' 폴더를 생성했습니다. 이 곳에 테스트할 PDF 파일들을 넣어주세요.")
        
    # 출력 폴더가 없다면 생성
    if not os.path.exists(test_output_directory):
        os.makedirs(test_output_directory)

    # Qt 애플리케이션 컨텍스트 생성(없으면)
    if QApplication.instance() is None:
        _ = QApplication(sys.argv)

    # 실제 일괄 처리 함수 호출
    # 위에서 생성한 입력 폴더에 PDF를 넣은 후 이 스크립트를 실행하세요.
    if os.path.exists(test_input_directory) and any(f.endswith('.pdf') for f in os.listdir(test_input_directory)):
        batch_process_pdfs(test_input_directory, test_output_directory)
    elif os.path.exists(test_input_directory):
        print(f"'{test_input_directory}'에 테스트할 PDF 파일이 없습니다. PDF 파일을 넣고 다시 실행해주세요.")
