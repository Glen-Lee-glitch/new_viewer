"""
PDF 주석(annotations) 중 전처리(show_pdf_page 기반)에서 누락되는 유형이 있는지 검사하는 유틸리티.

True  => 해당 PDF에 Stamp / Ink / FreeText 등 '전처리에서 사라질 가능성이 높은' 주석이 존재
False => 그런 주석이 없음 (현재 로직 기준, 전처리 시 손실 가능성 낮음)

사용 예시:
  python -m get_mail_logics.pdf_annotation_guard path/to/file_or_dir

출력:
  <파일경로> -> True|False  (True 면 위험 PDF)
"""

from __future__ import annotations

import os
import sys
from typing import Iterable, Tuple

try:
    import fitz  # PyMuPDF
except Exception as exc:  # pragma: no cover
    raise RuntimeError("PyMuPDF(fitz)가 필요합니다. requirements.txt에 맞춰 설치하세요.") from exc


# 전처리에서 show_pdf_page로는 복사되지 않는 대표적인 주석 유형들
ANNOT_TYPES_DROPPED = {
    "Stamp",      # 모바일/태블릿 도장, 이미지 스탬프
    "Ink",        # 자유곡선(디지털 펜)
    "FreeText",   # 자유 텍스트(주로 폼 바깥 배치)
    "Square",
    "Circle",
    "Polygon",
    "PolyLine",
    "Line",
    "Highlight",
    "Underline",
    "Squiggly",
    "StrikeOut",
    "Caret",
    "FileAttachment",
    "Sound",
    "Movie",
    # Link, Widget 등은 일반적으로 의미가 다르므로 제외
}


def _iter_pdf_files(path: str) -> Iterable[str]:
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for name in files:
                if name.lower().endswith(".pdf"):
                    yield os.path.join(root, name)
    else:
        yield path


def _page_has_dropped_annots(page: "fitz.Page") -> Tuple[bool, list]:
    has = False
    types: list[str] = []
    annot = page.first_annot
    while annot:
        try:
            t = annot.type[1]
        except Exception:
            t = "Unknown"
        if t in ANNOT_TYPES_DROPPED:
            has = True
            types.append(t)
        annot = annot.next
    return has, types


def pdf_will_lose_objects(pdf_path: str) -> bool:
    """현재 thread.py 전처리(show_pdf_page) 기준으로 손실될 수 있는 주석이 포함되어 있는지 판단.

    True  => 손실 가능 주석 존재 (전처리 시 시각 요소 소실 가능)
    False => 그런 주석이 없음
    """
    with fitz.open(pdf_path) as doc:
        for page in doc:
            has, _ = _page_has_dropped_annots(page)
            if has:
                return True
    return False


def main(argv: list[str]) -> int:
    if not argv:
        print("Usage: python -m get_mail_logics.pdf_annotation_guard <PDF or DIR> [more paths...]")
        return 2

    any_error = False
    for target in argv:
        try:
            for pdf in _iter_pdf_files(target):
                result = pdf_will_lose_objects(pdf)
                print(f"{pdf} -> {result}")
        except Exception as e:  # pragma: no cover
            any_error = True
            print(f"ERROR {target}: {e}")

    return 1 if any_error else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


