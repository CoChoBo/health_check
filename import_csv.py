from __future__ import annotations

import argparse
import csv
from pathlib import Path

from server import init_db, insert_result


HEADER_MAP = {
    "name": ["name", "이름", "성명", "참여자"],
    "date": ["date", "surveyDate", "survey_date", "날짜", "설문일", "제출일", "타임스탬프"],
    "totalScore": ["totalScore", "total_score", "총점", "점수", "건강점수"],
    "smoking": ["smoking", "흡연"],
    "steps": ["steps", "걸음수", "보행수"],
    "ldl": ["ldl", "LDL"],
    "bp": ["bp", "혈압"],
    "bmi": ["bmi", "BMI"],
}


def find_value(row: dict[str, str], field: str) -> str:
    for header in HEADER_MAP[field]:
        if header in row:
            return row[header]
    return ""


def convert_row(row: dict[str, str]) -> dict[str, str]:
    return {field: find_value(row, field) for field in HEADER_MAP}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import survey CSV data into SQLite")
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--encoding", default="utf-8-sig")
    args = parser.parse_args()

    init_db()

    inserted = 0
    with args.csv_path.open("r", newline="", encoding=args.encoding) as file:
        reader = csv.DictReader(file)
        for line_number, row in enumerate(reader, start=2):
            try:
                insert_result(convert_row(row))
                inserted += 1
            except ValueError as exc:
                print(f"Skipped line {line_number}: {exc}")

    print(f"Imported {inserted} rows into health_check.sqlite3")


if __name__ == "__main__":
    main()
