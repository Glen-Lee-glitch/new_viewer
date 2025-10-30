import re
import json


def extract_date(text: str) -> str | None:
    """텍스트에서 날짜를 YYYY-MM-DD 형식으로 추출"""
    if text is None:
        return None

    patterns = [
        r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일',
        r'(\d{4})/(\d{1,2})/(\d{1,2})',
        r'(\d{4})-(\d{1,2})-(\d{1,2})',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            year, month, day = match.groups()
            return f"{year}-{str(month).zfill(2)}-{str(day).zfill(2)}"

    return None


def parse_response_contract(text: str):
    """AI 응답에서 JSON을 파싱하여 날짜, 차량구성, 고객명, RN번호, 휴대폰번호, 이메일, 페이지번호 정보 추출"""
    if text is None:
        return None, None, None, None, None, None, None

    try:
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            data = json.loads(json_str)
            return (
                data.get('order_date'),
                data.get('vehicle_config'),
                data.get('customer_name'),
                data.get('rn'),
                data.get('phone_number'),
                data.get('email'),
                data.get('page_number'),
            )
    except Exception:
        pass

    date = extract_date(text)
    return date, None, None, None, None, None, None


def parse_response_resident_cert(text: str) -> dict | None:
    """AI 응답에서 JSON을 파싱하여 주민등록초본 정보 추출"""
    if text is None:
        return None

    try:
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            data = json.loads(json_str)

            if data.get('name'):
                data['name'] = (
                    data['name']
                    .replace(' ', '')
                    .replace('\n', '')
                    .replace('\r', '')
                    .replace('\t', '')
                )

            if data.get('address_1'):
                address = data['address_1']
                if '강원도' in address:
                    address = address.replace('강원도', '강원특별자치도')
                if '전라북도' in address:
                    address = address.replace('전라북도', '전북특별자치도')
                data['address_1'] = address

            if data.get('address_2'):
                address = data['address_2']
                if '강원도' in address:
                    address = address.replace('강원도', '강원특별자치도')
                if '전라북도' in address:
                    address = address.replace('전라북도', '전북특별자치도')
                data['address_2'] = address

            if data.get('issue_date'):
                issue_date = data['issue_date']
                date_match = re.search(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', issue_date)
                if date_match:
                    year = date_match.group(1)
                    month = str(date_match.group(2)).zfill(2)
                    day = str(date_match.group(3)).zfill(2)
                    data['issue_date'] = f"{year}-{month}-{day}"

            return data
    except Exception:
        pass

    return None


prompt_contract = """자동차 구매 계약 서류에서 다음 정보를 찾아서 JSON 형식으로 답변해주세요:

1. '온라인 주문 완료일' 날짜 (YYYY-MM-DD 형식)
2. '차량구성' 또는 '차량 구성내역' 섹션에서 첫 번째 행의 구성내역
3. '고객정보' 섹션에서 '고객 이름' - 영문 혹은 한글로 적힌 이름
4. '예약 번호'에 적힌 'RN123456789' 형식의 번호
5. '고객정보' 섹션에서 휴대폰 번호와 이메일 주소
6. 마지막으로 이 정보가 담긴 페이지 번호를 page_number 필드에 저장

답변 형식:
{
  "order_date": "2025-10-06",
  "vehicle_config": "Model Y 후륜구동",
  "customer_name": "John Doe",
  "rn": "RN123456789",
  "phone_number": "010-1234-5678",
  "email": "john.doe@naver.com",
  "page_number": 3
}

온라인 주문 완료일 예시:
- 2025/10/06 → 2025-10-06

판단해야하는 서류는 "자동차 구매 계약"과 "차량 구성"이라는 글자가 포함되어 있습니다.

차량구성은 정확히 첫 번째 행에 적힌 내용만 추출해주세요.

이메일 주소 및 휴대폰 번호 추출 시 주의사항:
- 대부분의 이메일이 다음 도메인을 사용합니다: naver.com, gmail.com, hanmail.net, nate.com, daum.net
- 이메일 주소는 정확히 @ 기호 앞뒤로 구성되어야 합니다
- 이메일 형식이 명확하지 않으면 null로 설정해주세요
- 휴대폰 번호는 010-XXXX-XXXX 형식으로 추출해주세요

"""


prompt_resident_cert = """주민등록초본에서 다음 정보를 찾아서 JSON 형식으로 답변해주세요:

1. 모든 페이지에서 '마지막 번호'에 해당하는 ['주소', '발생일'] 정보를 추출해주세요. 발생일은 at_date 필드에 저장해주세요.
2. '주소'는 대부분 2줄로 되어 있는데 2줄을 각각 [address_1, address_2] 형식으로 추출해주세요. ',' 쉼표와 '.' 문자는 제거해주세요.
3. '발생일'은 YYYY-MM-DD 형식으로 추출해주세요.
4. '성명', '주민등록번호'를 추출한 후 앞 6자리의 숫자를 birth_date 필드에 저장해주세요. 950516-1234567 -> 1995-05-16
5. 아무 페이지 상단에 '2025년' 이라는 문자열을 찾아서 일자 전체를 찾아주세요. issue_date 필드에 저장해주세요.
6. 주민등록초본 데이터가 포함된 모든 페이지 번호를 page_number 필드에 리스트 형태로 저장해주세요.
7. 초본이 없다고 판단되면 모든 값을 None으로 반환해주세요.


답변 형식:
{
  address_1: "서울특별시 강남구 역삼동 123-45",
  address_2: "자이아파트 101동 101호"
  at_date: "2025-04-16",
  birth_date: "1999-10-06",
  name: "홍길동",
  issue_date: "2025-04-16",
  page_number: [3, 4, 5]
}

주소와 발생일은 모든 페이지 중에서 '번호'가 가장 높은 row에 대해서 추출해주세요. 마지막 페이지가 아닌 가장 큰 번호가 포함된 페이지에서 추출해주세요.
초본이 1페이지만 있으면 [3], 여러 페이지에 걸쳐있으면 [3, 4, 5, 6]처럼 모든 페이지 번호를 포함해주세요.

issue_date 추출 시 주의사항:
- 항상 '0000년 0월 00일' 처럼 쓰여져 있습니다.
- '0000-00-00' 으로 쓰여져 있지 않습니다.
- 항상 '2025년' 이라는 문자열을 찾아서 일자 전체를 찾아주세요.
- 대부분 페이지 상단에 존재합니다.
"""


