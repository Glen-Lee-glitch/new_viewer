import unittest
import subprocess
import time
import os
import sys
from pywinauto.application import Application

class PDFViewerHardTest(unittest.TestCase):
    def setUp(self):
        """테스트 시작 전 애플리케이션 실행"""
        self.app_process = subprocess.Popen([sys.executable, '../main.py'])
        time.sleep(5) # 앱이 시작될 시간을 충분히 줍니다.
        try:
            # 먼저 프로세스에 연결만 합니다.
            self.app = Application(backend="win32").connect(process=self.app_process.pid, timeout=30)

            # 앱이 가진 최상위 윈도우들을 모두 찾습니다.
            top_windows = self.app.windows()
            print("찾은 최상위 윈도우:", top_windows)

            # 각 윈도우의 모든 식별자 정보를 출력합니다.
            if not top_windows:
                print("!! 앱의 윈도우를 찾지 못했습니다. 앱이 정상적으로 실행되었는지 확인해주세요.")
            
            for window in top_windows:
                print(f"--- 윈도우 '{window.window_text()}'의 식별자 정보 ---")
                window.print_control_identifiers(depth=1)
                print("------------------------------------------")

            # 디버그 정보 출력 후 테스트를 의도적으로 중단시킵니다.
            self.fail("디버그 정보가 출력되었습니다. 터미널의 내용을 확인해주세요.")

        except Exception as e:
            print(f"setUp 도중 오류 발생: {e}")
            self.tearDown()
            raise e

    def tearDown(self):
        """테스트 종료 후 애플리케이션 종료"""
        if hasattr(self, 'app_process') and self.app_process.poll() is None:
            self.app_process.terminate()
            self.app_process.wait()

    def test_application_startup_and_shutdown(self):
        """애플리케이션이 정상적으로 시작되고 종료되는지 테스트"""
        self.assertTrue(self.main_window.exists(), "메인 윈도우가 존재하지 않습니다.")
        print("애플리케이션이 성공적으로 시작되었습니다.")
        
        # 창 닫기 버튼 클릭 (타이틀 바의 닫기 버튼)
        self.main_window.close()
        print("애플리케이션이 성공적으로 종료되었습니다.")
        time.sleep(2)
        
        # 프로세스가 종료되었는지 확인
        self.assertIsNotNone(self.app_process.poll(), "애플리케이션 프로세스가 종료되지 않았습니다.")

    def test_open_pdf_and_navigate_pages(self):
        """PDF 파일을 열고 페이지를 넘기는 기능 테스트"""
        # "로컬에서 PDF 열기" 버튼 클릭
        open_button = self.main_window.child_window(title="로컬에서 PDF 열기", control_type="Button")
        self.assertTrue(open_button.exists(), "'로컬에서 PDF 열기' 버튼을 찾을 수 없습니다.")
        open_button.click()
        time.sleep(1)

        # 파일 열기 대화상자 처리
        file_dialog = self.app.window(title="파일 선택")
        self.assertTrue(file_dialog.exists(), "파일 열기 대화상자가 나타나지 않았습니다.")
        
        pdf_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '800.pdf'))
        
        # 파일 이름 입력 필드에 경로 입력
        file_dialog.child_window(class_name="Edit").set_edit_text(pdf_path)
        time.sleep(1)
        
        # 열기 버튼 클릭
        file_dialog.child_window(title="열기(O)", auto_id="1", control_type="Button").click()
        time.sleep(3) # PDF 로딩 대기

        # 페이지 네비게이션 확인
        page_label = self.main_window.child_window(control_type="Text", title_re=".* / .*")
        self.assertTrue(page_label.exists(), "페이지 번호 라벨을 찾을 수 없습니다.")
        self.assertIn("1 /", page_label.window_text(), "초기 페이지가 1이 아닙니다.")
        
        # "다음" 버튼 클릭
        next_button = self.main_window.child_window(title="다음", control_type="Button")
        self.assertTrue(next_button.exists(), "'다음' 버튼을 찾을 수 없습니다.")
        next_button.click()
        time.sleep(1)
        
        # 페이지 번호 변경 확인
        self.assertIn("2 /", page_label.window_text(), "페이지가 다음으로 넘어가지 않았습니다.")
        print("PDF 열기 및 페이지 넘김 테스트 성공")

    def test_add_stamp_and_save(self):
        """도장을 추가하고 PDF를 저장하는 기능 테스트"""
        # PDF 파일 열기 (위의 테스트와 중복되지만, 독립적인 테스트를 위해 재현)
        open_button = self.main_window.child_window(title="로컬에서 PDF 열기", control_type="Button")
        open_button.click()
        time.sleep(1)
        
        file_dialog = self.app.window(title="파일 선택")
        pdf_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '800.pdf'))
        file_dialog.child_window(class_name="Edit").set_edit_text(pdf_path)
        file_dialog.child_window(title="열기(O)", auto_id="1", control_type="Button").click()
        time.sleep(3)

        # Floating Toolbar의 도장 버튼 클릭
        # objectName으로 버튼을 식별합니다. ui 파일을 확인해야 할 수 있습니다.
        stamp_button = self.main_window.child_window(object_name="pushButton_stamp", control_type="Button")
        self.assertTrue(stamp_button.exists(), "도장 버튼을 찾을 수 없습니다.")
        stamp_button.click()
        time.sleep(1)

        # 도장 오버레이 위젯이 나타났는지 확인
        stamp_overlay = self.main_window.child_window(object_name="stamp_overlay")
        self.assertTrue(stamp_overlay.exists(), "도장 오버레이가 나타나지 않았습니다.")

        # 첫 번째 도장 이미지를 클릭
        # 도장 이미지는 QListWidget의 아이템일 가능성이 높습니다.
        stamp_list = stamp_overlay.child_window(control_type="List")
        self.assertTrue(stamp_list.exists(), "도장 목록을 찾을 수 없습니다.")
        first_stamp = stamp_list.children(control_type="ListItem")[0]
        first_stamp.click()
        time.sleep(1)

        # PDF 뷰 영역(QGraphicsView)을 클릭하여 도장 찍기
        pdf_view = self.main_window.child_window(object_name="zoomable_graphics_view")
        self.assertTrue(pdf_view.exists(), "PDF 뷰를 찾을 수 없습니다.")
        
        view_rect = pdf_view.rectangle()
        click_x = view_rect.left + view_rect.width() // 2
        click_y = view_rect.top + view_rect.height() // 2
        pdf_view.click_input(coords=(click_x, click_y))
        time.sleep(1)

        # 저장 버튼 클릭 (objectName: pushButton_5)
        save_button = self.main_window.child_window(object_name="pushButton_5", control_type="Button")
        self.assertTrue(save_button.exists(), "저장 버튼을 찾을 수 없습니다.")
        save_button.click()

        # 파일 저장 대화상자 처리
        save_dialog = self.app.window(title_re="파일 저장.*")
        self.assertTrue(save_dialog.exists(), "파일 저장 대화상자가 나타나지 않았습니다.")
        
        output_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'hard_test_output.pdf'))
        if os.path.exists(output_path):
            os.remove(output_path)
            
        save_dialog.child_window(class_name="Edit").set_edit_text(output_path)
        time.sleep(1)
        save_dialog.child_window(title="저장(S)", auto_id="1", control_type="Button").click()

        # 저장 완료 메시지 확인 (실제 앱의 동작에 따라 달라짐)
        time.sleep(5) # 압축 저장에 시간이 걸릴 수 있으므로 충분히 대기
        
        # 저장이 완료되면 초기 로드 화면으로 돌아가는지 확인
        self.assertTrue(open_button.exists(timeout=10), "저장 후 초기 화면으로 돌아가지 않았습니다.")
        
        # 저장된 파일이 실제로 생성되었는지 확인
        self.assertTrue(os.path.exists(output_path), "저장된 PDF 파일이 생성되지 않았습니다.")
        print("도장 추가 및 저장 테스트 성공")


if __name__ == '__main__':
    unittest.main()
