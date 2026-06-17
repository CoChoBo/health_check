import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
