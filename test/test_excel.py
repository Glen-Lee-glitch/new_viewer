import os
from datetime import datetime

import pandas as pd
import pymysql
from contextlib import closing

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
excel_path = os.path.join(project_root, "부산.xlsx")

# MySQL 연결 정보
DB_CONFIG = {
    'host': '192.168.0.114',
    'port': 3306,
    'user': 'my_pc_user',
    'password': '!Qdhdbrclf56',
    'db': 'greetlounge',
    'charset': 'utf8mb4'
}

TABLE_COLUMNS = [
    "순서",
    "신청자",
    "전처리",
    "지역",
    "RN",
    "주문시간",
    "성명",
    "생년월일",
    "성별",
    "사업자번호",
    "사업자명",
    "신청차종",
    "출고예정일",
    "주소1",
    "주소2",
    "전화",
    "휴대폰",
    "이메일",
    "신청유형",
    "우선순위",
    "다자녀수",
    "공동명의자",
    "공동생년월일",
    "보조금",
]

EXCEL_TO_TABLE = {
    "순서": "순서",
    "신청자": "신청자",
    "전처리": "전처리",
    "지역": "지역",
    "RN번호": "RN",  # 사용자 요구사항
    "주문시간": "주문시간",
    "성명(대표자)": "성명",
    "생년월일(법인번호)": "생년월일",
    "성별": "성별",
    "사업자번호": "사업자번호",
    "사업자명": "사업자명",
    "신청차종": "신청차종",
    "출고예정일": "출고예정일",
    "주소1": "주소1",
    "주소2": "주소2",
    "전화": "전화",
    "휴대폰": "휴대폰",
    "이메일": "이메일",
    "신청유형": "신청유형",
    "우선순위": "우선순위",
    "다자녀수": "다자녀수",
    "공동명의자": "공동명의자",
    "공동 생년월일": "공동생년월일",
    "보조금": "보조금",
}


def to_text_date(value: object) -> str | None:
    if pd.isna(value):
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d")
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        parsed = pd.to_datetime(text_value, errors="raise")
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return text_value


def to_int(value: object) -> int | None:
    if pd.isna(value):
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def summarize_dataframe(dataframe: pd.DataFrame) -> None:
    print("=" * 60)
    print("엑셀 파일 칼럼 구조")
    print("=" * 60)
    print(f"총 칼럼 수: {len(dataframe.columns)}\n")
    for idx, col in enumerate(dataframe.columns, 1):
        print(f"{idx:2d}. {col}")

    print("\n" + "=" * 60)
    print("칼럼별 데이터 타입 및 샘플 데이터")
    print("=" * 60)
    for col in dataframe.columns:
        print(f"\n칼럼명: {col}")
        print(f"  타입: {dataframe[col].dtype}")
        print(f"  NULL 개수: {dataframe[col].isna().sum()}/{len(dataframe)}")
        sample_series = dataframe[col].dropna()
        if not sample_series.empty:
            sample = str(sample_series.iloc[0])
            if len(sample) > 50:
                sample = sample[:50] + "..."
            print(f"  샘플: {sample}")

    print("\n" + "=" * 60)
    print("전체 데이터 행 수:", len(dataframe))
    print("=" * 60)


def map_to_table_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    mapped = {}
    missing_columns = []

    for excel_col, table_col in EXCEL_TO_TABLE.items():
        if excel_col not in dataframe.columns:
            missing_columns.append((excel_col, table_col))
            continue

        series = dataframe[excel_col]

        if excel_col == "순서":
            mapped[table_col] = series.apply(to_int)
        elif excel_col == "생년월일(법인번호)":
            mapped[table_col] = series.apply(to_text_date)
        elif excel_col == "공동 생년월일":
            mapped[table_col] = series.apply(to_text_date)
        elif excel_col == "다자녀수":
            mapped[table_col] = series.apply(to_int)
        elif excel_col == "보조금":
            mapped[table_col] = series.apply(to_int)
        elif excel_col == "주문시간":
            mapped[table_col] = series.dt.strftime("%Y-%m-%d") if pd.api.types.is_datetime64_any_dtype(series) else series
        elif excel_col == "출고예정일":
            mapped[table_col] = series.dt.strftime("%Y-%m-%d") if pd.api.types.is_datetime64_any_dtype(series) else series
        else:
            mapped[table_col] = series

    mapped_df = pd.DataFrame(mapped)

    print("\n" + "=" * 60)
    print("preprocessed_data 매핑 결과 요약")
    print("=" * 60)
    print(f"매핑된 칼럼 수: {len(mapped_df.columns)}/{len(TABLE_COLUMNS)}")
    print(f"누락된 칼럼 수: {len(missing_columns)}")
    if missing_columns:
        print("\n누락된 칼럼 목록 (엑셀 -> 테이블):")
        for excel_col, table_col in missing_columns:
            print(f"- {excel_col} -> {table_col}")

    preview_rows = min(5, len(mapped_df))
    if preview_rows > 0:
        print("\n매핑 데이터 미리보기 (상위 5행):")
        print(mapped_df.head(preview_rows).to_string(index=False))

    print("\n변환 대상 칼럼 샘플:")
    for col_name in ["생년월일", "다자녀수", "보조금"]:
        if col_name in mapped_df.columns:
            sample_values = mapped_df[col_name].head(3).tolist()
            print(f"- {col_name}: {sample_values}")

    return mapped_df


