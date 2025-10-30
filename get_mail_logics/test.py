import re
subject = "[] 보조금신청 RN126010745 / X / 한국환경공단 / 김형준 / "
rn_match = re.search(r'RN\d{9}', subject)
print(rn_match)  # None이 나오면 정규식 문제