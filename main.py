#!/usr/bin/env python3
"""
PDF Viewer 메인 애플리케이션
"""
import sys
from widgets.main_window import create_app

def main():
    """메인 함수"""
    try:
        app, window = create_app()
        
        # 화면의 사용 가능한 영역(작업 표시줄 제외) 크기 얻기
        screen = app.primaryScreen()
        available_geometry = screen.availableGeometry()
        
        # 너비는 고정, 높이는 화면에 꽉 차게 설정
        window.setGeometry(
            (available_geometry.width() - 1200) // 2, # x-pos
            available_geometry.top(),                  # y-pos
            1200,                                      # width
            available_geometry.height()                # height
        )
        
        window.show()
        
        # 애플리케이션 실행
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"애플리케이션 실행 중 오류 발생: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