def insert_to_database(dataframe: pd.DataFrame) -> bool:
    """
    preprocessed_data 테이블에 데이터를 삽입하고,
    processed_data 테이블의 순서를 업데이트한다.
    """
    if dataframe.empty:
        print("삽입할 데이터가 없습니다.")
        return False
    
    # 순서 칼럼 포함하여 삽입
    insert_columns = [col for col in TABLE_COLUMNS if col in dataframe.columns]
    
    if not insert_columns:
        print("삽입할 칼럼이 없습니다.")
        return False
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            with connection.cursor() as cursor:
                # INSERT 쿼리 생성
                columns_str = ", ".join([f"`{col}`" for col in insert_columns])
                placeholders = ", ".join(["%s"] * len(insert_columns))
                insert_query = f"""
                    INSERT INTO preprocessed_data ({columns_str})
                    VALUES ({placeholders})
                """
                
                # processed_data 테이블 업데이트용 쿼리
                update_query = """
                    UPDATE processed_data 
                    SET `순서` = %s 
                    WHERE RN = %s
                """
                
                inserted_count = 0
                updated_count = 0
                
                for _, row in dataframe.iterrows():
                    values = []
                    for col in insert_columns:
                        value = row[col]
                        # NaN/None 처리
                        if pd.isna(value):
                            values.append(None)
                        # 순서 칼럼은 정수로 변환
                        elif col == "순서":
                            order_value = to_int(value)
                            values.append(order_value)
                        # 날짜 칼럼 처리 (이미 문자열로 변환되었을 수 있음)
                        elif col in ["주문시간", "출고예정일", "공동생년월일"]:
                            if isinstance(value, str):
                                values.append(value)
                            elif isinstance(value, (datetime, pd.Timestamp)):
                                values.append(value.strftime("%Y-%m-%d"))
                            else:
                                values.append(None)
                        else:
                            values.append(value)
                    
                    try:
                        # preprocessed_data에 삽입
                        cursor.execute(insert_query, values)
                        inserted_count += 1
                        
                        # processed_data의 순서 업데이트 (RN이 있고 순서 값이 있을 때만)
                        rn_value = row.get('RN')
                        order_value = to_int(row.get('순서'))
                        if rn_value and pd.notna(rn_value) and order_value is not None:
                            cursor.execute(update_query, (order_value, rn_value))
                            if cursor.rowcount > 0:
                                updated_count += 1
                    except Exception as e:
                        print(f"행 삽입 실패 (RN: {row.get('RN', 'N/A')}): {e}")
                        continue
                
                connection.commit()
                print(f"\n성공적으로 {inserted_count}개 행이 preprocessed_data에 삽입되었습니다.")
                if updated_count > 0:
                    print(f"성공적으로 {updated_count}개 행의 processed_data 순서가 업데이트되었습니다.")
                return True
                
    except Exception as e:
        print(f"데이터베이스 삽입 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print(f"엑셀 파일 경로: {excel_path}")
    print(f"파일 존재 여부: {os.path.exists(excel_path)}\n")

    try:
        df = pd.read_excel(excel_path)
    except Exception as exc:
        print(f"엑셀 로드 실패: {exc}")
        raise

    summarize_dataframe(df)
    mapped_df = map_to_table_columns(df)

    print("\n" + "=" * 60)
    print("preprocessed_data 삽입 준비 상태")
    print("=" * 60)
    ready_columns = [col for col in TABLE_COLUMNS if col in mapped_df.columns]
    print(f"준비된 칼럼 ({len(ready_columns)}개): {', '.join(ready_columns)}")
    not_ready_columns = [col for col in TABLE_COLUMNS if col not in mapped_df.columns]
    if not_ready_columns:
        print(f"미매핑 칼럼 ({len(not_ready_columns)}개): {', '.join(not_ready_columns)}")
    
    # 데이터베이스에 삽입
    print("\n" + "=" * 60)
    print("데이터베이스 삽입 시작")
    print("=" * 60)
    insert_to_database(mapped_df)


if __name__ == "__main__":
    main()

