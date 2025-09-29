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
        window.show()
        
        # 애플리케이션 실행
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"애플리케이션 실행 중 오류 발생: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
