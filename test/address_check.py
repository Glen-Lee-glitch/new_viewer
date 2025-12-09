import requests
import xml.etree.ElementTree as ET

# API 문서에 명시된 실제 서비스 URL (여러 URL 시도)
possible_uris = [
    'http://openapi.epost.go.kr/postal/retrieveNewAdressAreaCdService/retrieveNewAdressAreaCdService/getNewAddressListAreaCd',
    'https://openapi.epost.go.kr/postal/retrieveNewAdressAreaCdService/retrieveNewAdressAreaCdService/getNewAddressListAreaCd',
    'http://openapi.epost.go.kr:80/postal/retrieveNewAdressAreaCdService/retrieveNewAdressAreaCdService/getNewAddressListAreaCd',
    'https://openapi.epost.go.kr:80/postal/retrieveNewAdressAreaCdService',
    'http://openapi.epost.go.kr/postal/retrieveNewAdressAreaCdService'
]

# 포털에서 제공한 인증키 (Encoding)
service_key = 'nvgv9Qp2uq3hfkOL6Zm6Yez3ej5KfHLDOHEU4HqhGFPDO3QBA5M2X2fFBe8%2F27GAvvW9axEnIRB%2FeZnLtNhMjA%3D%3D'
# 포털에서 제공한 인증키 (Decoding)
service_key_decoding = 'nvgv9Qp2uq3hfkOL6Zm6Yez3ej5KfHLDOHEU4HqhGFPDO3QBA5M2X2fFBe8/27GAvvW9axEnIRB/eZnLtNhMjA=='

print('=============== 도로명 주소 & 지번 주소 & 우편번호 =======================')
print('1. 지번으로 검색\n2. 도로명으로 검색\n3. 우편번호\n')

select = input('검색 방법 선택 : ')

if select == '1':
    seach_se = 'dong'
    srchwrd = input('지번 입력(예: 주월동 408-1) : ')
elif select == '2':
    seach_se = 'road'
    srchwrd = input('도로명 입력(예: 서문대로 745) : ')
else:
    seach_se = 'post'
    srchwrd = input('우편번호 입력(예: 61725) : ')

# API 문서에 따른 파라미터명 사용
payload = {
    'ServiceKey': service_key_decoding,
    'searchSe': seach_se,
    'srchwrd': srchwrd,
    'countPerPage': '10',
    'currentPage': '1',
    'type': 'xml'  # XML 형식으로 응답 받기
}

try:
    print('API 요청 중...')
    
    resp = None
    root = None
    success = False
    service_key_error_count = 0  # 서비스 키 에러 카운트
    
    # 여러 URL과 키 조합 시도
    for uri_idx, uri in enumerate(possible_uris, 1):
        print(f'\n[{uri_idx}/{len(possible_uris)}] URL 시도: {uri[:60]}...')
        
        # 먼저 encoding된 키로 시도
        for key_type, key_value in [('Encoding', service_key), ('Decoding', service_key_decoding)]:
            try:
                test_payload = payload.copy()
                test_payload['ServiceKey'] = key_value
                
                print(f'  → {key_type} 키로 시도 중...', end=' ')
                test_resp = requests.get(uri, params=test_payload, timeout=5)
                
                if test_resp.status_code == 200:
                    test_root = ET.fromstring(test_resp.text)
                    cmm_msg_header = test_root.find(".//cmmMsgHeader")
                    
                    if cmm_msg_header is not None:
                        success_yn = cmm_msg_header.findtext("successYN")
                        return_code = cmm_msg_header.findtext("returnCode")
                        
                        if success_yn == 'Y' or (success_yn != 'N' and not return_code):
                            print('✅ 성공!')
                            resp = test_resp
                            root = test_root
                            success = True
                            break
                        else:
                            err_msg = cmm_msg_header.findtext("errMsg")
                            print(f'❌ ({return_code}) {err_msg}')
                            
                            # 서비스 키 에러인 경우 카운트
                            if return_code == '30' or 'SERVICE KEY' in err_msg.upper():
                                service_key_error_count += 1
                                # 같은 에러가 3번 이상 나오면 조기 종료
                                if service_key_error_count >= 3:
                                    print('\n⚠️  서비스 키 등록 에러가 반복적으로 발생합니다.')
                                    break
                    else:
                        # 헤더가 없어도 데이터가 있을 수 있음
                        if test_root.findall(".//newAddressListAreaCd") or test_root.findall("newAddressListAreaCd"):
                            print('✅ 성공! (헤더 없음)')
                            resp = test_resp
                            root = test_root
                            success = True
                            break
                        else:
                            print('❌ 데이터 없음')
                else:
                    print(f'❌ HTTP {test_resp.status_code}')
                    
            except requests.exceptions.Timeout:
                print('⏱️ 타임아웃')
                continue
            except requests.exceptions.RequestException as e:
                print(f'❌ 네트워크 에러: {str(e)[:30]}')
                continue
            except ET.ParseError:
                print('❌ XML 파싱 실패')
                continue
        
        # 서비스 키 에러가 3번 이상이면 조기 종료
        if service_key_error_count >= 3:
            break
            
        if success:
            break
    
    if not success or resp is None or root is None:
        print('\n❌ 모든 URL과 키 조합 시도 실패!')
        print('\n⚠️  "SERVICE KEY IS NOT REGISTERED ERROR" 발생')
        print('\n💡 해결 방법:')
        print('1. 공공데이터포털(data.go.kr)에 로그인하세요')
        print('2. "도로명주소조회서비스" API 활용 신청을 완료하세요')
        print('   - https://www.data.go.kr/data/15000124/openapi.do')
        print('3. 활용 신청 후 승인 대기 시간이 필요할 수 있습니다 (자동승인)')
        print('4. 승인 완료 후 마이페이지에서 서비스 키를 다시 확인하세요')
        print('5. 서비스 키가 올바르게 복사되었는지 확인하세요 (앞뒤 공백 제거)')
        print('\n📝 참고:')
        print('- 개발계정: 자동승인, 트래픽 10,000건/일')
        print('- 운영계정: 자동승인, 활용사례 등록 시 트래픽 증가 가능')
        exit(1)
    
    # 성공한 경우 데이터 파싱
    newAddressListAreaCd = root.findall(".//newAddressListAreaCd")
    
    if not newAddressListAreaCd:
        newAddressListAreaCd = root.findall("newAddressListAreaCd")
    
    print('=============== 결과 출력 =======================')
    
    if not newAddressListAreaCd:
        print('검색 결과가 없습니다.')
    else:
        for r in newAddressListAreaCd:
            zip_no = r.findtext("zipNo")
            rn_adres = r.findtext("rnAdres")  # 문서에 따르면 도로명주소
            lnm_adres = r.findtext("lnmAdres")  # 문서에 따르면 지번주소
            
            print(f'우편번호 : {zip_no}')
            print(f'도로명 주소 : {rn_adres}')
            print(f'지번 주소 : {lnm_adres}')
            print('--------------------------------------------------------------------')
            
except requests.exceptions.Timeout:
    print('\n❌ 요청 시간 초과')
except requests.exceptions.RequestException as e:
    print(f'\n❌ 요청 에러 발생: {e}')
except ET.ParseError as e:
    print(f'\n❌ XML 파싱 에러: {e}')
    if 'resp' in locals() and resp:
        print(f'응답 내용: {resp.text[:500]}')
except Exception as e:
    print(f'\n❌ 예상치 못한 에러: {e}')
    import traceback
    traceback.print_exc()