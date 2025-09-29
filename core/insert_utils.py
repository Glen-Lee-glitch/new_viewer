from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QGraphicsPixmapItem


def add_stamp_item(
    stamp_pixmap: QPixmap,
    page_item: QGraphicsPixmapItem,
    position: QPointF,
    desired_width: int = 110,  # 원하는 너비(px)를 인자로 추가
) -> QGraphicsPixmapItem:
    """
    페이지 아이템에 스탬프(QGraphicsPixmapItem)를 추가하고 위치를 조정한다.

    Args:
        stamp_pixmap (QPixmap): 삽입할 스탬프의 QPixmap 객체.
        page_item (QGraphicsPixmapItem): 스탬프를 추가할 부모 페이지 아이템.
        position (QPointF): 스탬프를 추가할 위치 (페이지 아이템 내부 좌표).
        desired_width (int): 스탬프의 목표 너비 (px). 기본값 150.

    Returns:
        QGraphicsPixmapItem: 생성되고 위치가 조정된 스탬프 아이템.
    """
    # 원본 QPixmap을 원하는 너비로 스케일 조정
    scaled_pixmap = stamp_pixmap.scaledToWidth(
        desired_width, Qt.TransformationMode.SmoothTransformation
    )

    # 페이지 아이템의 좌표계를 기준으로 스탬프 QGraphicsPixmapItem 생성
    stamp_item = QGraphicsPixmapItem(scaled_pixmap, page_item)

    # 1. 마우스가 찍히는 지점이 '도장'의 중앙이 위치되도록 삽입.
    stamp_center_x = scaled_pixmap.width() / 2
    stamp_center_y = scaled_pixmap.height() / 2
    stamp_item.setPos(position.x() - stamp_center_x, position.y() - stamp_center_y)

    # 2. 현재 로드된 페이지에서 벗어나는 부분이 있을 경우에만 그 안쪽에 전부 보이도록 자동 배치
    page_rect = page_item.boundingRect()
    stamp_rect_in_parent = stamp_item.boundingRect().translated(stamp_item.pos())

    dx = 0
    dy = 0

    if stamp_rect_in_parent.left() < page_rect.left():
        dx = page_rect.left() - stamp_rect_in_parent.left()
    elif stamp_rect_in_parent.right() > page_rect.right():
        dx = page_rect.right() - stamp_rect_in_parent.right()

    if stamp_rect_in_parent.top() < page_rect.top():
        dy = page_rect.top() - stamp_rect_in_parent.top()
    elif stamp_rect_in_parent.bottom() > page_rect.bottom():
        dy = page_rect.bottom() - stamp_rect_in_parent.bottom()

    if dx != 0 or dy != 0:
        stamp_item.moveBy(dx, dy)

    return stamp_item