import http.client
import tempfile
import threading
import unittest
import csv
import io
import json
from pathlib import Path

import server


class ServerDatabaseTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_db_path = server.DB_PATH
        self.original_admin_username = server.ADMIN_USERNAME
        self.original_admin_password = server.ADMIN_PASSWORD
        self.original_session_secret = server.ADMIN_SESSION_SECRET
        self.original_session_hours = server.ADMIN_SESSION_HOURS
        self.original_cookie_secure = server.ADMIN_COOKIE_SECURE
        server.DB_PATH = Path(self.tempdir.name) / "test.sqlite3"
        server.ADMIN_USERNAME = "admin-test"
        server.ADMIN_PASSWORD = "test-password"
        server.ADMIN_SESSION_SECRET = b"test-session-secret"
        server.ADMIN_SESSION_HOURS = 8
        server.ADMIN_COOKIE_SECURE = False
        server.LOGIN_ATTEMPTS.clear()
        server.init_db()

    def tearDown(self):
        server.DB_PATH = self.original_db_path
        server.ADMIN_USERNAME = self.original_admin_username
        server.ADMIN_PASSWORD = self.original_admin_password
        server.ADMIN_SESSION_SECRET = self.original_session_secret
        server.ADMIN_SESSION_HOURS = self.original_session_hours
        server.ADMIN_COOKIE_SECURE = self.original_cookie_secure
        server.LOGIN_ATTEMPTS.clear()
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

    def test_fractional_score_is_preserved(self):
        server.insert_result(
            {
                "name": "소수점점수",
                "date": "2026-06-19",
                "totalScore": "19.5",
            }
        )

        with server.db_connection() as conn:
            score = conn.execute(
                "SELECT total_score FROM survey_results WHERE name = ?",
                ("소수점점수",),
            ).fetchone()["total_score"]

        self.assertEqual(score, 19.5)

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

    def test_admin_session_token(self):
        token = server.create_session_token(now=1_000)

        self.assertTrue(server.verify_session_token(token, now=1_001))
        self.assertFalse(server.verify_session_token(token, now=40_000))
        self.assertFalse(server.verify_session_token(f"{token}changed", now=1_001))
        self.assertTrue(server.credentials_match("admin-test", "test-password"))
        self.assertFalse(server.credentials_match("admin-test", "wrong"))

    def test_admin_routes_require_login(self):
        http_server = server.ThreadingHTTPServer(
            ("127.0.0.1", 0), server.HealthCheckHandler
        )
        thread = threading.Thread(target=http_server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection(
            "127.0.0.1", http_server.server_port, timeout=5
        )

        try:
            connection.request("GET", "/admin.html")
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 302)
            self.assertEqual(response.getheader("Location"), "/admin/login.html")

            connection.request("GET", "/api/results")
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 401)

            login_body = json.dumps(
                {"username": "admin-test", "password": "test-password"}
            )
            connection.request(
                "POST",
                "/api/admin/login",
                body=login_body,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 200)
            cookie = response.getheader("Set-Cookie")
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Strict", cookie)

            connection.request(
                "GET",
                "/api/results",
                headers={"Cookie": cookie.split(";", 1)[0]},
            )
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["summary"]["totalCount"], 0)

            connection.request(
                "GET",
                "/api/results-summary",
                headers={"Cookie": cookie.split(";", 1)[0]},
            )
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["summary"]["totalCount"], 0)
        finally:
            connection.close()
            http_server.shutdown()
            http_server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
