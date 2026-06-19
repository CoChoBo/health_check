import tempfile
import unittest
import csv
import io
from pathlib import Path

import server


class ServerDatabaseTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_db_path = server.DB_PATH
        server.DB_PATH = Path(self.tempdir.name) / "test.sqlite3"
        server.init_db()

    def tearDown(self):
        server.DB_PATH = self.original_db_path
        self.tempdir.cleanup()

    def test_insert_result_and_summary(self):
        result_id = server.insert_result(
            {
                "name": "홍길동",
                "date": "2026-06-17",
                "totalScore": "86",
                "smoking": "비흡연",
                "steps": "8500",
                "ldl": "110",
                "bp": "120/80",
                "bmi": "22.1",
            }
        )

        self.assertEqual(result_id, 1)

        with server.db_connection() as conn:
            row = conn.execute(
                """
                SELECT name, survey_date, total_score
                FROM survey_results
                """
            ).fetchone()

        self.assertEqual(row["name"], "홍길동")
        self.assertEqual(row["survey_date"], "2026-06-17")
        self.assertEqual(row["total_score"], 86)

    def test_database_results_summary_and_csv_export(self):
        server.insert_result(
            {
                "name": "홍길동",
                "date": "2026-06-17",
                "totalScore": 86,
                "smoking": "비흡연",
                "steps": "8500",
                "ldl": "110",
                "bp": "120/80",
                "bmi": "22.1",
            }
        )
        server.insert_result(
            {
                "name": "김영희",
                "date": "2026-06-18",
                "totalScore": 94,
            }
        )

        results = server.get_all_results()
        summary = server.get_database_summary()

        self.assertEqual([row["name"] for row in results], ["김영희", "홍길동"])
        self.assertEqual(summary["totalCount"], 2)
        self.assertEqual(summary["participantCount"], 2)
        self.assertEqual(summary["averageScore"], 90.0)
        self.assertEqual(summary["latestDate"], "2026-06-18")

        csv_text = server.build_results_csv().decode("utf-8-sig")
        csv_rows = list(csv.reader(io.StringIO(csv_text)))

        self.assertEqual(csv_rows[0][:4], ["ID", "이름", "날짜", "총점"])
        self.assertEqual(csv_rows[1][1:4], ["김영희", "2026-06-18", "94"])
        self.assertEqual(csv_rows[2][1:4], ["홍길동", "2026-06-17", "86"])


if __name__ == "__main__":
    unittest.main()
